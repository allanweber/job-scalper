"""Admin app container: the service container + admin-only wiring.

Reuses the service `Container` (DB, settings, allowlist, job queue) and adds the
admin web OAuth client, the server-side session store, and the session-cookie
secret. `from_env` builds the production wiring; tests construct it with a fake
OAuth client and the in-memory session store.
"""

from __future__ import annotations

from dataclasses import dataclass

from scalper.admin.oauth import GoogleOAuthClient, OAuthClient
from scalper.admin.sessions import SessionStore, build_session_store
from scalper.service.container import Container

_COOKIE_NAME = "scalper_admin"


@dataclass
class AdminContainer:
    service: Container
    oauth: OAuthClient
    sessions: SessionStore
    cookie_secret: str
    cookie_secure: bool = True
    cookie_name: str = _COOKIE_NAME

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "AdminContainer":
        service = Container.from_env(environ)
        env = service.environ
        client_id = env.get("SCALPER_ADMIN_GOOGLE_CLIENT_ID", "")
        client_secret = env.get("SCALPER_ADMIN_GOOGLE_CLIENT_SECRET", "")
        cookie_secret = env.get("SCALPER_ADMIN_COOKIE_SECRET")
        if not cookie_secret:
            raise RuntimeError("SCALPER_ADMIN_COOKIE_SECRET is not set")
        return cls(
            service=service,
            oauth=GoogleOAuthClient(client_id, client_secret),
            sessions=build_session_store(service.redis_url),
            cookie_secret=cookie_secret,
            cookie_secure=env.get("SCALPER_ADMIN_COOKIE_INSECURE") != "1",
        )
