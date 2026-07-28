from __future__ import annotations

from typing import Iterable

import zhconv


def to_simplified(text: str) -> str:
    if not text:
        return ""
    return zhconv.convert(text.strip(), "zh-cn")


def dedupe_labels(
    items: Iterable[str] | None,
    *,
    simplify: bool = True,
    limit: int | None = None,
) -> list[str]:
    """Strip, optional zh-simplify, de-duplicate; preserve first-seen order."""
    out: list[str] = []
    for raw in items or []:
        text = str(raw).strip() if raw is not None else ""
        if not text:
            continue
        lab = to_simplified(text) if simplify else text
        if lab and lab not in out:
            out.append(lab)
        if limit is not None and len(out) >= limit:
            break
    return out


def merge_labels(
    base: list[str] | None,
    extra: list[str] | None,
    *,
    limit: int | None = 24,
) -> list[str]:
    return dedupe_labels(list(base or []) + list(extra or []), simplify=True, limit=limit)
