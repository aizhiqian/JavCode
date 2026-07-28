from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import Database, open_database
from .labels import dedupe_labels
from .media import normalize_cover_url
from .models import MovieEntry
from .normalize import normalize_code
from .relationships import actress_index
from .search import label_index, search_library


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CollectionStore:
    """Movie collection persistence (SQLite / MySQL / PostgreSQL).

    Process-local library cache (single-instance assumption): list/search/index
    share one snapshot, invalidated on upsert/delete. Not coherent across
    multiple app processes writing the same remote DB.
    """

    def __init__(self, db: Database | str | Path) -> None:
        self.db = db if isinstance(db, Database) else open_database(db)
        self._cache_lock = threading.Lock()
        self._by_code: dict[str, MovieEntry] | None = None
        self._ordered: list[MovieEntry] | None = None

    def _invalidate_cache(self) -> None:
        with self._cache_lock:
            self._by_code = None
            self._ordered = None

    def _set_cache(self, ordered: list[MovieEntry]) -> None:
        self._ordered = ordered
        self._by_code = {e.code: e for e in ordered}

    def upsert(self, entry: MovieEntry) -> MovieEntry:
        code = normalize_code(entry.code)
        if not code:
            raise ValueError("code required")
        fields = {
            "code": code,
            "title": entry.title or "",
            "title_original": entry.title_original or "",
            "cover_url": normalize_cover_url(entry.cover_url or ""),
            "release_date": entry.release_date or "",
            "duration_minutes": entry.duration_minutes,
            "studio": entry.studio or "",
            "director": entry.director or "",
            "series": entry.series or "",
            "source": entry.source or "",
            "source_url": entry.source_url or "",
            "score": entry.score,
            "tags_json": json.dumps(entry.tags or [], ensure_ascii=False),
            "categories_json": json.dumps(entry.categories or [], ensure_ascii=False),
            "actresses_json": json.dumps(
                [a.to_dict() for a in entry.actresses], ensure_ascii=False
            ),
            "created_at": _utc_now(),
        }
        result = self._row_to_entry(self.db.upsert_movie(fields))
        self._invalidate_cache()
        return result

    def get_by_code(self, code: str) -> MovieEntry | None:
        code_n = normalize_code(code)
        with self._cache_lock:
            by_code = self._by_code
        if by_code is not None:
            return by_code.get(code_n)
        row = self.db.fetchone("SELECT * FROM movies WHERE code = ?", (code_n,))
        return self._row_to_entry(row) if row else None

    def list_all(self) -> list[MovieEntry]:
        with self._cache_lock:
            if self._ordered is not None:
                return list(self._ordered)
        rows = self.db.fetchall(
            "SELECT * FROM movies ORDER BY created_at DESC, id DESC"
        )
        entries = [self._row_to_entry(r) for r in rows]
        with self._cache_lock:
            # Another thread may have filled the cache while we queried.
            if self._ordered is not None:
                return list(self._ordered)
            self._set_cache(entries)
            return list(entries)

    def search(
        self,
        *,
        code: str | None = None,
        actress: str | None = None,
        tag: str | None = None,
        query: str | None = None,
    ) -> list[MovieEntry]:
        return search_library(
            self.list_all(),
            code=code,
            actress=actress,
            tag=tag,
            query=query,
        )

    def label_index(self) -> dict:
        return label_index(self.list_all())

    def actress_index(self) -> list[dict]:
        return actress_index(self.list_all())

    def delete(self, code: str) -> bool:
        code_n = normalize_code(code)
        ok = self.db.execute("DELETE FROM movies WHERE code = ?", (code_n,)) > 0
        if ok:
            self._invalidate_cache()
        return ok

    def update_labels(
        self,
        code: str,
        *,
        tags: list[str] | None = None,
        categories: list[str] | None = None,
    ) -> MovieEntry | None:
        entry = self.get_by_code(code)
        if entry is None:
            return None
        changes: dict[str, Any] = {}
        if tags is not None:
            changes["tags"] = dedupe_labels([str(x) for x in tags], simplify=True)
        if categories is not None:
            changes["categories"] = dedupe_labels(
                [str(x) for x in categories], simplify=True
            )
        if not changes:
            return entry
        return self.upsert(entry.evolve(**changes))

    def warm(self) -> int:
        """Load the library cache. Returns film count."""
        return len(self.list_all())

    @staticmethod
    def _row_to_entry(row: dict[str, Any]) -> MovieEntry:
        data = dict(row)
        data["tags"] = json.loads(data.pop("tags_json") or "[]")
        data["categories"] = json.loads(data.pop("categories_json") or "[]")
        data["actresses"] = json.loads(data.pop("actresses_json") or "[]")
        data["cover_url"] = normalize_cover_url(data.get("cover_url") or "")
        return MovieEntry.from_dict(data)
