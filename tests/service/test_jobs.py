from __future__ import annotations

import pytest
from _helpers import posting

from scalper.service.content_repos import (
    JobRepo,
    PostingRepo,
    ProfileRepo,
    ResumeRepo,
)
from scalper.service.jobs import (
    KIND_DRAFT,
    KIND_ENRICH,
    KIND_PROFILE,
    JobQueue,
    execute,
)
from scalper.service.models import GoogleIdentity
from scalper.service.quota import QuotaService
from scalper.service.repositories import UserRepo


@pytest.fixture
def user(conn):
    return UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub="s", email="u@example.com", name="U"), role="user")


@pytest.fixture
def with_resume_and_profile(conn, user):
    ResumeRepo(conn).upsert(user.id, filename="cv.txt", content_type="text/plain",
                            blob=b"Jane. Python. FastAPI backend.",
                            extracted_text="Jane. Python. FastAPI backend.")
    ProfileRepo(conn).upsert(user.id, "default", {
        "titles": ["Python Engineer"], "required_skills": ["python", "fastapi"],
        "keywords": ["backend"]})
    return user


@pytest.fixture
def pool_posting(conn):
    p = posting("remotive", "a", company="Acme", title="Senior Python Engineer",
                description="python fastapi backend remote")
    PostingRepo(conn).ingest([p])
    return p.dedup_key


def _run(container, conn, kind, user_id, params):
    jid = JobQueue(container).enqueue(conn, kind, user_id=user_id, params=params)
    return JobRepo(conn).get(jid)


def test_profile_job_builds_profile(container, conn, user):
    ResumeRepo(conn).upsert(user.id, filename="cv.txt", content_type="text/plain",
                            blob=b"Jane Python FastAPI", extracted_text="Jane Python FastAPI")
    rec = _run(container, conn, KIND_PROFILE, user.id, {})
    assert rec.status == "succeeded", rec.error
    assert ProfileRepo(conn).primary_for(user.id).titles == ["Python Engineer"]


def test_profile_job_fails_without_resume(container, conn, user):
    rec = _run(container, conn, KIND_PROFILE, user.id, {})
    assert rec.status == "failed" and "resume" in rec.error


def test_draft_job_creates_draft_and_marks_overlay(container, conn,
                                                   with_resume_and_profile, pool_posting):
    rec = _run(container, conn, KIND_DRAFT, with_resume_and_profile.id,
               {"posting_id": pool_posting})
    assert rec.status == "succeeded", rec.error
    assert rec.result["draft_id"]
    from scalper.service.content_repos import OverlayRepo
    ov = OverlayRepo(conn).get_many(with_resume_and_profile.id, [pool_posting])
    assert ov[pool_posting].drafted_at is not None


def test_draft_job_quota_exceeded(container, conn, settings,
                                  with_resume_and_profile, pool_posting):
    settings.set("quota.free", {"draft_per_month": 0, "profile_build_per_month": 5,
                                "enrich_per_month": 30})
    rec = _run(container, conn, KIND_DRAFT, with_resume_and_profile.id,
               {"posting_id": pool_posting})
    assert rec.status == "failed" and "quota_exceeded:draft" in rec.error


def test_enrich_job_and_cache_hit_is_free(container, conn, settings,
                                          with_resume_and_profile, pool_posting):
    quota = QuotaService(conn=conn, settings=settings)
    user = with_resume_and_profile
    rec = _run(container, conn, KIND_ENRICH, user.id, {"posting_id": pool_posting})
    assert rec.status == "succeeded", rec.error
    assert rec.result["cached"] is False
    used_after_first = quota.status(user, "enrich").used
    assert used_after_first == 1
    # Second enrich hits the shared cache: served free, quota not consumed again.
    rec2 = _run(container, conn, KIND_ENRICH, user.id, {"posting_id": pool_posting})
    assert rec2.result["cached"] is True
    assert quota.status(user, "enrich").used == used_after_first


def test_scrape_job_runs_as_system_job(container, conn):
    from _helpers import FakeAdapter, make_container

    adapter = FakeAdapter([posting("remotive", "z", company="Zeta", title="Dev")])
    c2 = make_container(container.vault, adapter=adapter)
    jid = JobRepo(conn).create("scrape", user_id=None, params={"sources": ["remotive"],
                                                               "terms": ["dev"]})
    execute(c2, jid)
    rec = JobRepo(conn).get(jid)
    assert rec.status == "succeeded"
    assert PostingRepo(conn).count() >= 1
