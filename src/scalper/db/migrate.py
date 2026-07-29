"""Numbered-`.sql` migration runner.

Migrations are plain SQL files in ``migrations/`` named ``NNNN_description.sql``.
They are applied in filename order; each applied version is recorded in a
``schema_migrations`` table so re-running is idempotent. Migrations are written
to be safe to re-run anyway (``CREATE TABLE IF NOT EXISTS`` / ``INSERT OR IGNORE``),
which makes the whole system tolerant of partial application.

The runner executes on API startup and is also exposed to the ops CLI
(``scalper admin migrate``). See ADR 0008.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

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


def apply_pending(conn: Any) -> list[str]:
    """Apply all pending migrations in order. Returns the versions applied.

    Each migration runs as its own transaction: on failure the partial
    migration is rolled back and the error propagates, leaving earlier
    migrations committed.
    """
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
