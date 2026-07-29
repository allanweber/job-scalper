from __future__ import annotations

from scalper.service.auth import (
    AdminAllowlist,
    AuthConfig,
    AuthService,
    IDTokenVerifier,
    InvalidToken,
)
from scalper.service.models import GoogleIdentity


class FakeVerifier(IDTokenVerifier):
    """Returns a preset identity; token 'bad' raises like a real failure."""

    def __init__(self, identity: GoogleIdentity):
        self.identity = identity

    def verify(self, id_token: str) -> GoogleIdentity:
        if id_token == "bad":
            raise InvalidToken("bad token")
        return self.identity


def make_auth(conn, identity: GoogleIdentity, admin_emails: list[str] | None = None) -> AuthService:
    return AuthService(
        conn,
        verifier=FakeVerifier(identity),
        allowlist=AdminAllowlist(admin_emails or []),
        config=AuthConfig(jwt_secret="test-secret", access_ttl_seconds=900),
    )
