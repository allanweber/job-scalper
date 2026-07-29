from __future__ import annotations

from scalper.service.models import GoogleIdentity
from scalper.service.repositories import LLMCredentialRepo, UserRepo


def test_settings_seeded_and_editable(conn, settings):
    assert settings.get("scrape.interval_minutes") == 360
    assert settings.get("sources.default") == ["remotive", "remoteok", "arbeitnow"]
    settings.set("scrape.interval_minutes", 120, updated_by="admin@x.com")
    assert settings.get("scrape.interval_minutes") == 120


def test_settings_cache_invalidates_on_set(conn):
    from scalper.service.settings import Settings
    s = Settings(conn, ttl_seconds=1000.0)   # long TTL
    assert s.get("retention.days") == 30
    s.set("retention.days", 7)               # set() must bust the cache
    assert s.get("retention.days") == 7


def test_llm_credential_roundtrip(conn, vault):
    user = UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub="c-1", email="c@x.com"), role="user"
    )
    repo = LLMCredentialRepo(conn)
    sealed = vault.seal("sk-ant-xyz")
    repo.upsert(user.id, "anthropic", sealed)

    got = repo.get_sealed(user.id, "anthropic")
    assert got is not None
    assert vault.open(got) == "sk-ant-xyz"
    assert repo.has_valid(user.id, "anthropic") is True
    assert repo.has_valid(user.id) is True
    assert [c.provider for c in repo.list_for(user.id)] == ["anthropic"]

    # Re-upsert replaces (rotation to a new key value).
    repo.upsert(user.id, "anthropic", vault.seal("sk-ant-new"))
    assert vault.open(repo.get_sealed(user.id, "anthropic")) == "sk-ant-new"

    repo.set_valid(user.id, "anthropic", False)
    assert repo.has_valid(user.id, "anthropic") is False

    repo.delete(user.id, "anthropic")
    assert repo.get_sealed(user.id, "anthropic") is None


def test_delete_user_cascades(conn, vault):
    repo_u = UserRepo(conn)
    user = repo_u.upsert_from_google(GoogleIdentity(sub="d-1", email="d@x.com"), role="user")
    LLMCredentialRepo(conn).upsert(user.id, "openai", vault.seal("sk"))
    repo_u.delete(user.id)
    assert LLMCredentialRepo(conn).get_sealed(user.id, "openai") is None
