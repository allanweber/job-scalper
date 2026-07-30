# PostgreSQL on Dokploy

Job Scalper stores everything in a single multi-tenant **PostgreSQL** database,
run as a **managed Dokploy Postgres service** (ADR 0012). Dokploy handles the
volume, and its built-in **scheduled backups to S3-compatible storage** cover the
whole "how do I back this up" problem — no self-managed dumps.

The app talks to Postgres via `psycopg`; local development and CI fall back to
sqlite automatically (no server needed), so the same code and migrations run
everywhere.

## 1. Create the Postgres service

In Dokploy: **Create Service → Database → PostgreSQL**.

| Setting | Value |
| --- | --- |
| Name | e.g. `job-scalper-db` |
| Database | `scalper` |
| User | `scalper` |
| Password | a long random value |
| Image tag | pin a version, e.g. `postgres:16` |

Do **not** expose it publicly — keep it on Dokploy's internal network. Dokploy
shows an **internal connection string / hostname**; you'll use that.

## 2. Point the app at it

In the app stack's `.env` (see `.env.example`), set:

```dotenv
SCALPER_DATABASE_URL=postgresql://scalper:<password>@<internal-host>:5432/scalper
```

`<internal-host>` is the Postgres service's internal hostname from Dokploy. For
the app containers to resolve it, the app stack joins Dokploy's shared network —
`docker-compose.yml` already declares `dokploy-network` as an external network on
the api/worker/scheduler services.

## 3. Migrations

Schema is managed by the app's numbered-`.sql` migration runner (tracked in a
`schema_migrations` table) and **applied automatically on API/admin startup** —
no manual step for a normal deploy.

## 4. Backups (the easy part now)

Enable Dokploy's **scheduled backups** on the Postgres service:

- Add an **S3 destination** (any S3-compatible bucket — **Cloudflare R2** is a
  great fit: create a bucket + R2 API token, use the `https://<accountid>.r2.cloudflarestorage.com`
  endpoint).
- Set a **schedule** (e.g. daily) and a **retention** count.
- Dokploy runs `pg_dump` on that schedule and ships the dump to your bucket.

Restore is a standard `pg_restore`/`psql` of a chosen dump into the service (or a
fresh one). **Test a restore once before you have real users.**

Still keep `SCALPER_ENC_KEYS` backed up separately (a password manager): a DB
restore can't decrypt users' BYO LLM keys without the encryption master key.

## 5. Encoding

Use a **UTF-8** database (Dokploy's Postgres images default to UTF-8). Avoid
`SQL_ASCII` — `psycopg` returns text columns as raw bytes under `SQL_ASCII`.

## 6. Scaling / notes

- One database holds everything; a single managed Postgres handles the MVP and
  well beyond. Redis (job queue + admin sessions) stays in the app stack and
  needs no backup — it's ephemeral.
- Moving hosts later is just a new `SCALPER_DATABASE_URL` (dump/restore across
  Postgres instances is standard).

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| App can't reach the DB | App stack isn't on `dokploy-network`, or wrong internal hostname/port in `SCALPER_DATABASE_URL`. |
| `password authentication failed` | Credentials in `SCALPER_DATABASE_URL` don't match the service. |
| Text comes back as bytes / weird errors | Database is `SQL_ASCII`; recreate it as UTF-8. |
| `psycopg` not installed | Deploy image must install `.[api]` (it does); locally use `pip install -e '.[api]'`. |
