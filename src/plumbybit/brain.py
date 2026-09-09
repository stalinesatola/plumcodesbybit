"""O 'cerebro' do agent: pede uma decisao de trade a um LLM.

Providers suportados:
  - anthropic : Claude (SDK oficial), structured output
  - nvidia    : integrate.api.nvidia.com (compativel com OpenAI), response_format JSON

A decisao e sempre estruturada (JSON validado). O LLM NUNCA envia ordens -
so devolve uma intencao. A execucao/limites vivem em risk.py e trader.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from tenacity import retry, stop_after_attempt, wait_exponential

from .config import AgentConfig, Provider, Settings
from .logging_conf import get_logger

log = get_logger(__name__)

Action = Literal["open_long", "open_short", "close", "hold"]

# JSON Schema partilhado pelos dois providers.
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "confidence", "rationale"],
    "properties": {
        "action": {"type": "string", "enum": ["open_long", "open_short", "close", "hold"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "size_fraction": {
            "type": "number", "minimum": 0, "maximum": 1,
            "description": "Fracao do max_position_usdt a usar ao abrir. Ignorado em close/hold.",
        },
        "rationale": {"type": "string", "maxLength": 600},
    },
}

ANTHROPIC_FORMAT = {"type": "json_schema", "json_schema": {"name": "trade_decision", "schema": _SCHEMA}}

SYSTEM = """Es um agente de trading quantitativo disciplinado a operar perpetuos na Bybit.
Recebes um snapshot de mercado e a posicao atual. Devolves UMA decisao estruturada em JSON.

Regras:
- Preferes 'hold' quando o sinal e ambiguo. Overtrading destroi capital.
- 'open_long' / 'open_short' apenas com tese clara (tendencia + momentum + nivel).
- 'close' se a tese que abriu a posicao deixou de ser valida ou o momentum inverteu.
- 'confidence' reflete a forca real do sinal; abaixo de 0.55 o sistema ignora aberturas.
- 'size_fraction' menor quando a volatilidade (atr14_pct) esta elevada.
- Nao inventas dados que nao estao no snapshot. Nao das conselhos financeiros ao utilizador.
O stop-loss e take-profit sao aplicados automaticamente pelo sistema; nao os giras.

Responde APENAS com um objeto JSON com as chaves: action, confidence, size_fraction, rationale."""


@dataclass
class Decision:
    action: Action
    confidence: float
    size_fraction: float
    rationale: str
    raw: dict[str, Any]

    @property
    def wants_entry(self) -> bool:
        return self.action in ("open_long", "open_short")


def _to_decision(data: dict[str, Any]) -> Decision:
    return Decision(
        action=data["action"],
        confidence=float(data["confidence"]),
        size_fraction=float(data.get("size_fraction", 1.0) or 0.0),
        rationale=data.get("rationale", ""),
        raw=data,
    )


def _user_payload(cfg: AgentConfig, snapshot: dict[str, Any], position: dict[str, Any] | None) -> str:
    return json.dumps(
        {
            "agent": cfg.name,
            "policy": {
                "interval": cfg.interval,
                "leverage": cfg.leverage,
                "max_position_usdt": cfg.max_position_usdt,
                "take_profit_pct": cfg.take_profit_pct,
                "stop_loss_pct": cfg.stop_loss_pct,
            },
            "current_position": position or "none",
            "market": snapshot,
        },
        default=str,
    )


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


class Brain:
    """Dispatcher: escolhe o provider por agent e devolve sempre um Decision."""

    def __init__(self, settings: Settings | None = None):
        self.s = settings or Settings()  # type: ignore[call-arg]
        self._anthropic = None
        self._nvidia = None

    # -- clientes (lazy) --------------------------------------------------
    def _anthropic_client(self):
        if self._anthropic is None:
            import anthropic

            if not self.s.anthropic_api_key:
                raise RuntimeError("ANTHROPIC_API_KEY em falta para provider 'anthropic'")
            self._anthropic = anthropic.Anthropic(api_key=self.s.anthropic_api_key)
        return self._anthropic

    def _nvidia_client(self):
        if self._nvidia is None:
            from openai import OpenAI

            if not self.s.nvidia_api_key:
                raise RuntimeError("NVIDIA_API_KEY em falta para provider 'nvidia'")
            self._nvidia = OpenAI(api_key=self.s.nvidia_api_key, base_url=self.s.nvidia_base_url)
        return self._nvidia

    # -- API publica ----------------------------------------------------
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20), reraise=True)
    def decide(self, cfg: AgentConfig, snapshot: dict[str, Any], position: dict[str, Any] | None) -> Decision:
        provider, model = self.s.resolve_llm(cfg)
        user = _user_payload(cfg, snapshot, position)
        if provider == "nvidia":
            data, usage = self._decide_nvidia(model, user)
        else:
            data, usage = self._decide_anthropic(model, user)
        log.info("decision", agent=cfg.name, provider=provider, model=model,
                 action=data.get("action"), confidence=data.get("confidence"), **usage)
        return _to_decision(data)

    # -- providers ----------------------------------------------------
    def _decide_anthropic(self, model: str, user: str) -> tuple[dict, dict]:
        resp = self._anthropic_client().messages.create(
            model=model,
            max_tokens=1200,
            system=SYSTEM,
            output_config={"format": ANTHROPIC_FORMAT},
            messages=[{"role": "user", "content": user}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        return json.loads(text), {"tokens_in": resp.usage.input_tokens, "tokens_out": resp.usage.output_tokens}

    def _decide_nvidia(self, model: str, user: str) -> tuple[dict, dict]:
        client = self._nvidia_client()
        kwargs: dict[str, Any] = dict(
            model=model,
            temperature=0.2,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user},
            ],
        )
        try:
            resp = client.chat.completions.create(
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "trade_decision", "schema": _SCHEMA, "strict": True},
                },
                **kwargs,
            )
        except Exception as exc:  # nem todos os modelos NIM suportam json_schema
            if "json_schema" not in str(exc) and "response_format" not in str(exc):
                raise
            resp = client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
        content = resp.choices[0].message.content or "{}"
        u = getattr(resp, "usage", None)
        usage = {"tokens_in": getattr(u, "prompt_tokens", None), "tokens_out": getattr(u, "completion_tokens", None)}
        return _extract_json(content), usage


__all__ = ["Action", "Brain", "Decision", "Provider"]
