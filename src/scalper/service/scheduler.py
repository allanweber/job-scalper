"""In-process scheduler: enqueues scrape + purge on the hot interval (ADR 0011).

Replaces Dokploy cron. Reads `scrape.interval_minutes` live from settings and
enqueues a scrape job when the last run is older than the interval; also enqueues
the retention auto-purge daily. Runs as its own always-on Dokploy service. The
interval and enabled sources are admin-editable and take effect without redeploy.

`tick()` is a single pure step (testable); `run_forever()` is the service loop.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from scalper.db import apply_pending
from scalper.service.container import Container
from scalper.service.jobs import KIND_PURGE, KIND_SCRAPE, JobQueue
from scalper.service.reaper import reap
from scalper.service.settings import Settings


def _parse_iso(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def scrape_due(settings: Settings, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    interval = int(settings.get("scrape.interval_minutes", 360) or 360)
    last = _parse_iso(settings.get("scrape.last_run_at"))
    if last is None:
        return True
    return now - last >= timedelta(minutes=interval)


def purge_due(settings: Settings, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    last = _parse_iso(settings.get("scrape.last_purge_at"))
    if last is None:
        return True
    return now - last >= timedelta(days=1)


def tick(container: Container, *, now: datetime | None = None) -> dict[str, Any]:
    """One scheduler step: reap stale work, then enqueue scrape/purge if due.

    Returns the scrape/purge job ids and the reaper's per-kind counts.
    """
    now = now or datetime.now(timezone.utc)
    conn = container.connect()
    out: dict[str, Any] = {"scrape": None, "purge": None, "reaped": None}
    try:
        settings = container.settings(conn)
        if bool(settings.get("maintenance.enabled", False)):
            return out
        # Reap first, every tick: a stuck draft/job shouldn't wait on the scrape
        # interval to be cleaned up (and its credit refunded).
        out["reaped"] = reap(conn, settings, now=now)
        queue = JobQueue(container)
        if scrape_due(settings, now=now):
            out["scrape"] = queue.enqueue(conn, KIND_SCRAPE, user_id=None, params={})
        if purge_due(settings, now=now):
            out["purge"] = queue.enqueue(conn, KIND_PURGE, user_id=None, params={})
            settings.set("scrape.last_purge_at", now.isoformat())
    finally:
        conn.close()
    return out


def run_forever(container: Container | None = None, *, poll_seconds: int = 60) -> None:  # pragma: no cover
    """Service loop: check for due work every `poll_seconds`."""
    container = container or Container.from_env()
    # Apply migrations on startup so the scheduler doesn't tick against a schema
    # that no other service has created yet (serialized by an advisory lock).
    conn = container.connect()
    try:
        apply_pending(conn)
    finally:
        conn.close()
    while True:
        try:
            tick(container)
        except Exception as e:  # noqa: BLE001 — never let one bad tick kill the loop
            print(f"scheduler tick error: {e}")
        time.sleep(poll_seconds)


def main() -> None:  # pragma: no cover
    run_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
