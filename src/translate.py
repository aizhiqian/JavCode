from __future__ import annotations

from .labels import dedupe_labels, to_simplified
from .media import normalize_cover_url
from .models import Actress, MovieEntry

# to_simplified lives in labels; re-export kept for older imports.
__all__ = ["to_simplified", "normalize_entry", "ensure_zh_fields"]


def normalize_entry(entry: MovieEntry) -> MovieEntry:
    """Domain normalize: zh-simplify text fields, dedupe labels, full cover URL."""
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
        tags=dedupe_labels(list(entry.tags), simplify=True),
        categories=dedupe_labels(list(entry.categories), simplify=True),
        cover_url=normalize_cover_url(entry.cover_url or ""),
        studio=to_simplified(entry.studio) if entry.studio else "",
        director=to_simplified(entry.director) if entry.director else "",
        series=to_simplified(entry.series) if entry.series else "",
    )


def ensure_zh_fields(entry: MovieEntry) -> bool:
    return bool(entry.title) and bool(entry.actresses) and bool(entry.tags or entry.categories)
