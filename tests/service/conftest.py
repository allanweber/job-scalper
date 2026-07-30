from __future__ import annotations

import base64
import os

import pytest
from _helpers import FakeAdapter, FakeProvider, make_container

from scalper.db import apply_pending, connect
from scalper.service.crypto import KeyVault, generate_master_key_b64
from scalper.service.quota import QuotaService
from scalper.service.settings import Settings


@pytest.fixture
def conn(tmp_path, monkeypatch):
    # When SCALPER_DATABASE_URL is set (CI's Postgres job), run the whole suite
    # against Postgres with a fresh schema per test; otherwise use a sqlite file.
    if os.environ.get("SCALPER_DATABASE_URL"):
        c = connect()
        c.execute("DROP SCHEMA IF EXISTS public CASCADE")
        c.execute("CREATE SCHEMA public")
        c.commit()
        apply_pending(c)
        yield c
        c.close()
    else:
        monkeypatch.delenv("SCALPER_DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
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


@pytest.fixture
def fake_provider():
    return FakeProvider()


@pytest.fixture
def fake_adapter():
    return FakeAdapter([])


@pytest.fixture
def container(conn, vault, fake_provider, fake_adapter):
    # `conn` set SCALPER_DB_PATH + migrated the DB; the container's connections
    # (opened via connect()) point at that same file.
    return make_container(vault, provider=fake_provider, adapter=fake_adapter)


@pytest.fixture
def client(container):
    from fastapi.testclient import TestClient

    from scalper.service.app import create_app

    with TestClient(create_app(container)) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    """Sign in the fake identity and return an Authorization header dict."""
    resp = client.post("/auth/google", json={"id_token": "good"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['tokens']['access_token']}"}
