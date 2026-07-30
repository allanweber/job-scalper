# Switch the service database from self-hosted libsql/sqld to managed PostgreSQL

- Status: accepted
- Supersedes the database choice in ADR 0008 (tenant-native core, FastAPI, **libsql**).

## Context

ADR 0008 chose a self-hosted single-node **`sqld`** (libsql) as the service
database, on the reasoning that it mirrors the original CLI's SQLite store and
migrating to Turso later would be a config change. In practice, before any
production use, the operational cost showed up first in **backups**: a
self-hosted `sqld` on a Docker volume has no turnkey backup story — you're left
hand-rolling consistent snapshots (online `.backup`/`VACUUM INTO`, or
stop-copy-start), wiring them to object storage, and testing restores yourself.
For a solo-operated Dokploy deployment that's disproportionate toil.

The deployment target (Dokploy) offers **managed PostgreSQL as a first-class
service with scheduled backups to S3-compatible storage** built in. That erases
the backup problem entirely and is a more familiar, better-supported database.

Nothing is in production yet, so there is no data migration to worry about.

## Decision

Use **PostgreSQL** as the service database, run as a **managed Dokploy Postgres
service** (separate from the app compose stack). Access it with **`psycopg`
(psycopg3)**.

Keep the data layer's raw-SQL, DB-API style unchanged by introducing a **thin
dialect adapter** in `scalper.db.connection`:

- The repositories and `.sql` migrations are written once in the sqlite style
  (`?` placeholders, positional rows, `executescript`).
- For Postgres, the adapter translates `?` → `%s` and the only DDL difference we
  use (`BLOB` → `BYTEA`), and runs migration scripts statement-by-statement.
- With **no Postgres URL configured, the factory falls back to sqlite**, so local
  development and CI stay fast and server-free.

The database is selected by `SCALPER_DATABASE_URL` (`DATABASE_URL` accepted as an
alias). Migrations still auto-apply on startup. Redis (job queue + admin
sessions) is unchanged and stays in the app stack.

CI runs the **full test suite against both** sqlite and a real Postgres service,
so dialect regressions are caught automatically.

## Consequences

- **Backups become trivial** — Dokploy's scheduled `pg_dump` to S3/R2; restore is
  standard `pg_restore`. This was the motivating win.
- **A more capable database** (proper concurrency, types, tooling) with no
  single-writer WAL ceiling to reason about.
- **Minimal code churn**: the adapter localizes the dialect differences to one module;
  repositories, migrations, and tests are essentially unchanged. Two portability
  fixes were needed — `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING`, and
  qualifying a self-referential upsert (`count = usage_counters.count + …`).
- **Encoding matters**: the database must be UTF-8 (psycopg returns text as raw
  bytes under `SQL_ASCII`).
- The "Turso later" escape hatch from ADR 0008 is dropped; the new escape hatch
  is "any Postgres host", which is more portable and standard.
- The libsql client dependency is removed from the `[api]` extra in favour of
  `psycopg[binary]`.
