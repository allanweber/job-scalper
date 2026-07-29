"""RQ worker entrypoint: drains the 'scalper' job queue (ADR 0009).

Runs as its own Dokploy service. Jobs are enqueued as `execute_job(job_id)`; this
worker imports and runs them, each rebuilding its own container + DB connection
from env. In local/CI (no Redis) jobs run eagerly in-process and this isn't used.
"""

from __future__ import annotations

import os


def main() -> None:  # pragma: no cover - requires Redis
    from redis import Redis
    from rq import Queue, Worker

    redis_url = os.environ.get("SCALPER_REDIS_URL") or os.environ.get("REDIS_URL")
    if not redis_url:
        raise RuntimeError("SCALPER_REDIS_URL (or REDIS_URL) is not set")
    connection = Redis.from_url(redis_url)
    worker = Worker([Queue("scalper", connection=connection)], connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":  # pragma: no cover
    main()
