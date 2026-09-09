"""Guardrails deterministicos. Toda a decisao do LLM passa por aqui antes de executar."""
from __future__ import annotations

from dataclasses import dataclass

from .brain import Decision
from .config import AgentConfig, Settings
from .state import Store

MIN_CONFIDENCE = 0.55


@dataclass
class RiskVerdict:
    allow: bool
    reason: str
    qty_usdt: float = 0.0


class RiskManager:
    def __init__(self, settings: Settings, store: Store):
        self.s = settings
        self.store = store

    def evaluate(
        self,
        cfg: AgentConfig,
        decision: Decision,
        position: dict | None,
        equity_usdt: float,
    ) -> RiskVerdict:
        has_pos = bool(position and float(position.get("size", 0) or 0) > 0)

        if decision.action == "hold":
            return RiskVerdict(False, "hold")

        if decision.action == "close":
            if not has_pos:
                return RiskVerdict(False, "close pedido mas sem posicao")
            return RiskVerdict(True, "close")

        # --- a partir daqui e uma abertura ---
        if has_pos:
            return RiskVerdict(False, "ja existe posicao aberta (max_open_positions)")

        if decision.confidence < MIN_CONFIDENCE:
            return RiskVerdict(False, f"confianca {decision.confidence:.2f} < {MIN_CONFIDENCE}")

        # kill switch de perda diaria
        loss_today = -self.store.realized_pnl_today(cfg.account)
        if loss_today >= self.s.max_daily_loss_usdt:
            return RiskVerdict(False, f"limite de perda diaria atingido ({loss_today:.2f} USDT)")

        # dimensionamento
        frac = max(0.1, min(1.0, decision.size_fraction or 1.0))
        qty_usdt = round(cfg.max_position_usdt * frac, 2)
        if equity_usdt and qty_usdt > equity_usdt * cfg.leverage:
            qty_usdt = round(equity_usdt * cfg.leverage * 0.95, 2)
        if qty_usdt < 5:
            return RiskVerdict(False, f"notional {qty_usdt} abaixo do minimo")

        return RiskVerdict(True, "ok", qty_usdt)
