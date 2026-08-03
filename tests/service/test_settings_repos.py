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


def test_delete_user_wipes_every_owned_table(conn, vault):
    """Deletion leaves no row keyed to the user in any user-owned table.

    Guards the explicit per-table wipe (which must not depend on FK cascade),
    so a table added later without a cascade clause can't silently retain data.
    """
    from scalper.models import JobPosting
    from scalper.service.content_repos import (
        DraftRepo,
        JobRepo,
        LLMUsageRepo,
        OverlayRepo,
        PostingRepo,
        ProfileRepo,
        ResumeRepo,
        UserSourceRepo,
    )
    from scalper.service.push_repos import NotificationPrefsRepo, PushDeviceRepo
    from scalper.service.repositories import (
        _USER_OWNED_TABLES,
        QuotaOverrideRepo,
        RefreshTokenRepo,
    )

    repo_u = UserRepo(conn)
    user = repo_u.upsert_from_google(
        GoogleIdentity(sub="d-2", email="d2@x.com"), role="user")

    post = JobPosting(
        source="remotive", source_id="p1", url="http://x/p1", company="Acme",
        title="Dev", remote=True)
    PostingRepo(conn).ingest([post])
    pid = post.dedup_key
    ProfileRepo(conn).upsert(user.id, "default", {"titles": ["Dev"]})
    ResumeRepo(conn).upsert(user.id, filename="cv.txt", content_type="text/plain",
                            blob=b"x", extracted_text="x")
    UserSourceRepo(conn).set_for(user.id, ["remotive"])
    OverlayRepo(conn).set_saved(user.id, pid, True)
    LLMCredentialRepo(conn).upsert(user.id, "openai", vault.seal("sk"))
    JobRepo(conn).create("draft", user_id=user.id, params={"posting_id": pid})
    DraftRepo(conn).create_pending(user.id, posting_id=pid)
    PushDeviceRepo(conn).register(user.id, "tok", "android")
    NotificationPrefsRepo(conn).upsert(user.id, match_alerts=True, min_score=80)
    RefreshTokenRepo(conn).create(user.id, "token-hash", "2999-01-01T00:00:00+00:00")
    QuotaOverrideRepo(conn).set(user.id, "draft", 5)
    LLMUsageRepo(conn).record(user.id, action="draft", provider="anthropic",
                              model="m", key_source="platform",
                              input_tokens=1, output_tokens=1)
    conn.execute(
        "INSERT INTO usage_counters (user_id, metric, period, count, updated_at) "
        "VALUES (?, 'draft', '2026-08', 1, '2026-08-03T00:00:00+00:00')",
        (user.id,))
    conn.commit()

    repo_u.delete(user.id)

    assert repo_u.get(user.id) is None
    for table in _USER_OWNED_TABLES:
        remaining = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (user.id,)
        ).fetchone()[0]
        assert remaining == 0, f"{table} still holds rows for the deleted user"
    # The shared pool is not user data — it stays.
    assert PostingRepo(conn).get(pid) is not None
