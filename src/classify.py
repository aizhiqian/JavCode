from __future__ import annotations

from .labels import dedupe_labels
from .models import MovieEntry

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


def derive_rule_labels(entry: MovieEntry) -> tuple[list[str], list[str]]:
    extra_tags: list[str] = []
    extra_categories: list[str] = []

    pref = _prefix(entry.code)
    if pref in CODE_PREFIX_LABEL:
        extra_categories.append(CODE_PREFIX_LABEL[pref])

    studio_key = (entry.studio or "").strip()
    if studio_key in STUDIO_CATEGORY:
        extra_categories.append(STUDIO_CATEGORY[studio_key])
    elif studio_key:
        extra_categories.append(studio_key)

    females = [a for a in entry.actresses if a.gender != "male"]
    if len(females) >= 2:
        for lab in ("多女优", "共演"):
            extra_tags.append(lab)
            extra_categories.append(lab)
    elif len(females) == 1:
        extra_tags.append("单体女优")
        extra_categories.append("单体女优")

    if entry.duration_minutes:
        if entry.duration_minutes >= 180:
            extra_tags.append("长篇")
            extra_categories.append("长篇")
        elif entry.duration_minutes <= 60:
            extra_tags.append("短片")
            extra_categories.append("短片")

    if entry.series:
        extra_tags.append("系列作品")
        extra_categories.append("系列作品")

    if entry.release_date and len(entry.release_date) >= 4:
        year = entry.release_date[:4]
        if year.isdigit():
            extra_categories.append(f"{year}年")

    tags = dedupe_labels(list(entry.tags) + extra_tags, simplify=True)
    categories = dedupe_labels(list(entry.categories) + extra_categories, simplify=True)
    return tags, categories


def classify(entry: MovieEntry) -> MovieEntry:
    tags, categories = derive_rule_labels(entry)
    return entry.evolve(tags=tags, categories=categories)
