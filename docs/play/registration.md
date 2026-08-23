# Google Play registration — data pack

Everything needed to fill in **Play Console → Set up your app** (app content
declarations) and **Main store listing**, plus the **Data safety** form. Values
are grounded in what the app actually does; keep this file in sync with reality
so the declaration always has a diff to review.

> ⚠️ These policies and declarations are written in good faith and in plain
> language from the app's real data flows — they are **not legal advice**. Have
> them reviewed before launch, and confirm the **governing law** (currently the
> Netherlands) in `portfolio/terms.html`.

## Public URLs (served from GitHub Pages, `portfolio/`)

Live after this change merges to `main` and the Pages workflow deploys:

- **Privacy policy:** https://allanweber.github.io/job-scalper/privacy.html
- **Terms of service:** https://allanweber.github.io/job-scalper/terms.html

Both are required by the store listing and the Data safety form.

---

## 1. Main store listing

| Field | Value |
| --- | --- |
| App name (≤30) | `Job Scalper` |
| Category | Business (alt: Productivity) |
| Contact email | a.cassianoweber@gmail.com |
| Privacy policy URL | https://allanweber.github.io/job-scalper/privacy.html |

**Short description** (≤80):

```
AI-matched remote tech jobs with tailored resumes and application tracking.
```

**Full description** (≤4000):

```
Job Scalper finds remote tech jobs that actually fit you — and helps you apply faster.

Instead of scrolling endless boards, Job Scalper searches many remote job sources at once, scores every posting against your profile, and shows you a ranked feed of the best matches. Upload your resume once and it builds your profile automatically.

WHAT YOU GET

• Matched feed — every job scored against your skills, title, and keywords, best matches first. Sort by match or by newest.
• One-tap tailoring — generate a resume and cover letter tailored to a specific job with AI, ready to review and send.
• Application tracker — move each application through Applied, Pre-screen, Interviewing, Offer, and see your funnel at a glance.
• Save and revisit — bookmark jobs to come back to.
• Add any job — paste a link or the job text to score and draft against roles you found elsewhere.
• Match alerts — get notified when strong new matches appear.

BUILT FOR REMOTE TECH ROLES

Job Scalper focuses on the remote-first job market, pulling from many company-agnostic sources so you see the market, not one company's board.

FREE TO START

Start free with a core set of job sources and monthly AI drafting. Bring your own AI key to lift limits.

Your resume is yours: it's used to match jobs and tailor your applications, and you can delete your account and data at any time.
```

**Graphics**

| Asset | Spec | Status |
| --- | --- | --- |
| App icon | 512×512 PNG | ✅ `mobile/brand_src/icon-square-512-play.png` |
| Feature graphic | 1024×500 | ❌ to create (PLAY-7) |
| Phone screenshots (≥2) | ≥1080 px | ✅ generate via `mobile/tool/portfolio_shots.py` / `main_*_shots.dart`; sources in `portfolio/images/` |

---

## 2. App content declarations ("Set up your app")

| Section | Answer |
| --- | --- |
| **App access** | All functionality requires Google Sign-In → **"All or some functionality is restricted."** Provide reviewer access (demo Google account or a review-only login path). ⬜ Decision needed — this blocks review if left empty. |
| **Ads** | **No** — the app contains no ads (no ad SDK). |
| **Content rating** | Category: Utility/Productivity. No violence, sexual content, profanity, drugs, or gambling. No public user-generated content. No location sharing. Expected: **Everyone / PEGI 3.** |
| **Target audience & content** | Target age **18+** (handles resumes / employment data). Not directed at or appealing to children → not in the Families program. |
| **News app** | No |
| **Government app** | No |
| **Financial features** | None. (Future subscriptions go through Google Play Billing, which is not a "financial feature".) |
| **Health** | No health data collected. |

---

## 3. Data safety form

All collected data is **encrypted in transit**; a deletion path exists (in-app
*Delete account*, plus the web deletion route from PLAY-5).

### Data collected

| Data type (Play category) | Collected | Shared | Purpose | Optional? |
| --- | --- | --- | --- | --- |
| Name — *Personal info* (Google) | Yes | No | App functionality, Account management | Required |
| Email address — *Personal info* (Google) | Yes | No | App functionality, Account management | Required |
| Resume — *Files & docs* | Yes | No* | App functionality (matching + tailored drafts) | Optional |
| In-app actions — *App activity* (saved/seen/drafted, application status) | Yes | No | App functionality | Required |
| Push token — *Device or other IDs* (FCM) | Yes | No | App functionality (notifications) | Optional |

**Not collected:** device location, financial info, health, contacts, photos/videos,
messages, audio, calendar, browsing history, advertising ID.

### Security section answers

- **Is data encrypted in transit?** Yes (HTTPS/TLS).
- **Can users request that data be deleted?** Yes (in-app *Delete account* + web deletion route).
- **Is data collection required or optional?** Account data required; the resume is optional.

### * The LLM-processing nuance (get this right)

When a user generates a tailored draft, their **resume text and the job posting
are sent to the AI provider (Anthropic / OpenAI)** to write the draft. Under Data
safety this is *processing by a service provider on our behalf*, not "sharing" for
the provider's own use — so mark the resume as **collected, not shared**, but the
privacy policy **must name Anthropic and OpenAI as sub-processors** (it does; see
`portfolio/privacy.html` §3). A resume is sensitive PII, so this must be accurate.

---

## 4. Open items before the listing can go live

1. **App access reviewer credentials / demo login** — decide and provide (blocks review).
2. **Feature graphic** (1024×500) — PLAY-7.
3. **First manual upload to Play** — the Publishing API can't bootstrap a brand-new
   app; create the app and upload one AAB by hand before the tagged-release
   automation (PLAY-2) can take over.
4. **Legal review** of the privacy policy and terms; confirm governing law.
5. **Reconcile the in-app legal text.** The app reads `/legal/*` from the API, whose
   bodies (`src/scalper/service/routers/system.py`) are still the older short stubs.
   Update those to match these public pages (and share the `2026-08-23` version
   string) so in-app consent and the public policy don't diverge. Follow-up.
