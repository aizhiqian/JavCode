from __future__ import annotations

import zhconv

from .models import Actress, MovieEntry


def to_simplified(text: str) -> str:
    if not text:
        return ""
    return zhconv.convert(text.strip(), "zh-cn")


def _dedupe_simplified(items: list[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        lab = to_simplified(item) if item else ""
        if lab and lab not in out:
            out.append(lab)
    return out


def normalize_entry(entry: MovieEntry) -> MovieEntry:
    actresses = [
        Actress(
            name=to_simplified(a.name_original or a.name) or (a.name_original or a.name),
            name_original=a.name_original or a.name,
            gender=a.gender,
        )
        for a in entry.actresses
    ]
    title_src = entry.title or entry.title_original
    return entry.evolve(
        title=to_simplified(title_src) or title_src,
        title_original=entry.title_original or entry.title,
        actresses=actresses,
        tags=_dedupe_simplified(list(entry.tags)),
        categories=_dedupe_simplified(list(entry.categories)),
        studio=to_simplified(entry.studio) if entry.studio else "",
        director=to_simplified(entry.director) if entry.director else "",
        series=to_simplified(entry.series) if entry.series else "",
    )


def ensure_zh_fields(entry: MovieEntry) -> bool:
    return bool(entry.title) and bool(entry.actresses) and bool(entry.tags or entry.categories)
