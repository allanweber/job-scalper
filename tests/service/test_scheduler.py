from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scalper.service.content_repos import JobRepo
from scalper.service.scheduler import purge_due, scrape_due, tick


def test_scrape_due_when_never_run(conn, settings):
    settings.set("scrape.last_run_at", None)
    assert scrape_due(settings) is True


def test_scrape_not_due_within_interval(conn, settings):
    settings.set("scrape.interval_minutes", 360)
    settings.set("scrape.last_run_at",
                 (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat())
    assert scrape_due(settings) is False


def test_scrape_due_after_interval(conn, settings):
    settings.set("scrape.interval_minutes", 60)
    settings.set("scrape.last_run_at",
                 (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat())
    assert scrape_due(settings) is True


def test_purge_due_daily(conn, settings):
    assert purge_due(settings) is True
    settings.set("scrape.last_purge_at", datetime.now(timezone.utc).isoformat())
    assert purge_due(settings) is False


def test_tick_enqueues_scrape_and_purge(container, conn, settings):
    settings.set("scrape.last_run_at", None)
    out = tick(container)
    assert out["scrape"] is not None and out["purge"] is not None
    # Eager execution ran them to completion as system jobs (no user_id).
    scrape = JobRepo(conn).get(out["scrape"])
    assert scrape.kind == "scrape" and scrape.status == "succeeded"


def test_tick_skips_when_maintenance(container, conn, settings):
    settings.set("maintenance.enabled", True)
    out = tick(container)
    assert out == {"scrape": None, "purge": None}
