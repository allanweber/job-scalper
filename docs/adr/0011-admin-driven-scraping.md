# Scraping is admin/schedule-driven, not user-triggered

Users have **no ability to start a scrape**. The shared postings pool is filled only by
**scheduled runs** and by an **admin "run now"** action in the admin portal. The scrape
interval is an admin-configurable **hot setting** (`scrape.interval_minutes`), changeable
live from the portal without a redeploy.

An **in-process scheduler** — its own always-on service using the existing RQ + Redis —
reads the interval from the `settings` table and enqueues a scrape job each interval;
"run now" enqueues the same job on demand. The scheduler also owns periodic auto-purge.
This **replaces Dokploy cron**, whose static expression can't express a runtime-editable
interval.

A run scrapes **every admin-enabled source** (`sources.enabled`) using the **union of
active users' profile terms** (active = a live user seen within
`scrape.active_user_window_days`); broad-feed sources just pull recent postings. The pool
is therefore demand-driven — it holds what users actually search for. Because users don't
scrape, the free-tier **"3 boards" limit now gates feed visibility only** (a user's feed
shows postings from their ≤3 chosen sources, a subset of the enabled catalog), and there is
**no user scrape quota or cooldown**.

## Considered options

- **Keep user-triggered on-demand scrape** (the earlier design) — immediacy for the user,
  but invites abuse/cost on shared infra, needs per-user cooldown + scrape quotas, and lets
  free users drive load across many boards. Rejected in favour of central control.
- **Interval mechanism — Dokploy cron + last-run gate** (frequent fixed tick that decides
  whether to scrape): no extra process, but granularity is capped by the tick and it idles
  every few minutes. **Rewrite Dokploy cron from the app**: couples to Dokploy's API and is
  brittle. Rejected for an in-process scheduler reading the hot setting.
- **Scrape scope — admin-defined global query** or **broad-feed-only**: simpler and fully
  predictable, but niche user profiles match little and query-only sources (Remotive search,
  Adzuna) are underused. Rejected for the union-of-active-users scope.

## Consequences

The Dokploy footprint gains an always-on **scheduler** service and loses Dokploy cron.
Scrape becomes a system job kind (`user_id` null) recorded in `jobs` for admin monitoring
and "run now"; `scrape.last_run_at` persists timing across restarts. The pool's coverage is
a function of the active user base, so a brand-new deployment with no users scrapes nothing
until profiles exist (the admin can seed terms by creating a profile or running manually).
Per-user scrape quotas/cooldown are removed from the quota model; the settings table carries
`scrape.interval_minutes`, `scrape.active_user_window_days`, `sources.enabled`, and
`sources.default` instead.
