# 0002 — Collect/report split over a local SQLite store

- Status: Accepted
- Date: 2026-06-15
- Amended by: ADR 0005 (`collect` is driven by a global `search:` query; `report`
  still re-scores against any profile independently)

## Context

Acquiring postings is slow and sometimes fragile: hard sources require headless-browser
scraping, and many sources must be queried each run. Viewing and re-querying results, by
contrast, should be instant and is done frequently — the user wants to filter, re-sort,
and ask "what's fresh today vs. last week" repeatedly without waiting.

The user also wants freshness windows and (eventually) the ability to see history and
turn on dedup, all of which require postings to persist with timestamps.

## Decision

Split the tool into two decoupled operations mediated by a local **SQLite** store:

- **`collect`** — slow, occasional, idempotent. Fetches all Sources → normalizes →
  persists Job Postings (timestamped) into SQLite. Cron-friendly; no long-running daemon.
- **`report --profile <name>`** — instant, frequent. Queries the store by a Profile's
  criteria → runs the scoring funnel → renders a self-contained HTML report.

## Alternatives considered

- **Stateless, scrape-on-run.** One command scrapes → scores → renders, no persistence.
  Simplest to start, but every report waits for a full slow collection, there is no
  cross-run history or freshness comparison, and hard sources would be hit far more often
  (raising ban risk). Rejected.
- **Long-running daemon/scheduler.** Convenient hands-off collection, but adds a persistent
  process, scheduling config, and failure handling unjustified for a single-user tool.
  Deferred to the user's own cron/systemd timer.

## Consequences

- Reports are fast and repeatable; the slow path runs only when the user (or cron) chooses.
- Postings persist with `published_at` and ingest timestamps, enabling freshness windows
  and history for free.
- Hard-source scraping stays naturally low-frequency, reducing ban risk.
- Introduces a schema and migration concern: the store's shape must accommodate future
  needs. In particular, a normalized `company+title+location` key is stored now (even
  though dedup is off) so dedup can later be a reporting-only change with no re-collection.
- Reversing the split would mean giving up fast reports and history — recorded here because
  it shapes the whole data flow.
