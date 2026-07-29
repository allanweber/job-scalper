"""Connection factory for the service database.

Prefers a self-hosted libsql (`sqld`) server when ``LIBSQL_URL`` is configured,
falling back to a local ``sqlite3`` file otherwise. The fallback keeps the code
runnable and testable without the libsql client installed (e.g. local dev, CI,
the ops CLI against a scratch file).

Both clients expose the DB-API surface the rest of the data layer relies on
(``execute``/``executemany``/``executescript``/``commit``/row access), so callers
don't care which backend is live.

Configuration (env):
  LIBSQL_URL          e.g. http://sqld:8080  (unset => local sqlite fallback)
  LIBSQL_AUTH_TOKEN   bearer token for sqld
  SCALPER_DB_PATH     local sqlite path used when LIBSQL_URL is unset
                      (default: ./scalper-service.db)
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

#: busy-timeout for the single-writer node (see ADR 0008). Milliseconds.
_BUSY_TIMEOUT_MS = 5000


def _apply_sqlite_pragmas(conn: sqlite3.Connection) -> None:
    """WAL + busy-timeout + FK enforcement for the local/sqlite backend."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")


def _connect_sqlite(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _apply_sqlite_pragmas(conn)
    return conn


def _connect_libsql(url: str, token: str | None) -> Any:
    """Connect to a remote sqld via the libsql client.

    Imported lazily so the module works without the dependency when falling
    back to sqlite. The libsql sync client mirrors the sqlite3 DB-API.
    """
    try:
        import libsql  # type: ignore
    except ModuleNotFoundError:
        try:
            import libsql_experimental as libsql  # type: ignore
        except ModuleNotFoundError as e:  # pragma: no cover - env-dependent
            raise RuntimeError(
                "LIBSQL_URL is set but no libsql client is installed. "
                "Install the service extras (e.g. pip install '.[api]') or unset "
                "LIBSQL_URL to use the local sqlite fallback."
            ) from e
    conn = libsql.connect(database=url, auth_token=token)
    # busy-timeout is best-effort on the remote client; WAL is a server concern.
    try:  # pragma: no cover - backend-dependent
        conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    except Exception:
        pass
    return conn


def connect() -> Any:
    """Return a DB connection: libsql when configured, else local sqlite."""
    url = os.environ.get("LIBSQL_URL")
    if url:
        return _connect_libsql(url, os.environ.get("LIBSQL_AUTH_TOKEN"))
    path = os.environ.get("SCALPER_DB_PATH", "scalper-service.db")
    return _connect_sqlite(path)
