from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import MovieEntry
from .normalize import normalize_code
from .parsers import normalize_cover_url


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_labels(items: list[Any] | None) -> list[str]:
    out: list[str] = []
    for raw in items or []:
        lab = str(raw).strip()
        if lab and lab not in out:
            out.append(lab)
    return out


class CollectionStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS movies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL DEFAULT '',
                    title_original TEXT NOT NULL DEFAULT '',
                    cover_url TEXT NOT NULL DEFAULT '',
                    release_date TEXT NOT NULL DEFAULT '',
                    duration_minutes INTEGER,
                    studio TEXT NOT NULL DEFAULT '',
                    director TEXT NOT NULL DEFAULT '',
                    series TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    score REAL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    categories_json TEXT NOT NULL DEFAULT '[]',
                    actresses_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_movies_code ON movies(code);
                """
            )

    def upsert(self, entry: MovieEntry) -> MovieEntry:
        code = normalize_code(entry.code)
        if not code:
            raise ValueError("code required")
        now = _utc_now()
        payload = (
            code,
            entry.title or "",
            entry.title_original or "",
            entry.cover_url or "",
            entry.release_date or "",
            entry.duration_minutes,
            entry.studio or "",
            entry.director or "",
            entry.series or "",
            entry.source or "",
            entry.source_url or "",
            entry.score,
            json.dumps(entry.tags or [], ensure_ascii=False),
            json.dumps(entry.categories or [], ensure_ascii=False),
            json.dumps([a.to_dict() for a in entry.actresses], ensure_ascii=False),
            now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO movies (
                    code, title, title_original, cover_url, release_date,
                    duration_minutes, studio, director, series, source, source_url,
                    score, tags_json, categories_json, actresses_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    title=excluded.title,
                    title_original=excluded.title_original,
                    cover_url=excluded.cover_url,
                    release_date=excluded.release_date,
                    duration_minutes=excluded.duration_minutes,
                    studio=excluded.studio,
                    director=excluded.director,
                    series=excluded.series,
                    source=excluded.source,
                    source_url=excluded.source_url,
                    score=excluded.score,
                    tags_json=excluded.tags_json,
                    categories_json=excluded.categories_json,
                    actresses_json=excluded.actresses_json
                """,
                payload,
            )
            row = conn.execute("SELECT * FROM movies WHERE code = ?", (code,)).fetchone()
        return self._row_to_entry(row)

    def get_by_code(self, code: str) -> MovieEntry | None:
        code_n = normalize_code(code)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM movies WHERE code = ?", (code_n,)).fetchone()
        return self._row_to_entry(row) if row else None

    def list_all(self) -> list[MovieEntry]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM movies ORDER BY created_at DESC, id DESC").fetchall()
        return [self._row_to_entry(r) for r in rows]

    def delete(self, code: str) -> bool:
        code_n = normalize_code(code)
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM movies WHERE code = ?", (code_n,))
            return cur.rowcount > 0

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
            changes["tags"] = _normalize_labels(tags)
        if categories is not None:
            changes["categories"] = _normalize_labels(categories)
        if not changes:
            return entry
        return self.upsert(entry.evolve(**changes))

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MovieEntry:
        data: dict[str, Any] = dict(row)
        data["tags"] = json.loads(data.pop("tags_json") or "[]")
        data["categories"] = json.loads(data.pop("categories_json") or "[]")
        data["actresses"] = json.loads(data.pop("actresses_json") or "[]")
        data["cover_url"] = normalize_cover_url(data.get("cover_url") or "")
        return MovieEntry.from_dict(data)
