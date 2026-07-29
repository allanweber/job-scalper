from __future__ import annotations

from scalper.db import connect
from scalper.llm.base import Completion
from scalper.models import JobPosting
from scalper.service.auth import (
    AdminAllowlist,
    AuthConfig,
    AuthService,
    IDTokenVerifier,
    InvalidToken,
)
from scalper.service.container import Container
from scalper.service.crypto import KeyVault
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


class FakeProvider:
    """Scripted LLM provider: infers which call it is from the prompt shape."""

    name = "fake"

    def __init__(self, *, calls: list | None = None):
        self.calls = calls if calls is not None else []

    def complete(self, prompt, *, model, system=None, max_tokens=1024,
                 temperature=0.2) -> Completion:
        self.calls.append({"prompt": prompt, "model": model, "system": system})
        if "Resume:" in prompt and "Job title" not in prompt:
            return Completion(
                text='{"titles":["Python Engineer"],"required_skills":["python",'
                     '"fastapi"],"nice_to_have_skills":["docker"],"keywords":["backend"]}',
                model=model, input_tokens=10, output_tokens=5)
        if "Matched skills" in prompt:
            return Completion(
                text="<<<RESUME>>>\n# Jane Doe\nExperience here\n"
                     "<<<COVER_LETTER>>>\nDear hiring team,\nRegards\n",
                model=model, input_tokens=20, output_tokens=30)
        return Completion(text='{"remote":true,"seniority":"senior"}',
                          model=model, input_tokens=8, output_tokens=4)


class FakeAdapter:
    """Source adapter that returns a fixed posting list, ignoring the query."""

    def __init__(self, postings: list[JobPosting]):
        self._postings = postings

    def fetch(self, query) -> list[JobPosting]:
        return list(self._postings)


def posting(source: str, source_id: str, *, company: str, title: str,
            description: str = "", remote: bool = True, url: str | None = None,
            **kw) -> JobPosting:
    return JobPosting(
        source=source, source_id=source_id, url=url or f"http://example/{source_id}",
        company=company, title=title, description=description, remote=remote, **kw)


def make_container(vault: KeyVault | None = None, *, provider: FakeProvider | None = None,
                   adapter: FakeAdapter | None = None, admin_emails: list[str] | None = None,
                   identity: GoogleIdentity | None = None,
                   platform_key: str | None = "platform-key") -> Container:
    """Build a Container wired to the test DB (via SCALPER_DB_PATH) with fakes.

    Relies on the `conn` fixture having set SCALPER_DB_PATH, so `connect()` opens
    the same database the test seeds through the `conn` fixture.
    """
    provider = provider or FakeProvider()
    ident = identity or GoogleIdentity(sub="g-user", email="user@example.com",
                                       email_verified=True, name="Test User")
    return Container(
        conn_factory=connect,
        verifier=FakeVerifier(ident),
        allowlist=AdminAllowlist(admin_emails or []),
        auth_config=AuthConfig(jwt_secret="test-secret", access_ttl_seconds=900),
        environ={"SCALPER_PLATFORM_ANTHROPIC_KEY": platform_key} if platform_key else {},
        vault=vault,
        redis_url=None,
        provider_builder=lambda name, api_key=None: provider,
        adapter_builder=lambda stype, params: (adapter or FakeAdapter([])),
        settings_ttl=0.0,
    )
