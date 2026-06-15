# Job Scalper — Build Plan

Living roadmap of remaining work to finish the project. Decisions behind these tasks
live in [`docs/adr/`](docs/adr/); vocabulary in [`CONTEXT.md`](CONTEXT.md). Update the
status boxes as work lands.

## Status snapshot (2026-06-15)

**Pivot (ADR 0005):** sources are now **company-agnostic** and **query-driven**. The early
company-keyed ATS adapters (greenhouse/lever/ashby) were removed; `collect` is driven by a
global `search:` block (`SearchQuery`) and the adapter contract is `fetch(query)`.

**Done:**
- ✅ `JobPosting` + `SearchQuery` models, SQLite store, collect/report split (ADR 0002/0005)
- ✅ Adapter contract + registry (ADR 0001/0005); **11 company-agnostic adapters**:
  remotive + jobicy + adzuna (search), remoteok + arbeitnow + themuse + workingnomads +
  himalayas (broad feed), weworkremotely (RSS), hackernews (Who's Hiring), reddit (Atom RSS).
  All keyless except adzuna (free key; skipped when unset).
- ✅ Stage 1 deterministic scoring + hard filters (ADR 0003)
- ✅ Self-contained HTML report (client-side sort/filter)
- ✅ `backend` + `java` profiles; java tech tokens in the global search
- ✅ Tests (28 passing); verified live (283 postings across the active sources, cross-company)

**Inert until built:** the `semantic` scoring component (weight renormalizes out) and the
Stage 2 LLM layer. The `semantic_scorer` hook in `scoring.py` is the wiring point.

---

## Phase 1 — Semantic similarity (Stage 1 completion)

Goal: turn on the `semantic` component so scoring catches relevant roles that don't
literally contain the skill keywords. Local embeddings, zero marginal cost (ADR 0003).

- [ ] Add `scalper/semantic.py`: a `SemanticScorer` implementation using
      `sentence-transformers` (default model `all-MiniLM-L6-v2` or `bge-small-en-v1.5`).
- [ ] Build the profile "criteria text" (titles + skills + keywords) once per report;
      embed each posting's `search_text`; score = cosine similarity in [0,1].
- [ ] Cache posting embeddings in SQLite keyed by `uid` + model name (recompute only on
      new/changed postings) so reports stay fast.
- [ ] Make it optional: import lazily; if `sentence-transformers` isn't installed, the
      hook returns `None` and weights renormalize (current behavior). Extra: `[semantic]`.
- [ ] Wire into `cmd_report` (pass the scorer to `score_all`) behind a `--no-semantic` flag.
- [ ] Tests: cosine of identical text ≈ 1.0; unrelated text low; cache hit path.
- **Acceptance:** with `[semantic]` installed, semantic column appears in the report
      breakdown and meaningfully reorders results; without it, behavior is unchanged.

## Phase 2 — Stage 2 LLM enrichment

Goal: on the shortlist only, generate the summary + skill-gap narrative (ADR 0003).
Cheap model by default, behind a swappable interface (ADR 0004 per-task model config).

- [ ] `scalper/llm/base.py`: `LLMProvider` protocol (`complete(prompt, *, model, ...)`),
      plus a registry/factory keyed by provider name.
- [ ] `scalper/llm/anthropic_provider.py`: default impl, model `claude-haiku-4-5` for
      enrichment. Extra: `[llm]`. Read API key from env (`ANTHROPIC_API_KEY`).
- [ ] `scalper/enrich.py`: take top-N scored postings (threshold/`--top` from config/CLI),
      produce a structured result (1–2 sentence summary, have/missing skill notes,
      optional low-confidence flag). Keep prompt small (title + trimmed description +
      profile criteria) to bound cost.
- [ ] Cache enrichment in SQLite keyed by `uid` + profile hash + model so re-reports are free.
- [ ] Config: `llm:` block (provider, enrich model, build model, top_n, on/off);
      per-task model selection (enrich vs. build) lands here for ADR 0004 reuse.
- [ ] Report: render summary + skill-gap into the detail panel; gracefully omit when
      enrichment is disabled or unavailable.
- [ ] Tests: enrichment with a stub provider (no network); cache hit; disabled path.
- **Acceptance:** `scalper report --profile X --enrich` adds LLM summaries to the top N
      only; cost is bounded by `top_n`, not collection volume; re-runs hit cache.

## Phase 3 — More structured adapters

Goal: broaden coverage with more company-agnostic API/RSS sources (the reliable backbone).
Each is one new module + registration; the core stays untouched (ADR 0001/0005). Each must
consume `SearchQuery` — a search source issues a native query, a broad-feed source filters
locally with `matches_any_term`.

- [x] **Remotive** — `https://remotive.com/api/remote-jobs` (search source).
- [x] **RemoteOK** — `https://remoteok.com/api` (broad feed; attribution UA set).
- [x] **Jobicy** — `https://jobicy.com/api/v2/remote-jobs` (search source via `tag`).
- [x] **Arbeitnow** — `https://www.arbeitnow.com/api/job-board-api` (broad feed, paginated).
- [x] **The Muse** — `https://www.themuse.com/api/public/jobs` (broad feed, category + paginated).
- [x] **Working Nomads** — `https://www.workingnomads.com/api/exposed_jobs/` (broad feed).
- [x] **Himalayas** — `https://himalayas.app/jobs/api` (broad feed, paginated, structured salary).
- [x] **We Work Remotely** — programming category RSS (broad feed; shared `rss_items` helper).
- [x] **Adzuna** — official search API; free `app_id`/`app_key` (config/env); skips if unset.
- [x] **Hacker News "Who's Hiring"** — Algolia API; finds the monthly thread, parses comments.
- [x] **Reddit** — job subreddits via public `.rss` (Atom); no account. Polite delay + 429
      retry, fail-soft. Best run from a home IP (see below).
- [ ] Promote the RSS/Atom helpers into a fully generic, mapping-driven adapter (declarative tier).
- [x] Per-adapter offline parsing tests with a captured sample payload.

Note: there are no public *Java-only* job-board APIs; Java focus is delivered by (a) the
`java` tech token in the global search (tag/keyword sources) + local term filtering, and
(b) a dedicated `java` profile that re-scores at report time.
- **Acceptance:** each adapter searches live with the global query and its postings
      score/report like the rest.

## Phase 4 — Hard sources (LinkedIn, Indeed)

Goal: best-effort coverage of the hostile sources via self-hosted Playwright, **anonymous
only, never the user's credentials**, low-frequency (ADR design + CONTEXT.md). Treat as
fragile gap-fillers, not the backbone.

- [ ] Add `[scrape]` extra (playwright) + `playwright install` doc step.
- [ ] `scalper/sources/_browser.py`: shared headless-browser helper (stealth-ish config,
      polite delays, per-source rate caps, retry/backoff, timeout, graceful failure).
- [ ] **LinkedIn** adapter: anonymous guest jobs endpoints only; map to `JobPosting`;
      expect breakage — keep parsing isolated and well-logged.
- [ ] **Indeed** adapter: Cloudflare-aware; accept partial/failed runs without aborting
      `collect` (already isolated per-source in the CLI).
- [ ] Mark these `tier = hard`; surface tier in the report so reliability is legible.
- [ ] Document the risk + low-frequency guidance in README.
- **Acceptance:** when reachable, hard sources contribute postings; when blocked, the run
      logs and continues without failing other sources.

## Phase 5

- [ ] Optional cross-source dedup as a **reporting-only** toggle (uses the already-stored
      `dedup_key`; ADR 0002) — keep best record, list "also seen on".
- [ ] Salary parsing for sources that expose structured compensation (Remotive `salary` is
      free text; RemoteOK min/max already parsed).
- [ ] Timezone extraction from location strings (currently mostly `None`).
- [ ] `scalper sources` command: list registered adapters / configured sources + counts.
- [ ] Packaging/run docs: cron example (in README), maybe a `--since` report filter.

---

## Working notes

- Live-verified company-agnostic sources (2026-06-15): a full collect pulled ~208 postings
  (remotive 31, remoteok 8, jobicy 53, arbeitnow 24, themuse 2, workingnomads 17,
  himalayas 31, weworkremotely 17, hackernews 25 (capped), reddit 0). The Muse runs low
  because most of its feed is on-site; bump `max_pages`/categories if wanted.
- **Per-source cap**: any source entry may set `limit:` to override the global
  `search.limit_per_source` (config `SourceConfig.limit` → `cmd_collect` clones the query).
  hackernews ships capped at 25. Search sources that union across terms (remotive, jobicy,
  adzuna) cap their final unioned total too, so the limit is honored everywhere.
- **Reddit reality** (diagnosed 2026-06-15): `www.reddit.com/r/{sub}.json` 403s anonymous
  library clients; the `.rss` (Atom) feeds work without an account but are rate-limited (HTTP
  429). In this sandbox's datacenter IP the throttle is brutal — first sub returns 200, the
  rest 429 even after multi-second delays (IP reputation, not burst timing). Residential IPs
  are throttled far more leniently, so anonymous RSS is viable when the user runs it locally
  (the intended deployment). OAuth would lift the limit but requires registering an app, which
  the user can't do — so the adapter stays RSS-only with a polite `delay`, a 429 retry, and
  fail-soft per subreddit. For dedicated job subs (java_jobs, techjobs, …) use
  `hiring_only: false`, since requiring a "[Hiring]" tag would drop real listings.
- **Hacker News** dominates volume (a Who's-Hiring thread has 300+ comments); its config
  `limit: 25` caps it. Comment headers are free text, so company/title parsing is best-effort —
  the full comment is kept as the description, which is what scoring reads.
- New adapters must take `SearchQuery`: search sources query natively; broad-feed sources
  pull recent postings and filter with `matches_any_term` (all words of a term, OR across terms).
- Run tests: `.venv/bin/python -m pytest -q`. Install extras as phases need them.
- Keep the core source-agnostic: new sources should never require touching store/scoring/report.
