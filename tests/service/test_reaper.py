"""The reliability reaper: fail stuck drafts/jobs and refund draft credits."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scalper.service.content_repos import DraftRepo, JobRepo
from scalper.service.models import GoogleIdentity
from scalper.service.quota import QuotaService
from scalper.service.reaper import reap_stale_drafts, reap_stale_jobs
from scalper.service.repositories import UserRepo


def _user(conn, sub="r1", email="r1@x.com"):
    return UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub=sub, email=email), role="user")


def _backdate(conn, table, col, id_, minutes):
    old = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    conn.execute(f"UPDATE {table} SET {col}=? WHERE id=?", (old, id_))
    conn.commit()


def test_reaps_stale_pending_draft_and_refunds(conn, settings):
    settings.set("quota.free", {
        "draft_per_month": 3, "profile_build_per_month": 5, "enrich_per_month": 5})
    user = _user(conn)
    q = QuotaService(conn=conn, settings=settings)
    q.consume(user, "draft")                       # the crashed job took a credit
    assert q.status(user, "draft").used == 1

    did = DraftRepo(conn).create_pending(user.id, posting_id=None)
    _backdate(conn, "drafts", "updated_at", did, 30)

    assert reap_stale_drafts(conn, settings) == 1
    d = DraftRepo(conn).get(did, user.id)
    assert d.status == "failed"
    assert d.error and "regenerate" in d.error.lower()
    # The credit the crash consumed is returned.
    assert q.status(user, "draft").used == 0


def test_leaves_fresh_pending_draft_alone(conn, settings):
    user = _user(conn, sub="r2", email="r2@x.com")
    did = DraftRepo(conn).create_pending(user.id, posting_id=None)  # updated_at=now
    assert reap_stale_drafts(conn, settings) == 0
    assert DraftRepo(conn).get(did, user.id).status == "pending"


def test_reaps_stale_running_job(conn, settings):
    jid = JobRepo(conn).create("scrape", user_id=None, params={})
    JobRepo(conn).mark_running(jid)
    _backdate(conn, "jobs", "created_at", jid, 120)

    assert reap_stale_jobs(conn, settings) == 1
    assert JobRepo(conn).get(jid).status == "failed"


def test_leaves_recent_running_job_alone(conn, settings):
    jid = JobRepo(conn).create("scrape", user_id=None, params={})
    JobRepo(conn).mark_running(jid)
    assert reap_stale_jobs(conn, settings) == 0
    assert JobRepo(conn).get(jid).status == "running"
