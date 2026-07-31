from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import MovieEntry
from .pinyin_meta import name_pinyin_meta


def _female_names(entry: MovieEntry) -> list[str]:
    names: list[str] = []
    for a in entry.actresses:
        if a.gender == "male":
            continue
        name = (a.name or a.name_original or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def actress_index(entries: Iterable[MovieEntry]) -> list[dict]:
    films: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        for name in _female_names(entry):
            if entry.code not in films[name]:
                films[name].append(entry.code)

    result = []
    for name, codes in sorted(films.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        result.append(
            {
                "name": name,
                "codes": codes,
                "film_count": len(codes),
                **name_pinyin_meta(name),
            }
        )
    return result
