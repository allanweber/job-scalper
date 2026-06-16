# Job Scalper

## Commands

```bash
source .venv/bin/activate

scalper collect -s indeed                           # just Indeed
scalper collect -s indeed linkedin                  # both, in config order
scalper collect                                     # all sources (unchanged)

scalper report --profile backend                    # first run downloads the model, then caches embeddings
scalper report --profile backend --open             # score + open HTML report (instant)
scalper report --all-profiles --open                # one combined report, a tab per profile

scalper report --profile backend --enrich           # enrich the top N (config llm.top_n)
scalper report --profile backend --enrich --top 5   # or cap it per run
scalper report --profile backend --enrich --top 5   # or cap it per run
scalper report --all-profiles --enrich --top 5

scalper report --profile backend --since 14         # only postings from the last 14 days
scalper report --profile backend --since 2026-06-01 # …or on/after a date
scalper report --profile backend --dedup            # collapse the same job seen on >1 source

scalper sources                                     # list adapters + configured sources with counts

scalper profile from-resume --name backend --resume resume.pdf         # draft, print YAML
scalper profile from-resume --name backend --resume resume.pdf --write # …and append to config.yaml
scalper profile from-resume --name backend --resume resume.pdf --write --force # overwrite

scalper draft remotive::123 -p backend --resume resume.pdf             # one posting
scalper draft remotive::123 remotive::456 -p backend --resume resume.pdf --out drafts/  # several

```

A personal CLI that searches remote tech jobs across many **company-agnostic** sources
(it ranks the market, it doesn't watch a fixed list of employers), scores each against
your search criteria, and emits a self-contained HTML report. Single-user, local-first.

See [`CONTEXT.md`](CONTEXT.md) for the vocabulary and [`docs/adr/`](docs/adr/) for the
key design decisions.

## How it works

Collection and reporting are decoupled through a local SQLite store (ADR 0002):

- **`collect`** — slow, occasional. Searches every configured source with the global
  `search:` query (ADR 0004), normalizes postings, and stores them. Cron-friendly; no daemon.
- **`report`** — instant. Scores stored postings against a named profile and renders HTML.

Sources are searched by *criteria*, not by naming employers: the `search:` block drives
collection broadly, and each `--profile` re-scores the results narrowly at report time.

Scoring is a two-stage funnel (ADR 0003). **Stage 1** runs on every posting: hard filters
(remote, freshness, excludes, salary floor) plus an explainable Match % blending skill
coverage + title + keyword + an optional local **semantic** similarity component. **Stage 2**
is optional LLM enrichment that runs on the top-scored shortlist only — it adds a summary and
a have/missing skill narrative but never changes the headline Match %, so cost is bounded by
the shortlist size, not collection volume.

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

### LLM enrichment (optional)

Stage 2 sends only the top-scored postings to an LLM for a short summary and a have/missing
skill narrative (ADR 0003). It's advisory — it never changes the Match %. Off until you
install the extra and provide a key:

```bash
pip install -e '.[llm]'              # pulls the anthropic SDK
export ANTHROPIC_API_KEY=sk-ant-…
scalper report --profile backend --enrich          # enrich the top N (config llm.top_n)
scalper report --profile backend --enrich --top 5  # or cap it per run
```

Cost is bounded by `--top`/`llm.top_n`, not by how many postings you collected. Results are
cached in the store keyed by posting + profile criteria + model, so re-running a report is
free until the profile, model, or shortlist changes. Without the extra (or a key), `report`
prints a one-line hint and renders the deterministic Stage 1 report unchanged. Configure the
provider, models, and default `top_n` under the `llm:` block (uses Haiku by default); set
`llm.enabled: true` to enrich without passing `--enrich`.

**Logs and cost.** With `--enrich`, every request (system + user prompt) and the model's raw
response are streamed to **stderr** as they happen, and a token/cost summary is printed to
**stdout** at the end:

```
─── enrich [1/10] remotive::123 — Senior Python Developer (Proxify) ───
REQUEST (model=claude-haiku-4-5):
[system] …
[user]   …
RESPONSE (in=843 out=126 tok): {"summary": …}
…
LLM enrichment usage (claude-haiku-4-5):
  calls:          7  (3 served from cache)
  input tokens:   5,901
  output tokens:  882
  est. cost:      $0.0103  (input $0.0059 + output $0.0044)
```

Cached postings are logged as `cache hit` and cost nothing. Pass `--quiet-llm` to suppress the
per-request logs while keeping the usage summary. Costs are estimated from a built-in price
table; if your model isn't listed it shows `n/a` — set `llm.input_price_per_mtok` /
`llm.output_price_per_mtok` (USD per 1M tokens) to override.

### Resume-driven profiles (optional)

`profile from-resume --resume <file>` reads your resume (PDF, markdown, or plain text —
`pypdf` ships as a core dependency so PDF works out of the box) and asks the LLM to draft a
profile's `titles` / `required_skills` / `nice_to_have_skills` / `keywords` for you, instead
of hand-authoring them. It reuses the same `[llm]` extra/key as enrichment (model from
`llm.build_model`).

```bash
pip install -e '.[llm]'              # if not already installed
export ANTHROPIC_API_KEY=sk-ant-…

scalper profile from-resume --name backend --resume resume.pdf          # prints YAML
scalper profile from-resume --name backend --resume resume.pdf --write  # …and appends it
```

`--resume` is required and validated up front — a clear `error:` if the file is missing. By
default nothing is written — review the printed block and paste it in yourself, or pass
`--write` to append it under `<name>` in config.yaml (existing comments are preserved).
`--write` refuses to overwrite a profile that already exists; add `--force` to replace it.
Without the `[llm]` extra or an API key, the command prints a one-line `error:` hint instead
of crashing.

### Application drafts (optional)

`draft <uid> [<uid> ...] -p <profile> --resume <file>` asks the LLM to write a cover
letter plus tailored resume bullets for one or more stored postings (find uids in a
`report`'s rows or HTML), grounded in the posting text, your resume, and that profile's
Stage 1 matched/missing skills. Reuses the same `[llm]` extra/key as enrichment (model
from `llm.build_model`).

```bash
pip install -e '.[llm]'              # if not already installed
export ANTHROPIC_API_KEY=sk-ant-…

scalper draft remotive::123 -p backend --resume resume.pdf
scalper draft remotive::123 remotive::456 -p backend --resume resume.pdf --out drafts/
```

Every posting is drafted into its **own file**, never just printed: `--out DIR` (or
`draft_output_dir` in config.yaml, or the current directory if neither is set) gets one
`[profile]_[position_name]_[uid].md` per posting, holding both sections. An unknown uid
reports cleanly — listing every uid not found in the store — before any LLM call is
made. Same logging contract as enrichment/profile-drafting: request/response stream to
stderr (`--quiet-llm` to silence), a token/cost summary always prints. Without the
`[llm]` extra or an API key, the command prints a one-line `error:` hint instead of
crashing.

### Hard sources — LinkedIn & Indeed (optional, off by default)

LinkedIn and Indeed have no public API and actively resist automation, so they
can't be reached like the structured sources above. When enabled, they're scraped
with a self-hosted headless browser (Playwright) — **anonymously only, never with
your own account or credentials** — and the results are tagged `hard` in the report
so you can see they're best-effort.

```bash
pip install -e '.[scrape]'
playwright install chromium        # one-time browser download
```

Then uncomment the `linkedin` / `indeed` entries in `config.yaml`. **Treat these as
fragile gap-fillers, not the backbone:** their markup changes often and they throttle
or block automated traffic — much harder from datacenter/cloud IPs than from a home
connection, so they work best run locally and **at low frequency** (once a day at
most). A blocked page, a markup change, or a missing `[scrape]` extra makes the source
contribute nothing and log a one-line note; it never aborts the run or affects the
other sources. LinkedIn uses its unauthenticated *guest* search endpoint; Indeed is
Cloudflare-aware and skips cleanly when challenged.

**When Indeed shows a Cloudflare challenge.** The tool never auto-solves one — that's an
evasion arms race and against Indeed's ToS. Instead, in order of effectiveness: (1) run
from a **home IP** — datacenter/cloud IPs get challenged far more, and from a residential
connection a *passive* "checking your browser" challenge usually clears on its own;
(2) if it persists, set `headless: false` to open a visible window and solve the challenge
**yourself, by hand**, with `user_data_dir: .indeed-profile` so the cleared cookies are
reused on later runs; (3) raise `challenge_wait` to give the page (or you) time to clear it.
For reliable, scrape-free coverage of this kind of listing, prefer **Adzuna** (a free key,
no browser).

Schedule collection with cron, e.g. nightly (collect at 07:00, then rebuild the report):

```cron
0 7 * * *  cd /home/allan/projects/job-scalper && .venv/bin/scalper collect
5 7 * * *  cd /home/allan/projects/job-scalper && .venv/bin/scalper report --profile backend
```

Restrict a run to specific sources with `-s/--source` (handy for the slow hard sources):

```bash
scalper collect -s indeed linkedin   # just these, in config order
```

### Reporting filters & dedup

All of these are **report-time** and operate on the existing store — no re-collection:

- `--since <DAYS|DATE>` — score only recent postings: a day count (`--since 14`) or an ISO
  date (`--since 2026-06-01`). Postings with no known publish date are kept.
- `--dedup` — collapse the same job seen on multiple sources into one row, keeping the
  best-scoring record and listing the others under "also seen on". Uses the normalized
  company+title+location key stored at collect time (ADR 0002).
- `exclude_non_latin: true` (per profile, **on by default**) — drop predominantly
  CJK (Chinese/Japanese/Korean) listings; set `false` to keep them.
- `--all-profiles` — score every profile in one run into a single combined HTML report
  (one tab per profile, each independently sortable/filterable). Mutually exclusive with
  `--profile`. `--since` applies to the whole run; each profile still applies its own hard
  filters (including its own freshness window). Empty profiles keep a "0 matched" tab.

Salary is parsed into a structured range even from sources that report it as free text
(e.g. Remotive's `"$90k – $120k"`), and a timezone hint is inferred from the location
string (`UTC+2`, `CET`, `Americas`, …) when the source doesn't supply one.

### Inspecting sources

```bash
scalper sources   # registered adapters + each configured source's tier and stored count
```

Lists every configured source with its tier (`structured`/`hard`) and how many postings it
has in the store, plus adapters that are registered but not yet in your config.

## Configuration

`config.yaml` holds the database path, a global `search:` block, a list of sources, and
named profiles. See `config.example.yaml` for a documented template. Thirteen company-agnostic
adapters ship today — eleven structured (all keyless except Adzuna) plus two optional hard
(scraped) sources, off by default:

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
| `linkedin` | guest jobs endpoint | **hard** (scraped) | anonymous; needs `[scrape]`; off by default |
| `indeed` | results page | **hard** (scraped) | anonymous, Cloudflare-aware; needs `[scrape]`; off by default |

Adapters are tiered: *structured* sources have official APIs/feeds and form the reliable
backbone; *hard* sources (LinkedIn, Indeed) are scraped anonymously, best-effort, and off
by default (see [Hard sources](#hard-sources--linkedin--indeed-optional-off-by-default)).

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
- ✅ Company-agnostic, query-driven sources + adapter registry 
- ✅ 11 structured adapters: Remotive/Jobicy/Adzuna (search) + RemoteOK/Arbeitnow/The Muse/Working Nomads/Himalayas/We Work Remotely/Hacker News/Reddit (feeds)
- ✅ 2 hard adapters: LinkedIn + Indeed via self-hosted Playwright, anonymous only, off by default — `pip install -e .[scrape]`
- ✅ Stage 1 deterministic scoring + hard filters
- ✅ Semantic similarity in Stage 1 (local sentence-transformers, cached) — `pip install -e .[semantic]`
- ✅ Stage 2 LLM enrichment: summary + skill-gap on the shortlist, cached, swappable provider — `pip install -e .[llm]`
- ✅ Self-contained HTML report (client-side sort/filter, tier badges)
- ✅ Resume-driven profile drafting (`profile from-resume`) and Application Drafts
  (`draft`, cover letter + resume bullets per posting) — both `pip install -e .[llm]`
- ✅ Tests for scoring, semantic, enrichment, and adapter parsing (structured + hard)

Layered on next (designed, not yet built):
- ⏳ Generic mapping-driven RSS/JSON adapter (declarative tier for `add-source`)
- ⏳ `add-source <url>` self-building command, tiered + approval-gated (ADR 0004)

## Tests

```bash
pip install -e .[dev]
pytest
```
