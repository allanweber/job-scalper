# Configuring self-hosted libsql (`sqld`) on Dokploy

Job Scalper stores everything in a single multi-tenant **libsql** database, served by a
self-hosted **`sqld`** instance (the libsql server). The API, the RQ worker, and the
scheduled-collect cron all connect to it over the libsql protocol with a URL + auth token —
exactly like Turso, so migrating to Turso Cloud later is a config change, not a rewrite.

This guide covers running `sqld` as its own Dokploy service and pointing the app at it.

## 1. Create the `sqld` service

In Dokploy, add a new **Application** (or a Compose service) using the official image:

```
ghcr.io/tursodatabase/libsql-server:latest
```

Recommended container settings:

| Setting | Value | Notes |
| --- | --- | --- |
| Internal port | `8080` | HTTP/libsql endpoint |
| Command/env | see below | enables auth + persistence |
| Restart policy | `unless-stopped` | |

### Environment variables

```dotenv
# Require a bearer token for all connections (asymmetric or shared-key auth).
# Simplest: a shared token the app presents. Generate a long random value.
SQLD_AUTH_JWT_KEY=        # optional: for JWT-based auth (advanced)
SQLD_HTTP_LISTEN_ADDR=0.0.0.0:8080

# Where the database lives inside the container (mount a volume here — see §2).
SQLD_DB_PATH=/var/lib/sqld/data
```

If you use the simpler shared-token model instead of JWT keys, set the auth token the app
will present (see the image docs for the exact variable of the version you pin — the app
side only needs the matching token in `LIBSQL_AUTH_TOKEN`). **Pin a specific image tag in
production** rather than `latest` so restarts are reproducible.

## 2. Persist the data on a volume

`sqld` is single-node here, so its data must survive restarts and redeploys. Attach a
**Dokploy persistent volume** mapped to the container's `SQLD_DB_PATH`:

```
Volume name:   scalper-sqld-data
Mount path:    /var/lib/sqld/data
```

Without this, a redeploy wipes every user, resume, and posting. Verify the volume is
attached before pointing real traffic at it.

## 3. Expose it privately

The database should **not** be publicly reachable. Prefer Dokploy's internal Docker network
so only the API / worker / cron services can reach `sqld`:

- Give the `sqld` service an internal hostname (e.g. `sqld`) on the shared project network.
- Do **not** attach a public domain to it.

The app then connects to `http://sqld:8080` from inside the network. If you must expose it
(e.g. to run migrations from your laptop), put it behind a subdomain with an IP allowlist and
always require the auth token.

## 4. Point the app at it

The API, worker, and cron read these environment variables (set them on each service in
Dokploy):

```dotenv
LIBSQL_URL=http://sqld:8080        # internal service URL (https:// if TLS-terminated)
LIBSQL_AUTH_TOKEN=<the token>      # must match the sqld auth configuration
```

The data layer uses the libsql Python client with these values; **WAL mode and a
busy-timeout are set by the app on connect** (the single-writer node tolerates concurrent
readers, and bulk writes are funneled through the worker to minimise contention).

## 5. Migrations

Schema is managed by the app's numbered-`.sql` migration runner (tracked in a
`schema_migrations` table) and **applied automatically on API startup**. No manual step is
needed for a normal deploy. To apply migrations out-of-band (e.g. from the ops CLI):

```
scalper admin migrate         # runs pending migrations against LIBSQL_URL
```

## 6. Backups

Because everything is in one database, back it up on a schedule:

- **Simplest:** a Dokploy scheduled job that snapshots the volume (or copies the DB file)
  off-box on a cron.
- **libsql-native:** enable `sqld`'s bottomless/S3 replication if you have object storage —
  set the relevant `SQLD_BOTTOMLESS_*`/S3 env vars for the version you pinned.

Test a restore at least once before you have real users.

## 7. Moving to Turso Cloud later

Nothing in the app assumes self-hosting: point `LIBSQL_URL` / `LIBSQL_AUTH_TOKEN` at a Turso
database instead and the app is unchanged. Do this if you outgrow the single-node write
ceiling or want managed replication/backups.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `database is locked` under load | Concurrent writers on the single node — ensure bulk writes go through the worker; the busy-timeout retries briefly. |
| Data gone after redeploy | The persistent volume isn't attached to `SQLD_DB_PATH`. |
| `401`/auth errors from the app | `LIBSQL_AUTH_TOKEN` doesn't match the `sqld` auth config. |
| App can't reach `sqld` | Service isn't on the same internal network, or wrong internal hostname/port. |
