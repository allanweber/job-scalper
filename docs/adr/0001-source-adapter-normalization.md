# 0001 — Source adapters return normalized Job Postings

- Status: Accepted
- Date: 2026-06-15
- Amended by: ADR 0005 (sources are company-agnostic; `fetch` takes a `SearchQuery`)

## Context

Job Scalper pulls from heterogeneous, **company-agnostic** Sources: structured sources
(Remotive, RemoteOK, Arbeitnow, Adzuna, HN "Who's Hiring") return clean structured
payloads with salary/location fields, while hard sources (LinkedIn, Indeed) return messy
HTML obtained via self-hosted Playwright scraping. Each searches the whole market by the
user's criteria. New sources will be added over time — extensibility is an explicit goal.

The core of the tool (dedup-key generation, scoring funnel, LLM enrichment, HTML
reporting) must operate on a single canonical shape regardless of where a posting came
from. The question is *where* the mapping from each source's raw format to that canonical
shape lives.

## Decision

Each Source is implemented as a self-contained **Adapter** module exposing a uniform
interface:

```
fetch(query) -> list[JobPosting]
```

The adapter owns all source-specific concerns — auth, pagination, HTML/JSON parsing, and
applying freshness/remote filters natively where the source supports them — and returns
**already-normalized `JobPosting` objects**. The core never sees a source's raw format.

Adding a new source is a single new file implementing `fetch` plus registration; the core
is not touched.

## Alternatives considered

- **Adapters return raw payloads; a central layer normalizes.** Centralizes mapping logic
  but couples the core to every source's format — the core grows with each new site,
  undermining the extensibility goal.
- **Two-method adapters (`fetch` + `parse`).** Better offline testability for fragile
  scrapers (snapshot raw, test parse), but more ceremony per adapter. Rejected for now;
  individual adapters may still split internally if a scraper needs it.

## Consequences

- The core stays completely source-agnostic; new sources are isolated, drop-in files.
- The `JobPosting` schema is the load-bearing contract — changing it touches every adapter,
  so it must be designed deliberately and changed rarely.
- Per-adapter normalization means mapping logic is distributed, not centralized; reading
  "how is field X derived" means opening the relevant adapter.
- Reversing this (moving to centralized normalization) is costly — it would require
  rewriting every adapter — which is why it is recorded here.
