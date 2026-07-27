from __future__ import annotations

import os

import pytest


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
        "JAVCODE_HTTP_PROXY",
        "JAVCODE_HTTPS_PROXY",
        "JAVCODE_ADMIN_USERNAME",
        "JAVCODE_ADMIN_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)
    yield
