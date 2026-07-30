from __future__ import annotations

import os
import sqlite3

import pytest

from scalper.db import apply_pending, connect, pending_migrations
from scalper.db.migrate import _all_migration_files


@pytest.fixture
def conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "m.db"))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_pending_then_applied(conn):
    pending = [p.stem for p in pending_migrations(conn)]
    assert "0001_initial_schema" in pending
    applied = apply_pending(conn)
    assert applied == pending
    assert pending_migrations(conn) == []


def test_apply_is_idempotent(conn):
    assert apply_pending(conn)            # first run applies
    assert apply_pending(conn) == []      # second run is a no-op


def test_records_versions_in_tracking_table(conn):
    apply_pending(conn)
    rows = conn.execute(
        "SELECT version, applied_at FROM schema_migrations"
    ).fetchall()
    versions = {r[0] for r in rows}
    assert {p.stem for p in _all_migration_files()} == versions
    assert all(r[1] for r in rows)        # applied_at populated


def test_schema_and_seeds_present(conn):
    apply_pending(conn)
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    for expected in ("users", "postings", "posting_sources", "llm_credentials",
                     "usage_counters", "settings", "admin_audit", "drafts"):
        assert expected in tables
    n = conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
    assert n >= 8                          # seeded defaults inserted


def test_migrations_sorted_by_numeric_prefix():
    names = [p.name for p in _all_migration_files()]
    assert names == sorted(names)


@pytest.mark.skipif(not os.environ.get("SCALPER_DATABASE_URL"),
                    reason="Postgres advisory-lock behaviour (needs a Postgres URL)")
def test_apply_pending_lock_safe_across_connections():
    # Two separate connections apply against a fresh schema: one does the work,
    # the other sees it already migrated. Proves the advisory lock is acquired
    # AND released (a leaked lock would deadlock the second call).
    c1 = connect()
    c1.execute("DROP SCHEMA IF EXISTS public CASCADE")
    c1.execute("CREATE SCHEMA public")
    c1.commit()
    try:
        assert apply_pending(c1)          # first run applies everything
        c2 = connect()
        try:
            assert apply_pending(c2) == []  # second connection: no-op, no deadlock
        finally:
            c2.close()
    finally:
        c1.close()
