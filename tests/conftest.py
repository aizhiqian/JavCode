from __future__ import annotations

import pytest

# Load project .env once so integration tests can see JAVCODE_DB (MySQL, etc.).
# AI-related keys are still cleared per-test below.
from src.env import load_project_env

load_project_env()


@pytest.fixture(autouse=True)
def _isolate_ai_env(monkeypatch):
    for key in (
        "JAVCODE_AI_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "JAVCODE_AI_ENABLED",
        "JAVCODE_AI_BASE_URL",
        "JAVCODE_AI_MODEL",
        "JAVCODE_AI_TIMEOUT",
        "JAVCODE_PROXY",
        "JAVCODE_ADMIN_USERNAME",
        "JAVCODE_ADMIN_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
