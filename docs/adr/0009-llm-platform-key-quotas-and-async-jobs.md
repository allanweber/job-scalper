# LLM access: a platform key with hard quotas, BYO to lift limits, and async job execution

Every user starts on a **platform-provided LLM key** (the operator pays), subject to
**hard, admin-configurable quotas**: drafts/mo, profile-builds/mo, enrich/mo, and
scrapes/day (plus a scrape cooldown), with a per-request token ceiling as a backstop.
**Adding a personal Anthropic/OpenAI key lifts the LLM-bound limits** — that work runs on
the user's own tokens; infra limits still apply by plan. Providers are Anthropic **and**
OpenAI behind the existing swappable `LLMProvider` interface.

Platform-key work uses admin-configured **low-cost models**; BYO work uses an
admin-configured **higher-quality model** — both live in the hot `settings` table. BYO keys
are **encrypted at rest** (envelope; master key in env) and each ciphertext carries a
**key-version** tag so rotation is a background re-encrypt. The platform key stays in env.

**All slow operations run as async RQ jobs** (`job_id` + polling): scrape,
profile-from-resume, draft, and enrich — none may block an HTTP request. **Enrichment is
cached and shared across users** by `(posting, profile_hash, model)` (its inputs are public
posting text + profile criteria, not the resume); **drafts are strictly per-user**. Per-user
token usage is tracked for quota enforcement and admin visibility. Semantic scoring is
dropped for MVP; enrichment is on-demand per job.

## Considered options

- **BYO key required for everyone** — no operator LLM cost, but a "paste an API key before
  you can do anything" wall that most sign-ups would bounce off. Rejected: the platform key
  removes that funnel.
- **Platform key only, no BYO** — simplest UX, but the operator eats 100% of LLM cost with
  no escape valve for heavy users. Rejected.
- **Unified credits / per-user token budget** instead of per-action counters — flexible or
  tighter cost control respectively, but credits are more to build and a raw token budget is
  opaque to users. Rejected for per-action monthly counters + a token ceiling backstop.
- **Synchronous LLM/scrape calls** — simpler flow, but 30–60s requests time out and drop on
  mobile networks. Rejected for async jobs across the board.
- **Strictly per-user enrichment cache** — cleaner privacy story, but re-pays platform
  tokens for identical public-posting enrichments. Rejected; drafts stay private, enrichment
  is shared.

## Consequences

The operator carries free-tier LLM cost, so quota tuning is a first-class, hot-editable
concern and usage accounting is mandatory. Two key-routing paths (platform vs BYO) and two
model tiers must be threaded through every LLM call site. The shared enrichment cache keys on
profile criteria, so identical free-tier profiles benefit each other; drafts never leak
across tenants. Async execution makes `job_id` + polling the uniform client contract for all
heavy actions.
