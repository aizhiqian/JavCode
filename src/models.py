from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

from .normalize import normalize_code


@dataclass
class Actress:
    name: str
    name_original: str = ""
    gender: str = "female"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Actress":
        return cls(
            name=data.get("name", ""),
            name_original=data.get("name_original", "") or data.get("name", ""),
            gender=data.get("gender", "female"),
        )


@dataclass
class MovieEntry:
    code: str
    title: str = ""
    title_original: str = ""
    actresses: list[Actress] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    cover_url: str = ""
    release_date: str = ""
    duration_minutes: int | None = None
    studio: str = ""
    director: str = ""
    series: str = ""
    source: str = ""
    source_url: str = ""
    score: float | None = None
    id: int | None = None
    created_at: str = ""

    def actress_names(self) -> list[str]:
        return [a.name for a in self.actresses if a.gender != "male"]

    def evolve(self, **changes: Any) -> "MovieEntry":
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MovieEntry":
        actresses: list[Actress] = []
        for item in data.get("actresses") or []:
            if isinstance(item, str):
                actresses.append(Actress(name=item, name_original=item))
            elif isinstance(item, dict):
                actresses.append(Actress.from_dict(item))
        raw_code = str(data.get("code", "") or "")
        return cls(
            code=normalize_code(raw_code) or raw_code.upper().strip(),
            title=data.get("title") or "",
            title_original=data.get("title_original") or "",
            actresses=actresses,
            tags=list(data.get("tags") or []),
            categories=list(data.get("categories") or []),
            cover_url=data.get("cover_url") or "",
            release_date=data.get("release_date") or "",
            duration_minutes=data.get("duration_minutes"),
            studio=data.get("studio") or "",
            director=data.get("director") or "",
            series=data.get("series") or "",
            source=data.get("source") or "",
            source_url=data.get("source_url") or "",
            score=data.get("score"),
            id=data.get("id"),
            created_at=data.get("created_at") or "",
        )
