from __future__ import annotations

import re


def normalize_cover_url(url: str) -> str:
    """Upgrade known thumbnail URLs to full covers; leave others intact.

    Canonical owner of cover URL shape. Call at persistence (store write) and
    domain normalize (translate); parsers may pre-normalize for convenience.
    Store also upgrades on read for legacy thumb rows.
    """
    if not url:
        return ""
    u = str(url).strip()
    if u.startswith("//"):
        u = "https:" + u
    if "jdbstatic.com" in u and "/thumbs/" in u:
        u = u.replace("/thumbs/", "/covers/")
    u = re.sub(r"ps\.(jpe?g)(\?.*)?$", r"pl.\1\2", u, flags=re.IGNORECASE)
    u = re.sub(r"_s\.(jpe?g)(\?.*)?$", r"_b.\1\2", u, flags=re.IGNORECASE)
    return u
