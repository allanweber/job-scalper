# Deploying to Dokploy behind a Cloudflare Tunnel

This is the end-to-end setup for the chosen topology: **one Docker Compose stack**
on Dokploy (api + admin + worker + scheduler + Redis) plus a **managed Dokploy
PostgreSQL** service, fronted by a **Cloudflare Tunnel** — no public inbound ports
on the server. Work through the steps in order; each produces a value you paste
into the next.

The stack files live at the repo root: `Dockerfile`, `docker-compose.yml`,
`.env.example`.

---

## 0. Prerequisites

- A domain on **Cloudflare** (DNS managed by Cloudflare). We'll use
  `api.example.com` and `admin.example.com` — substitute your own.
- A **Dokploy** server you can log into.
- A **Google Cloud** project (for Sign-In / OAuth).
- An **Anthropic API key** (the platform key that free users run on).

---

## 1. Google OAuth clients

In **Google Cloud Console → APIs & Services → Credentials**:

1. **OAuth consent screen** — configure it (External, add your email as a test
   user while unverified).
2. **Android client** (for the mobile app, Phase 6): *Create credentials → OAuth
   client ID → Android*. Note the **client ID**.
3. **Web client for the mobile audience**: *Create credentials → OAuth client ID
   → Web application*. This is the `aud` the backend verifies mobile ID tokens
   against. Note its **client ID**.
4. **Web client for the admin app**: another *Web application* client.
   - **Authorized redirect URI:** `https://admin.example.com/auth/callback`
   - Note its **client ID** and **client secret**.

You now have: android client id, mobile-audience client id, admin client id +
secret.

---

## 2. Generate secrets

Run these locally (or on the server) and keep the output:

```bash
# JWT signing secret
python -c "import secrets; print('SCALPER_JWT_SECRET=' + secrets.token_urlsafe(48))"

# Admin session cookie secret
python -c "import secrets; print('SCALPER_ADMIN_COOKIE_SECRET=' + secrets.token_urlsafe(48))"

# BYO-key encryption master key (version 1)
python -c "from scalper.service.crypto import generate_master_key_b64 as g; import json; print('SCALPER_ENC_KEYS=' + json.dumps({'1': g()}))"
```

(The last one needs the package importable: `pip install -e '.[api]'` in a checkout.)

---

## 3. Cloudflare Tunnel

In the **Cloudflare dashboard → Zero Trust → Networks → Tunnels**:

1. **Create a tunnel** (Cloudflared type). Name it e.g. `job-scalper`.
2. On the "Install connector" screen, **copy the tunnel token** (the long string
   after `--token`). That's `CLOUDFLARE_TUNNEL_TOKEN`. You do **not** run the
   install command — our `cloudflared` compose service uses the token.
3. Add **Public Hostnames** (routes) on the tunnel:

   | Subdomain | Domain        | Service (type → URL)      |
   |-----------|---------------|---------------------------|
   | `api`     | `example.com` | `HTTP` → `api:8080`       |
   | `admin`   | `example.com` | `HTTP` → `admin:8081`     |

   Cloudflare creates the `api` / `admin` DNS records automatically and proxies
   them. The service URLs use the **compose service names** on the internal
   network — that's why nothing needs a public port.

> TLS is terminated at Cloudflare; traffic to the origin rides the tunnel. The
> app runs with `--proxy-headers`, so it honours the forwarded HTTPS scheme when
> building the admin OAuth redirect URI.

---

## 4. Create the managed Postgres service

**Create Service → Database → PostgreSQL** (database `scalper`, user `scalper`, a
strong password, pinned image e.g. `postgres:16`). Keep it internal (no public
domain). Copy its **internal connection URL** — you'll paste it into
`SCALPER_DATABASE_URL`. Full details + backups: `postgres-dokploy.md`.

## 5. Deploy the stack in Dokploy

1. **Create a Compose** service pointing at this repo (branch with these files),
   or paste `docker-compose.yml` directly. It joins Dokploy's `dokploy-network`
   so it can reach the Postgres service above.
2. **Environment**: copy `.env.example` into the service's env / an `.env`, and
   fill every value:
   - `SCALPER_DATABASE_URL=postgresql://scalper:<password>@<pg-internal-host>:5432/scalper`
   - `SCALPER_REDIS_URL=redis://redis:6379/0`
   - `SCALPER_JWT_SECRET`, `SCALPER_ADMIN_COOKIE_SECRET`, `SCALPER_ENC_KEYS` from
     step 2.
   - `SCALPER_GOOGLE_AUDIENCES=` the android + mobile-audience client ids
     (comma-separated).
   - `SCALPER_ADMIN_GOOGLE_CLIENT_ID` / `SCALPER_ADMIN_GOOGLE_CLIENT_SECRET` from
     step 1.4.
   - `SCALPER_ADMIN_EMAILS=` your Google email (grants you admin).
   - `SCALPER_ADMIN_BASE_URL=https://admin.example.com`
   - `SCALPER_PLATFORM_ANTHROPIC_KEY=` your Anthropic key.
   - `CLOUDFLARE_TUNNEL_TOKEN=` from step 3.
3. **Backups**: enable Dokploy's **scheduled backups** on the Postgres service
   (S3/R2 destination + schedule). The compose's only volume is `redis-data`,
   which is ephemeral and needs no backup.
4. **Deploy.** On first boot the API/admin apply DB migrations automatically.

---

## 6. Verify

```bash
curl https://api.example.com/healthz     # {"message":"ok"}
curl https://api.example.com/readyz      # {"message":"ready"}  (DB reachable)
curl https://api.example.com/legal/tos   # ToS stub JSON
```

Open `https://admin.example.com` → **Sign in with Google** with an allowlisted
email → you land on the dashboard.

---

## 7. First-run configuration (in the admin app)

1. **Settings** — review the seeded hot settings: `scrape.interval_minutes`,
   `sources.enabled`, `sources.default`, `quota.free`, `llm.platform_models`,
   `retention.days`, `upload.max_bytes`. Adjust to taste; saves are audited.
2. **Jobs & Pool → Run scrape now** — kicks off the first pool fill (the
   scheduler will then run it every `scrape.interval_minutes`). With no active
   users yet it uses the fallback terms; once users build profiles the scope
   becomes the union of their terms.
3. **Users** — appears as people sign in from the app (Phase 6).

---

## Notes & operations

- **Database + backups:** a managed Dokploy Postgres service with scheduled
  backups to S3/R2 — see `postgres-dokploy.md`. Nothing to hand-roll.
- **Key rotation:** add a new version to `SCALPER_ENC_KEYS`
  (`{"1":"…","2":"…"}`) and bump `SCALPER_ENC_ACTIVE_VERSION=2`; old ciphertexts
  still decrypt with v1 (envelope encryption is version-tagged). Back up
  `SCALPER_ENC_KEYS` separately — a DB restore can't decrypt BYO keys without it.
- **Worker/scheduler share the image**, so a single rebuild updates every
  process. Redis-backed jobs run on the `worker`; the `scheduler` only enqueues.
- **The DB is internal:** the Postgres service has no public hostname; only the
  app stack reaches it over `dokploy-network`.
