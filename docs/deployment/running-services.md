# Running the service processes (Phase 3)

Phase 3 adds three long-running processes plus the shared database. They are all
one codebase; each is a different entrypoint. Full Dokploy wiring lands in Phase 5
— this documents the process contract so the pieces can be run anywhere.

## Processes

| Process    | Command                                                            | Role |
|------------|-------------------------------------------------------------------|------|
| Public API | `uvicorn --factory scalper.service.app:create_app --host 0.0.0.0 --port 8080` | Serves the HTTP API (OpenAPI at `/docs`). |
| Worker     | `scalper-worker` (`python -m scalper.service.worker`)             | Drains the RQ `scalper` queue (profile/draft/enrich jobs). |
| Scheduler  | `scalper-scheduler` (`python -m scalper.service.scheduler`)       | Enqueues scrape on `scrape.interval_minutes` + daily auto-purge. |

Install with the service extras: `pip install -e '.[api]'`.

The API applies pending DB migrations on startup, so a fresh database is
self-provisioning. Migrations are also applied by the CLI/tests via
`scalper.db.apply_pending`.

### Jobs without Redis

If `SCALPER_REDIS_URL` (or `REDIS_URL`) is **unset**, jobs run **eagerly**
in-process (the enqueue call executes the work synchronously). This is what local
dev and CI use — no worker or Redis required. Set the Redis URL to switch to the
real queue + worker.

## Environment

Secrets stay in the environment; hot runtime config lives in the `settings` table
(edited from the admin app in Phase 4).

| Variable | Required | Purpose |
|----------|----------|---------|
| `SCALPER_GOOGLE_AUDIENCES` | yes | Comma-separated Google OAuth client IDs accepted when verifying mobile ID tokens. |
| `SCALPER_JWT_SECRET` | yes | HS256 secret for access JWTs. |
| `SCALPER_ACCESS_TTL` / `SCALPER_REFRESH_TTL` | no | Access/refresh token lifetimes in seconds (defaults: 900 / 30 days). |
| `SCALPER_ADMIN_EMAILS` | no | Comma-separated admin allowlist (source of truth for the `admin` role). |
| `SCALPER_ENC_KEYS` | for BYO keys | JSON `{"<version>": "<base64 32-byte key>"}` master keys for BYO-key encryption. Absent ⇒ BYO keys disabled (API returns 503). |
| `SCALPER_ENC_ACTIVE_VERSION` | no | Master-key version used for new encryptions (defaults to the highest present). |
| `SCALPER_PLATFORM_ANTHROPIC_KEY` | for platform LLM | Platform Anthropic key all free users run on (operator pays). `SCALPER_PLATFORM_LLM_KEY` is an alias. |
| `SCALPER_PLATFORM_LLM_PROVIDER` | no | Platform provider (default `anthropic`). |
| `SCALPER_REDIS_URL` / `REDIS_URL` | for the queue | Redis URL for the RQ queue. Unset ⇒ eager in-process jobs. |
| `SCALPER_DATABASE_URL` | prod DB | PostgreSQL URL (`postgresql://user:pass@host:5432/db`); `DATABASE_URL` is accepted as an alias. Unset ⇒ local sqlite fallback (`SCALPER_DB_PATH`). See `postgres-dokploy.md`. |
| `SCALPER_DB_PATH` | no | Local sqlite path when no Postgres URL is set (default `scalper-service.db`). |
| `SCALPER_CORS_ORIGINS` | no | Comma-separated allowed CORS origins (default `*`). |

## Health

- `GET /healthz` — process is up (no DB touch).
- `GET /readyz` — DB connection + schema reachable (a trivial pool query).
