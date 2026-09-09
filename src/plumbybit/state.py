"""Persistencia leve em SQLite: log de decisoes e controlo de perda diaria."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    agent TEXT NOT NULL,
    account TEXT NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence REAL,
    executed INTEGER NOT NULL DEFAULT 0,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    day TEXT NOT NULL,
    agent TEXT NOT NULL,
    account TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL,
    realized_pnl REAL NOT NULL DEFAULT 0
);
"""


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._cx = sqlite3.connect(path, check_same_thread=False)
        self._cx.executescript(_SCHEMA)
        self._cx.commit()

    def log_decision(self, agent: str, account: str, symbol: str, action: str,
                     confidence: float, executed: bool, detail: dict[str, Any]) -> None:
        with _LOCK:
            self._cx.execute(
                "INSERT INTO decisions (ts, agent, account, symbol, action, confidence, executed, detail) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (_now(), agent, account, symbol, action, confidence, int(executed), json.dumps(detail, default=str)),
            )
            self._cx.commit()

    def record_fill(self, agent: str, account: str, symbol: str, side: str,
                    qty: float, realized_pnl: float = 0.0) -> None:
        with _LOCK:
            self._cx.execute(
                "INSERT INTO fills (ts, day, agent, account, symbol, side, qty, realized_pnl) VALUES (?,?,?,?,?,?,?,?)",
                (_now(), _today(), agent, account, symbol, side, qty, realized_pnl),
            )
            self._cx.commit()

    def realized_pnl_today(self, account: str | None = None) -> float:
        q = "SELECT COALESCE(SUM(realized_pnl),0) FROM fills WHERE day = ?"
        args: list[Any] = [_today()]
        if account:
            q += " AND account = ?"
            args.append(account)
        with _LOCK:
            return float(self._cx.execute(q, args).fetchone()[0])


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")
