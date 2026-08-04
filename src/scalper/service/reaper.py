"""Reliability reaper: fail drafts/jobs stuck past a timeout (worker died).

A worker that crashes mid-job leaves a draft in 'pending' forever — with its
quota already consumed but never refunded (the reservation's refund only runs on
a clean exception, not a killed process) — and a job stuck in 'queued'/'running'.
The reaper sweeps these on each scheduler tick: a stale pending draft becomes
'failed' with a clear reason and its draft credit is refunded, and a stale job
becomes 'failed'. It's idempotent and gated by a timeout, so in-flight work is
never touched.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from scalper.service.content_repos import DraftRepo
from scalper.service.models import now as _now, now_iso
from scalper.service.quota import QuotaService
from scalper.service.repositories import UserRepo
from scalper.service.settings import Settings

#: A stuck draft is one 'pending' longer than this; a draft normally fills in
#: seconds, so minutes of no progress means the worker died.
DEFAULT_DRAFT_TIMEOUT_MIN = 15
#: A job past this (queued or running) is treated as abandoned. Generous so a
#: legitimately long scrape is never reaped mid-run.
DEFAULT_JOB_TIMEOUT_MIN = 30

_REAP_DRAFT_MSG = (
    "Drafting didn’t finish in time — the worker may have restarted. Your draft "
    "credit was refunded; tap Regenerate to try again."
)
_REAP_JOB_MSG = "Reaped: exceeded the max runtime (worker likely restarted)."


def _cutoff_iso(minutes: int, now: datetime | None) -> str:
    return ((now or _now()) - timedelta(minutes=minutes)).isoformat()


def reap_stale_drafts(conn: Any, settings: Settings, *,
                      now: datetime | None = None) -> int:
    """Fail pending drafts older than the timeout and refund their draft credit.

    Returns how many were reaped.
    """
    minutes = int(settings.get("reaper.draft_timeout_minutes",
                               DEFAULT_DRAFT_TIMEOUT_MIN) or DEFAULT_DRAFT_TIMEOUT_MIN)
    cutoff = _cutoff_iso(minutes, now)
    rows = conn.execute(
        "SELECT id, user_id FROM drafts WHERE status='pending' AND updated_at < ?",
        (cutoff,),
    ).fetchall()
    drafts = DraftRepo(conn)
    users = UserRepo(conn)
    quota = QuotaService(conn=conn, settings=settings)
    for did, uid in rows:
        drafts.mark_failed(did, uid, _REAP_DRAFT_MSG)
        # Favor the user: refund the draft credit a crashed job never returned.
        user = users.get(uid)
        if user is not None:
            quota.refund(user, "draft")
    return len(rows)


def reap_stale_jobs(conn: Any, settings: Settings, *,
                    now: datetime | None = None) -> int:
    """Fail jobs stuck queued/running past the timeout. Returns how many."""
    minutes = int(settings.get("reaper.job_timeout_minutes",
                               DEFAULT_JOB_TIMEOUT_MIN) or DEFAULT_JOB_TIMEOUT_MIN)
    cutoff = _cutoff_iso(minutes, now)
    cur = conn.execute(
        "UPDATE jobs SET status='failed', error=?, finished_at=? "
        "WHERE status IN ('queued','running') AND created_at < ?",
        (_REAP_JOB_MSG, now_iso(), cutoff),
    )
    conn.commit()
    return cur.rowcount if cur.rowcount is not None else 0


def reap(conn: Any, settings: Settings, *,
         now: datetime | None = None) -> dict[str, int]:
    """One reaper sweep: stale drafts + stale jobs. Returns per-kind counts."""
    return {
        "drafts": reap_stale_drafts(conn, settings, now=now),
        "jobs": reap_stale_jobs(conn, settings, now=now),
    }
