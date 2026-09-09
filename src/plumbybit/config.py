"""Carregamento de configuracao: variaveis de ambiente (.env) + agents.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Account = Literal["demo", "real"]


class Settings(BaseSettings):
    """Configuracao global vinda do ambiente / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY")
    llm_model: str = Field("claude-sonnet-5", alias="PLUMBYBIT_LLM_MODEL")

    bybit_demo_api_key: str = Field("", alias="BYBIT_DEMO_API_KEY")
    bybit_demo_api_secret: str = Field("", alias="BYBIT_DEMO_API_SECRET")
    bybit_real_api_key: str = Field("", alias="BYBIT_REAL_API_KEY")
    bybit_real_api_secret: str = Field("", alias="BYBIT_REAL_API_SECRET")

    allow_real: bool = Field(False, alias="PLUMBYBIT_ALLOW_REAL")
    dry_run: bool = Field(True, alias="PLUMBYBIT_DRY_RUN")
    max_daily_loss_usdt: float = Field(50.0, alias="PLUMBYBIT_MAX_DAILY_LOSS_USDT")

    agents_config: str = Field("config/agents.yaml", alias="PLUMBYBIT_AGENTS_CONFIG")
    log_level: str = Field("INFO", alias="PLUMBYBIT_LOG_LEVEL")
    state_db: str = Field("data/plumbybit.db", alias="PLUMBYBIT_STATE_DB")

    def credentials(self, account: Account) -> tuple[str, str]:
        if account == "demo":
            return self.bybit_demo_api_key, self.bybit_demo_api_secret
        return self.bybit_real_api_key, self.bybit_real_api_secret

    def real_trading_armed(self) -> bool:
        """So True se explicitamente autorizado e fora de dry-run."""
        return self.allow_real and not self.dry_run


class AgentConfig(BaseModel):
    name: str
    account: Account = "demo"
    symbol: str
    enabled: bool = True
    category: str = "linear"
    interval: str = "15"
    poll_seconds: int = 180
    leverage: int = 3
    max_position_usdt: float = 100.0
    max_open_positions: int = 1
    take_profit_pct: float = 1.5
    stop_loss_pct: float = 1.0
    candles_lookback: int = 200


def load_agents(path: str | Path) -> list[AgentConfig]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    defaults: dict = raw.get("defaults", {})
    agents: list[AgentConfig] = []
    for entry in raw.get("agents", []):
        merged = {**defaults, **entry}
        agents.append(AgentConfig(**merged))
    names = [a.name for a in agents]
    if len(names) != len(set(names)):
        raise ValueError(f"Nomes de agent duplicados: {names}")
    return agents
