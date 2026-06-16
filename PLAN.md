# Job Scalper — Build Plan

Living roadmap of remaining work to finish the project. Decisions behind these tasks
live in [`docs/adr/`](docs/adr/); vocabulary in [`CONTEXT.md`](CONTEXT.md). Update the
status boxes as work lands.

**Done:**
- ✅ `JobPosting` + `SearchQuery` models, SQLite store, collect/report split (ADR 0002/0004)
- ✅ Adapter contract + registry (ADR 0001/0004); **13 company-agnostic adapters**:
  remotive + jobicy + adzuna (search), remoteok + arbeitnow + themuse + workingnomads +
  himalayas (broad feed), weworkremotely (RSS), hackernews (Who's Hiring), reddit (Atom RSS).
  All keyless except adzuna (free key; skipped when unset). Plus two **hard (scraped)**
  sources — linkedin + indeed — anonymous only, behind `[scrape]`, off by default.
- ✅ Stage 1 deterministic scoring + hard filters (ADR 0003)
- ✅ Self-contained HTML report (client-side sort/filter)
- ✅ `backend` + `java` profiles; java tech tokens in the global search
- ✅ Tests (112 passing); verified live (470 postings across the active sources, cross-company)

- ✅ **Phase 1: semantic similarity** — local `sentence-transformers` scorer behind the
  `[semantic]` extra, SQLite embedding cache, `--no-semantic` flag; fails soft to the
  deterministic blend when the dep/model is absent.

- ✅ **Phase 2: Stage 2 LLM enrichment** — `LLMProvider` registry + Anthropic provider
  behind the `[llm]` extra; `Enricher` summarizes the top-N shortlist (summary + have/missing
  skills, low-confidence flag), cached in SQLite by uid + profile hash + model; `--enrich` /
  `--top` / `--enrich-model` flags + `llm:` config block. Fails soft to Stage 1 when the
  dep/key is absent; never affects the deterministic Match %.

- ✅ **Phase 4: hard sources** — LinkedIn + Indeed scraped via a shared Playwright helper
  (`sources/_browser.py`) behind the `[scrape]` extra, **anonymous only**, off by default.
  `tier = hard`, surfaced as a report badge + footer note. Parsing isolated and tested
  offline; every fetch fails soft (blocked / challenged / extra-absent → no postings, never
  aborts collect).

- ✅ **Phase 5: reporting polish & operability** — `report --dedup` (cross-source dedup with
  "also seen on"), `report --since <DAYS|DATE>`, free-text salary parsing (Remotive) +
  location→timezone inference (render-time fallback), and a `scalper sources` command listing
  configured sources with tiers + stored counts. All report-time, no re-collection.

- ✅ **Phase 6: thin-CLI refactor** — business logic moved into a `scalper/commands/` package
  (`run_collect` / `run_report` / `run_sources`, each returning a typed result), with a purity
  contract (no argparse/print/exit/browser; `CommandError` subclasses + injected callbacks).
  `cli.py` is now a dispatch shell. No behavior change; front-end-ready for a future web/app layer.

- ✅ **Phase 8: all-profiles combined report** — `report --all-profiles` scores every profile
  in one run and renders one tabbed HTML file (a tab per profile, each with its own
  sort/filter; empty profiles keep a "0 matched" tab). Shared store/semantic-model/enricher;
  `run_report_all` reuses `run_report`'s scoring internals.

**Designed, not yet built:** the `add-source` self-building command (ADR 0004) — its
`build_model` per-task slot and the swappable `LLMProvider` registry it reuses already exist.

---

## Phase 1 — Semantic similarity (Stage 1 completion) ✅

Goal: turn on the `semantic` component so scoring catches relevant roles that don't
literally contain the skill keywords. Local embeddings, zero marginal cost (ADR 0003).

- [x] Added `scalper/semantic.py`: a `SemanticScorer` using `sentence-transformers`
      (default model `all-MiniLM-L6-v2`; override with `report --model`).
- [x] Builds the profile "criteria text" (titles + skills + keywords), embeds each
      posting's `search_text`, scores = cosine similarity clamped to [0,1].
- [x] Caches posting embeddings in SQLite (`embeddings` table) keyed by `uid` + model
      name; `prepare()` batch-embeds only cache misses so reports stay fast.
- [x] Optional: lazy import; if `sentence-transformers` isn't installed,
      `build_semantic_scorer` returns `None` and weights renormalize (prior behavior).
      Extra: `[semantic]`. Model-load failures fail soft to deterministic scoring.
- [x] Wired into `cmd_report` (passes the scorer to `score_all`) behind `--no-semantic`.
- [x] Tests: cosine of identical text ≈ 1.0; unrelated ≈ 0.0; blended score; store
      cache round-trip / no-recompute (stub model, so no heavy dep in CI).
- **Acceptance:** with `[semantic]` installed, a `semantic` bar appears in the report
      breakdown and reorders results; without it, behavior is unchanged (verified live —
      report falls back to deterministic scores and prints an install hint).

## Phase 2 — Stage 2 LLM enrichment ✅

Goal: on the shortlist only, generate the summary + skill-gap narrative (ADR 0003).
Cheap model by default, behind a swappable interface (ADR 0004 per-task model config).

- [x] `scalper/llm/base.py`: `LLMProvider` protocol (`complete(prompt, *, model, ...)`),
      plus a registry/factory keyed by provider name (fails soft to `None`).
- [x] `scalper/llm/anthropic_provider.py`: default impl, model `claude-haiku-4-5` for
      enrichment. Extra: `[llm]`. Reads API key from env (`ANTHROPIC_API_KEY`); lazy SDK import.
- [x] `scalper/enrich.py`: takes top-N scored postings (`--top`/`llm.top_n`), produces a
      structured `Enrichment` (1–2 sentence summary, matches/gaps, low-confidence flag).
      Prompt is small (criteria + title + trimmed description) to bound cost; JSON reply
      parsed fail-soft.
- [x] Caches enrichment in SQLite (`enrichments` table) keyed by `uid` + profile hash +
      model, so re-reports are free until profile/model/shortlist change.
- [x] Config: `llm:` block (provider, enrich_model, build_model, top_n, enabled);
      per-task model selection (enrich vs. build) lands here for ADR 0004 reuse.
- [x] Report: renders summary + matches/gaps into the detail panel behind `enriched`;
      gracefully omits (Stage 1 only) when enrichment is disabled or unavailable.
- [x] Observability: `complete()` returns a `Completion` (text + token usage); `--enrich`
      streams each request/response to stderr and prints a token + estimated-cost summary
      (built-in price table, overridable via `llm.input/output_price_per_mtok`). `--quiet-llm`
      keeps the summary only. Cache hits are logged and counted as free.
- [x] Tests: enrichment with a stub provider (no network); cache hit / no-recompute;
      profile-change invalidation; top-N bounding; JSON parse edge cases; disabled path;
      usage accumulation, cost (built-in/override/unknown), and request/response logging.
- **Acceptance:** `scalper report --profile X --enrich` adds LLM summaries to the top N
      only; cost is bounded by `top_n`, not collection volume; re-runs hit cache. (Verified:
      stub-provider render caches to the store and re-serves with 0 calls; without `[llm]`/key
      the CLI prints an install hint and renders Stage 1 unchanged. Live Anthropic path not
      exercised here — `[llm]` not installed in this env.)

## Phase 3 — More structured adapters

Goal: broaden coverage with more company-agnostic API/RSS sources (the reliable backbone).
Each is one new module + registration; the core stays untouched (ADR 0001/0004). Each must
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

## Phase 4 — Hard sources (LinkedIn, Indeed) ✅

Goal: best-effort coverage of the hostile sources via self-hosted Playwright, **anonymous
only, never the user's credentials**, low-frequency (ADR design + CONTEXT.md). Treat as
fragile gap-fillers, not the backbone.

- [x] `[scrape]` extra (playwright) already declared; `playwright install chromium` documented.
- [x] `scalper/sources/_browser.py`: shared headless-browser helper — lazy Playwright import
      (so adapters register without the extra), stealth-ish context (realistic UA, hidden
      `navigator.webdriver`), polite inter-fetch delays, retry/backoff, hard timeout, and a
      `get()` that never raises (returns rendered HTML or `None`).
- [x] **LinkedIn** adapter: anonymous *guest* search endpoint only; parsing isolated in pure
      module functions (`parse_search_cards`); search source (terms unioned + deduped). Logs
      and skips when blocked / `[scrape]` absent.
- [x] **Indeed** adapter: Cloudflare-aware (`is_challenge_page`); extracts the embedded
      `mosaic-provider-jobcards` JSON via a brace-balanced scanner; accepts partial/failed runs.
- [x] Both `tier = hard`; report surfaces a `hard` badge per row + a footer note (tier derived
      from the adapter registry at render time — no store migration).
- [x] Documented the risk + low-frequency / run-locally guidance in README and config.example.
- [x] Offline parsing tests with captured payloads (guest fragment + Indeed results page),
      fail-soft paths, dedup/limit, remote inference, tier lookup.
- **Acceptance:** when reachable, hard sources contribute postings; when blocked, the run
      logs and continues without failing other sources. (Verified offline: parsers + adapters
      drive from captured payloads; fail-soft returns `[]` with a one-line hint when `[scrape]`
      is absent or a page is challenged. Live browser path not exercised — `[scrape]` not
      installed in this env.)

## Phase 5 — Reporting polish & operability ✅

All report-time, operating on the existing store (no re-collection); pure helpers tested offline.

- [x] Optional cross-source dedup as a **reporting-only** toggle (`report --dedup`; uses the
      already-stored `dedup_key`, ADR 0002) — keeps the best-scoring record and lists the
      others as "also seen on" (`scoring.dedup_scored`; rendered in the source cell).
- [x] Salary parsing for free-text compensation (`_util.parse_salary`): handles `$`/`€`/`£` +
      ISO codes, `k`/`m` magnitudes, ranges and "up to", with an annual sanity window so
      hourly rates / `401(k)` noise are ignored. Wired into Remotive (RemoteOK min/max already
      parsed).
- [x] Timezone extraction from location strings (`_util.extract_timezone`): explicit `UTC±N`
      offsets, named abbreviations (`CET`, `EST`…), then coarse region buckets
      (`Americas`/`Europe`/`EMEA`…). Applied as a render-time fallback when the source gave none.
- [x] `scalper sources` command: lists each configured source's tier + stored count
      (`store.counts_by_source`), plus registered-but-unconfigured adapters and any orphaned
      stored sources.
- [x] Packaging/run docs: cron example (collect + report) and `-s/--source` in README; added a
      `report --since <DAYS|DATE>` filter (day count or ISO date; unknown-date postings kept).

---

## Phase 6 — Thin-CLI refactor (front-end-ready core) ✅

Pure refactor, no new user features. Makes `cli.py` a dispatch shell so the same logic can
later back a web/desktop/mobile front end. No behavior change; tests stay green throughout.

- [x] Added a `scalper/commands/` package, one module per subcommand:
      `commands/collect.py`, `commands/report.py`, `commands/sources.py`. Each exposes a
      single entry function (`run_collect` → `CollectResult`, `run_report` → `ReportResult`,
      `run_sources` → `SourcesResult`) taking plain typed params and returning a typed result
      object (`@dataclass`).
- [x] Moved the bodies of `cmd_collect` / `cmd_report` / `cmd_sources` into those functions.
      **Purity contract honored:** the command layer has no `argparse`, no `print`/direct stderr,
      no `sys.exit`, and no browser-opening; it raises `CommandError` subclasses
      (`NoSourcesError` / `ProfileNotFoundError` / `StoreNotFoundError`) instead of exiting, and
      `run_report` returns the rendered HTML string (the CLI writes the file / opens the browser).
- [x] Streaming output goes through **injected callbacks** (`on_info` / `on_warning`, default
      no-op; enrich's per-request logs via `on_enrich_log`) so the CLI prints it while a future
      app can stream it differently.
- [x] `cli.py` shrank to: build parser → map `Namespace` to params → call the command function →
      render the result to stdout / write the file / launch `--open` → return the exit code. The
      CLI owns *all* printing, exit codes, and the browser launch.
- [x] `_parse_since` stays CLI-side (still importable from `scalper.cli`; produces the typed
      `since` cutoff passed to `run_report`); `_aware` (domain logic) moved into `commands/report.py`.
- **Acceptance:** ✅ every command behaves identically from the CLI (verified: error-path ordering
      and messages, and a live `report` run, are unchanged); each command function is importable
      and runnable with no argparse/print/exit in its call path; existing 100 tests pass and 8 new
      `tests/test_commands.py` cases call the command functions directly without the CLI (108 total).

---

## Phase 8 — All-profiles combined report ✅

Goal: report against *every* profile in one run, rendering one combined, tabbed HTML file
(one tab per profile) instead of invoking `report` once per profile. Pure reporting feature;
no new collection. See the Combined Report term in `CONTEXT.md`.

- [x] `report --all-profiles` flag, **mutually exclusive** with `-p/--profile` (argparse
      `add_mutually_exclusive_group(required=True)` — exactly one is required).
- [x] One combined self-contained HTML at `--out`: a tab bar (one tab per profile, with its
      match count), each tab a full results table with its own client-side sort/filter. First
      tab active; every configured profile keeps a tab even at 0 matches (empty-state panel).
- [x] Templates refactored into shared partials (`_styles.html`, `_panel.html` panel-scoped
      JS via `_script.html`); `report.html` is a single-panel wrapper, `report_combined.html`
      adds the tab bar. Single-profile output unchanged.
- [x] Command layer: `run_report_all(config, profile_names, …) -> MultiReportResult` sharing
      `_prepare`/`_score_one` with `run_report` — store opened once, semantic model loaded
      once, one enricher shared so its usage/cost tally aggregates across profiles. New
      `NoProfilesError`; `render_combined_report` + `ReportPanel` in `report.py`.
- [x] `--since` applied once (run-level) to the shared posting list; each profile still
      self-filters via its own `passes_filters` (incl. its own freshness window).
- **Acceptance:** ✅ `report --all-profiles` emits one tabbed file with correct per-profile
      counts; `-p`/`--all-profiles` mutually exclusive (and one required); single-profile path
      unchanged; 112 tests pass (4 new covering `run_report_all`, `NoProfilesError`, and the
      combined-template render incl. a 0-match tab).

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
