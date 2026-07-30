from __future__ import annotations

import pytest

from scalper.db import connect
from scalper.db.connection import (
    _PgConnection,
    _postgres_url,
    _split_statements,
    _to_pg_ddl,
)


def test_sqlite_fallback_used_without_database_url(tmp_path, monkeypatch):
    monkeypatch.delenv("SCALPER_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SCALPER_REQUIRE_POSTGRES", raising=False)
    db = tmp_path / "fallback.db"
    monkeypatch.setenv("SCALPER_DB_PATH", str(db))
    conn = connect()
    try:
        conn.execute("CREATE TABLE t (x)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        assert conn.execute("SELECT x FROM t").fetchone()[0] == 1
        assert db.exists()
    finally:
        conn.close()


def test_pragmas_applied_on_sqlite(tmp_path, monkeypatch):
    monkeypatch.delenv("SCALPER_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SCALPER_REQUIRE_POSTGRES", raising=False)
    monkeypatch.setenv("SCALPER_DB_PATH", str(tmp_path / "p.db"))
    conn = connect()
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


# --- factory routing (pure, no server) ---

@pytest.mark.parametrize("url", [
    "postgresql://u:p@h:5432/db",
    "postgres://u:p@h/db",
])
def test_postgres_url_is_recognized(url):
    assert _postgres_url({"SCALPER_DATABASE_URL": url}) == url


def test_database_url_alias_recognized():
    assert _postgres_url({"DATABASE_URL": "postgresql://x/y"}) == "postgresql://x/y"


def test_non_postgres_url_ignored():
    assert _postgres_url({"SCALPER_DATABASE_URL": "mysql://x/y"}) is None
    assert _postgres_url({}) is None


def test_postgres_url_strips_quotes_and_whitespace():
    # A dashboard/.env copy-paste with surrounding quotes or spaces still works.
    assert _postgres_url({"SCALPER_DATABASE_URL": '  "postgresql://u:p@h/db" '}) \
        == "postgresql://u:p@h/db"
    assert _postgres_url({"SCALPER_DATABASE_URL": "'postgres://h/db'"}) == "postgres://h/db"


def test_require_postgres_fails_loudly_without_url(monkeypatch):
    monkeypatch.delenv("SCALPER_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SCALPER_REQUIRE_POSTGRES", "1")
    with pytest.raises(RuntimeError, match="valid PostgreSQL URL"):
        connect()


# --- the sqlite->postgres dialect adapter (pure, no server) ---

def test_to_pg_ddl_maps_blob_to_bytea():
    assert _to_pg_ddl("file_blob BLOB NOT NULL") == "file_blob BYTEA NOT NULL"
    assert "BYTEA" in _to_pg_ddl("x blob")           # case-insensitive
    assert _to_pg_ddl("blobby TEXT") == "blobby TEXT"  # word-bounded


def test_split_statements_strips_comments_and_splits():
    script = "CREATE TABLE a (x);  -- comment\nINSERT INTO a VALUES (1);\n-- trailing\n"
    assert _split_statements(script) == ["CREATE TABLE a (x)", "INSERT INTO a VALUES (1)"]


def test_pg_connection_translates_placeholders():
    calls = []

    class _Fake:
        def execute(self, sql, params):
            calls.append((sql, params))

    _PgConnection(_Fake()).execute("SELECT * FROM t WHERE a=? AND b=?", (1, 2))
    assert calls == [("SELECT * FROM t WHERE a=%s AND b=%s", (1, 2))]
