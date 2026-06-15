# Job Scalper

A personal CLI that searches remote tech jobs across many **company-agnostic** sources
(it ranks the market, it doesn't watch a fixed list of employers), scores each against
your search criteria, and emits a self-contained HTML report. Single-user, local-first.

See [`CONTEXT.md`](CONTEXT.md) for the vocabulary and [`docs/adr/`](docs/adr/) for the
key design decisions.

## How it works

Collection and reporting are decoupled through a local SQLite store (ADR 0002):

- **`collect`** — slow, occasional. Searches every configured source with the global
  `search:` query (ADR 0005), normalizes postings, and stores them. Cron-friendly; no daemon.
- **`report`** — instant. Scores stored postings against a named profile and renders HTML.

Sources are searched by *criteria*, not by naming employers: the `search:` block drives
collection broadly, and each `--profile` re-scores the results narrowly at report time.

Scoring is a two-stage funnel (ADR 0003). This slice implements **Stage 1**: hard
filters (remote, freshness, excludes, salary floor) plus an explainable Match % blending
skill coverage + title + keyword + an optional local **semantic** similarity component
(the Stage 2 LLM layer comes later).

Every source is a self-contained adapter returning normalized `JobPosting`s (ADR 0001).

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```bash
cp config.example.yaml config.yaml   # then edit sources + profiles
scalper collect                      # populate the local store (slow)
scalper report --profile backend --open   # score + open HTML report (instant)
```

### Semantic scoring (optional)

The Match % includes a local semantic-similarity component that catches relevant roles
which don't contain your exact skill words. It's off until you install the extra:

```bash
pip install -e '.[semantic]'        # pulls sentence-transformers (+ torch)
scalper report --profile backend    # first run downloads the model, then caches embeddings
```

Without the extra, `report` simply falls back to the deterministic score (skill + title +
keyword) and prints a one-line install hint. Use `--no-semantic` to skip it even when
installed, or `--model <name>` to pick a different sentence-transformers model. Embeddings
are cached in the store keyed by posting + model, so only new postings are encoded.

Schedule collection with cron, e.g. nightly:

```cron
0 7 * * *  cd /home/allan/projects/job-scalper && .venv/bin/scalper collect
```

## Configuration

`config.yaml` holds the database path, a global `search:` block, a list of sources, and
named profiles. See `config.example.yaml` for a documented template. Eleven company-agnostic
adapters ship today (all keyless except Adzuna):

| Adapter | Endpoint | Shape | Notes |
| --- | --- | --- | --- |
| `remotive` | remotive.com API | search (keyword) | |
| `jobicy` | jobicy.com API | search (tag) | |
| `adzuna` | api.adzuna.com | search | free `app_id`/`app_key`; skipped if unset |
| `remoteok` | remoteok.com API | broad feed | |
| `arbeitnow` | arbeitnow.com API | broad feed (paginated) | |
| `themuse` | themuse.com API | broad feed (category, paginated) | |
| `workingnomads` | workingnomads.com API | broad feed | |
| `himalayas` | himalayas.app API | broad feed (paginated, salary) | |
| `weworkremotely` | weworkremotely.com RSS | broad feed (RSS) | |
| `hackernews` | hn.algolia.com API | broad feed | monthly "Who is hiring?" thread |
| `reddit` | reddit.com `.rss` | broad feed (Atom) | no account; rate-limited, best run locally |

Search sources issue a native query; broad-feed sources pull a recent feed and filter
locally against `search.terms`. There are no public Java-only boards, so Java focus comes
from a `java` tech token in the global search plus a dedicated `java` profile at report time.

`search.limit_per_source` caps how many postings each source contributes per run. Any source
entry can override it with its own `limit:` — e.g. Hacker News ships capped at 25 so its
300+-comment thread doesn't swamp the store.

**Adzuna** needs a free key — register at [developer.adzuna.com](https://developer.adzuna.com)
and set `app_id`/`app_key` in config or the `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` env vars.
**Reddit** uses the public per-subreddit `.rss` feeds — no account or app registration. List
the job subreddits you want (`subreddits:`); set `hiring_only: false` for dedicated job boards
(e.g. `java_jobs`, `techjobs`) where every post is a listing, or `true` for mixed subs like
`forhire` to drop `[For Hire]` seekers. Reddit rate-limits anonymous clients (HTTP 429), much
harder from datacenter/cloud IPs than from a home connection, so it works best run locally;
raise `delay` if you see 429s. Throttled or missing subreddits are skipped without failing the
run.

## Status / roadmap

Implemented:
- ✅ `JobPosting` model + SQLite store
- ✅ Company-agnostic, query-driven sources + adapter registry (ADR 0005)
- ✅ 11 adapters: Remotive/Jobicy/Adzuna (search) + RemoteOK/Arbeitnow/The Muse/Working Nomads/Himalayas/We Work Remotely/Hacker News/Reddit (feeds)
- ✅ Stage 1 deterministic scoring + hard filters
- ✅ Semantic similarity in Stage 1 (local sentence-transformers, cached) — `pip install -e .[semantic]`
- ✅ Self-contained HTML report (client-side sort/filter)
- ✅ Tests for scoring, semantic, and adapter parsing

Layered on next (designed, not yet built):
- ⏳ Stage 2 LLM enrichment: summary + skill-gap (Haiku default, swappable provider) — `[llm]`
- ⏳ Generic mapping-driven RSS/JSON adapter (declarative tier for `add-source`)
- ⏳ Hard sources (LinkedIn, Indeed) via self-hosted Playwright, anonymous only — `[scrape]`
- ⏳ `add-source <url>` self-building command, tiered + approval-gated (ADR 0004)

## Tests

```bash
pip install -e .[dev]
pytest
```
