"""FastAPI: painel de controlo dos agents. Entrypoint: `plumbybit-web`."""
from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import AgentConfig, Settings
from ..configstore import TUNABLE_KEYS
from ..exchange import get_exchange
from ..logging_conf import configure, get_logger, recent_logs
from ..supervisor import Supervisor
from .auth import COOKIE, Auth, require_auth

log = get_logger("web")
STATIC = Path(__file__).parent / "static"

_LLM_KEYS = {"llm_provider", "llm_model", "nvidia_model", "nvidia_base_url"}


class LoginBody(BaseModel):
    password: str


class SettingsBody(BaseModel):
    dry_run: bool | None = None
    allow_real: bool | None = None
    max_daily_loss_usdt: float | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    nvidia_model: str | None = None
    nvidia_base_url: str | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()  # type: ignore[call-arg]
    configure(settings.log_level)
    auth = Auth(settings)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        sup = Supervisor(settings)
        app.state.sup = sup
        await sup.start()
        log.info("web.ready", host=settings.web_host, port=settings.web_port, auth=auth.enabled)
        try:
            yield
        finally:
            await sup.stop()

    app = FastAPI(title="plumcodesbybit", lifespan=lifespan)
    guard = Depends(require_auth(auth))

    def sup() -> Supervisor:
        return app.state.sup

    # -- auth ---------------------------------------------------------
    @app.post("/api/login")
    def login(body: LoginBody, response: Response):
        if not auth.enabled:
            return {"ok": True, "auth": False}
        if not auth.verify_password(body.password):
            raise HTTPException(status_code=401, detail="password invalida")
        response.set_cookie(COOKIE, auth.issue_token(), httponly=True, samesite="lax",
                            max_age=auth.max_age)
        return {"ok": True}

    @app.post("/api/logout")
    def logout(response: Response):
        response.delete_cookie(COOKIE)
        return {"ok": True}

    # -- estado -----------------------------------------------------
    @app.get("/api/state", dependencies=[guard])
    def state() -> dict[str, Any]:
        s = sup()
        return {
            "settings": s.config.all_settings(),
            "tunable_keys": list(TUNABLE_KEYS),
            "secrets": {
                "anthropic": bool(settings.anthropic_api_key),
                "nvidia": bool(settings.nvidia_api_key),
                "bybit_demo": bool(settings.bybit_demo_api_key),
                "bybit_real": bool(settings.bybit_real_api_key),
            },
            "real_trading_armed": s.runtime.real_trading_armed(),
            "agents": s.status(),
            "pnl": s.store.pnl_summary(),
        }

    @app.put("/api/settings", dependencies=[guard])
    async def put_settings(body: SettingsBody):
        values = {k: v for k, v in body.model_dump().items() if v is not None}
        if not values:
            raise HTTPException(status_code=400, detail="nada para atualizar")
        updated = sup().config.set_settings(values)
        if values.keys() & _LLM_KEYS:
            await sup().reload_llm()
        log.info("web.settings_updated", keys=list(values))
        return updated

    # -- agents -----------------------------------------------------
    @app.get("/api/agents", dependencies=[guard])
    def list_agents():
        return [a.model_dump() for a in sup().config.list_agents()]

    @app.post("/api/agents", dependencies=[guard])
    async def create_agent(cfg: AgentConfig):
        if sup().config.get_agent(cfg.name):
            raise HTTPException(status_code=409, detail="ja existe um agent com esse nome")
        sup().config.upsert_agent(cfg)
        status = await sup().reload_agent(cfg.name)
        return {"agent": cfg.model_dump(), "status": status}

    @app.put("/api/agents/{name}", dependencies=[guard])
    async def update_agent(name: str, cfg: AgentConfig):
        if not sup().config.get_agent(name):
            raise HTTPException(status_code=404, detail="agent nao encontrado")
        if cfg.name != name:
            sup().config.delete_agent(name)
            await sup().reload_agent(name)
        sup().config.upsert_agent(cfg)
        status = await sup().reload_agent(cfg.name)
        return {"agent": cfg.model_dump(), "status": status}

    @app.delete("/api/agents/{name}", dependencies=[guard])
    async def delete_agent(name: str):
        if not sup().config.delete_agent(name):
            raise HTTPException(status_code=404, detail="agent nao encontrado")
        await sup().reload_agent(name)
        return {"ok": True}

    @app.post("/api/agents/{name}/{op}", dependencies=[guard])
    async def toggle_agent(name: str, op: str):
        if op not in ("start", "stop"):
            raise HTTPException(status_code=400, detail="op invalida")
        cfg = sup().config.get_agent(name)
        if not cfg:
            raise HTTPException(status_code=404, detail="agent nao encontrado")
        cfg.enabled = op == "start"
        sup().config.upsert_agent(cfg)
        status = await sup().reload_agent(name)
        return {"name": name, "status": status}

    # -- observabilidade -------------------------------------------
    @app.get("/api/decisions", dependencies=[guard])
    def decisions(limit: int = 100, agent: str | None = None):
        return sup().store.recent_decisions(limit=min(limit, 500), agent=agent)

    @app.get("/api/fills", dependencies=[guard])
    def fills(limit: int = 100):
        return sup().store.recent_fills(limit=min(limit, 500))

    @app.get("/api/logs", dependencies=[guard])
    def logs(after: int = 0, limit: int = 400):
        return recent_logs(after_seq=after, limit=min(limit, 1000))

    @app.get("/api/positions", dependencies=[guard])
    async def positions():
        accounts = {a["account"] for a in sup().status()}
        out: list[dict] = []
        for acc in accounts:
            try:
                rows = await asyncio.to_thread(lambda a=acc: get_exchange(a).positions("linear"))
                for p in rows:
                    if float(p.get("size", 0) or 0) > 0:
                        out.append({"account": acc, **{k: p.get(k) for k in
                                    ("symbol", "side", "size", "avgPrice", "markPrice",
                                     "unrealisedPnl", "leverage", "takeProfit", "stopLoss")}})
            except Exception as exc:  # noqa: BLE001 - painel nao pode rebentar
                out.append({"account": acc, "error": str(exc)})
        return out

    # -- estatico -------------------------------------------------
    app.mount("/assets", StaticFiles(directory=STATIC), name="assets")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    return app


def main() -> None:
    import uvicorn

    settings = Settings()  # type: ignore[call-arg]
    uvicorn.run(create_app(settings), host=settings.web_host, port=settings.web_port,
                log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
