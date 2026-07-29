# Job Scalper — SaaS Design

> The architecture for extending the single-user `scalper` CLI into a multi-tenant
> service: a Python API, a Flutter Android app, and an admin web app. This is the
> master spec; individual load-bearing decisions have their own ADRs (0008–0010).
> Where this document and `CONTEXT.md` disagree, `CONTEXT.md` describes the *original
> personal tool* and this document describes the *service* it is becoming.

## What changes, and why it isn't "just an API on top"

The CLI was built single-user and local: config is a git-ignored `config.yaml`
(profiles, LLM key, sources), the store is a local SQLite file with no owner, job
postings are one shared pool, scraping runs synchronously, and drafts/PDFs are written
to local folders. The command layer (`scalper.commands.*`) was deliberately kept
front-end-agnostic, which helps — but the service still requires a **tenant-native
rewrite** of the core: `user_id` pushed through the commands and the store, and config
sourced from the database rather than YAML.

## Product

- **Multi-tenant SaaS**, self-deployed to a **Dokploy** environment (Docker).
- Surfaces:
  - **Public HTTP API** + **Flutter Android app** — end users.
  - **Admin web app** — operators.
- **Remote-first** job product (the structured sources are remote-centric).
- Features: profile-from-resume, scrape jobs, draft tailored resume + cover letter.
- **Free tier:** 1 profile, up to 3 user-chosen boards. A `plan`/quota model exists;
  **no payment integration yet.**

## Backend & core

- **FastAPI** (async web layer). The codebase is already pydantic v2, so the domain
  models double as request/response schemas.
- **Tenant-native core:** `user_id` flows through the commands and store; per-user
  config (profile, sources, keys, quotas) is read from the DB, not `config.yaml`.
- The **`scalper` CLI is kept as an admin/ops tool** (run collect, inspect the pool,
  manage users) — not an end-user surface.
- **Data access:** raw SQL against the libsql client + a **numbered-`.sql` migration
  runner** (tracked in a `schema_migrations` table, applied on startup).
- **All heavy operations run as async RQ jobs** returning a `job_id` the client polls:
  scrape, profile-from-resume, draft, and enrich. Nothing slow blocks an HTTP request.

## Data model (single multi-tenant libsql database)

- **Self-hosted `sqld`**, single node, **WAL + busy-timeout**. The single-writer ceiling
  is accepted for MVP; bulk writes funnel through workers. See `deployment/sqld-dokploy.md`.
- **Shared postings pool, deduped at storage-time:** one physical row per `dedup_key`;
  the contributing sources are retained as a list on the row so provenance isn't lost.
- **Per-user overlays:** seen / saved / drafted / scores, plus a per-user last-seen
  timestamp that drives the feed's "new" badge.
- **Resumes:** stored per user as a libsql BLOB + an extracted-text column.
- **Drafts:** markdown + WeasyPrint-rendered PDF blobs, **private per user**, never shared.
- **Retention:** a scheduled auto-purge job trims postings older than an
  admin-configurable window; the admin panel also has a manual purge.

## Auth

- **Mobile:** native Google Sign-In → the app posts the Google **ID token** once →
  backend verifies it against Google's keys, upserts the user by `sub`/email, and issues
  its **own short-lived access JWT + a revocable refresh token** (stored in DB).
- **Admin:** Google **web** OAuth redirect, gated by an **admin-email allowlist** (env);
  a **server-side session cookie** (session store in Redis) keeps admins logged in.
- Multiple Google OAuth client IDs are involved (Android client, a server/audience client
  used to verify mobile ID tokens, and a web client for the admin app).

## LLM (platform key + BYO)

- **Every user starts on a platform-provided key** (the operator pays), subject to hard
  quotas. **Adding a personal Anthropic/OpenAI key lifts the LLM-bound limits** — that
  work then runs on the user's own tokens (effectively unlimited LLM); infra limits like
  the scrape cooldown still apply by plan.
- **Providers:** Anthropic **and** OpenAI, behind the existing swappable `LLMProvider`
  interface (an OpenAI provider is added).
- **Model policy (hot settings):** platform-key work uses admin-configured low-cost
  models; BYO work uses an admin-configured higher-quality model.
- **Free-tier hard limits** (admin-set, monthly reset): drafts/mo, profile-builds/mo,
  enrich/mo, and **scrapes/day** (plus the cooldown). A **per-request token ceiling** is a
  backstop so one pathological resume can't blow the bill. At a limit: block + prompt to
  add a personal key or wait for reset.
- **BYO keys are encrypted at rest** (envelope, master key from env/secret); each
  ciphertext is **tagged with a key-version** so future rotation is a background
  re-encrypt, not a migration. The platform key lives in env/secret, never the DB.
- **Caching:** enrichment (derived from public posting + profile criteria, no personal
  resume) is cached and **shared across users** by `(posting, profile_hash, model)` to
  save platform tokens; **drafts are strictly per-user**. Per-user token usage is tracked
  for quotas and admin visibility.
- **Semantic scoring is dropped for MVP** (deterministic skill/title/keyword scoring;
  workers stay light — no PyTorch). **Enrichment is on-demand per job.**

## Scraping / jobs

- **Structured API sources only** for now — no Playwright/Chromium; the "hard" sources
  (LinkedIn/Indeed) are deferred pending a deliberate legal posture, since operating them
  commercially for many users is materially different from the original personal use.
- **RQ + Redis**, sync workers in a separate container.
- **On-demand scrape** (async job + poll) **and** a **scheduled collect** (a Dokploy cron
  task enqueuing RQ jobs). Both write the shared pool.
- **The "3 boards" limit gates both scraping and feed visibility:** a user's scrape only
  touches their chosen sources, and their feed only shows postings from those sources —
  otherwise the limit would be cosmetic in a shared pool.
- **Feed** = the full ranked list of pool postings matching the user's profile (within
  their allowed sources), with a per-user "new" badge derived from last-seen.

## Mobile

- **Flutter (Android), Riverpod**, repository pattern over a **typed Dart client
  generated from the OpenAPI spec**. The app renders a native JSON feed, not the HTML report.
- Drafting: **pool postings (by uid) for free users**; **arbitrary-URL drafting is gated
  to BYO-key / paid users** and SSRF-hardened (block private ranges / egress control).

## Admin web app

- **FastAPI + Jinja2 + HTMX** (same codebase, no separate JS build), run as its **own
  Dokploy service on a separate subdomain** so it can be network-isolated independently.
- **Capabilities:** global settings / management config; user management
  (list/search/suspend/delete + data deletion); plan/quota overrides; job/queue + pool
  monitoring (queue depth, running/failed jobs with retry/cancel, pool counts, purge).
- **Settings** live in a libsql `settings` table, **hot-applied** (short cache, no
  redeploy). Secrets (admin allowlist, master key, DB URL, OAuth secrets, platform LLM key)
  stay in env.
- **`admin_audit`** records who/what/when/before→after on every state-changing action.

## Channel security

- **HTTPS/TLS (terminated by Dokploy) + JWT** only — no certificate pinning or
  application-layer payload encryption.

## Uploads & legal

- Uploads: admin-configurable **size cap**, **PDF/markdown/plain-text allowlist**, and a
  clear error when text extraction yields nothing (scanned/image-only PDF). No AV/OCR at MVP.
- **Basic ToS + Privacy Policy stubs** are served via the API (resumes are sensitive PII);
  consent is captured at sign-up. GDPR-style deletion is covered by admin user-delete.

## Dokploy footprint

Public API · Admin app (separate service/subdomain) · RQ worker · Redis (job queue +
admin sessions) · `sqld` · Dokploy cron (scheduled collect + auto-purge).

## Phasing

1. **Core tenant-native refactor** + libsql store (storage-time dedup, per-user overlays)
   + schema (`users`, roles, plans, tokens, sessions, `resumes`, `drafts`, `settings`,
   `admin_audit`, usage) + migration runner.
2. **Auth** (mobile JWT + admin session) + user/role/plan model + admin allowlist +
   encrypted BYO keys (version-tagged) + the quota engine.
3. **Public API + RQ worker:** async scrape/profile/draft/enrich, match feed, quotas +
   cooldown, platform-vs-BYO key routing, shared-enrichment cache.
4. **Admin web app** (HTMX): settings, users, plan/quota, queue/pool, audit.
5. **Dokploy deployment** (all services) + `sqld` docs + ToS/Privacy stubs.
6. **Flutter app** against the generated client.

## Knobs to pick at build time (not blockers)

Exact free-tier numbers (drafts/mo, profile-builds/mo, enrich/mo, scrapes/day, cooldown
minutes, per-request token ceiling); the 3 default sources; default platform vs BYO model
IDs; the retention window.
