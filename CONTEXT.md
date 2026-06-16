# Job Scalper — Context Glossary

> Ubiquitous language for this project. Definitions only — no implementation details.

## Scope

**Personal tool.** Single user (the author). Runs locally / on a small personal VPS.
No multi-tenancy, no auth, no public product surface. Legal/ToS risk is accepted
personally by the user.

## Terms

### Job Posting
A single open position discovered from a Source. The atomic, normalized unit the tool
collects, scores, stores, and reports on. Canonical fields: company, title, description,
location, remote flag, timezone, salary range, url, source, published_at.

### Source
A **company-agnostic** origin of Job Postings: it searches the whole job market by the
user's criteria and returns matches from many employers (it is *not* tied to one
company). Sources fall into tiers by how they're accessed:

- **Structured source** — exposes an official API or RSS/Atom feed. Fast, reliable, mostly
  free, low-maintenance. Examples: Remotive, RemoteOK, Jobicy, Arbeitnow, The Muse, Working
  Nomads, Himalayas, We Work Remotely, Hacker News "Who's Hiring", Adzuna (needs a free key).
  Some community feeds (e.g. Reddit's public RSS) sit at the fragile edge of this tier —
  reachable without auth but heavily rate-limited, so they're treated as best-effort and
  fail soft.
- **Hard source** — actively resists automated access (login walls, bot detection,
  IP bans, litigation history). Examples: LinkedIn, Indeed. Accessed only via
  anonymous/guest paths (self-hosted Playwright) — never the user's own credentials.

By how they consume the Search Query, sources also split into two shapes :
a **search source** issues a native query (e.g. Remotive), while a **broad-feed source**
pulls a recent feed and filters locally (e.g. RemoteOK).

### Search Query
The criteria passed into every Source at collect time: query terms, location hint,
remote flag, and a per-source result cap. Job Scalper searches *by* this, not by naming
employers. Configured once globally under `search:` ; distinct from a Profile,
which is applied later at report time for scoring.

### Adapter
The module implementing a single Source. Exposes `fetch(query) -> list[JobPosting]`,
owning its own auth, pagination, parsing, and native filtering, and returns
already-normalized Job Postings. See ADR 0001 / ADR 0004.

### Generic Adapter
A hand-written, well-tested Adapter that is parameterized rather than site-specific:
it serves a whole class of Sources (e.g. any clean JSON or RSS job feed) driven by a
Source Definition. Adding such a Source means adding configuration, not code.

### Source Definition
The declarative configuration that points a Generic Adapter at a concrete Source —
e.g. the endpoint URL plus a field mapping for a generic JSON/RSS feed. Stored on disk,
inspectable and hand-editable.

### Build Tier
Which path the `add-source` command takes for a given URL, in order of preference:
1. **Config tier** — a known platform an existing adapter already handles → a Source
   Definition for that adapter. No new code.
2. **Declarative tier** — clean JSON/RSS API → a field-mapping Source Definition for the
   generic API/RSS adapter. No new code.
3. **Codegen tier** — bespoke HTML site with no API → an LLM-generated, site-specific
   Adapter module. The only path that produces and runs new code. See ADR 0004.

### add-source
The CLI command (`scalper add-source <url> [--name X]`) that builds a new Source from a
URL: it auto-detects the Build Tier, produces the artifact (Source Definition or generated
Adapter), validates it against `JobPosting` via a live dry-run, shows sample postings, and
registers it into the collection chain only on explicit user approval. See ADR 0004.

### Search Criteria
The user's definition of a desired job, stored as a named Profile: position/title
patterns, required and nice-to-have skills, keywords, exclusions, location (primarily
remote) and timezone, salary floor, Freshness Window, and scoring weights.

### Profile
A named, reusable set of Search Criteria in `config.yaml`. A report run targets either
one Profile (`--profile`) or every Profile at once (`--all-profiles`); the two are
mutually exclusive. Multiple Profiles coexist for distinct job searches.

### Combined Report
A single self-contained HTML Report covering several Profiles at once (`--all-profiles`),
one tab per Profile. Each Profile is scored independently against the same stored postings
through its own lens — its own hard filters (including its own Freshness Window) and
weights — so the same Job Posting may appear under more than one Profile, each with that
Profile's Match Score. Every configured Profile keeps a tab even when it matches nothing,
distinguishing "searched, found none" from "not searched".

### Freshness Window
A user-set upper bound on how recently a Job Posting was published (e.g. "today",
"last 7 days"). Acts as a hard filter, not a score component.

### Match Score
A percentage expressing how well a Job Posting fits a Profile. Computed
deterministically (skill coverage + title match + semantic similarity), with a
visible breakdown so every score is auditable. See ADR 0003.

### Funnel
The two-stage scoring pipeline: a cheap, no-LLM Stage 1 scores all postings; a Stage 2
LLM enriches only the resulting shortlist. See ADR 0003.

### Fresh Catch
A **store-relative, per-collect-run** property of a Job Posting: it was first seen
(entered the store) *during this run's collect*. It tracks what *this scrape* turned up
that the store didn't already hold — regardless of whether the user has looked, and
regardless of how old the underlying job is (contrast the Freshness Window, which
hard-filters on the job's publish age). The unit a Digest reports on.

### Digest
A single combined operation that scrapes first, then reports only the Fresh Catch:
capture a run start, run the same Collect path, then render the postings first seen
during that run. Answers "what new postings did this run surface, and how do they score
against my Profiles" in one step. Distinct from Report, which never collects.

### Resume
The user's own CV, passed explicitly per command via `--resume <file>` (PDF is the
expected format, parsed with `pypdf`; plain-text/markdown also read as-is). Not stored in
config and not a Job Posting — never persisted in the postings database. Read fresh by
both LLM features that need it: drafting a Profile, and drafting Application Drafts.

### Application Draft
LLM-generated application material tailored to one Job Posting for one Profile: a cover
letter plus suggested resume bullet edits, grounded in the posting text, the user's
Resume, and the Profile's matched/missing skills from Stage 1. Output for the user to
edit — never sent anywhere by the tool.

### Market Insights
A read-only aggregate description of the *stored market* (not a fit to any Profile): how
sought-after the user's skills are across postings, salary distribution, postings per
Source, and recent collection volume. Describes supply, not a Match Score.

### Collect / Report
The two decoupled operations. **Collect** is slow and occasional: search all Sources with
the global Search Query → normalize → store. **Report** is instant and frequent: score the
stored postings against a Profile → render HTML. See ADR 0002 / ADR 0004.

## Decisions log
- Sources are company-agnostic: searched by criteria, not by enumerating employers;
  `collect` is driven by a global `search:` query . The early company-keyed ATS
  adapters (Greenhouse/Lever/Ashby) were removed.
- Data acquisition: API/RSS-first backbone (Remotive, RemoteOK, Arbeitnow, Adzuna, HN);
  LinkedIn + Indeed required as hard sources via self-hosted Playwright (anonymous/guest only).
- Architecture: Python CLI over a local SQLite store; collect/report split (ADR 0002).
- Source adapters return normalized Job Postings (ADR 0001).
- Scoring funnel with deterministic headline % + LLM narrative on shortlist (ADR 0003).
- Embeddings: local (sentence-transformers).
- LLM: swappable `LLMProvider` interface, Anthropic Haiku as default.
- Dedup: none for now (tag source); store a normalized company+title+location key so
  dedup can later be a reporting-only change.
- Report: single self-contained HTML file with client-side sort/filter. `--all-profiles`
  produces one combined file with a tab per Profile (Combined Report); profiles are scored
  independently and empty profiles keep a "0 matched" tab.
- Digest scrapes first, then reports only the Fresh Catch (postings first seen during
  that run, via the preserved first-seen `collected_at`). Its "new" is store-relative and
  per-run — what this scrape surfaced that the store didn't already hold. See ADR 0005.
- Resume is passed per-command via `--resume <file>` (no config-level default), shared by
  two LLM features: drafting a Profile from it, and drafting Application Drafts (cover
  letter + resume bullets) per posting. Both are `[llm]`-gated and fail-soft; profile
  drafting prints YAML to review (opt-in `--write`).
- Market Insights is a read-only, no-LLM aggregate over the store (skill demand, salary,
  source/volume) — it describes supply, never scores a fit.
- Scheduling: manual `collect` command, cron-friendly; no daemon.
- `add-source` builds new Sources from a URL via tiered detection (config / declarative /
  codegen), behind a validate→sample→approve gate; codegen output is reviewed before it
  ever runs (ADR 0004). Build uses a stronger model than enrichment, per-task configurable.
