from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .constants import DEFAULT_AI_BASE_URL, DEFAULT_AI_MODEL
from .db import Database, open_database

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


@dataclass(frozen=True)
class ResolvedValue:
    value: str
    source: str  # "settings" | "env" | "default" | "inferred"


@dataclass(frozen=True)
class AdminState:
    """In-memory admin credentials (loaded once, replaced on setup/password change)."""

    username: str
    password_hash: str

    @property
    def configured(self) -> bool:
        return bool(self.password_hash.strip())


class SettingsStore:
    """App settings / admin meta (same DB as collection; multi-backend)."""

    def __init__(self, db: Database | str | Path) -> None:
        self.db = db if isinstance(db, Database) else open_database(db)
        self._admin: AdminState | None = None
        self._secret_key: str | None = None

    def _key_col(self) -> str:
        # Historical column name `key`; MySQL needs quoting (reserved word).
        return self.db.ident("key")

    def get(self, key: str, default: str = "") -> str:
        row = self.db.fetchone(
            f"SELECT value FROM app_meta WHERE {self._key_col()} = ?",
            (key,),
        )
        if row is None:
            return default
        val = row.get("value")
        return val if val is not None else default

    def set(self, key: str, value: str) -> None:
        self.db.upsert_meta(key, value if value is not None else "")
        self._on_meta_written(key, value if value is not None else "")

    def delete(self, key: str) -> None:
        self.db.execute(
            f"DELETE FROM app_meta WHERE {self._key_col()} = ?",
            (key,),
        )
        self._on_meta_written(key, "")

    def _on_meta_written(self, key: str, value: str) -> None:
        """Keep in-memory admin/secret mirrors coherent after a meta write."""
        if key == META_SECRET_KEY:
            self._secret_key = value or None
            return
        if key not in (META_ADMIN_USERNAME, META_ADMIN_PASSWORD_HASH):
            return
        current = self._admin
        if current is None:
            # Do not invent a partial AdminState; next read reloads from DB.
            return
        if key == META_ADMIN_USERNAME:
            self._admin = AdminState(
                username=value.strip() or DEFAULT_ADMIN_USERNAME,
                password_hash=current.password_hash,
            )
        else:
            self._admin = AdminState(
                username=current.username,
                password_hash=value,
            )

    def get_many(self, keys: list[str] | tuple[str, ...]) -> dict[str, str]:
        if not keys:
            return {}
        kcol = self._key_col()
        placeholders = ", ".join(["?"] * len(keys))
        rows = self.db.fetchall(
            f"SELECT {kcol} AS meta_key, value FROM app_meta "
            f"WHERE {kcol} IN ({placeholders})",
            tuple(keys),
        )
        out: dict[str, str] = {}
        for row in rows:
            k = row.get("meta_key")
            v = row.get("value")
            if k is not None and v is not None:
                out[str(k)] = v
        return out

    def set_many(self, mapping: dict[str, str | None]) -> None:
        # Single transaction so a settings save is all-or-nothing.
        with self.db.transaction():
            for key, value in mapping.items():
                if value is None:
                    continue
                if value == "":
                    self.delete(key)
                else:
                    self.set(key, value)

    def ensure_secret_key(self) -> str:
        if self._secret_key:
            return self._secret_key
        existing = self.get(META_SECRET_KEY, "")
        if existing:
            self._secret_key = existing
            return existing
        key = secrets.token_hex(32)
        self.set(META_SECRET_KEY, key)
        return key

    def _admin_state(self) -> AdminState:
        if self._admin is not None:
            return self._admin
        meta = self.get_many((META_ADMIN_USERNAME, META_ADMIN_PASSWORD_HASH))
        state = AdminState(
            username=(
                meta.get(META_ADMIN_USERNAME, DEFAULT_ADMIN_USERNAME).strip()
                or DEFAULT_ADMIN_USERNAME
            ),
            password_hash=meta.get(META_ADMIN_PASSWORD_HASH, ""),
        )
        self._admin = state
        return state

    def is_admin_configured(self) -> bool:
        return self._admin_state().configured

    def admin_username(self) -> str:
        return self._admin_state().username

    def admin_password_hash(self) -> str:
        return self._admin_state().password_hash

    def set_admin(self, username: str, password_hash: str) -> None:
        name = (username or DEFAULT_ADMIN_USERNAME).strip() or DEFAULT_ADMIN_USERNAME
        with self.db.transaction():
            self.db.upsert_meta(META_ADMIN_USERNAME, name)
            self.db.upsert_meta(META_ADMIN_PASSWORD_HASH, password_hash)
        self._admin = AdminState(username=name, password_hash=password_hash)

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
    key: str,
    *,
    stored: Mapping[str, str] | None = None,
    store: SettingsStore | None = None,
    env_names: tuple[str, ...] = (),
    default: str = "",
) -> ResolvedValue:
    """Resolve one setting: explicit stored map → store.get → env → default.

    Prefer passing `stored` (from one get_many) when resolving many keys so a
    remote DB pays a single round-trip.
    """
    if stored is not None:
        raw = stored.get(key, "")
    elif store is not None:
        raw = store.get(key, "")
    else:
        raw = ""
    if raw is not None and str(raw).strip() != "":
        return ResolvedValue(value=str(raw), source="settings")
    for name in env_names:
        val = os.environ.get(name)
        if val is not None and str(val).strip() != "":
            return ResolvedValue(value=str(val).strip(), source="env")
    return ResolvedValue(value=default, source="default")


def _stored_settings(store: SettingsStore | None) -> dict[str, str]:
    if store is None:
        return {}
    return store.get_many(SETTING_KEYS)


def effective_ai_fields(
    store: SettingsStore | None,
    *,
    stored: Mapping[str, str] | None = None,
) -> dict[str, ResolvedValue]:
    """Resolve AI settings once. Pass ``stored`` to avoid a second get_many."""
    if stored is None:
        stored = _stored_settings(store)
    key = resolve_setting(
        "ai_api_key",
        stored=stored,
        env_names=("JAVCODE_AI_API_KEY", "XAI_API_KEY", "OPENAI_API_KEY"),
    )
    base = resolve_setting(
        "ai_base_url",
        stored=stored,
        env_names=("JAVCODE_AI_BASE_URL", "OPENAI_BASE_URL"),
        default=DEFAULT_AI_BASE_URL,
    )
    model = resolve_setting(
        "ai_model",
        stored=stored,
        env_names=("JAVCODE_AI_MODEL", "OPENAI_MODEL"),
        default=DEFAULT_AI_MODEL,
    )
    enabled = resolve_setting(
        "ai_enabled",
        stored=stored,
        env_names=("JAVCODE_AI_ENABLED",),
        default="",
    )
    timeout = resolve_setting(
        "ai_timeout",
        stored=stored,
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


def effective_proxy(
    store: SettingsStore | None,
    *,
    stored: Mapping[str, str] | None = None,
) -> ResolvedValue:
    """Proxy URL: settings override → JAVCODE_PROXY → empty (direct)."""
    if stored is None:
        stored = _stored_settings(store)
    return resolve_setting(
        "proxy",
        stored=stored,
        env_names=("JAVCODE_PROXY",),
        default="",
    )


def resolve_proxy_dict(store: SettingsStore | None = None) -> dict[str, str]:
    """Single entry for HTTP clients: settings → JAVCODE_PROXY → {} (direct)."""
    url = (effective_proxy(store).value or "").strip()
    if not url:
        return {}
    return {"http": url, "https": url}


def proxy_public_status(store: SettingsStore | None = None) -> dict[str, Any]:
    """Redacted proxy status for health / UI (via resolve_proxy_dict only)."""
    resolved = resolve_proxy_dict(store)
    url = (resolved.get("http") or resolved.get("https") or "").strip()

    def _redact(u: str) -> str:
        if "@" not in u:
            return u
        try:
            scheme, rest = u.split("://", 1)
            if "@" in rest:
                rest = rest.split("@", 1)[1]
                return f"{scheme}://***@{rest}"
        except ValueError:
            pass
        return "***"

    shown = _redact(url) if url else ""
    return {"enabled": bool(url), "http": shown, "https": shown}


def settings_public_view(store: SettingsStore) -> dict[str, Any]:
    stored = store.get_many(SETTING_KEYS)
    fields = effective_ai_fields(store, stored=stored)
    proxy = effective_proxy(store, stored=stored)

    def pack(key: str, rv: ResolvedValue) -> dict[str, Any]:
        return {
            "value": rv.value,
            "source": rv.source,
            "override": stored.get(key, ""),
        }

    enabled_rv = fields["ai_enabled"]
    if enabled_rv.value != "":
        enabled_field = pack("ai_enabled", enabled_rv)
    else:
        key_present = bool(fields["ai_api_key"].value.strip())
        enabled_field = {
            "value": "1" if key_present else "0",
            "source": "inferred",
            "override": stored.get("ai_enabled", ""),
        }

    return {
        "admin_username": store.admin_username(),
        "fields": {
            "ai_api_key": pack("ai_api_key", fields["ai_api_key"]),
            "ai_base_url": pack("ai_base_url", fields["ai_base_url"]),
            "ai_model": pack("ai_model", fields["ai_model"]),
            "ai_enabled": enabled_field,
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
        mapping[key] = (
            str(raw).strip() if not isinstance(raw, bool) else ("1" if raw else "0")
        )

    new_password = data.get("admin_password") or data.get("new_password")
    password_hash: str | None = None
    if new_password is not None and str(new_password).strip() != "":
        from .auth import hash_password

        password_hash = hash_password(str(new_password))

    admin_name: str | None = None
    if "admin_username" in data and data["admin_username"] is not None:
        admin_name = str(data["admin_username"]).strip() or DEFAULT_ADMIN_USERNAME

    if mapping or admin_name is not None or password_hash is not None:
        with store.db.transaction():
            if mapping:
                store.set_many(mapping)
            if admin_name is not None:
                store.set(META_ADMIN_USERNAME, admin_name)
            if password_hash is not None:
                store.set(META_ADMIN_PASSWORD_HASH, password_hash)

    return settings_public_view(store)
