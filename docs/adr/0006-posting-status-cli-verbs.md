# 0006 — Posting Status set via CLI, not an interactive report

- Status: Accepted
- Date: 2026-06-16

## Context

The next phase adds **Posting Status** (the user's asserted disposition toward a Job
Posting — `interested` / `applied` / `dismissed`) and a derived **New / Unseen** badge, so
the tool stops being a stateless re-scan and starts tracking the user's workflow across
runs.

This collides with two standing decisions: the report is a **single self-contained HTML
file** (ADR 0002 / decisions log) and the tool runs **with no daemon**. A static `file://`
page has no server to receive a click, so it cannot persist a status change to the SQLite
store. Letting the user "click ★ applied in the report" is therefore not free — it forces
a choice between keeping the server-less model and getting in-page interactivity.

## Decision

Status is set through the CLI, never by the report writing back:

- A unified verb — `scalper status <uid> [<uid> …] <interested|applied|dismissed|clear>` —
  is the only thing that mutates status. It accepts multiple uids so a shell can batch
  (`scalper status $(…) dismissed`).
- Status is stored per Posting, keyed by `uid` (alongside embeddings and enrichments), in
  a side table so re-collection's `INSERT OR REPLACE` on `postings` can never clobber it.
  A generic `status_updated_at` is recorded; merging across duplicate sources is a
  **render-time** rule (the strongest status in a `--dedup` group wins), not stored state.
- The report stays a static HTML file. Each row renders its `uid` and one button per
  action that copies the **complete command** (e.g. `scalper status remotive::123 applied`)
  to the clipboard. The user pastes and runs it; the new badge appears on the next render.

## Alternatives considered

- **Local serve mode** (`scalper serve` backed by a localhost server accepting status
  POSTs). Most ergonomic, but breaks "self-contained static HTML" as the report surface and
  introduces a foreground process. Deferred, not rejected — it can be added later as an
  optional mode that calls the same store methods, so the CLI verbs are not wasted.
- **Browser-local state + re-import** (report JS writes to `localStorage` / a download,
  a `scalper sync` re-imports). Keeps the static file but splits state across two stores
  that desync. Rejected as fiddly and error-prone.
- **Status keyed by `dedup_key` (the Job) instead of `uid` (the Posting).** Would track
  "applied once, everywhere," but `dedup_key` is a fragile exact-match key that can both
  split one job and collide two distinct jobs — too risky to anchor irreversible user
  intent. Rejected; cross-source convenience is handled at render time instead.

## Consequences

- The server-less, CLI-over-SQLite model is preserved end to end; the report surface stays
  a single static file.
- There's a deliberate ergonomic gap: the user acts in the terminal and sees the result on
  the next render, rather than clicking in place. Accepted as small for a single-user local
  tool, and recoverable later via the deferred serve mode.
- Status survives re-collection and never affects the Match Score (it is user-asserted, not
  computed).
