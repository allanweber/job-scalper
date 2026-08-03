"""The email usage ledger: quotas that survive delete-and-recreate."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scalper.service.models import GoogleIdentity
from scalper.service.quota import QuotaExceeded, QuotaService
from scalper.service.repositories import UsageLedgerRepo, UserRepo


def _free_limit(settings, draft=2):
    settings.set("quota.free", {
        "draft_per_month": draft,
        "profile_build_per_month": 5,
        "enrich_per_month": 5,
    })


def test_ledger_increment_and_prune(conn):
    r = UsageLedgerRepo(conn)
    assert r.increment("a@x.com", "draft", "2026-06", 1) == 1
    assert r.increment("a@x.com", "draft", "2026-06", 2) == 3
    r.increment("a@x.com", "draft", "2026-08", 1)
    removed = r.prune_before("2026-08")            # drop everything before Aug
    assert removed == 1
    assert r.get_count("a@x.com", "draft", "2026-06") == 0
    assert r.get_count("a@x.com", "draft", "2026-08") == 1


def test_quota_survives_delete_and_recreate(conn, settings):
    _free_limit(settings, draft=2)
    identity = GoogleIdentity(sub="abuser-1", email="a@x.com")
    user = UserRepo(conn).upsert_from_google(identity, role="user")

    q = QuotaService(conn=conn, settings=settings)
    q.consume(user, "draft")
    q.consume(user, "draft")                       # 2/2 used
    with pytest.raises(QuotaExceeded):
        q.consume(user, "draft")

    # Full account deletion, then re-sign-in with the SAME email.
    UserRepo(conn).delete(user.id)
    user2 = UserRepo(conn).upsert_from_google(identity, role="user")
    assert user2.id != user.id                     # genuinely a fresh account

    q2 = QuotaService(conn=conn, settings=settings)
    # The per-account counter reset to 0, but the email ledger survived, so the
    # quota is still exhausted for this period.
    assert q2.status(user2, "draft").used == 2
    with pytest.raises(QuotaExceeded):
        q2.consume(user2, "draft")


def test_quota_resets_in_a_new_period(conn, settings):
    _free_limit(settings, draft=1)
    identity = GoogleIdentity(sub="u2", email="u2@x.com")
    user = UserRepo(conn).upsert_from_google(identity, role="user")

    aug = QuotaService(conn=conn, settings=settings,
                       clock=lambda: datetime(2026, 8, 1, tzinfo=timezone.utc))
    aug.consume(user, "draft")
    with pytest.raises(QuotaExceeded):
        aug.consume(user, "draft")

    # A new month starts fresh — the ledger is keyed by period.
    sep = QuotaService(conn=conn, settings=settings,
                       clock=lambda: datetime(2026, 9, 1, tzinfo=timezone.utc))
    assert sep.status(user, "draft").used == 0
    sep.consume(user, "draft")                     # allowed again


def test_refund_releases_from_the_ledger(conn, settings):
    _free_limit(settings, draft=2)
    user = UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub="u3", email="u3@x.com"), role="user")
    q = QuotaService(conn=conn, settings=settings)
    q.consume(user, "draft")
    assert q.status(user, "draft").used == 1
    q.refund(user, "draft")
    assert q.status(user, "draft").used == 0       # both counter and ledger back
