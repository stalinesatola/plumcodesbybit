"""RuntimeConfig: mesma superficie que Settings, mas com as flags afinaveis
lidas do ConfigStore (mutaveis em runtime pelo web UI). Segredos e caminhos
continuam a vir das Settings do ambiente.

E isto que passamos a RiskManager / Trader / Brain / Agent em vez de Settings.
"""
from __future__ import annotations

from .config import AgentConfig, Provider, Settings
from .configstore import ConfigStore


class RuntimeConfig:
    def __init__(self, settings: Settings, store: ConfigStore):
        self._s = settings
        self._store = store

    # -- segredos / caminhos (imutaveis, do ambiente) --------------------
    @property
    def anthropic_api_key(self) -> str:
        return self._s.anthropic_api_key

    @property
    def nvidia_api_key(self) -> str:
        return self._s.nvidia_api_key

    @property
    def state_db(self) -> str:
        return self._s.state_db

    # -- flags afinaveis (do store) ---------------------------------
    @property
    def dry_run(self) -> bool:
        return bool(self._store.get_setting("dry_run"))

    @property
    def allow_real(self) -> bool:
        return bool(self._store.get_setting("allow_real"))

    @property
    def max_daily_loss_usdt(self) -> float:
        return float(self._store.get_setting("max_daily_loss_usdt"))

    @property
    def llm_provider(self) -> Provider:
        return self._store.get_setting("llm_provider")

    @property
    def llm_model(self) -> str:
        return self._store.get_setting("llm_model")

    @property
    def nvidia_model(self) -> str:
        return self._store.get_setting("nvidia_model")

    @property
    def nvidia_base_url(self) -> str:
        return self._store.get_setting("nvidia_base_url")

    # -- helpers (identicos aos de Settings) --------------------------
    def real_trading_armed(self) -> bool:
        return self.allow_real and not self.dry_run

    def resolve_llm(self, agent: AgentConfig) -> tuple[Provider, str]:
        provider: Provider = agent.provider or self.llm_provider
        if agent.model:
            return provider, agent.model
        return provider, (self.nvidia_model if provider == "nvidia" else self.llm_model)
