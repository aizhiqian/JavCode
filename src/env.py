from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def load_project_env(dotenv_path: Path | str | None = None, *, override: bool = False) -> bool:
    """Load project .env into process env. Does not touch proxy or other app settings."""
    from dotenv import load_dotenv

    path = Path(dotenv_path) if dotenv_path is not None else ROOT / ".env"
    return bool(load_dotenv(path, override=override))


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
