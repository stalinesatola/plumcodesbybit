"""Smoke tests do web UI (sem rede - agents nao arrancam por falta de chaves)."""
from __future__ import annotations

import tempfile

import pytest
from fastapi.testclient import TestClient

from plumbybit.config import Settings
from plumbybit.web.app import create_app


def _settings(**over) -> Settings:
    base = dict(
        ANTHROPIC_API_KEY="x", NVIDIA_API_KEY="",
        PLUMBYBIT_STATE_DB=tempfile.mkdtemp() + "/s.db",
        PLUMBYBIT_AGENTS_CONFIG="/nao/existe.yaml",
        PLUMBYBIT_WEB_PASSWORD="", PLUMBYBIT_WEB_SECRET="t",
    )
    base.update(over)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


@pytest.fixture()
def client():
    with TestClient(create_app(_settings())) as c:
        yield c


def test_state_ok_without_auth(client):
    r = client.get("/api/state")
    assert r.status_code == 200
    body = r.json()
    assert "settings" in body and "agents" in body
    assert body["settings"]["dry_run"] is True


def test_crud_agent_and_toggle(client):
    payload = {"name": "t1", "symbol": "BTCUSDT", "account": "demo", "enabled": False}
    assert client.post("/api/agents", json=payload).status_code == 200
    assert any(a["name"] == "t1" for a in client.get("/api/agents").json())

    r = client.put("/api/settings", json={"max_daily_loss_usdt": 12.5})
    assert r.json()["max_daily_loss_usdt"] == 12.5

    assert client.post("/api/agents/t1/start").json()["status"] in ("running", "stopped")
    assert client.delete("/api/agents/t1").status_code == 200
    assert client.get("/api/agents/").status_code in (200, 404)


def test_auth_enforced_when_password_set():
    with TestClient(create_app(_settings(PLUMBYBIT_WEB_PASSWORD="segredo"))) as c:
        assert c.get("/api/state").status_code == 401
        assert c.post("/api/login", json={"password": "errada"}).status_code == 401
        assert c.post("/api/login", json={"password": "segredo"}).status_code == 200
        assert c.get("/api/state").status_code == 200
