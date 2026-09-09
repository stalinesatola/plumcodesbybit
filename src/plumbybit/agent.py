"""Loop de um agent: snapshot -> decisao LLM -> risco -> execucao. 24/7."""
from __future__ import annotations

import asyncio
from typing import Any

from .brain import Brain
from .config import AgentConfig, Settings
from .exchange import get_exchange
from .logging_conf import get_logger
from .market_data import build_snapshot
from .risk import RiskManager
from .state import Store
from .trader import Trader

log = get_logger(__name__)


class Agent:
    def __init__(self, cfg: AgentConfig, settings: Settings, store: Store, brain: Brain):
        self.cfg = cfg
        self.s = settings
        self.store = store
        self.brain = brain
        self.risk = RiskManager(settings, store)
        self.trader = Trader(settings, store)
        self._log = get_logger("agent").bind(agent=cfg.name, account=cfg.account, symbol=cfg.symbol)

    def _current_position(self, ex) -> dict[str, Any] | None:
        for p in ex.positions(self.cfg.category, self.cfg.symbol):
            if float(p.get("size", 0) or 0) > 0:
                return p
        return None

    async def _tick(self) -> None:
        ex = get_exchange(self.cfg.account)
        position = await asyncio.to_thread(self._current_position, ex)
        snapshot = await asyncio.to_thread(build_snapshot, ex, self.cfg)
        equity = await asyncio.to_thread(ex.wallet_usdt)

        decision = await asyncio.to_thread(self.brain.decide, self.cfg, snapshot, position)
        verdict = self.risk.evaluate(self.cfg, decision, position, equity)

        executed: dict[str, Any] | None = None
        if verdict.allow:
            price = float(snapshot["ticker"]["last_price"])
            executed = await asyncio.to_thread(
                self.trader.execute, ex, self.cfg, decision, verdict, position, price
            )
        else:
            self._log.info("skip", action=decision.action, reason=verdict.reason,
                           confidence=round(decision.confidence, 2))

        self.store.log_decision(
            self.cfg.name, self.cfg.account, self.cfg.symbol, decision.action,
            decision.confidence, executed is not None,
            {"rationale": decision.rationale, "verdict": verdict.reason, "executed": executed},
        )

    async def run(self) -> None:
        self._log.info("agent.start", poll_seconds=self.cfg.poll_seconds)
        while True:
            try:
                await self._tick()
            except Exception:  # noqa: BLE001 - um agent nao pode derrubar os outros
                self._log.exception("tick.error")
            await asyncio.sleep(self.cfg.poll_seconds)
