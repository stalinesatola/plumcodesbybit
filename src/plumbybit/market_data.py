"""Montagem do snapshot de mercado que e passado ao LLM."""
from __future__ import annotations

from typing import Any

from .config import AgentConfig
from .exchange import Exchange
from .indicators import klines_to_df, summarize


def build_snapshot(ex: Exchange, cfg: AgentConfig) -> dict[str, Any]:
    rows = ex.klines(cfg.category, cfg.symbol, cfg.interval, cfg.candles_lookback)
    df = klines_to_df(rows)
    tk = ex.ticker(cfg.category, cfg.symbol)

    recent = df.tail(12)[["start", "open", "high", "low", "close", "volume"]].copy()
    recent["start"] = recent["start"].dt.strftime("%Y-%m-%dT%H:%MZ")

    return {
        "symbol": cfg.symbol,
        "interval": cfg.interval,
        "generated_from_candles": len(df),
        "ticker": {
            "last_price": float(tk.get("lastPrice", 0) or 0),
            "mark_price": float(tk.get("markPrice", 0) or 0),
            "funding_rate": float(tk.get("fundingRate", 0) or 0),
            "price_24h_pct": float(tk.get("price24hPcnt", 0) or 0) * 100,
            "open_interest_value": float(tk.get("openInterestValue", 0) or 0),
        },
        "indicators": summarize(df),
        "recent_candles": recent.to_dict(orient="records"),
    }
