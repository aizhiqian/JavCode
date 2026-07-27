from __future__ import annotations

import re

_CODE_RE = re.compile(r"([A-Za-z]{2,10})\s*[-_]?\s*(\d{2,5})", re.IGNORECASE)


def normalize_code(raw: str) -> str:
    if not raw:
        return ""
    s = str(raw).strip().upper().replace("_", "-")
    m = _CODE_RE.search(s)
    if not m:
        return s.replace(" ", "")
    return f"{m.group(1).upper()}-{m.group(2)}"
