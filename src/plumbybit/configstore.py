"""Fonte de verdade da configuracao editavel pelo web UI (SQLite).

- Tabela `agents`: uma linha por agent (espelha AgentConfig).
- Tabela `app_settings`: pares chave/valor para as flags globais afinaveis
  em runtime (dry_run, allow_real, max_daily_loss_usdt, provider/modelos LLM...).

Segredos (API keys) NAO vivem aqui - continuam so no ambiente / .env.
No primeiro arranque, se as tabelas estiverem vazias, sao semeadas a partir
do agents.yaml e das Settings do ambiente.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .config import AgentConfig, Settings, load_agents

_LOCK = threading.RLock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    name TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# flags globais afinaveis em runtime + defaults (vindos das Settings)
TUNABLE_KEYS = (
    "dry_run",
    "allow_real",
    "max_daily_loss_usdt",
    "llm_provider",
    "llm_model",
    "nvidia_model",
    "nvidia_base_url",
)


class ConfigStore:
    def __init__(self, path: str, settings: Settings):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._cx = sqlite3.connect(path, check_same_thread=False)
        self._cx.row_factory = sqlite3.Row
        self._cx.executescript(_SCHEMA)
        self._cx.commit()
        self._settings = settings
        self._seed_if_empty()

    # -- seed -----------------------------------------------------------
    def _seed_if_empty(self) -> None:
        with _LOCK:
            if not self._cx.execute("SELECT 1 FROM app_settings LIMIT 1").fetchone():
                for k in TUNABLE_KEYS:
                    self._set_raw(k, getattr(self._settings, k))
            if not self._cx.execute("SELECT 1 FROM agents LIMIT 1").fetchone():
                try:
                    seeded = load_agents(self._settings.agents_config)
                except (FileNotFoundError, OSError):
                    seeded = []
                for a in seeded:
                    self.upsert_agent(a)

    # -- settings -----------------------------------------------------
    def _set_raw(self, key: str, value: Any) -> None:
        self._cx.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        self._cx.commit()

    def get_setting(self, key: str) -> Any:
        with _LOCK:
            row = self._cx.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return getattr(self._settings, key, None)
        return json.loads(row["value"])

    def all_settings(self) -> dict[str, Any]:
        return {k: self.get_setting(k) for k in TUNABLE_KEYS}

    def set_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        with _LOCK:
            for k, v in values.items():
                if k not in TUNABLE_KEYS:
                    raise KeyError(f"setting nao afinavel: {k}")
                self._set_raw(k, v)
        return self.all_settings()

    # -- agents -----------------------------------------------------
    def list_agents(self) -> list[AgentConfig]:
        with _LOCK:
            rows = self._cx.execute("SELECT data FROM agents ORDER BY name").fetchall()
        return [AgentConfig(**json.loads(r["data"])) for r in rows]

    def get_agent(self, name: str) -> AgentConfig | None:
        with _LOCK:
            row = self._cx.execute("SELECT data FROM agents WHERE name = ?", (name,)).fetchone()
        return AgentConfig(**json.loads(row["data"])) if row else None

    def upsert_agent(self, agent: AgentConfig) -> AgentConfig:
        with _LOCK:
            self._cx.execute(
                "INSERT INTO agents (name, data) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET data = excluded.data",
                (agent.name, agent.model_dump_json()),
            )
            self._cx.commit()
        return agent

    def delete_agent(self, name: str) -> bool:
        with _LOCK:
            cur = self._cx.execute("DELETE FROM agents WHERE name = ?", (name,))
            self._cx.commit()
        return cur.rowcount > 0
