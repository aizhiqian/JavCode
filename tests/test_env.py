from __future__ import annotations

import os
from pathlib import Path

from src.ai import AIConfig
from src.env import load_project_env, parse_bool
from src.settings import proxy_public_status, resolve_proxy_dict


def test_parse_bool_truthy_falsey_and_default():
    assert parse_bool(True) is True
    assert parse_bool(False) is False
    assert parse_bool("1") is True
    assert parse_bool("yes") is True
    assert parse_bool("OFF") is False
    assert parse_bool("0") is False
    assert parse_bool(None, default=None) is None
    assert parse_bool(None, default=False) is False
    assert parse_bool("", default=True) is True
    assert parse_bool("maybe", default=None) is None


def test_load_project_env_from_file(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "JAVCODE_AI_API_KEY=from-dotenv-file\n"
        "JAVCODE_AI_BASE_URL=https://example.test/v1\n"
        "JAVCODE_AI_MODEL=file-model\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("JAVCODE_AI_API_KEY", raising=False)
    monkeypatch.delenv("JAVCODE_AI_BASE_URL", raising=False)
    monkeypatch.delenv("JAVCODE_AI_MODEL", raising=False)

    assert load_project_env(env_file) is True
    cfg = AIConfig.resolve(None)
    assert cfg.api_key == "from-dotenv-file"
    assert cfg.model == "file-model"
    assert "example.test" in cfg.base_url
    assert cfg.available is True


def test_load_project_env_does_not_override_existing(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("JAVCODE_AI_API_KEY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("JAVCODE_AI_API_KEY", "from-shell")
    assert load_project_env(env_file) is True
    assert os.environ["JAVCODE_AI_API_KEY"] == "from-shell"


def test_resolve_does_not_read_dotenv_file_itself(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("JAVCODE_AI_API_KEY=should-not-appear\n", encoding="utf-8")
    monkeypatch.delenv("JAVCODE_AI_API_KEY", raising=False)
    cfg = AIConfig.resolve(None)
    assert cfg.api_key == ""
    assert cfg.available is False


def test_proxy_from_javcode_env(monkeypatch):
    monkeypatch.delenv("JAVCODE_PROXY", raising=False)
    monkeypatch.setenv("JAVCODE_PROXY", "http://127.0.0.1:7890")

    assert resolve_proxy_dict(None) == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }
    status = proxy_public_status()
    assert status["enabled"] is True
    assert "7890" in status["http"]


def test_proxy_default_empty(monkeypatch):
    monkeypatch.delenv("JAVCODE_PROXY", raising=False)
    assert resolve_proxy_dict(None) == {}
    status = proxy_public_status()
    assert status["enabled"] is False
    assert status["http"] == ""
    assert status["https"] == ""


def test_load_project_env_sets_javcode_proxy(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("JAVCODE_PROXY=http://proxy.example:8080\n", encoding="utf-8")
    monkeypatch.delenv("JAVCODE_PROXY", raising=False)
    assert load_project_env(env_file) is True
    assert os.environ.get("JAVCODE_PROXY") == "http://proxy.example:8080"
    assert resolve_proxy_dict(None) == {
        "http": "http://proxy.example:8080",
        "https": "http://proxy.example:8080",
    }


def test_proxy_public_status_redacts_credentials(monkeypatch):
    monkeypatch.setenv("JAVCODE_PROXY", "http://user:secret@127.0.0.1:7890")
    status = proxy_public_status()
    assert status["enabled"] is True
    assert "secret" not in status["http"]
    assert "***@" in status["http"]


def test_fetcher_ignores_env_proxy_unless_injected(monkeypatch):
    from src.fetchers import SourceFetcher

    monkeypatch.setenv("JAVCODE_PROXY", "http://env-proxy:1")
    monkeypatch.setenv("HTTP_PROXY", "http://ambient:9")
    bare = SourceFetcher()
    assert bare.session.trust_env is False
    assert bare.session.proxies.get("http") in (None, "")
    injected = SourceFetcher(proxies={"http": "http://x:1", "https": "http://x:1"})
    assert injected.session.proxies.get("http") == "http://x:1"
