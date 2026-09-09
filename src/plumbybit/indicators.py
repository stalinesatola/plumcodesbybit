"""Indicadores tecnicos basicos para alimentar o contexto do LLM.

Sem dependencias de TA externas - apenas pandas/numpy.
"""
from __future__ import annotations

import pandas as pd


def klines_to_df(rows: list[list[str]]) -> pd.DataFrame:
    """Converte a lista de klines da Bybit (ordem antiga->recente) num DataFrame."""
    df = pd.DataFrame(rows, columns=["start", "open", "high", "low", "close", "volume", "turnover"])
    for col in ("open", "high", "low", "close", "volume", "turnover"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["start"] = pd.to_datetime(pd.to_numeric(df["start"]), unit="ms", utc=True)
    return df


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def summarize(df: pd.DataFrame) -> dict:
    """Resumo compacto e numerico do estado do mercado."""
    close = df["close"]
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    rsi14 = _rsi(close)
    ret = close.pct_change()
    atr = (df["high"] - df["low"]).rolling(14).mean()
    last = close.iloc[-1]

    def r(x, n=4):
        return round(float(x), n)

    return {
        "last_price": r(last),
        "ema20": r(ema20.iloc[-1]),
        "ema50": r(ema50.iloc[-1]),
        "ema20_gt_ema50": bool(ema20.iloc[-1] > ema50.iloc[-1]),
        "price_vs_ema20_pct": r((last / ema20.iloc[-1] - 1) * 100, 2),
        "rsi14": r(rsi14.iloc[-1], 1),
        "return_1_pct": r(ret.iloc[-1] * 100, 2),
        "return_5_pct": r((close.iloc[-1] / close.iloc[-6] - 1) * 100, 2) if len(close) > 6 else None,
        "return_20_pct": r((close.iloc[-1] / close.iloc[-21] - 1) * 100, 2) if len(close) > 21 else None,
        "atr14": r(atr.iloc[-1]),
        "atr14_pct": r(atr.iloc[-1] / last * 100, 2),
        "high_20": r(df["high"].iloc[-20:].max()),
        "low_20": r(df["low"].iloc[-20:].min()),
        "volume_vs_avg20": r(df["volume"].iloc[-1] / df["volume"].iloc[-20:].mean(), 2),
    }
