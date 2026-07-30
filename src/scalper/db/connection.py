"""Connection factory for the service database.

**Production is PostgreSQL** (a managed Dokploy Postgres service — see ADR 0012 and
`docs/deployment/postgres-dokploy.md`). Local development and CI use a **sqlite**
fallback so the test suite stays fast and server-free.

The data layer is written once in the sqlite DB-API style (``?`` placeholders,
positional rows, ``executescript`` for migrations). A thin adapter
(``_PgConnection``) makes a psycopg (Postgres) connection present that same
surface, translating ``?`` → ``%s`` and the couple of DDL dialect differences
(``BLOB`` → ``BYTEA``) so the identical repositories and migrations run on both
backends.

Configuration (env):
  SCALPER_DATABASE_URL   postgresql://user:pass@host:5432/db  (prod)
                         (``DATABASE_URL`` is accepted as an alias)
  SCALPER_DB_PATH        local sqlite path when no Postgres URL is set
                         (default: ./scalper-service.db)
"""

from __future__ import annotations

import os
import re
import sqlite3
from typing import Any

#: busy-timeout for the local sqlite fallback. Milliseconds.
_BUSY_TIMEOUT_MS = 5000

_BLOB_RE = re.compile(r"\bBLOB\b", re.IGNORECASE)


# --------------------------------------------------------------------------- sqlite


def _apply_sqlite_pragmas(conn: sqlite3.Connection) -> None:
    """WAL + busy-timeout + FK enforcement for the local/sqlite backend."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")


def _connect_sqlite(path: str) -> sqlite3.Connection:
    # check_same_thread=False: the API opens one connection per request but FastAPI
    # may run a request's dependency and endpoint on different threadpool threads.
    # Access stays sequential within a request, so this is safe (matches how the
    # psycopg connection is used); it is not shared concurrently across requests.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _apply_sqlite_pragmas(conn)
    return conn


# --------------------------------------------------------------------------- postgres


def _to_pg_ddl(sql: str) -> str:
    """Adapt a migration's DDL to Postgres (only ``BLOB`` differs in our schema)."""
    return _BLOB_RE.sub("BYTEA", sql)


def _split_statements(script: str) -> list[str]:
    """Split a migration script into individual statements for psycopg.

    Our migrations contain no ``;`` or ``--`` inside string literals, so stripping
    line comments and splitting on ``;`` is safe (and keeps the multi-row seed
    INSERT — whose ``),(`` has no ``;`` — as one statement).
    """
    cleaned = "\n".join(line.split("--", 1)[0] for line in script.splitlines())
    return [s.strip() for s in cleaned.split(";") if s.strip()]


class _PgConnection:
    """Adapts a psycopg connection to the sqlite3-style surface the repos use."""

    def __init__(self, conn: Any):
        self._conn = conn

    def execute(self, sql: str, params: tuple | list = ()) -> Any:
        # Repos use '?' placeholders; psycopg uses '%s'. No literal '%' or '?'
        # appears in our SQL outside placeholders, so this substitution is safe.
        return self._conn.execute(sql.replace("?", "%s"), params)

    def executescript(self, sql: str) -> "_PgConnection":
        with self._conn.cursor() as cur:
            for statement in _split_statements(_to_pg_ddl(sql)):
                cur.execute(statement)
        return self

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def _connect_postgres(url: str) -> _PgConnection:
    try:
        import psycopg
    except ModuleNotFoundError as e:  # pragma: no cover - env-dependent
        raise RuntimeError(
            "SCALPER_DATABASE_URL is set but psycopg is not installed. "
            "Install the service extras (pip install '.[api]')."
        ) from e
    # Non-autocommit: multi-step repo methods (e.g. replace-sources) rely on an
    # explicit commit() to be atomic. psycopg connections are thread-safe for the
    # sequential, one-per-request use here.
    conn = psycopg.connect(url)
    return _PgConnection(conn)


# --------------------------------------------------------------------------- factory


def _postgres_url(environ: dict[str, str]) -> str | None:
    url = environ.get("SCALPER_DATABASE_URL") or environ.get("DATABASE_URL")
    if url and url.startswith(("postgres://", "postgresql://")):
        return url
    return None


def connect() -> Any:
    """Return a DB connection: Postgres when configured, else local sqlite."""
    url = _postgres_url(os.environ)
    if url:
        return _connect_postgres(url)
    path = os.environ.get("SCALPER_DB_PATH", "scalper-service.db")
    return _connect_sqlite(path)
