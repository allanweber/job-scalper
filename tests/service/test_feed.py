from __future__ import annotations

import pytest
from _helpers import posting

from scalper.service.content_repos import (
    OverlayRepo,
    PostingRepo,
    ProfileRepo,
    UserSourceRepo,
)
from scalper.service.feed import FeedService
from scalper.service.models import GoogleIdentity
from scalper.service.repositories import UserRepo


@pytest.fixture
def seeded(conn, settings):
    user = UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub="s", email="u@example.com"), role="user")
    ProfileRepo(conn).upsert(user.id, "default", {
        "titles": ["Python Engineer"], "required_skills": ["python", "fastapi"],
        "keywords": ["backend"]})
    PostingRepo(conn).ingest([
        posting("remotive", "a", company="Acme", title="Senior Python Engineer",
                description="python fastapi backend remote role"),
        posting("remotive", "b", company="Beta", title="Rust Systems Engineer",
                description="rust systems low level"),
        posting("weworkremotely", "c", company="Gamma", title="Python Backend",
                description="python backend django"),
    ])
    return user


def test_feed_scores_and_filters_by_source(conn, settings, seeded):
    UserSourceRepo(conn).set_for(seeded.id, ["remotive"])
    items = FeedService(conn, settings).build(seeded.id, min_score=0)
    titles = [i.title for i in items]
    # Only remotive postings are visible; ranked with Python role on top.
    assert "Python Backend" not in titles              # weworkremotely filtered out
    assert titles[0] == "Senior Python Engineer"
    assert items[0].score >= items[-1].score
    assert set(items[0].sources) == {"remotive"}


def test_feed_new_badge_flips_after_seen(conn, settings, seeded):
    UserSourceRepo(conn).set_for(seeded.id, ["remotive"])
    svc = FeedService(conn, settings)
    items = svc.build(seeded.id, min_score=0)
    top = items[0]
    assert top.is_new is True
    OverlayRepo(conn).mark_seen(seeded.id, top.posting_id)
    again = svc.build(seeded.id, min_score=0)
    assert next(i for i in again if i.posting_id == top.posting_id).is_new is False


def test_feed_defaults_to_platform_sources_when_none_chosen(conn, settings, seeded):
    settings.set("sources.default", ["remotive"])
    items = FeedService(conn, settings).build(seeded.id, min_score=0)
    assert all("remotive" in i.sources for i in items)


def test_feed_empty_without_profile(conn, settings):
    user = UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub="np", email="np@example.com"), role="user")
    assert FeedService(conn, settings).build(user.id) == []


def test_min_score_filters(conn, settings, seeded):
    UserSourceRepo(conn).set_for(seeded.id, ["remotive"])
    high = FeedService(conn, settings).build(seeded.id, min_score=90)
    assert all(i.score >= 90 for i in high)


def test_meta_reports_pool_and_sources(conn, settings, seeded):
    UserSourceRepo(conn).set_for(seeded.id, ["remotive"])
    meta = FeedService(conn, settings).meta(seeded.id)
    assert meta.sources_count == 1          # one board chosen
    assert meta.sources_max == 3            # free-tier cap
    assert meta.has_profile is True
    assert meta.pool_size == 2              # two remotive postings in the pool


def test_meta_without_profile_or_boards(conn, settings):
    user = UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub="bare", email="bare@example.com"), role="user")
    settings.set("sources.default", [])
    meta = FeedService(conn, settings).meta(user.id)
    assert meta.has_profile is False
    assert meta.pool_size == 0
    assert meta.sources_count == 0
