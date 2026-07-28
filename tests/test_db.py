from __future__ import annotations

import json
import os
import sqlite3

import pytest

from src.db import (
    MOVIE_COLUMNS,
    MOVIE_UPDATE_COLS,
    MOVIE_WRITE_COLS,
    Database,
    _default_ssl_mode,
    _mysql_decl,
    _schema_statements,
    open_database,
    parse_db_location,
    resolve_db_location,
)
from src.models import Actress, MovieEntry
from src.settings import SettingsStore
from src.store import CollectionStore


def test_parse_sqlite_plain_path(tmp_path):
    cfg = parse_db_location(tmp_path / "a.db")
    assert cfg.backend == "sqlite"
    assert cfg.path == tmp_path / "a.db"


def test_parse_sqlite_url(tmp_path):
    cfg = parse_db_location(f"sqlite:///{tmp_path / 'b.db'}")
    assert cfg.backend == "sqlite"
    assert cfg.path == tmp_path / "b.db"


def test_parse_mysql_url():
    cfg = parse_db_location("mysql://alice:s3cret@db.example:3307/javcode?ssl=disable")
    assert cfg.backend == "mysql"
    assert cfg.user == "alice"
    assert cfg.password == "s3cret"
    assert cfg.host == "db.example"
    assert cfg.port == 3307
    assert cfg.database == "javcode"
    assert cfg.query == {"ssl": "disable"}
    assert "***" in cfg.display()
    assert "s3cret" not in cfg.display()


def test_parse_postgres_url_aliases():
    for url in (
        "postgresql://u:p@localhost/mydb",
        "postgres://u:p@localhost/mydb",
    ):
        cfg = parse_db_location(url)
        assert cfg.backend == "postgresql"
        assert cfg.database == "mydb"
        assert cfg.effective_port == 5432


def test_parse_rejects_unknown_scheme():
    with pytest.raises(ValueError, match="unsupported"):
        parse_db_location("redis://localhost/0")


def test_parse_server_url_requires_database():
    with pytest.raises(ValueError, match="database name"):
        parse_db_location("mysql://u:p@localhost")


def test_resolve_db_location_priority(tmp_path, monkeypatch):
    monkeypatch.delenv("JAVCODE_DB", raising=False)
    assert "collection.db" in resolve_db_location(None)

    monkeypatch.setenv("JAVCODE_DB", "mysql://u:p@h/db")
    assert resolve_db_location(None) == "mysql://u:p@h/db"
    assert resolve_db_location(tmp_path / "x.db") == str(tmp_path / "x.db")


def test_default_ssl_mode_local_vs_remote():
    for host in ("localhost", "127.0.0.1", "::1", "mysql", "postgres", "db"):
        assert _default_ssl_mode(host) == "disable"
    assert _default_ssl_mode("db.aiven.example") == "require"
    assert _default_ssl_mode("prod-mysql.internal") == "require"


def test_movie_column_lists_are_consistent():
    assert tuple(c.name for c in MOVIE_COLUMNS) == MOVIE_WRITE_COLS
    assert "code" in MOVIE_WRITE_COLS
    assert "created_at" in MOVIE_WRITE_COLS
    assert "code" not in MOVIE_UPDATE_COLS
    assert "created_at" not in MOVIE_UPDATE_COLS
    assert set(MOVIE_UPDATE_COLS) < set(MOVIE_WRITE_COLS)
    for backend in ("sqlite", "mysql", "postgresql"):
        ddl = "\n".join(_schema_statements(backend))
        for name in MOVIE_WRITE_COLS:
            assert name in ddl
        # app_meta keeps historical column name `key` (quoted on MySQL).
        assert "key" in ddl
        assert "meta_key" not in ddl


def test_mysql_decl_strips_text_defaults():
    """MySQL errno 1101: TEXT/BLOB/JSON cannot use non-expression DEFAULT."""
    assert _mysql_decl("TEXT NOT NULL DEFAULT ''") == "TEXT NOT NULL"
    assert _mysql_decl("TEXT NOT NULL DEFAULT '[]'") == "TEXT NOT NULL"
    assert _mysql_decl("TEXT NOT NULL UNIQUE") == "VARCHAR(64) NOT NULL"
    assert _mysql_decl("TEXT NOT NULL") == "VARCHAR(64) NOT NULL"
    assert _mysql_decl("INTEGER") == "INT"
    assert _mysql_decl("REAL") == "DOUBLE"

    mysql_ddl = "\n".join(_schema_statements("mysql"))
    assert "title TEXT NOT NULL" in mysql_ddl
    assert "DEFAULT ''" not in mysql_ddl
    assert "DEFAULT '[]'" not in mysql_ddl
    # code stays short VARCHAR; created_at has no DEFAULT in source decl.
    assert "code VARCHAR(64) NOT NULL" in mysql_ddl


def test_set_many_is_atomic(tmp_path):
    db = open_database(tmp_path / "atomic.db")
    settings = SettingsStore(db)
    settings.set("keep", "1")

    original_upsert = db.upsert_meta
    calls = {"n": 0}

    def flaky(key: str, value: str) -> None:
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("boom")
        original_upsert(key, value)

    db.upsert_meta = flaky  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="boom"):
        settings.set_many({"a": "x", "b": "y", "c": "z"})

    # First write in the failed batch must not stick; pre-existing key remains.
    assert settings.get("a") == ""
    assert settings.get("b") == ""
    assert settings.get("keep") == "1"


def test_sqlite_store_and_settings_share_schema(tmp_path):
    db = open_database(tmp_path / "shared.db")
    store = CollectionStore(db)
    settings = SettingsStore(db)

    entry = store.upsert(
        MovieEntry(
            code="SSIS-001",
            title="标题",
            tags=["美乳"],
            actresses=[Actress(name="葵")],
            cover_url="https://c0.jdbstatic.com/thumbs/zy/ZY5eq.jpg",
        )
    )
    assert entry.code == "SSIS-001"
    assert "/covers/" in entry.cover_url

    settings.set("ai_model", "test-model")
    assert settings.get("ai_model") == "test-model"
    settings.set_many({"ai_model": "", "proxy": "http://127.0.0.1:1"})
    assert settings.get("ai_model") == ""
    assert settings.get("proxy") == "http://127.0.0.1:1"
    many = settings.get_many(("proxy", "ai_model", "missing"))
    assert many["proxy"] == "http://127.0.0.1:1"
    assert "ai_model" not in many

    got = store.get_by_code("SSIS-001")
    assert got is not None
    assert got.tags == ["美乳"]
    assert store.delete("SSIS-001") is True
    assert store.get_by_code("SSIS-001") is None


def test_sqlite_upsert_preserves_json_unicode(tmp_path):
    store = CollectionStore(tmp_path / "u.db")
    store.upsert(
        MovieEntry(
            code="ABC-123",
            title="中文",
            actresses=[Actress(name="女優", name_original="女優")],
            tags=["标签"],
            categories=["分类"],
        )
    )
    row_entry = store.get_by_code("ABC-123")
    assert row_entry is not None
    assert row_entry.title == "中文"
    row = store.db.fetchone(
        "SELECT tags_json, actresses_json FROM movies WHERE code = ?",
        ("ABC-123",),
    )
    assert row is not None
    assert json.loads(row["tags_json"]) == ["标签"]
    assert json.loads(row["actresses_json"])[0]["name"] == "女優"


def test_store_accepts_path_or_database(tmp_path):
    path = tmp_path / "p.db"
    a = CollectionStore(path)
    a.upsert(MovieEntry(code="X-1", title="a"))
    b = CollectionStore(open_database(path))
    assert b.get_by_code("X-1") is not None


def test_existing_sqlite_app_meta_key_column_upgrades(tmp_path):
    """Pre-multi-backend DBs used app_meta(key, value); must keep working."""
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE movies (
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
        CREATE TABLE app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
        INSERT INTO app_meta (key, value) VALUES
            ('secret_key', 'legacy-secret'),
            ('ai_model', 'legacy-model');
        INSERT INTO movies (
            code, title, title_original, cover_url, release_date,
            duration_minutes, studio, director, series, source, source_url,
            score, tags_json, categories_json, actresses_json, created_at
        ) VALUES (
            'LEG-001', '旧片', '', '', '',
            NULL, '', '', '', '', '',
            NULL, '[]', '[]', '[]', '2020-01-01T00:00:00Z'
        );
        """
    )
    conn.commit()
    conn.close()

    db = open_database(path)
    settings = SettingsStore(db)
    store = CollectionStore(db)

    assert settings.get("secret_key") == "legacy-secret"
    assert settings.get("ai_model") == "legacy-model"
    settings.set("proxy", "http://127.0.0.1:9")
    assert settings.get("proxy") == "http://127.0.0.1:9"

    got = store.get_by_code("LEG-001")
    assert got is not None
    assert got.title == "旧片"
    store.upsert(got.evolve(title="旧片更新"))
    assert store.get_by_code("LEG-001").title == "旧片更新"


def test_mysql_ident_quotes_key():
    cfg = parse_db_location("mysql://u:p@mysql/db")
    # Don't connect — only need ident() which is backend-local.
    # Build a bare instance without init by checking SQL helpers via open on sqlite
    # is wrong; use a stub path that won't be used for ident.
    db = object.__new__(Database)
    db.config = cfg
    assert db.ident("key") == "`key`"
    assert db.backend == "mysql"


def _mysql_url_from_env() -> str | None:
    raw = (os.environ.get("JAVCODE_DB") or "").strip()
    if raw.startswith("mysql://") or raw.startswith("mariadb://"):
        return raw
    return None


@pytest.fixture(scope="module")
def mysql_db():
    """Live MySQL from JAVCODE_DB (loaded via conftest / dotenv if present)."""
    from src.env import load_project_env

    load_project_env()
    url = _mysql_url_from_env()
    if not url:
        pytest.skip("JAVCODE_DB is not a mysql:// URL")
    try:
        db = open_database(url)
    except Exception as exc:
        pytest.skip(f"MySQL unavailable: {type(exc).__name__}")
    yield db
    try:
        db.execute("DELETE FROM movies WHERE code LIKE ?", ("JQMYSQL-%",))
        db.execute(
            f"DELETE FROM app_meta WHERE {db.ident('key')} LIKE ?",
            ("__test_javcode_%",),
        )
        db.close()
    except Exception:
        pass


def test_mysql_roundtrip_movie_and_settings(mysql_db: Database):
    store = CollectionStore(mysql_db)
    settings = SettingsStore(mysql_db)
    code = "JQMYSQL-99991"
    meta_key = "__test_javcode_ai_model"

    store.delete(code)
    settings.delete(meta_key)

    entry = store.upsert(
        MovieEntry(
            code=code,
            title="MySQL 测试",
            tags=["标签A"],
            actresses=[Actress(name="测试女优")],
            cover_url="https://c0.jdbstatic.com/thumbs/zy/ZY5eq.jpg",
            source="test",
        )
    )
    assert entry.code == code
    got = store.get_by_code(code)
    assert got is not None
    assert got.title == "MySQL 测试"
    assert got.tags == ["标签A"]
    assert "/covers/" in (got.cover_url or "")

    store.upsert(got.evolve(title="MySQL 更新"))
    assert store.get_by_code(code).title == "MySQL 更新"

    settings.set_many({meta_key: "grok-test", "__test_javcode_proxy": "http://x"})
    assert settings.get(meta_key) == "grok-test"
    assert settings.get("__test_javcode_proxy") == "http://x"
    assert settings.get_many((meta_key,))[meta_key] == "grok-test"
    settings.set_many({meta_key: "", "__test_javcode_proxy": ""})
    assert settings.get(meta_key) == ""
    assert settings.get("__test_javcode_proxy") == ""

    assert store.delete(code) is True
    assert store.get_by_code(code) is None
