from __future__ import annotations

import os

import pytest

from src.ai import AIConfig
from src.auth import hash_password, verify_password
from src.server import create_app
from src.settings import (
    SettingsStore,
    effective_proxy,
    settings_public_view,
    update_settings_from_payload,
)


def _login(client, username="admin", password="secret"):
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )


def _setup(client, username="admin", password="secret"):
    return client.post(
        "/api/auth/setup",
        json={"username": username, "password": password},
    )


def test_password_hash_roundtrip():
    h = hash_password("hello")
    assert h != "hello"
    assert verify_password(h, "hello")
    assert not verify_password(h, "wrong")


def test_settings_override_beats_env(tmp_path, monkeypatch):
    monkeypatch.setenv("JAVCODE_AI_API_KEY", "from-env-key")
    monkeypatch.setenv("JAVCODE_PROXY", "http://env-proxy:1")
    store = SettingsStore(tmp_path / "s.db")
    cfg = AIConfig.resolve(store)
    assert cfg.api_key == "from-env-key"
    assert effective_proxy(store).source == "env"

    update_settings_from_payload(
        store,
        {"ai_api_key": "from-settings-key", "proxy": "http://settings-proxy:2"},
    )
    cfg2 = AIConfig.resolve(store)
    assert cfg2.api_key == "from-settings-key"
    assert effective_proxy(store).value == "http://settings-proxy:2"
    assert effective_proxy(store).source == "settings"

    update_settings_from_payload(store, {"ai_api_key": "", "proxy": ""})
    cfg3 = AIConfig.resolve(store)
    assert cfg3.api_key == "from-env-key"
    assert effective_proxy(store).source == "env"


def test_settings_public_view_plain_text(tmp_path, monkeypatch):
    monkeypatch.delenv("JAVCODE_AI_API_KEY", raising=False)
    store = SettingsStore(tmp_path / "s.db")
    update_settings_from_payload(
        store, {"ai_api_key": "sk-plain-secret", "proxy": "http://127.0.0.1:7890"}
    )
    view = settings_public_view(store)
    assert view["fields"]["ai_api_key"]["value"] == "sk-plain-secret"
    assert view["fields"]["proxy"]["value"] == "http://127.0.0.1:7890"
    assert view["fields"]["ai_api_key"]["source"] == "settings"


def test_api_requires_auth(tmp_path):
    app = create_app(db_path=tmp_path / "a.db")
    c = app.test_client()
    r = c.get("/api/movies")
    assert r.status_code == 401
    assert r.get_json()["code"] in ("unauthorized", "setup_required")


def test_setup_login_logout_flow(tmp_path):
    app = create_app(db_path=tmp_path / "a.db")
    c = app.test_client()

    st = c.get("/api/auth/status").get_json()
    assert st["configured"] is False
    assert st["authenticated"] is False

    bad = _setup(c, password="12")
    assert bad.status_code == 400

    ok = _setup(c, username="boss", password="passw0rd")
    assert ok.status_code == 200
    assert ok.get_json()["authenticated"] is True
    assert ok.get_json()["username"] == "boss"

    again = _setup(c, password="other")
    assert again.status_code == 400

    movies = c.get("/api/movies")
    assert movies.status_code == 200

    c.post("/api/auth/logout", json={})
    assert c.get("/api/movies").status_code == 401

    wrong = _login(c, "boss", "nope")
    assert wrong.status_code == 401

    good = _login(c, "boss", "passw0rd")
    assert good.status_code == 200
    assert c.get("/api/movies").status_code == 200


def test_settings_api_plain_and_hot_priority(tmp_path, monkeypatch):
    monkeypatch.setenv("JAVCODE_AI_API_KEY", "env-key-xxx")
    app = create_app(db_path=tmp_path / "a.db")
    c = app.test_client()
    _setup(c, password="secret1")

    got = c.get("/api/settings").get_json()
    assert got["ok"] is True
    assert got["fields"]["ai_api_key"]["value"] == "env-key-xxx"
    assert got["fields"]["ai_api_key"]["source"] == "env"

    put = c.put(
        "/api/settings",
        json={"ai_api_key": "settings-key-yyy", "proxy": "http://1.2.3.4:1080"},
    )
    assert put.status_code == 200
    body = put.get_json()
    assert body["fields"]["ai_api_key"]["value"] == "settings-key-yyy"
    assert body["fields"]["ai_api_key"]["source"] == "settings"
    assert body["fields"]["proxy"]["value"] == "http://1.2.3.4:1080"

    ai = c.get("/api/ai/status").get_json()["ai"]
    assert ai["configured"] is True

    c.post("/api/auth/logout", json={})
    assert c.get("/api/settings").status_code == 401


def test_bootstrap_admin_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("JAVCODE_ADMIN_USERNAME", "root")
    monkeypatch.setenv("JAVCODE_ADMIN_PASSWORD", "env-admin-pass")
    app = create_app(db_path=tmp_path / "a.db")
    c = app.test_client()
    st = c.get("/api/auth/status").get_json()
    assert st["configured"] is True
    assert st["authenticated"] is False
    login = _login(c, "root", "env-admin-pass")
    assert login.status_code == 200


def test_health_hides_secrets_when_anonymous(tmp_path):
    app = create_app(db_path=tmp_path / "a.db")
    c = app.test_client()
    h = c.get("/api/health").get_json()
    assert h["ok"] is True
    assert "ai" not in h or h.get("authenticated") is False
