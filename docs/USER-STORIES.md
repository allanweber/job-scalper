# Job Scalper — Launch & Monetization Backlog

> Prioritised user stories for taking the service from "feature-complete internal build"
> to a published, paid Google Play app. Complements `docs/DESIGN.md` (the architecture)
> and `CONTEXT.md` (the vocabulary). Story IDs are stable; phases are ordered by what
> blocks what, not by size.

## Where we are today

Phases 1–6 of `DESIGN.md` are built. What exists, grounded in the tree:

| Area | Built | Gap |
| --- | --- | --- |
| API | 40+ endpoints across auth / account / feed / postings / drafts / jobs / system | no billing surface, no feed search, no pagination cursor |
| Mobile | 4-tab shell (Feed / Saved / Applications / Profile), onboarding, drafts + PDFs, FCM push, delete-account | no paywall, no purchase flow, no in-app search/filters, no reminders |
| Admin | users, plans, quota overrides, settings, jobs/queue, usage, postings, sources, audit | no revenue/subscription views, no support tooling, no cohort metrics |
| Monetization | `plan` column, `_PLANS = ["free", "pro"]`, quota engine (`service/quota.py`), LLM cost estimates (`service/pricing.py`) | **nothing charges money** — no Play Billing, no entitlement sync, no promotional grants |
| Release | `mobile.yml` builds a signed **APK** to a GitHub Release | Play needs an **AAB**; no Play Console upload; no track automation |
| Legal | ToS + Privacy served as hard-coded stubs from `routers/system.py` | Play needs **publicly reachable URLs**; stubs are too thin for a resume-handling app |

The short version: the product works, but nothing about it is *publishable* or *chargeable* yet.

---

## Phase 1 — Play-ready (blocks everything else)

Goal: an internal-testing build live in Play Console, with every store declaration
answerable truthfully.

### PLAY-1 — Ship an App Bundle, not an APK
**As the operator, I want CI to produce a signed `.aab`, so that the build is uploadable to Play.**
- `mobile.yml` gains `flutter build appbundle --release` alongside the existing APK step.
- Play App Signing enrolled; the CI keystore becomes the *upload* key only.
- APK output stays for sideload/QA; the release job attaches both.
- Acceptance: a tagged `mobile-v*` run yields `app-release.aab` verified by `bundletool`.

### PLAY-2 — Automated upload to the internal track
**As the operator, I want tagged builds pushed to Play's internal track automatically, so that releases don't depend on manual uploads.**
- Service-account JSON in repo secrets; upload via the Play Developer Publishing API.
- `versionCode` derived monotonically (the workflow already derives a version — extend it).
- Acceptance: pushing `mobile-v1.0.0` lands a release on the internal track without human steps.

### PLAY-3 — Target API level and permission audit
**As the operator, I want the app to meet Play's current target-API requirement, so that submission isn't rejected.**
- Pin `targetSdk` explicitly rather than inheriting `flutter.targetSdkVersion`; confirm the
  threshold in Play Console at submission time (it moves each year).
- Audit the merged manifest: justify `POST_NOTIFICATIONS`, drop anything unused; no
  `QUERY_ALL_PACKAGES`.
- Acceptance: pre-launch report clean; no policy warnings in Play Console.

### PLAY-4 — Public legal pages
**As a prospective user, I want to read the privacy policy before installing, so that I know what happens to my resume.**
- Move `_TOS_BODY` / `_PRIVACY_BODY` out of `routers/system.py` into versioned Markdown,
  rendered both at `/legal/*` (the app reads it today) **and** as static pages on the
  existing GitHub Pages site (`portfolio/`).
- Content must actually cover: Google identity, resume blob + extracted text, LLM
  sub-processors (Anthropic/OpenAI), BYO-key handling, retention window, deletion path.
- Acceptance: `https://<site>/privacy` and `/terms` resolve publicly; the in-app copy and
  the web copy render from the same source and share a version string.

### PLAY-5 — Web account deletion
**As a user who has uninstalled the app, I want to delete my account from the web, so that I'm not forced to reinstall.**
- Play requires an externally reachable deletion route in addition to the in-app one
  (`delete_account_screen.dart` → `DELETE /account` covers in-app).
- Google sign-in on a small web page → same deletion path → confirmation email.
- Acceptance: deletion URL declared in the Data Safety form and reachable without the app.

### PLAY-6 — Data Safety declaration
**As the operator, I want the Data Safety form to match reality, so that the listing is truthful and durable.**
- Inventory what's collected: identity (Google sub/email), documents (resume), app activity
  (seen/saved/drafted), device tokens (FCM). Resume is sensitive — declare it as such.
- Declare encryption in transit, deletion path, and third-party sharing (LLM providers).
- Acceptance: a checked-in `docs/play/data-safety.md` mirrors the submitted form so future
  changes have a diff to review.

### PLAY-7 — Store listing assets
**As a prospective user, I want a listing that explains the product, so that I install it.**
- The screenshot harnesses (`mobile/tool/*_shots.py`, `main_*_shots.dart`) already generate
  deterministic captures — wire them to produce the exact Play sizes (phone + 7"/10" tablet
  if tablet is declared).
- Feature graphic (1024×500), icon (`brand_src/icon-square-512-play.png` exists), short +
  full description, content rating questionnaire.
- Acceptance: listing complete; screenshots regenerate from a single command.

### PLAY-8 — Closed testing cohort
**As the operator, I want the testing requirement satisfied early, so that production access isn't the thing that delays launch.**
- Personal developer accounts must run closed testing with a minimum tester count for a
  continuous window before production is unlocked — verify the current numbers in Console
  and **start the clock during Phase 1**, not after.
- Acceptance: closed track running with the required testers opted in; countdown started.

---

## Phase 2 — Monetization

Goal: `plan` flips to `pro` because someone paid, and flips back when they stop.

### MON-1 — Define the value ladder
**As the operator, I want Free and Pro to differ in ways users feel, so that upgrading is rational.**
Current free-tier constraints already in code: 1 profile, `_FREE_MAX_SOURCES` boards
(`routers/account.py:163`), monthly `draft` / `profile_build` / `enrich` quotas.
Proposed split (numbers are the knob, mechanism already exists):

| Capability | Free | Pro |
| --- | --- | --- |
| Job boards in feed | 3 | all enabled sources |
| Profiles | 1 | several (multi-search) |
| Drafts / month | small cap | large cap |
| Enrich / month | small cap | large cap |
| Draft from arbitrary URL | ✗ | ✓ (already designed as gated; SSRF-hardened) |
| Match alerts | daily digest | instant |
| Application tracking | ✓ | ✓ + reminders + export |

- Note: BYO key already lifts LLM limits for free, so Pro must sell *breadth and
  convenience*, not only tokens — otherwise the paid tier is undercut by a free workaround.
- Acceptance: the ladder lives in `quota.<plan>` settings + a small entitlement map, so it's
  tunable from the admin portal without a redeploy.

### MON-2 — Google Play Billing integration
**As a user, I want to subscribe from inside the app, so that upgrading takes one tap.**
- Monthly + annual subscription products in Play Console; `in_app_purchase` in Flutter.
- Purchase flow: buy → obtain purchase token → POST to the API → server verifies against the
  Play Developer API → sets `plan = "pro"` → app refreshes entitlement.
- **Never trust the client**: the app's local purchase state is a hint; the server's verified
  record is the truth.
- Acceptance: a test purchase on the internal track upgrades the account end-to-end.

### MON-3 — Server-side subscription state
**As the operator, I want subscription state stored and reconciled, so that entitlement survives reinstalls and refunds.**
- New `subscriptions` table: user, product, purchase token, state, current period end,
  auto-renew flag, latest verified payload.
- Real-time Developer Notifications (Pub/Sub → webhook) handle renew, cancel, grace period,
  account hold, pause, revoke, refund.
- A reconciliation job re-verifies active subscriptions on a schedule, so a missed
  notification self-heals.
- Acceptance: cancel/refund in a test account downgrades to `free` within one cycle.

### MON-4 — Paywall and upgrade prompts
**As a user hitting a limit, I want to understand what Pro gives me, so that I can decide in context.**
- A paywall screen plus contextual prompts at the exact block points: quota exhausted
  (`QuotaExceeded` already carries `QuotaStatus`), 4th board selection, URL-draft attempt.
- Show current usage vs limit (the `/account/quota` endpoint already returns this).
- Restore-purchases action for reinstalls.
- Acceptance: every 402/403-style block in the app routes to the paywall with the reason
  pre-filled, never a raw error.

### MON-5 — Grace, downgrade, and data safety on downgrade
**As a lapsed subscriber, I want my data intact when I downgrade, so that I'm not punished for pausing.**
- Downgrade reduces *limits*, never deletes drafts, applications, or resumes.
- Over-limit state (e.g. 5 boards on a plan allowing 3) is read-only until the user chooses
  what to keep — no silent truncation.
- Acceptance: downgrade path has tests covering boards, profiles, and draft retention.

### MON-6 — Billing in the admin portal
**As the operator, I want subscription and revenue visibility, so that I can run the business and support users.**
- Per-user: current plan, source of that plan (paid vs admin override), subscription state,
  period end, purchase token, verification history.
- Global: active subscribers, MRR estimate, trials, churn, refunds, and a **margin view**
  joining subscription revenue to the LLM cost estimates already produced by
  `service/pricing.py`.
- Acceptance: an admin can answer "is this user paid, and are they costing us money?" in one
  screen.

---

## Phase 2b — Coupons and promotional grants

Goal: the operator can hand a specific user a code that lifts their limits, and that code
works exactly once.

The quota engine already resolves a limit as *per-user override, else plan default*
(`service/quota.py:limit_for`). Coupons must **not** reuse `user_quota_overrides` — an
override is an absolute replacement set by an admin, so a coupon written into it would
silently overwrite (and be overwritten by) manual support grants and could never expire
cleanly. Coupons are a separate, **additive, expiring** layer.

### COUP-1 — Coupon model and redemption ledger
**As the operator, I want coupons stored with their grant and their redemption history, so that a code can never be used twice.**
- New migration (next in sequence after `0010_draft_tone.sql`) adding:
  - `coupons` — `code` (unique, stored case-folded), label, description, grant payload,
    `valid_from` / `valid_until`, `max_redemptions` (global cap, null = unlimited),
    `targeting` (`selected` | `open`), `created_by`, `revoked_at`.
  - `coupon_targets` — `coupon_id` + `user_id`/`email`, for `selected` coupons.
  - `coupon_redemptions` — `coupon_id`, `user_id`, **`email`**, `redeemed_at`, and a snapshot
    of what was granted. **Unique on `(coupon_id, email)`.**
- The unique constraint is keyed on **email, not `user_id`**, mirroring the existing durable
  usage ledger (`0009_usage_ledger_email.sql`): deleting and recreating an account must not
  reset a redemption, exactly as it must not reset consumed quota.
- Grant payload shape (JSON, so new grant kinds don't need a migration):
  ```json
  {"metrics": {"draft": 25, "enrich": 50}, "plan": "pro", "duration_days": 30}
  ```
  — extra units per metric, and/or a temporary plan upgrade. Absent keys grant nothing.
- Acceptance: a second redemption of the same code by the same identity is rejected with a
  distinct, testable error; concurrent redemptions of a `max_redemptions: 1` coupon settle so
  exactly one wins.

### COUP-2 — Additive grants in the quota engine
**As a user with a coupon, I want my extra units to actually raise my limit, so that the grant is real.**
- `limit_for` becomes: `base = override ?? plan_default`, then `base + sum(active grants)`.
- Unlimited stays absorbing: if `base == -1` or a grant is unlimited, the result is `-1`.
- A grant is active when it is unexpired and, for period-scoped grants, matches the current
  period key (`QuotaService.period()`, `YYYY-MM`).
- `QuotaStatus` gains `base_limit` and `granted` so callers can show *where* the headroom came
  from; `consume` / `refund` are untouched — coupons move the ceiling, never the counter.
- Acceptance: unit tests covering grant + override interaction, expiry mid-period, unlimited
  absorption, and that a refund after a coupon-funded call restores the right number.

### COUP-3 — Admin: create, target, and manage coupons
**As the operator, I want to create a coupon and assign it to a named user, so that I can compensate or onboard someone individually.**
- New admin section (`/coupons`) beside the existing users/settings/jobs pages:
  - Create: code (or generate one), grant payload built from a form — extra units per metric,
    optional temporary plan upgrade and its duration — validity window, targeting.
  - Target: pick specific users by email (typeahead over the user list), or mark the coupon
    open with a global redemption cap.
  - List: code, grant, targets, redeemed count / cap, validity, state.
  - Revoke: stops future redemptions; **already-redeemed grants keep running** unless
    explicitly clawed back (a separate, audited action).
- Every create/revoke/clawback writes to `admin_audit` with before→after, like the existing
  plan and quota actions.
- From a user's detail page, a one-click "issue coupon to this user" shortcut, since
  support-driven issuance is the common case.
- Acceptance: an operator can go from a support email to a targeted, single-use code in under
  a minute, and the audit log shows who issued it.

### COUP-4 — Mobile: redeem a code and see the grant
**As a user, I want to enter my code and immediately see my new limits, so that I trust it worked.**
- `POST /account/coupons/redeem` with the code; typed failures the app can phrase properly:
  unknown, expired, revoked, not targeted at you, already redeemed, globally exhausted.
- Redemption entry point in Profile → Usage, and as a secondary action on the paywall
  (MON-4) — "have a code?" — so a coupon is an alternative to paying, in context.
- After redeeming, the usage screen shows the boosted limit with its origin and expiry
  ("50 drafts — 25 from LAUNCH25, expires 30 Sep").
- `GET /account/quota` returns active grants so this renders without a second call.
- Acceptance: redeeming updates the usage screen without a restart; every failure mode has
  human copy, never a raw error.

### COUP-5 — Expiry, downgrade interaction, and notification
**As a user whose coupon is ending, I want to know before it lapses, so that I'm not surprised mid-application.**
- A scheduled sweep (the scheduler already owns periodic work) expires grants and, for
  plan-upgrade coupons, returns the user to their underlying plan.
- Interaction with MON-5: expiry reduces *limits only*. Drafts, applications, resumes, and
  board selections survive; anything now over-limit becomes read-only until the user chooses,
  never silently truncated.
- Optional push a few days before a grant expires (reuses the existing FCM sender).
- Acceptance: a plan-upgrade coupon on a free account reverts cleanly, and a user who paid for
  Pro during a coupon window keeps Pro afterwards.

### COUP-6 — Abuse and policy guardrails
**As the operator, I want coupons to be safe to hand out, so that a leaked code isn't a bill.**
- Rate-limit redemption attempts per account and per IP; codes generated with enough entropy
  that guessing is impractical; never expose a code-existence oracle (unknown and
  not-targeted-at-you should be indistinguishable to an untargeted caller).
- Every coupon grant is LLM-bound spend — surface coupon-funded usage separately in the admin
  cost view (ADM-4) so promotional cost is visible alongside plan cost.
- **Play policy:** a coupon here is a *free operator-issued grant*, which is fine. It must not
  become a way to sell Pro outside Play Billing — discounted or paid promotions belong in
  Play's own promo codes and subscription offers. Keep the two mechanisms distinct.
- Acceptance: a leaked open coupon is capped by `max_redemptions` and revocable in one action.

---

## Phase 3 — Usefulness (the "would I keep this on my phone" phase)

### APP-1 — Search and filter the feed
**As a job seeker, I want to search and filter my feed, so that I can find the right posting quickly.**
- Feed currently supports only `limit`, `min_score`, `sort` (`routers/feed.py`). Add: free-text
  query, company, location/timezone, salary floor, source, posted-within, hide-seen.
- Server-side, so it works across the whole pool rather than a fetched page.
- Acceptance: filters persist per user; empty states explain *why* nothing matched.

### APP-2 — Paginate the feed
**As a user with a broad profile, I want the feed to load progressively, so that it stays fast.**
- Replace the `limit`-capped list with cursor pagination + infinite scroll.
- Acceptance: a 5,000-posting pool scrolls smoothly on a mid-range device.

### APP-3 — Application reminders and follow-ups
**As an applicant, I want reminders to follow up, so that applications don't go stale.**
- The pipeline (`applied → pre_screen → interviewing → offer / ghosted / rejected`) exists but
  is passive. Add: per-application notes, interview date, next-action date, and a push
  reminder; auto-suggest "ghosted" after a configurable silence.
- Acceptance: setting a follow-up date produces a push at that date.

### APP-4 — Multiple profiles / saved searches
**As a job seeker exploring two directions, I want more than one profile, so that I can track both.**
- The CLI already supports multiple named profiles; the service enforces one. Lift to N for
  Pro, with per-profile feeds and alerts.
- Acceptance: switching profiles re-scores the feed without a re-scrape.

### APP-5 — Editable drafts and richer export
**As an applicant, I want to edit generated drafts before sending, so that they sound like me.**
- Draft update already exists (`PUT /drafts/{id}`); expose in-app markdown editing with live
  PDF regeneration, plus DOCX export and share-sheet integration.
- Acceptance: edit → re-render → share, all in-app.

### APP-6 — Onboarding that proves value fast
**As a new user, I want to see real matches within a minute, so that I don't abandon setup.**
- Resume upload → profile draft → feed is already the flow; measure and shorten it. Show a
  live match count during the profile-build wait rather than a spinner.
- Acceptance: time-to-first-match instrumented and reported in the admin portal.

### APP-7 — Digest notifications
**As a user, I want a daily digest instead of a stream of pings, so that alerts stay welcome.**
- Notification prefs today are `match_alerts` + `min_score`. Add cadence (instant / daily /
  weekly), quiet hours, and per-profile alerts.
- Acceptance: a daily digest push groups the day's matches into one notification.

### APP-8 — Offline and error resilience
**As a commuter, I want the app to work on a bad connection, so that it's usable in real life.**
- Cache the last feed, saved list, and drafts (sqflite is already a dependency); queue writes;
  typed error surfaces instead of raw dio failures.
- Acceptance: airplane mode still shows the last feed and stored PDFs.

---

## Phase 4 — Admin portal completeness

### ADM-1 — Support console per user
**As an operator answering a support email, I want one page with the user's whole story, so that I can resolve it without SQL.**
- Timeline: sign-up, consent version, jobs run, quota consumption, subscription events,
  push delivery, errors. Actions: resend notification, re-run failed job, grant one-off
  credits, force entitlement re-check.
- Acceptance: no operator task requires a database shell.

### ADM-2 — Product and funnel metrics
**As the operator, I want activation and retention metrics, so that I know whether the product works.**
- Sign-ups, onboarding completion, time-to-first-match, feed opens, drafts created,
  applications marked, D1/D7/D30 retention, free→paid conversion.
- Acceptance: a dashboard answering "did last week's release help?".

### ADM-3 — Source health and yield
**As the operator, I want to see which sources actually produce matches, so that I can prune dead ones.**
- Per source: last successful run, error rate, postings added, share of *matched* postings,
  duplicate rate, average latency. Auto-disable on sustained failure with an alert.
- Acceptance: a failing adapter surfaces within one scrape interval.

### ADM-4 — Cost controls and alerting
**As the operator, I want spend guardrails, so that a bad day can't produce a shocking bill.**
- Daily/monthly platform-LLM budget with soft alert and hard cutover to BYO-only.
- Per-user anomaly detection (one account consuming disproportionate tokens).
- Acceptance: crossing the soft threshold notifies the operator; crossing the hard one stops
  platform-key spend.

### ADM-5 — Content moderation and abuse
**As the operator, I want to act on abuse, so that the platform stays lawful and cheap to run.**
- Flag/suspend flows exist (`/users/{id}/suspend`); add rate-limit visibility, repeated-URL
  import abuse detection, and a blocklist for import domains.
- Acceptance: a suspended user's jobs stop consuming platform tokens immediately.

### ADM-6 — Release and config safety
**As the operator, I want risky settings changes to be reversible, so that a typo isn't an outage.**
- `admin_audit` records before→after already; add one-click revert, plus a staged rollout
  flag for new features (server-driven feature flags the app reads at startup).
- Acceptance: any settings change can be reverted from the audit log.

---

## Phase 5 — Platform hardening (parallel track)

- **PLT-1** Structured logging + error tracking (Sentry or equivalent) across API, worker, scheduler.
- **PLT-2** Uptime/health alerting on `/healthz` and `/readyz`, plus queue-depth alerts.
- **PLT-3** Backup restore *drill* — the Postgres backups exist (ADR 0012); prove a restore.
- **PLT-4** Load test the feed query at realistic pool size; add the indexes it demands.
- **PLT-5** Rate limiting per user and per IP on the public API.
- **PLT-6** GDPR export ("download my data") alongside the existing deletion path.
- **PLT-7** iOS parity decision — the Flutter project has an `ios/` target; either commit to
  App Store submission (a separate compliance track) or explicitly defer it.

---

## Sequencing

```
Phase 1 (Play-ready) ──> Phase 2 (Monetization) ──> Phase 3 (Usefulness)
        │                        │
        │                        ├── Phase 2b (Coupons) — needs MON-1's ladder, not Billing
        └── PLAY-8 clock          └── Phase 4 (Admin) tracks alongside 2 and 3
            starts early
Phase 5 runs continuously.
```

**Critical path to a paid app:** PLAY-1 → PLAY-2 → PLAY-4 → PLAY-6 → PLAY-8 (clock) →
MON-1 → MON-2 → MON-3 → MON-4.

Coupons are **off** that path — COUP-1/COUP-2 touch only the quota engine and can land
before Billing exists, which makes them a useful way to compensate closed-testing testers
(PLAY-8) while the payment work is still in flight.

**Biggest risks:**
1. **The testing-window clock.** It is calendar time you cannot compress — start it first.
2. **Pro undercut by BYO keys.** If Pro only buys LLM quota, a free user with an Anthropic key
   gets the same product. MON-1 must put breadth (boards, profiles, URL drafting) behind the
   paywall, not just tokens.
3. **Privacy scrutiny.** Resumes are sensitive personal data; a stub policy is a rejection
   risk and a real liability. PLAY-4 deserves proper drafting, not a paraphrase.
4. **Unit economics.** Platform LLM spend per free user is currently unbounded except by
   quota; ADM-4 should land before any marketing push. Coupons raise that ceiling by design,
   so coupon-funded usage needs to be visible (COUP-6) before codes go out widely.
5. **Coupon replay.** Keying single-use on `user_id` would let a delete-and-recreate redeem
   again — the same hole the email-keyed usage ledger already closes. COUP-1 keys on email
   for that reason.
