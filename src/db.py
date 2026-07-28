"""Multi-backend database layer: SQLite, MySQL, PostgreSQL.

JAVCODE_DB / open_database(location) accepts:
  - plain path or sqlite:///path          → SQLite (default)
  - mysql://user:pass@host:3306/dbname
  - postgresql://user:pass@host:5432/dbname  (also postgres://)

Application SQL always uses `?` placeholders (no literal `?` or `%` in SQL
text). Callers use execute/fetch* and optionally transaction() for multi-statement
atomicity.

TLS defaults for server backends:
  - loopback / compose service hosts → disabled (local docker works out of the box)
  - other hosts → require (managed providers)
  - override with ?ssl= / ?sslmode=
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Literal, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlparse

Backend = Literal["sqlite", "mysql", "postgresql"]

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = ROOT / "data" / "collection.db"

_SCHEME_MAP: dict[str, Backend] = {
    "sqlite": "sqlite",
    "mysql": "mysql",
    "mariadb": "mysql",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "pgsql": "postgresql",
}

_FALSEY = frozenset({"0", "false", "disable", "disabled", "off", "no"})
_TRUTHY = frozenset({"1", "true", "require", "on", "yes"})

# Hosts where TLS is off by default (compose service names + loopback).
_LOCAL_TLS_HOSTS = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "mysql",
        "mariadb",
        "postgres",
        "postgresql",
        "db",
    }
)


@dataclass(frozen=True)
class MovieColumn:
    """Movie column: one generic SQL declaration + upsert participation.

    Declarations are SQLite/PostgreSQL oriented. MySQL gets a light mechanical
    mapping (INTEGER→INT, REAL→DOUBLE, drop inline UNIQUE — table-level instead).
    """

    name: str
    decl: str = "TEXT NOT NULL DEFAULT ''"
    on_conflict_update: bool = True


# Single source of truth for movie field names, DDL, and upsert column sets.
MOVIE_COLUMNS: tuple[MovieColumn, ...] = (
    MovieColumn("code", "TEXT NOT NULL UNIQUE", on_conflict_update=False),
    MovieColumn("title"),
    MovieColumn("title_original"),
    MovieColumn("cover_url"),
    MovieColumn("release_date"),
    MovieColumn("duration_minutes", "INTEGER"),
    MovieColumn("studio"),
    MovieColumn("director"),
    MovieColumn("series"),
    MovieColumn("source"),
    MovieColumn("source_url"),
    MovieColumn("score", "REAL"),
    MovieColumn("tags_json", "TEXT NOT NULL DEFAULT '[]'"),
    MovieColumn("categories_json", "TEXT NOT NULL DEFAULT '[]'"),
    MovieColumn("actresses_json", "TEXT NOT NULL DEFAULT '[]'"),
    MovieColumn("created_at", "TEXT NOT NULL", on_conflict_update=False),
)

MOVIE_WRITE_COLS: tuple[str, ...] = tuple(c.name for c in MOVIE_COLUMNS)
MOVIE_UPDATE_COLS: tuple[str, ...] = tuple(
    c.name for c in MOVIE_COLUMNS if c.on_conflict_update
)


@dataclass(frozen=True)
class DbConfig:
    backend: Backend
    path: Path | None = None
    host: str = "127.0.0.1"
    port: int = 0
    user: str = ""
    password: str = ""
    database: str = ""
    location: str = ""
    query: Mapping[str, str] | None = None

    @property
    def effective_port(self) -> int:
        if self.port:
            return self.port
        if self.backend == "mysql":
            return 3306
        if self.backend == "postgresql":
            return 5432
        return 0

    def display(self) -> str:
        if self.backend == "sqlite":
            return f"sqlite:///{self.path}"
        auth = self.user or ""
        if self.password:
            auth = f"{auth}:***"
        if auth:
            auth = f"{auth}@"
        return (
            f"{self.backend}://{auth}{self.host}:{self.effective_port}/{self.database}"
        )


def resolve_db_location(
    location: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    """Pick DB location: explicit arg → env JAVCODE_DB → default SQLite path."""
    if location is not None and str(location).strip() != "":
        return str(location).strip()
    environ = env if env is not None else os.environ
    from_env = (environ.get("JAVCODE_DB") or "").strip()
    if from_env:
        return from_env
    return str(DEFAULT_SQLITE_PATH)


def _query_map(raw_query: str) -> dict[str, str]:
    if not raw_query:
        return {}
    parsed = parse_qs(raw_query, keep_blank_values=True)
    return {k: (v[-1] if v else "") for k, v in parsed.items()}


def parse_db_location(location: str | Path) -> DbConfig:
    raw = str(location).strip()
    if not raw:
        raise ValueError("database location is empty")

    if "://" not in raw:
        return DbConfig(backend="sqlite", path=Path(raw), location=raw)

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    backend = _SCHEME_MAP.get(scheme)
    if backend is None:
        raise ValueError(
            f"unsupported database scheme {scheme!r}; "
            "use sqlite, mysql, or postgresql"
        )

    query = _query_map(parsed.query or "")

    if backend == "sqlite":
        path_part = raw.split("://", 1)[1].split("?", 1)[0]
        if path_part.startswith("//"):
            file_path = path_part[1:]
        elif path_part.startswith("/"):
            file_path = path_part.lstrip("/") or "."
        else:
            file_path = path_part
        return DbConfig(
            backend="sqlite",
            path=Path(unquote(file_path)),
            location=raw,
            query=query or None,
        )

    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 0
    database = unquote((parsed.path or "").lstrip("/"))
    if not database:
        raise ValueError(f"{backend} URL must include a database name")
    return DbConfig(
        backend=backend,
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        location=raw,
        query=query or None,
    )


def open_database(location: str | Path | None = None) -> "Database":
    return Database(parse_db_location(resolve_db_location(location)))


def _translate_sql(sql: str, backend: Backend) -> str:
    """Map application `?` placeholders to driver style.

    Contract: SQL must be fully parameterized — no string literals containing
    `?` or `%`. All call sites in this project follow that rule.
    """
    if backend == "sqlite":
        return sql
    out: list[str] = []
    for ch in sql:
        if ch == "?":
            out.append("%s")
        elif ch == "%":
            out.append("%%")
        else:
            out.append(ch)
    return "".join(out)


def _row_as_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    if isinstance(row, sqlite3.Row):
        return {k: row[k] for k in row.keys()}
    try:
        return dict(row)
    except Exception as exc:
        raise TypeError(f"unsupported row type: {type(row)!r}") from exc


def _ssl_flag(query: Mapping[str, str] | None, *keys: str, default: str = "") -> str:
    if not query:
        return default
    for key in keys:
        if key in query and str(query[key]).strip() != "":
            return str(query[key]).strip().lower()
    return default


def _default_ssl_mode(host: str) -> str:
    """disable on local/compose hosts; require for everything else."""
    h = (host or "").strip().lower()
    if h in _LOCAL_TLS_HOSTS or h.endswith(".local"):
        return "disable"
    return "require"


# MySQL/MariaDB reject non-expression DEFAULT on TEXT/BLOB/JSON (errno 1101).
# Strip `DEFAULT '…'` so long string columns stay TEXT; writers always supply values.
_MYSQL_TEXT_DEFAULT_RE = re.compile(
    r"^TEXT(?P<nullability>(?:\s+NOT\s+NULL)?)\s+DEFAULT\s+'[^']*'$",
    re.IGNORECASE,
)


def _mysql_decl(decl: str) -> str:
    """Mechanical SQLite-ish → MySQL type mapping."""
    out = decl
    for src, dst in (
        ("DOUBLE PRECISION", "DOUBLE"),
        ("REAL", "DOUBLE"),
        ("INTEGER", "INT"),
    ):
        out = out.replace(src, dst)
    # Inline UNIQUE becomes a table-level key (needed for ON DUPLICATE KEY).
    out = out.replace(" UNIQUE", "")
    # Tighten code-sized NOT NULL text without DEFAULT for the unique column.
    if out == "TEXT NOT NULL":
        return "VARCHAR(64) NOT NULL"
    # Drop illegal TEXT defaults (title, tags_json, …). App always writes columns.
    m = _MYSQL_TEXT_DEFAULT_RE.match(out.strip())
    if m:
        nullability = m.group("nullability") or ""
        return f"TEXT{nullability}"
    return out


class Database:
    """Parameterized queries for one backend.

    One Database instance is shared by CollectionStore and SettingsStore.

    Connections:
      - SQLite: thread-local; closed on release_request (cheap file handle).
      - MySQL / PostgreSQL: one process-wide connection behind an RLock.
        Remote TLS is ~1s+; keeping a single live connection avoids that on
        every request. Personal-library concurrency is low enough that a
        single serialized connection is the right tradeoff.
    """

    def __init__(self, config: DbConfig) -> None:
        self.config = config
        self._local = threading.local()
        # Shared conn for server backends (None until first use / after close).
        self._shared_lock = threading.RLock()
        self._shared_conn: Any | None = None
        if config.backend == "sqlite":
            assert config.path is not None
            config.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_drivers()
        self.init_schema()
        # SQLite: don't leave the schema connection open on the import thread.
        self.release_request()

    @property
    def backend(self) -> Backend:
        return self.config.backend

    @property
    def location(self) -> str:
        return self.config.display()

    def ident(self, name: str) -> str:
        """Quote an identifier when the backend requires it (MySQL reserved words)."""
        if self.backend == "mysql":
            return f"`{name.replace('`', '``')}`"
        return name

    def _ensure_drivers(self) -> None:
        if self.backend == "mysql":
            try:
                import pymysql  # noqa: F401
            except ImportError as exc:
                raise ImportError(
                    "MySQL backend requires pymysql: pip install pymysql"
                ) from exc
        elif self.backend == "postgresql":
            try:
                import psycopg  # noqa: F401
            except ImportError as exc:
                raise ImportError(
                    "PostgreSQL backend requires psycopg: "
                    "pip install 'psycopg[binary]'"
                ) from exc

    def _sql(self, sql: str) -> str:
        return _translate_sql(sql, self.backend)

    @property
    def _shared(self) -> bool:
        return self.backend != "sqlite"

    def _ops_lock(self) -> Any:
        """Serialize server-backend access; SQLite stays free-threaded."""
        return self._shared_lock if self._shared else nullcontext()

    def _open_raw(self) -> Any:
        if self.backend == "sqlite":
            conn = sqlite3.connect(
                str(self.config.path),
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn

        if self.backend == "mysql":
            import pymysql
            from pymysql.cursors import DictCursor

            flag = _ssl_flag(
                self.config.query,
                "ssl",
                "sslmode",
                default=_default_ssl_mode(self.config.host),
            )
            ssl_params: dict[str, Any] | None = None if flag in _FALSEY else {}

            # autocommit=True: plain SELECTs are one RTT (no extra COMMIT).
            # transaction() flips this off for multi-statement writes.
            return pymysql.connect(
                host=self.config.host,
                port=self.config.effective_port,
                user=self.config.user or None,
                password=self.config.password or "",
                database=self.config.database,
                charset="utf8mb4",
                cursorclass=DictCursor,
                autocommit=True,
                connect_timeout=15,
                read_timeout=60,
                write_timeout=60,
                ssl=ssl_params,
            )

        import psycopg
        from psycopg.rows import dict_row

        conninfo: dict[str, Any] = {
            "host": self.config.host,
            "port": self.config.effective_port,
            "dbname": self.config.database,
            "row_factory": dict_row,
            "autocommit": True,
            "connect_timeout": 15,
        }
        if self.config.user:
            conninfo["user"] = self.config.user
        if self.config.password:
            conninfo["password"] = self.config.password
        flag = _ssl_flag(
            self.config.query,
            "sslmode",
            "ssl",
            default=_default_ssl_mode(self.config.host),
        )
        if flag in _FALSEY:
            conninfo["sslmode"] = "disable"
        elif flag in _TRUTHY:
            conninfo["sslmode"] = "require"
        else:
            conninfo["sslmode"] = flag
        return psycopg.connect(**conninfo)

    def _set_autocommit(self, conn: Any, enabled: bool) -> None:
        if self.backend == "mysql":
            conn.autocommit(enabled)
        elif self.backend == "postgresql":
            conn.autocommit = enabled

    def _is_conn_error(self, exc: BaseException) -> bool:
        if self.backend == "mysql":
            import pymysql.err

            return isinstance(
                exc, (pymysql.err.OperationalError, pymysql.err.InterfaceError)
            )
        if self.backend == "postgresql":
            import psycopg

            return isinstance(exc, psycopg.OperationalError)
        return isinstance(exc, sqlite3.OperationalError)

    def _discard_conn(self, conn: Any | None = None) -> None:
        """Close and drop the current connection (shared or thread-local)."""
        if self._shared:
            target = conn if conn is not None else self._shared_conn
            self._shared_conn = None
        else:
            target = conn if conn is not None else getattr(self._local, "conn", None)
            self._local.conn = None
        if target is not None:
            try:
                target.close()
            except Exception:
                pass

    def _conn(self) -> Any:
        """Return a live connection. Caller must hold _ops_lock for server backends."""
        if self._shared:
            if self._shared_conn is not None:
                return self._shared_conn
            self._shared_conn = self._open_raw()
            return self._shared_conn

        conn = getattr(self._local, "conn", None)
        if conn is not None:
            return conn
        conn = self._open_raw()
        self._local.conn = conn
        return conn

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        """Nestable write transaction. Outermost call commits or rolls back.

        Reads (fetch*) stay on autocommit and do not enter this path.
            with db.transaction():
                db.execute(...)
                db.execute(...)
        """
        depth = getattr(self._local, "tx_depth", 0)
        outermost = depth == 0
        lock_cm = self._ops_lock() if outermost else nullcontext()
        with lock_cm:
            if outermost:
                self._local.tx_failed = False
            self._local.tx_depth = depth + 1
            conn = self._conn()
            if outermost and self._shared:
                self._set_autocommit(conn, False)
            try:
                yield conn
            except Exception:
                self._local.tx_failed = True
                raise
            finally:
                self._local.tx_depth = depth
                if outermost:
                    failed = bool(getattr(self._local, "tx_failed", False))
                    try:
                        if failed:
                            conn.rollback()
                        else:
                            conn.commit()
                    except Exception:
                        self._discard_conn(conn)
                        if not failed:
                            raise
                    else:
                        if self._shared:
                            try:
                                self._set_autocommit(conn, True)
                            except Exception:
                                self._discard_conn(conn)

    def _cursor_execute(
        self,
        conn: Any,
        sql: str,
        params: Sequence[Any] = (),
    ) -> Any:
        cur = conn.cursor()
        cur.execute(self._sql(sql), tuple(params))
        return cur

    def _with_read(self, fn: Any) -> Any:
        """Run ``fn(conn)`` for a full read under the ops lock.

        The lock covers execute + fetch + cursor close so a shared MySQL/PG
        connection is never used by two threads at once. Already inside
        ``transaction()``: lock is held by the outer frame; reuse that conn.
        Retries once on connection errors (outside a write transaction).
        """
        if getattr(self._local, "tx_depth", 0) > 0:
            return fn(self._conn())

        def _once() -> Any:
            return fn(self._conn())

        with self._ops_lock():
            try:
                return _once()
            except Exception as exc:
                if not self._is_conn_error(exc):
                    raise
                self._discard_conn()
                return _once()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Run DML/DDL. Returns rowcount when available."""
        with self.transaction() as conn:
            cur = self._cursor_execute(conn, sql, params)
            try:
                return int(cur.rowcount or 0)
            finally:
                cur.close()

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        def _do(conn: Any) -> dict[str, Any] | None:
            cur = self._cursor_execute(conn, sql, params)
            try:
                row = cur.fetchone()
            finally:
                cur.close()
            return _row_as_dict(row) if row is not None else None

        return self._with_read(_do)

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        def _do(conn: Any) -> list[dict[str, Any]]:
            cur = self._cursor_execute(conn, sql, params)
            try:
                rows = cur.fetchall()
            finally:
                cur.close()
            return [_row_as_dict(r) for r in rows]

        return self._with_read(_do)

    def executemany_script(self, statements: Sequence[str]) -> None:
        """Run multiple DDL statements (no parameters) in one transaction."""
        with self.transaction() as conn:
            for stmt in statements:
                s = stmt.strip().rstrip(";")
                if not s:
                    continue
                cur = conn.cursor()
                try:
                    cur.execute(s)
                finally:
                    cur.close()

    def init_schema(self) -> None:
        self.executemany_script(_schema_statements(self.backend))

    def _upsert_movie_sql(self) -> str:
        cols = ", ".join(MOVIE_WRITE_COLS)
        placeholders = ", ".join(["?"] * len(MOVIE_WRITE_COLS))
        if self.backend == "mysql":
            # MySQL 8.0.19+ row alias (avoids deprecated VALUES()).
            assignments = ", ".join(f"{c}=_new.{c}" for c in MOVIE_UPDATE_COLS)
            return (
                f"INSERT INTO movies ({cols}) VALUES ({placeholders}) AS _new "
                f"ON DUPLICATE KEY UPDATE {assignments}"
            )
        assignments = ", ".join(f"{c}=excluded.{c}" for c in MOVIE_UPDATE_COLS)
        return (
            f"INSERT INTO movies ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(code) DO UPDATE SET {assignments}"
        )

    def upsert_movie(self, fields: Mapping[str, Any]) -> dict[str, Any]:
        """Insert or update one movie row from a column→value mapping."""
        missing = [c for c in MOVIE_WRITE_COLS if c not in fields]
        if missing:
            raise ValueError(f"upsert_movie missing fields: {missing}")
        values = tuple(fields[c] for c in MOVIE_WRITE_COLS)
        code = fields["code"]
        insert_sql = self._upsert_movie_sql()
        with self.transaction() as conn:
            cur = self._cursor_execute(conn, insert_sql, values)
            cur.close()
            cur = self._cursor_execute(
                conn, "SELECT * FROM movies WHERE code = ?", (code,)
            )
            try:
                row = cur.fetchone()
            finally:
                cur.close()
        if row is None:
            raise RuntimeError(f"upsert movie failed for code={code!r}")
        return _row_as_dict(row)

    def _upsert_meta_sql(self) -> str:
        # Column name stays `key` for SQLite upgrade compatibility; MySQL quotes it.
        k = self.ident("key")
        if self.backend == "mysql":
            return (
                f"INSERT INTO app_meta ({k}, value) VALUES (?, ?) AS _new "
                f"ON DUPLICATE KEY UPDATE value = _new.value"
            )
        return (
            f"INSERT INTO app_meta ({k}, value) VALUES (?, ?) "
            f"ON CONFLICT({k}) DO UPDATE SET value = excluded.value"
        )

    def upsert_meta(self, key: str, value: str) -> None:
        self.execute(self._upsert_meta_sql(), (key, value))

    def close(self) -> None:
        """Close connections for this process/thread."""
        if self._shared:
            with self._shared_lock:
                self._discard_conn()
        else:
            self._discard_conn()

    def release_request(self) -> None:
        """End-of-request hook: close SQLite; keep the shared server connection.

        MySQL/PG stay open under _shared_lock so the next request reuses TLS.
        """
        if self._shared:
            return
        if getattr(self._local, "tx_depth", 0) > 0:
            return
        self._discard_conn()

def _col_decl(col: MovieColumn, backend: Backend) -> str:
    if backend == "mysql":
        return _mysql_decl(col.decl)
    return col.decl


def _schema_statements(backend: Backend) -> list[str]:
    """DDL from MOVIE_COLUMNS + backend primary key / engine options.

    app_meta uses column name `key` (historical SQLite schema). MySQL quotes it
    because KEY is reserved.
    """
    body = ",\n                ".join(
        f"{c.name} {_col_decl(c, backend)}" for c in MOVIE_COLUMNS
    )

    if backend == "sqlite":
        movies = f"""
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {body}
            )
        """
        meta = """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            )
        """
        return [
            movies,
            meta,
            "CREATE INDEX IF NOT EXISTS idx_movies_code ON movies(code)",
        ]

    if backend == "mysql":
        movies = f"""
            CREATE TABLE IF NOT EXISTS movies (
                id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                {body},
                UNIQUE KEY uq_movies_code (code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        meta = """
            CREATE TABLE IF NOT EXISTS app_meta (
                `key` VARCHAR(191) NOT NULL PRIMARY KEY,
                value TEXT NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        return [movies, meta]

    movies = f"""
        CREATE TABLE IF NOT EXISTS movies (
            id SERIAL PRIMARY KEY,
            {body}
        )
    """
    meta = """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        )
    """
    return [
        movies,
        meta,
        "CREATE INDEX IF NOT EXISTS idx_movies_code ON movies(code)",
    ]
