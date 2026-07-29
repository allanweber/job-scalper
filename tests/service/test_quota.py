from __future__ import annotations

import pytest

from scalper.service.models import User, now_iso
from scalper.service.quota import QuotaExceeded, QuotaService
from scalper.service.repositories import QuotaOverrideRepo


def _user(conn, plan="free") -> User:
    from scalper.service.repositories import UserRepo
    from scalper.service.models import GoogleIdentity
    u = UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub="q-1", email="q@x.com"), role="user"
    )
    if plan != "free":
        UserRepo(conn).set_plan(u.id, plan)
        u.plan = plan
    return u


def test_limit_from_plan_settings(conn, quota):
    user = _user(conn)
    # seeded quota.free: draft=5, profile_build=5, enrich=30
    assert quota.limit_for(user, "draft") == 5
    assert quota.limit_for(user, "enrich") == 30


def test_override_wins(conn, quota):
    user = _user(conn)
    QuotaOverrideRepo(conn).set(user.id, "draft", 2)
    assert quota.limit_for(user, "draft") == 2


def test_consume_until_exhausted(conn, quota):
    user = _user(conn)
    QuotaOverrideRepo(conn).set(user.id, "draft", 2)
    quota.consume(user, "draft")
    s = quota.consume(user, "draft")
    assert s.used == 2 and s.remaining == 0 and not s.allowed
    with pytest.raises(QuotaExceeded):
        quota.consume(user, "draft")


def test_check_is_nonmutating(conn, quota):
    user = _user(conn)
    quota.check(user, "draft")
    quota.check(user, "draft")
    assert quota.status(user, "draft").used == 0


def test_unlimited_never_blocks_but_records(conn, quota):
    user = _user(conn)
    QuotaOverrideRepo(conn).set(user.id, "draft", 1)
    for _ in range(5):
        s = quota.consume(user, "draft", unlimited=True)
    assert s.unlimited and s.remaining == -1
    # usage still recorded for admin visibility
    assert quota.status(user, "draft").used == 5


def test_unknown_metric_raises(conn, quota):
    user = _user(conn)
    with pytest.raises(ValueError):
        quota.limit_for(user, "teleport")


def test_period_is_month(conn, quota):
    assert len(quota.period()) == 7 and quota.period()[4] == "-"
