from __future__ import annotations

import importlib.util

import pytest

from scalper.db import connect


def _libsql_available() -> bool:
    return (
        importlib.util.find_spec("libsql") is not None
        or importlib.util.find_spec("libsql_experimental") is not None
    )


def test_sqlite_fallback_used_without_libsql_url(tmp_path, monkeypatch):
    monkeypatch.delenv("LIBSQL_URL", raising=False)
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
    monkeypatch.delenv("LIBSQL_URL", raising=False)
    monkeypatch.setenv("SCALPER_DB_PATH", str(tmp_path / "p.db"))
    conn = connect()
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        conn.close()


@pytest.mark.skipif(_libsql_available(), reason="libsql client is installed")
def test_libsql_url_without_client_errors(monkeypatch):
    monkeypatch.setenv("LIBSQL_URL", "http://sqld:8080")
    with pytest.raises(RuntimeError, match="libsql client"):
        connect()
