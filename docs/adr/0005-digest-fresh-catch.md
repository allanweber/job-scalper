# 0005 — Digest scrapes first and reports the Fresh Catch

- Status: Accepted
- Date: 2026-06-16

## Context

We want a "what's new" command. The instinct is to define "new" relative to the
*reader* (postings seen since you last looked), but that needs per-user, per-profile
view-tracking state the tool doesn't have and that complicates the static-report model.
There's a cheaper, already-available signal: `postings.collected_at` is set on first
insert and **preserved** by the `ON CONFLICT(uid) DO UPDATE` clause (it isn't in the
update list), so it is effectively a stable *first-seen* timestamp.

## Decision

`scalper digest` is one verb that **collects first, then reports only the Fresh Catch**:
capture a `run_start`, run the normal collect path, then render only the postings whose
first-seen `collected_at >= run_start` through the existing report renderer. "New" is
therefore **store-relative and per-run** — what this scrape surfaced that the store
didn't already hold — not reader-relative. No schema change is required, and a posting
already in the store that merely re-appears this run is *not* a Fresh Catch.

## Considered Options

- **Reader-relative "new" (since you last reported).** More personal, but needs
  per-profile view state and a writable surface the static `file://` report doesn't have.
  Rejected as too much machinery for a personal, server-less tool. (An earlier
  Posting-Status / New-Unseen design that went this way was dropped.)
- **A separate `first_seen` column / run-log table.** Redundant: `collected_at` already
  survives re-collection and gives us first-seen for free.

## Consequences

- "New" in the Digest means *new to the store this run*, deliberately distinct from how
  old the underlying job is (the Freshness Window). A future reader comparing the two
  should not expect them to agree.
- The semantics are correct only as long as `collected_at` stays out of the upsert's
  `DO UPDATE SET` list — that preservation is load-bearing, not incidental.
