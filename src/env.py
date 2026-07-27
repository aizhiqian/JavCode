from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def load_project_env(dotenv_path: Path | str | None = None, *, override: bool = False) -> bool:
    from dotenv import load_dotenv

    path = Path(dotenv_path) if dotenv_path is not None else ROOT / ".env"
    loaded = bool(load_dotenv(path, override=override))
    apply_proxy_from_env()
    return loaded


def apply_proxy_from_env() -> dict[str, str]:
    single = (
        os.environ.get("JAVCODE_PROXY")
        or os.environ.get("JAVCODE_ALL_PROXY")
        or os.environ.get("ALL_PROXY")
        or os.environ.get("all_proxy")
        or ""
    ).strip()
    http = (
        os.environ.get("JAVCODE_HTTP_PROXY")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or single
        or ""
    ).strip()
    https = (
        os.environ.get("JAVCODE_HTTPS_PROXY")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or single
        or ""
    ).strip()

    jav_http = (os.environ.get("JAVCODE_HTTP_PROXY") or "").strip()
    jav_https = (os.environ.get("JAVCODE_HTTPS_PROXY") or "").strip()
    jav_all = (
        os.environ.get("JAVCODE_PROXY") or os.environ.get("JAVCODE_ALL_PROXY") or ""
    ).strip()
    if jav_all or jav_http or jav_https:
        http = jav_http or jav_all or http
        https = jav_https or jav_all or https
        single = jav_all or single

    if http:
        os.environ["HTTP_PROXY"] = http
        os.environ["http_proxy"] = http
    if https:
        os.environ["HTTPS_PROXY"] = https
        os.environ["https_proxy"] = https
    if single or (http and https and http == https):
        all_val = single or http
        if all_val:
            os.environ["ALL_PROXY"] = all_val
            os.environ["all_proxy"] = all_val

    proxies: dict[str, str] = {}
    if http:
        proxies["http"] = http
    if https:
        proxies["https"] = https
    return proxies


def proxy_public_status() -> dict[str, Any]:
    proxies = apply_proxy_from_env()
    enabled = bool(proxies)

    def _redact(url: str) -> str:
        if "@" not in url:
            return url
        try:
            scheme, rest = url.split("://", 1)
            if "@" in rest:
                rest = rest.split("@", 1)[1]
                return f"{scheme}://***@{rest}"
        except ValueError:
            pass
        return "***"

    return {
        "enabled": enabled,
        "http": _redact(proxies["http"]) if "http" in proxies else "",
        "https": _redact(proxies["https"]) if "https" in proxies else "",
    }


def parse_bool(value: Any, *, default: bool | None = None) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    s = str(value).strip().lower()
    if s == "":
        return default
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default
