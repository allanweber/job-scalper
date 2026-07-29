# The tool becomes a multi-tenant service: tenant-native core, FastAPI, libsql, shared pool

Job Scalper is extended from a single-user local CLI into a hosted, multi-tenant service
(API + Flutter Android app + admin web app), self-deployed to Dokploy. The core is
**rewritten tenant-native**: `user_id` is pushed through the command layer and the store,
and per-user config (profile, sources, keys, quotas) is read from the database instead of
`config.yaml`. The `scalper` CLI is retained as an admin/ops tool, not an end-user surface.

The web layer is **FastAPI** (the codebase is already pydantic v2, so domain models are the
API schema and an OpenAPI spec drives a typed Dart client). The database is **libsql** via
a self-hosted single-node **`sqld`**, accessed with **raw SQL + a numbered-`.sql` migration
runner** (no ORM). Job postings live in **one shared pool, deduped at storage-time** (one
physical row per `dedup_key`, contributing sources retained on the row), with **per-user
overlay tables** for seen/saved/drafted/scores and a per-user last-seen timestamp.

## Considered options

- **Per-user Config assembler over the existing commands** — smaller change, but leaves a
  yaml-shaped seam and pushes tenancy into an adapter rather than the domain. Rejected in
  favour of a clean tenant-native core.
- **Flask / Litestar** instead of FastAPI — Flask is sync-first with no native pydantic or
  OpenAPI; Litestar is fine but smaller-ecosystem. FastAPI fits an async, pydantic,
  mobile-backing API best.
- **SQLModel/SQLAlchemy ORM** — nicer typing, but libsql's SQLAlchemy dialect is immature
  and it would rewrite the whole raw-SQL data layer. Rejected.
- **Fully per-user postings** — trivial isolation but redundant scraping/storage across
  users searching the same terms. Rejected for the shared pool + overlay.
- **Database-per-tenant** — incompatible with a shared postings pool; rejected in favour of
  a single multi-tenant database scoped by `user_id`.

## Consequences

The proven collect/report/draft logic is preserved but re-plumbed for tenancy, which is the
bulk of Phase 1. A single-node `sqld` is single-writer (WAL + busy-timeout, bulk writes via
workers) — an accepted MVP ceiling. Storage-time dedup diverges from the CLI's report-time
dedup, so ingestion gains a merge step. The shared pool means a user's feed and scraping are
both filtered to the user's allowed sources, so the free-tier "3 boards" limit is real rather
than cosmetic.
