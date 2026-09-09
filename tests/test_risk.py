"""Testes dos guardrails de risco (nao tocam na rede)."""
from __future__ import annotations

import tempfile

import pytest

from plumbybit.brain import Decision
from plumbybit.config import AgentConfig
from plumbybit.risk import MIN_CONFIDENCE, RiskManager
from plumbybit.state import Store


class FakeSettings:
    max_daily_loss_usdt = 50.0

    def real_trading_armed(self) -> bool:
        return False


@pytest.fixture()
def rm() -> RiskManager:
    store = Store(tempfile.mkstemp(suffix=".db")[1])
    return RiskManager(FakeSettings(), store)  # type: ignore[arg-type]


def _cfg(**kw) -> AgentConfig:
    base = dict(name="t", account="demo", symbol="BTCUSDT")
    base.update(kw)
    return AgentConfig(**base)


def _dec(action: str, confidence: float = 0.9, size: float = 1.0) -> Decision:
    return Decision(action=action, confidence=confidence, size_fraction=size, rationale="", raw={})


def test_hold_never_executes(rm):
    assert rm.evaluate(_cfg(), _dec("hold"), None, 1000).allow is False


def test_low_confidence_blocks_entry(rm):
    v = rm.evaluate(_cfg(), _dec("open_long", confidence=MIN_CONFIDENCE - 0.01), None, 1000)
    assert v.allow is False


def test_entry_blocked_when_position_open(rm):
    pos = {"size": "0.1", "side": "Buy"}
    assert rm.evaluate(_cfg(), _dec("open_long"), pos, 1000).allow is False


def test_valid_entry_sizes_notional(rm):
    v = rm.evaluate(_cfg(max_position_usdt=100), _dec("open_long", size=0.5), None, 10_000)
    assert v.allow is True
    assert v.qty_usdt == pytest.approx(50.0)


def test_close_requires_position(rm):
    assert rm.evaluate(_cfg(), _dec("close"), None, 1000).allow is False
    assert rm.evaluate(_cfg(), _dec("close"), {"size": "0.1", "side": "Buy"}, 1000).allow is True


def test_daily_loss_kill_switch(rm):
    rm.store.record_fill("t", "demo", "BTCUSDT", "close", 0.1, realized_pnl=-60)
    assert rm.evaluate(_cfg(), _dec("open_long"), None, 1000).allow is False
