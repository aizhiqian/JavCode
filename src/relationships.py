from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from pypinyin import Style, lazy_pinyin

from .models import MovieEntry

_LATIN_INITIAL = re.compile(r"[A-Za-z]")


def name_pinyin_meta(name: str) -> dict[str, str]:
    raw = (name or "").strip()
    if not raw:
        return {"pinyin": "", "pinyin_key": "", "initial": "#"}
    syllables = lazy_pinyin(raw, style=Style.NORMAL, errors="default")
    parts: list[str] = []
    for s in syllables:
        token = str(s).strip()
        if token:
            parts.append(token)
    key_chars: list[str] = []
    for s in parts:
        for ch in s.lower():
            if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
                key_chars.append(ch)
    pinyin_key = "".join(key_chars)
    initial = "#"
    for ch in pinyin_key:
        if "a" <= ch <= "z":
            initial = ch.upper()
            break
    if initial == "#":
        m = _LATIN_INITIAL.search(raw)
        if m:
            initial = m.group(0).upper()
    return {
        "pinyin": " ".join(parts),
        "pinyin_key": pinyin_key,
        "initial": initial,
    }


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
        meta = name_pinyin_meta(name)
        result.append(
            {
                "name": name,
                "codes": codes,
                "film_count": len(codes),
                "pinyin": meta["pinyin"],
                "pinyin_key": meta["pinyin_key"],
                "initial": meta["initial"],
            }
        )
    return result
