from __future__ import annotations

import os
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .env import apply_proxy_from_env

SETTING_KEYS = (
    "ai_api_key",
    "ai_base_url",
    "ai_model",
    "ai_enabled",
    "ai_timeout",
    "proxy",
)

META_ADMIN_USERNAME = "admin_username"
META_ADMIN_PASSWORD_HASH = "admin_password_hash"
META_SECRET_KEY = "secret_key"

DEFAULT_ADMIN_USERNAME = "admin"


@dataclass
class ResolvedValue:
    value: str
    source: str


class SettingsStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def get(self, key: str, default: str = "") -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_meta WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return default
        return row["value"] if row["value"] is not None else default

    def set(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_meta (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value if value is not None else ""),
            )

    def delete(self, key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM app_meta WHERE key = ?", (key,))

    def get_many(self, keys: list[str] | tuple[str, ...]) -> dict[str, str]:
        out: dict[str, str] = {}
        with self._connect() as conn:
            for key in keys:
                row = conn.execute(
                    "SELECT value FROM app_meta WHERE key = ?", (key,)
                ).fetchone()
                if row is not None and row["value"] is not None:
                    out[key] = row["value"]
        return out

    def set_many(self, mapping: dict[str, str | None]) -> None:
        with self._connect() as conn:
            for key, value in mapping.items():
                if value is None:
                    continue
                if value == "":
                    conn.execute("DELETE FROM app_meta WHERE key = ?", (key,))
                else:
                    conn.execute(
                        """
                        INSERT INTO app_meta (key, value) VALUES (?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value
                        """,
                        (key, value),
                    )

    def ensure_secret_key(self) -> str:
        existing = self.get(META_SECRET_KEY, "")
        if existing:
            return existing
        key = secrets.token_hex(32)
        self.set(META_SECRET_KEY, key)
        return key

    def is_admin_configured(self) -> bool:
        return bool(self.get(META_ADMIN_PASSWORD_HASH, "").strip())

    def admin_username(self) -> str:
        return self.get(META_ADMIN_USERNAME, DEFAULT_ADMIN_USERNAME).strip() or DEFAULT_ADMIN_USERNAME

    def admin_password_hash(self) -> str:
        return self.get(META_ADMIN_PASSWORD_HASH, "")

    def set_admin(self, username: str, password_hash: str) -> None:
        name = (username or DEFAULT_ADMIN_USERNAME).strip() or DEFAULT_ADMIN_USERNAME
        self.set(META_ADMIN_USERNAME, name)
        self.set(META_ADMIN_PASSWORD_HASH, password_hash)

    def bootstrap_admin_from_env(self) -> bool:
        if self.is_admin_configured():
            return False
        password = (os.environ.get("JAVCODE_ADMIN_PASSWORD") or "").strip()
        if not password:
            return False
        from .auth import hash_password

        username = (
            os.environ.get("JAVCODE_ADMIN_USERNAME") or DEFAULT_ADMIN_USERNAME
        ).strip() or DEFAULT_ADMIN_USERNAME
        self.set_admin(username, hash_password(password))
        return True


def resolve_setting(
    store: SettingsStore | None,
    key: str,
    *,
    env_names: tuple[str, ...] = (),
    default: str = "",
) -> ResolvedValue:
    if store is not None:
        raw = store.get(key, "")
        if raw is not None and str(raw).strip() != "":
            return ResolvedValue(value=str(raw), source="settings")
    for name in env_names:
        val = os.environ.get(name)
        if val is not None and str(val).strip() != "":
            return ResolvedValue(value=str(val).strip(), source="env")
    return ResolvedValue(value=default, source="default")


def effective_ai_fields(store: SettingsStore | None) -> dict[str, ResolvedValue]:
    from .ai import DEFAULT_BASE_URL, DEFAULT_MODEL

    key = resolve_setting(
        store,
        "ai_api_key",
        env_names=("JAVCODE_AI_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY"),
    )
    base = resolve_setting(
        store,
        "ai_base_url",
        env_names=("JAVCODE_AI_BASE_URL", "OPENAI_BASE_URL"),
        default=DEFAULT_BASE_URL,
    )
    model = resolve_setting(
        store,
        "ai_model",
        env_names=("JAVCODE_AI_MODEL", "OPENAI_MODEL"),
        default=DEFAULT_MODEL,
    )
    enabled = resolve_setting(
        store,
        "ai_enabled",
        env_names=("JAVCODE_AI_ENABLED",),
        default="",
    )
    timeout = resolve_setting(
        store,
        "ai_timeout",
        env_names=("JAVCODE_AI_TIMEOUT",),
        default="60",
    )
    return {
        "ai_api_key": key,
        "ai_base_url": ResolvedValue(base.value.rstrip("/"), base.source),
        "ai_model": model,
        "ai_enabled": enabled,
        "ai_timeout": timeout,
    }


def effective_proxy(store: SettingsStore | None) -> ResolvedValue:
    return resolve_setting(
        store,
        "proxy",
        env_names=(
            "JAVCODE_PROXY",
            "JAVCODE_ALL_PROXY",
            "JAVCODE_HTTPS_PROXY",
            "JAVCODE_HTTP_PROXY",
            "HTTPS_PROXY",
            "HTTP_PROXY",
            "ALL_PROXY",
        ),
        default="",
    )


def apply_effective_proxy(store: SettingsStore | None) -> dict[str, str]:
    resolved = effective_proxy(store)
    if resolved.source == "settings" and resolved.value:
        os.environ["JAVCODE_PROXY"] = resolved.value
        os.environ["HTTP_PROXY"] = resolved.value
        os.environ["HTTPS_PROXY"] = resolved.value
        os.environ["http_proxy"] = resolved.value
        os.environ["https_proxy"] = resolved.value
        os.environ["ALL_PROXY"] = resolved.value
        os.environ["all_proxy"] = resolved.value
    return apply_proxy_from_env()


def settings_public_view(store: SettingsStore) -> dict[str, Any]:
    fields = effective_ai_fields(store)
    proxy = effective_proxy(store)
    stored = store.get_many(SETTING_KEYS)

    def pack(key: str, rv: ResolvedValue) -> dict[str, Any]:
        return {
            "value": rv.value,
            "source": rv.source,
            "override": stored.get(key, ""),
        }

    enabled_rv = fields["ai_enabled"]
    enabled_display = enabled_rv.value
    if enabled_rv.source == "default" or enabled_display == "":
        key_present = bool(fields["ai_api_key"].value.strip())
        enabled_display = "1" if key_present else "0"

    return {
        "admin_username": store.admin_username(),
        "fields": {
            "ai_api_key": pack("ai_api_key", fields["ai_api_key"]),
            "ai_base_url": pack("ai_base_url", fields["ai_base_url"]),
            "ai_model": pack("ai_model", fields["ai_model"]),
            "ai_enabled": {
                "value": enabled_display if enabled_rv.value != "" else enabled_display,
                "source": enabled_rv.source if enabled_rv.value != "" else (
                    "default" if "ai_enabled" not in stored else "settings"
                ),
                "override": stored.get("ai_enabled", ""),
            },
            "ai_timeout": pack("ai_timeout", fields["ai_timeout"]),
            "proxy": pack("proxy", proxy),
        },
    }


def update_settings_from_payload(
    store: SettingsStore,
    data: dict[str, Any],
) -> dict[str, Any]:
    mapping: dict[str, str | None] = {}
    for key in SETTING_KEYS:
        if key not in data:
            continue
        raw = data[key]
        if raw is None:
            continue
        mapping[key] = str(raw).strip() if not isinstance(raw, bool) else ("1" if raw else "0")

    if mapping:
        store.set_many(mapping)

    if "admin_username" in data and data["admin_username"] is not None:
        name = str(data["admin_username"]).strip() or DEFAULT_ADMIN_USERNAME
        store.set(META_ADMIN_USERNAME, name)

    new_password = data.get("admin_password") or data.get("new_password")
    if new_password is not None and str(new_password).strip() != "":
        from .auth import hash_password

        store.set(META_ADMIN_PASSWORD_HASH, hash_password(str(new_password)))

    apply_effective_proxy(store)
    return settings_public_view(store)
