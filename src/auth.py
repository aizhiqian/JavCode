from __future__ import annotations

from typing import Any

from flask import session
from werkzeug.security import check_password_hash, generate_password_hash

from .settings import DEFAULT_ADMIN_USERNAME, SettingsStore

SESSION_USER_KEY = "admin_user"


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash or password is None:
        return False
    try:
        return check_password_hash(password_hash, password)
    except (ValueError, TypeError):
        return False


def is_authenticated() -> bool:
    return bool(session.get(SESSION_USER_KEY))


def current_username() -> str:
    return str(session.get(SESSION_USER_KEY) or "")


def login_user(username: str) -> None:
    session.clear()
    session[SESSION_USER_KEY] = username
    session.permanent = True


def logout_user() -> None:
    session.clear()


def auth_status(store: SettingsStore) -> dict[str, Any]:
    configured = store.is_admin_configured()
    return {
        "configured": configured,
        "authenticated": bool(is_authenticated()) and configured,
        "username": store.admin_username() if configured else "",
        "session_user": current_username() if is_authenticated() else "",
    }


def try_login(store: SettingsStore, username: str, password: str) -> tuple[bool, str]:
    if not store.is_admin_configured():
        return False, "尚未初始化管理员，请先完成设置"
    want = store.admin_username()
    if (username or "").strip() != want:
        return False, "用户名或密码错误"
    if not verify_password(store.admin_password_hash(), password or ""):
        return False, "用户名或密码错误"
    login_user(want)
    return True, ""


def try_setup(
    store: SettingsStore,
    username: str,
    password: str,
) -> tuple[bool, str]:
    if store.is_admin_configured():
        return False, "管理员已初始化"
    name = (username or DEFAULT_ADMIN_USERNAME).strip() or DEFAULT_ADMIN_USERNAME
    pwd = password or ""
    if len(pwd) < 4:
        return False, "密码至少 4 位"
    store.set_admin(name, hash_password(pwd))
    login_user(name)
    return True, ""
