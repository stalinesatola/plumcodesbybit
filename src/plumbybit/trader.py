"""Execucao: converte uma decisao aprovada em ordens de mercado na Bybit."""
from __future__ import annotations

import math
from typing import Any

from .brain import Decision
from .config import AgentConfig, Settings
from .exchange import Exchange
from .logging_conf import get_logger
from .risk import RiskVerdict
from .state import Store

log = get_logger(__name__)


def _round_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor(value / step) * step


class Trader:
    def __init__(self, settings: Settings, store: Store):
        self.s = settings
        self.store = store

    def _qty_from_usdt(self, ex: Exchange, cfg: AgentConfig, usdt: float, price: float) -> str:
        inst = ex.instrument(cfg.category, cfg.symbol)
        lot = inst.get("lotSizeFilter", {})
        step = float(lot.get("qtyStep", "0.001"))
        min_qty = float(lot.get("minOrderQty", step))
        qty = _round_step(usdt / price, step)
        qty = max(qty, min_qty)
        decimals = max(0, len(str(step).split(".")[-1])) if "." in str(step) else 0
        return f"{qty:.{decimals}f}"

    def execute(
        self,
        ex: Exchange,
        cfg: AgentConfig,
        decision: Decision,
        verdict: RiskVerdict,
        position: dict[str, Any] | None,
        price: float,
    ) -> dict[str, Any]:
        dry = self.s.dry_run or (cfg.account == "real" and not self.s.real_trading_armed())
        result: dict[str, Any] = {"dry_run": dry, "action": decision.action}

        if decision.action == "close":
            side = "Sell" if (position or {}).get("side") == "Buy" else "Buy"
            qty = str(position.get("size")) if position else "0"
            result.update(side=side, qty=qty)
            if not dry:
                result["order"] = ex.place_market_order(cfg.category, cfg.symbol, side, qty, reduce_only=True)
                self.store.record_fill(cfg.name, cfg.account, cfg.symbol, f"close-{side}", float(qty),
                                       float((position or {}).get("unrealisedPnl", 0) or 0))
            log.info("execute.close", agent=cfg.name, dry_run=dry, side=side, qty=qty)
            return result

        # abertura
        side = "Buy" if decision.action == "open_long" else "Sell"
        qty = self._qty_from_usdt(ex, cfg, verdict.qty_usdt, price)
        tp_mult = 1 + cfg.take_profit_pct / 100 if side == "Buy" else 1 - cfg.take_profit_pct / 100
        sl_mult = 1 - cfg.stop_loss_pct / 100 if side == "Buy" else 1 + cfg.stop_loss_pct / 100
        tp = f"{price * tp_mult:.4f}"
        sl = f"{price * sl_mult:.4f}"
        result.update(side=side, qty=qty, take_profit=tp, stop_loss=sl, notional_usdt=verdict.qty_usdt)

        if not dry:
            ex.set_leverage(cfg.category, cfg.symbol, cfg.leverage)
            result["order"] = ex.place_market_order(cfg.category, cfg.symbol, side, qty, take_profit=tp, stop_loss=sl)
            self.store.record_fill(cfg.name, cfg.account, cfg.symbol, f"open-{side}", float(qty))

        log.info("execute.open", agent=cfg.name, dry_run=dry, side=side, qty=qty, tp=tp, sl=sl)
        return result
