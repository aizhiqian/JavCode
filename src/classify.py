from __future__ import annotations

from .models import MovieEntry
from .translate import to_simplified

STUDIO_CATEGORY: dict[str, str] = {
    "S1 NO.1 STYLE": "S1作品",
    "SOD Create": "SOD作品",
    "SOD star": "SOD作品",
    "MOODYZ": "MOODYZ作品",
    "IDEA POCKET": "IDEA POCKET作品",
    "PREMIUM": "PREMIUM作品",
    "E-BODY": "E-BODY作品",
}

CODE_PREFIX_LABEL: dict[str, str] = {
    "SSIS": "S1",
    "SSNI": "S1",
    "OFJE": "S1精选",
    "STARS": "SOD star",
    "START": "SOD star",
    "MIDE": "MOODYZ",
    "MIDV": "MOODYZ",
    "IPX": "IDEA POCKET",
    "IPZZ": "IDEA POCKET",
    "PRED": "PREMIUM",
    "EYAN": "E-BODY",
    "JUL": "Madonna",
    "JUY": "Madonna",
    "ADN": "Attackers",
    "SAME": "Attackers",
}


def _prefix(code: str) -> str:
    if not code or "-" not in code:
        return (code or "").upper()
    return code.split("-", 1)[0].upper()


def _dedupe_append(bucket: list[str], label: str) -> None:
    lab = to_simplified(label)
    if lab and lab not in bucket:
        bucket.append(lab)


def derive_rule_labels(entry: MovieEntry) -> tuple[list[str], list[str]]:
    tags = list(entry.tags)
    categories = list(entry.categories)

    pref = _prefix(entry.code)
    if pref in CODE_PREFIX_LABEL:
        _dedupe_append(categories, CODE_PREFIX_LABEL[pref])

    studio_key = (entry.studio or "").strip()
    if studio_key in STUDIO_CATEGORY:
        _dedupe_append(categories, STUDIO_CATEGORY[studio_key])
    elif studio_key:
        _dedupe_append(categories, studio_key)

    females = [a for a in entry.actresses if a.gender != "male"]
    if len(females) >= 2:
        for lab in ("多女优", "共演"):
            _dedupe_append(tags, lab)
            _dedupe_append(categories, lab)
    elif len(females) == 1:
        _dedupe_append(tags, "单体女优")
        _dedupe_append(categories, "单体女优")

    if entry.duration_minutes:
        if entry.duration_minutes >= 180:
            _dedupe_append(tags, "长篇")
            _dedupe_append(categories, "长篇")
        elif entry.duration_minutes <= 60:
            _dedupe_append(tags, "短片")
            _dedupe_append(categories, "短片")

    if entry.series:
        _dedupe_append(tags, "系列作品")
        _dedupe_append(categories, "系列作品")

    if entry.release_date and len(entry.release_date) >= 4:
        year = entry.release_date[:4]
        if year.isdigit():
            _dedupe_append(categories, f"{year}年")

    return tags, categories


def classify(entry: MovieEntry) -> MovieEntry:
    tags, categories = derive_rule_labels(entry)
    return entry.evolve(tags=tags, categories=categories)
