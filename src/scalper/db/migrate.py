"""Numbered-`.sql` migration runner.

Migrations are plain SQL files in ``migrations/`` named ``NNNN_description.sql``.
They are applied in filename order; each applied version is recorded in a
``schema_migrations`` table so re-running is idempotent. Migrations are written
to be safe to re-run anyway (``CREATE TABLE IF NOT EXISTS`` / ``ON CONFLICT DO
NOTHING``), which makes the whole system tolerant of partial application.

Migrations are backend-agnostic: they run on Postgres (prod) via the connection
adapter and on sqlite (local/CI) directly. The runner executes on API startup.
See ADR 0008 and ADR 0012.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

#: Postgres advisory-lock key so concurrent service cold-starts serialize their
#: migration runs (avoids CREATE TABLE / schema_migrations races). Arbitrary but
#: stable. No-op on sqlite (single local process).
_MIGRATION_LOCK_KEY = 743019

_TRACK_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
)
"""


def _all_migration_files() -> list[Path]:
    """Every migration file, sorted by its numeric filename prefix."""
    files = [p for p in MIGRATIONS_DIR.glob("*.sql") if p.is_file()]
    return sorted(files, key=lambda p: p.name)


def _applied_versions(conn: Any) -> set[str]:
    conn.execute(_TRACK_TABLE)
    conn.commit()
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    # Rows may be sqlite3.Row or plain tuples depending on the backend.
    return {row[0] for row in rows}


def pending_migrations(conn: Any) -> list[Path]:
    """Migration files not yet recorded as applied, in order."""
    applied = _applied_versions(conn)
    return [p for p in _all_migration_files() if p.stem not in applied]


def _lock(conn: Any) -> None:
    """Serialize migrations across services with a Postgres advisory lock."""
    if getattr(conn, "is_postgres", False):
        conn.execute("SELECT pg_advisory_lock(?)", (_MIGRATION_LOCK_KEY,))
        conn.commit()  # session-level lock persists across the per-migration commits


def _unlock(conn: Any) -> None:
    if getattr(conn, "is_postgres", False):
        try:
            conn.rollback()  # clear any aborted tx from a failed migration
        except Exception:
            pass
        try:
            conn.execute("SELECT pg_advisory_unlock(?)", (_MIGRATION_LOCK_KEY,))
            conn.commit()
        except Exception:
            pass


def apply_pending(conn: Any) -> list[str]:
    """Apply all pending migrations in order. Returns the versions applied.

    Each migration runs as its own transaction: on failure the partial
    migration is rolled back and the error propagates, leaving earlier
    migrations committed. On Postgres a database-wide advisory lock serializes
    concurrent runs (multiple services applying on cold start), so exactly one
    performs the work and the others see an already-migrated schema.
    """
    _lock(conn)
    try:
        applied: list[str] = []
        for path in pending_migrations(conn):
            sql = path.read_text()
            try:
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (path.stem, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            applied.append(path.stem)
        return applied
    finally:
        _unlock(conn)
