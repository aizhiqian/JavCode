from __future__ import annotations

import re

from pypinyin import Style, lazy_pinyin

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
