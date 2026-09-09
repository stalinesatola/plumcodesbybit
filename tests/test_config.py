"""Resolucao de provider/modelo do cerebro por agent."""
from __future__ import annotations

from plumbybit.config import AgentConfig, Settings


def _settings(**env) -> Settings:
    base = dict(
        ANTHROPIC_API_KEY="x", PLUMBYBIT_LLM_PROVIDER="anthropic",
        PLUMBYBIT_LLM_MODEL="claude-sonnet-5",
        NVIDIA_API_KEY="y", PLUMBYBIT_NVIDIA_MODEL="meta/llama-3.3-70b-instruct",
    )
    base.update(env)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


def _agent(**kw) -> AgentConfig:
    return AgentConfig(name="a", symbol="BTCUSDT", **kw)


def test_default_provider_is_global():
    assert _settings().resolve_llm(_agent()) == ("anthropic", "claude-sonnet-5")


def test_global_provider_nvidia():
    s = _settings(PLUMBYBIT_LLM_PROVIDER="nvidia")
    assert s.resolve_llm(_agent()) == ("nvidia", "meta/llama-3.3-70b-instruct")


def test_agent_overrides_provider_and_model():
    s = _settings()
    got = s.resolve_llm(_agent(provider="nvidia", model="deepseek-ai/deepseek-r1"))
    assert got == ("nvidia", "deepseek-ai/deepseek-r1")


def test_agent_provider_override_uses_that_providers_default_model():
    assert _settings().resolve_llm(_agent(provider="nvidia")) == ("nvidia", "meta/llama-3.3-70b-instruct")
