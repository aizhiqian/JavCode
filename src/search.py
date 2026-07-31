from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import MovieEntry
from .normalize import normalize_code
from .pinyin_meta import name_pinyin_meta


def _hay_actress(entry: MovieEntry) -> str:
    parts: list[str] = []
    for a in entry.actresses:
        parts.append(a.name or "")
        parts.append(a.name_original or "")
    return " ".join(parts).lower()


def _hay_labels(entry: MovieEntry) -> str:
    return " ".join(list(entry.tags or []) + list(entry.categories or [])).lower()


def search_library(
    entries: list[MovieEntry],
    *,
    code: str | None = None,
    actress: str | None = None,
    tag: str | None = None,
    query: str | None = None,
) -> list[MovieEntry]:
    results = list(entries)

    if code:
        want = normalize_code(code)
        results = [
            e
            for e in results
            if normalize_code(e.code) == want or want in normalize_code(e.code)
        ]

    if actress:
        needle = actress.strip().lower()
        results = [e for e in results if needle in _hay_actress(e)]

    if tag:
        needle = tag.strip().lower()
        results = [e for e in results if needle in _hay_labels(e)]

    if query:
        q = query.strip().lower()
        q_code = normalize_code(query).lower()

        def match(e: MovieEntry) -> bool:
            if q_code and q_code in normalize_code(e.code).lower():
                return True
            if q in (e.title or "").lower():
                return True
            if q in (e.title_original or "").lower():
                return True
            if q in _hay_actress(e):
                return True
            if q in _hay_labels(e):
                return True
            if q in (e.studio or "").lower():
                return True
            return False

        results = [e for e in results if match(e)]

    return results


def _count_labels(entries: Iterable[MovieEntry], attr: str) -> list[dict]:
    films: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        for label in getattr(entry, attr, None) or []:
            name = str(label).strip()
            if not name:
                continue
            if entry.code not in films[name]:
                films[name].append(entry.code)
    result = []
    for name, codes in sorted(films.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        result.append(
            {
                "name": name,
                "count": len(codes),
                "codes": codes,
                **name_pinyin_meta(name),
            }
        )
    return result


def label_index(entries: Iterable[MovieEntry]) -> dict:
    entry_list = list(entries)
    return {
        "categories": _count_labels(entry_list, "categories"),
        "tags": _count_labels(entry_list, "tags"),
    }
