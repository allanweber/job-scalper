from __future__ import annotations

from datetime import datetime, timedelta, timezone

from _helpers import FakeAdapter, posting

from scalper.service.content_repos import PostingRepo, ProfileRepo
from scalper.service.ingest import Ingestor
from scalper.service.models import GoogleIdentity
from scalper.service.repositories import UserRepo


def _ingestor(conn, settings, adapter):
    return Ingestor(conn, settings, adapter_builder=lambda stype, params: adapter)


def test_run_ingests_and_dedups(conn, settings):
    adapter = FakeAdapter([
        posting("remotive", "a", company="Acme", title="Python Dev"),
        posting("remotive", "b", company="Beta", title="Go Dev"),
    ])
    settings.set("sources.enabled", ["remotive", "remoteok"])
    out = _ingestor(conn, settings, adapter).run()
    # Two enabled sources each return the same 2 postings -> 2 physical rows.
    assert PostingRepo(conn).count() == 2
    assert out["ingested"]["new"] == 2
    assert settings.get("scrape.last_run_at") is not None


def test_scope_terms_uses_active_user_profiles(conn, settings):
    user = UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub="s", email="u@example.com"), role="user")
    ProfileRepo(conn).upsert(user.id, "default",
                             {"titles": ["Platform Engineer"], "keywords": ["kafka"]})
    terms = _ingestor(conn, settings, FakeAdapter([])).scope_terms()
    assert "Platform Engineer" in terms and "kafka" in terms


def test_scope_terms_fallback_when_no_active_users(conn, settings):
    terms = _ingestor(conn, settings, FakeAdapter([])).scope_terms()
    assert terms  # non-empty fallback so broad feeds still refresh


def test_scope_terms_uses_admin_default_terms(conn, settings):
    # No active users -> the admin-configured default scrape terms are used.
    settings.set("scrape.default_terms", ["kubernetes", "platform engineer"])
    terms = _ingestor(conn, settings, FakeAdapter([])).scope_terms()
    assert terms == ["kubernetes", "platform engineer"]


def test_freshness_drops_stale_postings(conn, settings):
    now = datetime.now(timezone.utc)
    adapter = FakeAdapter([
        posting("remotive", "fresh", company="A", title="New", published_at=now),
        posting("remotive", "stale", company="B", title="Old",
                published_at=now - timedelta(days=40)),
        posting("remotive", "undated", company="C", title="NoDate"),  # kept
    ])
    settings.set("scrape.freshness_days", 7)
    out = _ingestor(conn, settings, adapter).run(sources=["remotive"], terms=["x"])
    assert out["dropped_stale"] == 1
    titles = {p.title for p in PostingRepo(conn).candidates_for_sources(["remotive"])}
    assert titles == {"New", "NoDate"}  # stale dropped, undated kept


def test_per_source_failure_is_isolated(conn, settings):
    class Boom:
        def fetch(self, q):
            raise RuntimeError("source down")

    good = FakeAdapter([posting("remotive", "a", company="Acme", title="Dev")])
    builders = {"remotive": good, "broken": Boom()}
    ing = Ingestor(conn, settings, adapter_builder=lambda s, p: builders[s])
    out = ing.run(sources=["remotive", "broken"], terms=["dev"])
    assert out["per_source"]["remotive"] == 1
    assert "broken" in out["errors"]
    assert PostingRepo(conn).count() == 1


def test_purge_respects_retention(conn, settings):
    PostingRepo(conn).ingest([posting("remotive", "a", company="Acme", title="Dev")])
    settings.set("retention.days", 0)
    out = _ingestor(conn, settings, FakeAdapter([])).purge()
    assert out["deleted"] == 1 and PostingRepo(conn).count() == 0
