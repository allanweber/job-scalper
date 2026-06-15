# 0005 — Company-agnostic search sources, query-driven collect

- Status: Accepted
- Date: 2026-06-15
- Amends: ADR 0001 (adapter contract), ADR 0002 (collect inputs)

## Context

Job Scalper's purpose is to answer "find me remote jobs that fit my criteria,
*anywhere*" — it ranks the market, it does not watch a fixed list of employers.

The first implementation got this wrong. The initial adapters (Greenhouse, Lever,
Ashby) were company-keyed ATS boards: each is configured with a specific employer
(`company: stripe`, `board: openai`) and can only return that employer's jobs. To
use them you must already know which companies to look at — a **directory** model,
the opposite of company-agnostic search. The aggregator sources that actually
search the whole market (Remotive, RemoteOK, Arbeitnow, Adzuna, and the originally
requested LinkedIn/Indeed) had been deferred as "more coverage."

This also exposed a contract gap. A company-agnostic source must be told *what to
search for*, but the implemented adapter contract was `fetch()` with no query, and
`collect` was criteria-agnostic (dump everything, score later — fine for a bounded
company board, impossible for an unbounded search API).

## Decision

1. **Sources are company-agnostic.** A Source searches the market by criteria and
   returns postings from many employers. The company-keyed ATS adapters are
   removed entirely; the user opted not to keep them even as an optional feature.

2. **`collect` is query-driven.** A single global `search:` block in config
   (`SearchQuery`: terms, location, remote, per-source limit) is passed into every
   adapter: the contract is `fetch(query) -> list[JobPosting]`. One global search
   spec, not per-profile — `collect` stays a single bulk pass, and `report
   --profile` still re-scores the stored postings against any profile independently
   (preserving the ADR 0002 split).

3. **Two source shapes under one contract.**
   - *Search sources* (e.g. Remotive) translate `query.terms` into a native search
     request; each term is queried independently and results are unioned (OR).
   - *Broad-feed sources* (e.g. RemoteOK) can't search server-side, so they pull
     the recent feed and filter locally with `matches_any_term` (all words of a
     term must appear; OR across terms; empty terms keep everything).

## Alternatives considered

- **Per-profile search drives collect** (`collect --profile X` queries with that
  profile's terms). More targeted, but couples collection to scoring and forces a
  re-collect per profile. Rejected: keeps the bulk/instant split clean to use one
  broad global search and many narrow report-time profiles.
- **Per-source explicit query params.** Maximum control, maximum repetition, no
  shared search intent. Rejected as the default; a source may still expose its own
  knobs (e.g. Remotive `category`) on top of the global query.
- **Keep ATS adapters as an optional "watch these companies" feature.** Offered;
  the user chose to drop them to keep the surface focused on market-wide search.

## Consequences

- The tool now does what it was for: market-wide, criteria-ranked search.
- `JobPosting.source` is the *platform* (`remotive`, `remoteok`), and `company`
  comes from each posting — not from config. Per-source dedup is by platform id.
- Adapters must handle being given broad or empty queries gracefully.
- Store, scoring, funnel, and report are unaffected — the pivot is contained to the
  source layer, the adapter contract, `collect`, and config.
- Reversing this (returning to company-keyed sources) would re-break the core use
  case; recorded here because it redefines what a Source *is*.
