from __future__ import annotations

import pytest

from scalper.admin.container import AdminContainer
from scalper.admin.oauth import OAuthClient, OAuthError
from scalper.admin.sessions import MemorySessionStore
from scalper.db import apply_pending, connect
from scalper.service.auth import AdminAllowlist, AuthConfig, IDTokenVerifier
from scalper.service.container import Container
from scalper.service.models import GoogleIdentity
from scalper.service.settings import Settings

ADMIN_EMAIL = "admin@example.com"


class _NoVerifier(IDTokenVerifier):
    def verify(self, id_token: str) -> GoogleIdentity:  # pragma: no cover
        raise NotImplementedError


class FakeOAuth(OAuthClient):
    """Scripted admin OAuth: any code returns `identity`; code 'bad' fails."""

    def __init__(self, identity: GoogleIdentity):
        self.identity = identity

    def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        return f"https://accounts.google.example/auth?state={state}&redirect_uri={redirect_uri}"

    def exchange_code(self, *, code: str, redirect_uri: str) -> GoogleIdentity:
        if code == "bad":
            raise OAuthError("bad code")
        return self.identity


class _Adapter:
    def fetch(self, query):
        return []


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
    return Settings(conn, ttl_seconds=0.0)


@pytest.fixture
def service_container(conn):
    return Container(
        conn_factory=connect,
        verifier=_NoVerifier(),
        allowlist=AdminAllowlist([ADMIN_EMAIL]),
        auth_config=AuthConfig(jwt_secret="test-secret"),
        environ={"SCALPER_PLATFORM_ANTHROPIC_KEY": "k"},
        vault=None,
        redis_url=None,
        provider_builder=lambda name, api_key=None: None,
        adapter_builder=lambda stype, params: _Adapter(),
        settings_ttl=0.0,
    )


@pytest.fixture
def admin_identity():
    return GoogleIdentity(sub="admin-sub", email=ADMIN_EMAIL, email_verified=True,
                          name="Admin User")


@pytest.fixture
def admin_container(service_container, admin_identity):
    return AdminContainer(
        service=service_container,
        oauth=FakeOAuth(admin_identity),
        sessions=MemorySessionStore(),
        cookie_secret="cookie-secret",
        cookie_secure=False,
    )


@pytest.fixture
def client(admin_container):
    from fastapi.testclient import TestClient

    from scalper.admin.app import create_admin_app

    with TestClient(create_admin_app(admin_container)) as c:
        yield c


def _do_login(client):
    """Run the OAuth dance against the fake client; leaves a session cookie set."""
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 303
    # State is echoed into the (fake) Google URL; reuse it on the callback.
    location = r.headers["location"]
    state = location.split("state=", 1)[1].split("&", 1)[0]
    cb = client.get(f"/auth/callback?code=good&state={state}", follow_redirects=False)
    assert cb.status_code == 303 and cb.headers["location"] == "/"
    return cb


@pytest.fixture
def logged_in(client):
    _do_login(client)
    return client
