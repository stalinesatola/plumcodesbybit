"""O 'cerebro' do agent: pede uma decisao de trade ao Claude.

A decisao e sempre estruturada (JSON validado) atraves de structured outputs.
O LLM NUNCA envia ordens - so devolve uma intencao. A execucao/limites vivem
em risk.py e trader.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import AgentConfig, Settings
from .logging_conf import get_logger

log = get_logger(__name__)

Action = Literal["open_long", "open_short", "close", "hold"]

DECISION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "trade_decision",
        "schema": {
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
        },
    },
}

SYSTEM = """Es um agente de trading quantitativo disciplinado a operar perpetuos na Bybit.
Recebes um snapshot de mercado e a posicao atual. Devolves UMA decisao estruturada.

Regras:
- Preferes 'hold' quando o sinal e ambiguo. Overtrading destroi capital.
- 'open_long' / 'open_short' apenas com tese clara (tendencia + momentum + nivel).
- 'close' se a tese que abriu a posicao deixou de ser valida ou o momentum inverteu.
- 'confidence' reflete a forca real do sinal; abaixo de 0.55 o sistema ignora aberturas.
- 'size_fraction' menor quando a volatilidade (atr14_pct) esta elevada.
- Nao inventas dados que nao estao no snapshot. Nao das conselhos financeiros ao utilizador.
O stop-loss e take-profit sao aplicados automaticamente pelo sistema; nao os giras."""


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


class Brain:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or Settings()  # type: ignore[call-arg]
        self.client = anthropic.Anthropic(api_key=self.s.anthropic_api_key)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20), reraise=True)
    def decide(self, cfg: AgentConfig, snapshot: dict[str, Any], position: dict[str, Any] | None) -> Decision:
        user = {
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
        }
        resp = self.client.messages.create(
            model=self.s.llm_model,
            max_tokens=1200,
            system=SYSTEM,
            output_config={"format": DECISION_SCHEMA},
            messages=[{"role": "user", "content": json.dumps(user, default=str)}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        data = json.loads(text)
        log.info("decision", agent=cfg.name, action=data.get("action"),
                 confidence=data.get("confidence"), tokens_in=resp.usage.input_tokens,
                 tokens_out=resp.usage.output_tokens)
        return Decision(
            action=data["action"],
            confidence=float(data["confidence"]),
            size_fraction=float(data.get("size_fraction", 1.0) or 0.0),
            rationale=data.get("rationale", ""),
            raw=data,
        )
