"""Supervisor assincrono dos agents. Usado pela CLI (runner) e pelo web UI.

Mantem uma task por agent ativo e permite start/stop/reload individuais em
runtime, sem reiniciar o processo.
"""
from __future__ import annotations

import asyncio

from .agent import Agent
from .brain import Brain
from .config import AgentConfig, Settings
from .configstore import ConfigStore
from .logging_conf import get_logger
from .runtime import RuntimeConfig
from .state import Store

log = get_logger(__name__)


class Supervisor:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()  # type: ignore[call-arg]
        self.config = ConfigStore(self.settings.state_db, self.settings)
        self.store = Store(self.settings.state_db)
        self.runtime = RuntimeConfig(self.settings, self.config)
        self.brain = Brain(self.runtime)  # type: ignore[arg-type]
        self._tasks: dict[str, asyncio.Task] = {}

    # -- ciclo de vida -------------------------------------------------
    async def start(self) -> None:
        for cfg in self.config.list_agents():
            if cfg.enabled:
                self._spawn(cfg)
        log.info("supervisor.start", running=list(self._tasks))

    async def stop(self) -> None:
        for t in self._tasks.values():
            t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        log.info("supervisor.stop")

    def _spawn(self, cfg: AgentConfig) -> None:
        agent = Agent(cfg, self.runtime, self.store, self.brain)  # type: ignore[arg-type]
        self._tasks[cfg.name] = asyncio.create_task(agent.run(), name=cfg.name)

    # -- operacoes em runtime ---------------------------------------
    async def reload_agent(self, name: str) -> str:
        old = self._tasks.pop(name, None)
        if old:
            old.cancel()
            await asyncio.gather(old, return_exceptions=True)
        cfg = self.config.get_agent(name)
        if cfg and cfg.enabled:
            self._spawn(cfg)
            return "running"
        return "stopped"

    async def reload_llm(self) -> None:
        """Rebuild do Brain (apanha provider/modelo/base_url novos) + agents."""
        self.brain = Brain(self.runtime)  # type: ignore[arg-type]
        names = list(self._tasks)
        await self.stop()
        for name in names:
            await self.reload_agent(name)
        log.info("supervisor.reload_llm", running=list(self._tasks))

    def status(self) -> list[dict]:
        out = []
        for cfg in self.config.list_agents():
            task = self._tasks.get(cfg.name)
            provider, model = self.runtime.resolve_llm(cfg)
            out.append({
                "name": cfg.name, "symbol": cfg.symbol, "account": cfg.account,
                "enabled": cfg.enabled, "poll_seconds": cfg.poll_seconds,
                "provider": provider, "model": model,
                "running": bool(task and not task.done()),
            })
        return out
