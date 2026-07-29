from __future__ import annotations

import base64

import pytest

from scalper.db import apply_pending, connect
from scalper.service.crypto import KeyVault, generate_master_key_b64
from scalper.service.quota import QuotaService
from scalper.service.settings import Settings


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.delenv("LIBSQL_URL", raising=False)
    monkeypatch.setenv("SCALPER_DB_PATH", str(tmp_path / "svc.db"))
    c = connect()
    apply_pending(c)
    yield c
    c.close()


@pytest.fixture
def settings(conn):
    # ttl=0 => always reload, so set()/get() are deterministic in tests.
    return Settings(conn, ttl_seconds=0.0)


@pytest.fixture
def vault():
    key = base64.b64decode(generate_master_key_b64())
    return KeyVault({1: key}, active_version=1)


@pytest.fixture
def quota(conn, settings):
    return QuotaService(conn=conn, settings=settings)
