-- Initial multi-tenant schema for the Job Scalper service.
--
-- Conventions:
--   * Ids are TEXT (uuid4 hex or a content hash), assigned by the app.
--   * Timestamps are TEXT ISO-8601 UTC (matches the original sqlite store).
--   * Booleans are INTEGER 0/1.
--   * JSON payloads are TEXT.
--   * Binary (files, ciphertext) is BLOB.
--
-- Tenancy: postings + enrichments are a SHARED pool (no user_id); everything a
-- user owns (profiles, resumes, drafts, overlays, usage) is scoped by user_id.

------------------------------------------------------------------------------
-- Identity, auth, consent
------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id                  TEXT PRIMARY KEY,
    google_sub          TEXT NOT NULL UNIQUE,
    email               TEXT NOT NULL UNIQUE,
    display_name        TEXT,
    avatar_url          TEXT,
    role                TEXT NOT NULL DEFAULT 'user',    -- 'user' | 'admin'
    status              TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'suspended'
    plan                TEXT NOT NULL DEFAULT 'free',
    tos_accepted_at     TEXT,
    privacy_accepted_at TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    last_login_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Mobile refresh tokens (access JWTs are stateless). We store only a hash so a
-- DB leak can't replay tokens. Revocation = set revoked_at.
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    device_info TEXT,
    issued_at   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    revoked_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_tokens(user_id);

-- Admin web sessions live in Redis, not here (see ADR 0010).

------------------------------------------------------------------------------
-- BYO LLM credentials (encrypted at rest, version-tagged for rotation)
------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS llm_credentials (
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL,               -- 'anthropic' | 'openai'
    ciphertext      BLOB NOT NULL,               -- envelope-encrypted API key
    nonce           BLOB NOT NULL,               -- AEAD nonce/IV
    key_version     INTEGER NOT NULL,            -- master-key version used
    valid           INTEGER NOT NULL DEFAULT 1,  -- last validation result
    last_validated_at TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (user_id, provider)
);

------------------------------------------------------------------------------
-- Per-user search config: profile (free = 1) + chosen sources (<= 3 free)
------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS profiles (
    id                    TEXT PRIMARY KEY,
    user_id               TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                  TEXT NOT NULL,
    titles                TEXT NOT NULL DEFAULT '[]',  -- JSON string[]
    required_skills       TEXT NOT NULL DEFAULT '[]',
    nice_to_have_skills   TEXT NOT NULL DEFAULT '[]',
    keywords              TEXT NOT NULL DEFAULT '[]',
    exclude_keywords      TEXT NOT NULL DEFAULT '[]',
    remote_only           INTEGER NOT NULL DEFAULT 1,
    salary_floor          REAL NOT NULL DEFAULT 0,
    exclude_non_latin     INTEGER NOT NULL DEFAULT 1,
    weights               TEXT NOT NULL DEFAULT '{}',   -- JSON Weights
    origin                TEXT NOT NULL DEFAULT 'manual', -- 'resume' | 'manual'
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profiles_user ON profiles(user_id);

-- The boards a user searches / sees (gates BOTH scrape and feed visibility).
CREATE TABLE IF NOT EXISTS user_sources (
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,     -- adapter key, e.g. 'remotive'
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, source_type)
);

------------------------------------------------------------------------------
-- Resumes (one active per user; re-upload updates it). BLOB + extracted text.
------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS resumes (
    user_id        TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    filename       TEXT,
    content_type   TEXT,
    size_bytes     INTEGER NOT NULL DEFAULT 0,
    file_blob      BLOB NOT NULL,
    extracted_text TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

------------------------------------------------------------------------------
-- Shared postings pool (storage-time deduped) + per-source provenance
------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS postings (
    id              TEXT PRIMARY KEY,            -- app-assigned (dedup_key-derived)
    dedup_key       TEXT NOT NULL UNIQUE,        -- normalized company+title+location
    company         TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    location        TEXT,
    remote          INTEGER NOT NULL DEFAULT 0,
    timezone        TEXT,
    salary_min      REAL,
    salary_max      REAL,
    salary_currency TEXT,
    url             TEXT NOT NULL,               -- best/primary url
    published_at    TEXT,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    raw             TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_postings_published ON postings(published_at);
CREATE INDEX IF NOT EXISTS idx_postings_last_seen ON postings(last_seen_at);

-- Every source a deduped posting was seen on (keeps provenance; drives the
-- source-filtered feed). One row per exact within-source identity.
CREATE TABLE IF NOT EXISTS posting_sources (
    source      TEXT NOT NULL,       -- adapter name, e.g. 'remotive'
    source_id   TEXT NOT NULL,       -- stable id within that source
    posting_id  TEXT NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
    url         TEXT NOT NULL,
    seen_at     TEXT NOT NULL,
    PRIMARY KEY (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_posting_sources_posting ON posting_sources(posting_id);
CREATE INDEX IF NOT EXISTS idx_posting_sources_source ON posting_sources(source);

------------------------------------------------------------------------------
-- Shared enrichment cache (NOT user-scoped): reused across users to save
-- platform tokens. Keyed by posting + profile-criteria hash + model.
------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS enrichments (
    posting_id   TEXT NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
    profile_hash TEXT NOT NULL,
    model        TEXT NOT NULL,
    data         TEXT NOT NULL,       -- JSON enrichment payload
    created_at   TEXT NOT NULL,
    PRIMARY KEY (posting_id, profile_hash, model)
);

------------------------------------------------------------------------------
-- Per-user overlay on the shared pool: score, seen ("new" badge), saved, drafted
------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_posting_overlay (
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    posting_id      TEXT NOT NULL REFERENCES postings(id) ON DELETE CASCADE,
    score           REAL,
    score_breakdown TEXT,            -- JSON
    first_matched_at TEXT,           -- when it first matched this user (for "new")
    seen_at         TEXT,            -- null => unseen => "new" badge
    saved           INTEGER NOT NULL DEFAULT 0,
    drafted_at      TEXT,
    PRIMARY KEY (user_id, posting_id)
);
CREATE INDEX IF NOT EXISTS idx_overlay_user ON user_posting_overlay(user_id);

------------------------------------------------------------------------------
-- Drafts (PRIVATE per user; never shared). Markdown source + rendered PDFs.
------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS drafts (
    id                TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    profile_id        TEXT REFERENCES profiles(id) ON DELETE SET NULL,
    posting_id        TEXT REFERENCES postings(id) ON DELETE SET NULL,
    job_source        TEXT NOT NULL DEFAULT 'pool', -- 'pool' | 'url'
    source_url        TEXT,                          -- when job_source='url'
    resume_md         TEXT,
    cover_letter_md   TEXT,
    stretch_claims_md TEXT,
    resume_pdf        BLOB,
    cover_letter_pdf  BLOB,
    provider          TEXT,
    model             TEXT,
    key_source        TEXT,                          -- 'platform' | 'byo'
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drafts_user ON drafts(user_id);

------------------------------------------------------------------------------
-- Async jobs (durable record backing job_id polling + admin monitoring).
-- RQ holds the live queue state in Redis; this mirrors it for querying.
------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,     -- our id (also the RQ job id)
    user_id     TEXT REFERENCES users(id) ON DELETE CASCADE,  -- null for system jobs
    kind        TEXT NOT NULL,        -- 'scrape'|'profile'|'draft'|'enrich'|'collect'|'purge'
    status      TEXT NOT NULL DEFAULT 'queued', -- queued|running|succeeded|failed
    params      TEXT NOT NULL DEFAULT '{}',
    result      TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

------------------------------------------------------------------------------
-- Quotas & usage. Fast counters for enforcement + a detailed token ledger.
------------------------------------------------------------------------------

-- Per-user, per-metric, per-period counters (period: 'YYYY-MM' or 'YYYY-MM-DD').
CREATE TABLE IF NOT EXISTS usage_counters (
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    metric     TEXT NOT NULL,        -- 'draft'|'profile_build'|'enrich' (users never scrape)
    period     TEXT NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, metric, period)
);

-- Detailed LLM spend ledger (cost visibility + admin).
CREATE TABLE IF NOT EXISTS llm_usage_events (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ts            TEXT NOT NULL,
    action        TEXT NOT NULL,     -- 'draft'|'profile_build'|'enrich'
    provider      TEXT NOT NULL,
    model         TEXT NOT NULL,
    key_source    TEXT NOT NULL,     -- 'platform' | 'byo'
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    est_cost_usd  REAL,
    job_id        TEXT
);
CREATE INDEX IF NOT EXISTS idx_llm_usage_user_ts ON llm_usage_events(user_id, ts);

-- Per-user quota overrides (admin can raise a single user's limits without billing).
CREATE TABLE IF NOT EXISTS user_quota_overrides (
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    metric      TEXT NOT NULL,
    limit_value INTEGER NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, metric)
);

------------------------------------------------------------------------------
-- Hot-applied global settings + admin audit trail
------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,       -- JSON
    updated_at TEXT NOT NULL,
    updated_by TEXT
);

CREATE TABLE IF NOT EXISTS admin_audit (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    admin_user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
    action      TEXT NOT NULL,
    target_type TEXT,
    target_id   TEXT,
    before      TEXT,               -- JSON
    after       TEXT,               -- JSON
    note        TEXT
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_ts ON admin_audit(ts);

------------------------------------------------------------------------------
-- Seed default hot settings (edited later via the admin app). ON CONFLICT DO
-- NOTHING so re-running is a no-op and admin edits are never clobbered. (This
-- form is valid on both Postgres and sqlite.)
------------------------------------------------------------------------------

INSERT INTO settings (key, value, updated_at) VALUES
    -- User quotas (LLM-bound only; users never trigger scrapes — see ADR 0011).
    ('quota.free',          '{"draft_per_month":5,"profile_build_per_month":5,"enrich_per_month":30}', '1970-01-01T00:00:00+00:00'),
    ('llm.per_request_token_ceiling', '20000', '1970-01-01T00:00:00+00:00'),
    ('llm.platform_models',  '{"anthropic":{"enrich":"claude-haiku-4-5","draft":"claude-haiku-4-5"}}', '1970-01-01T00:00:00+00:00'),
    ('llm.byo_models',       '{"anthropic":{"enrich":"claude-haiku-4-5","draft":"claude-sonnet-4-6"},"openai":{"enrich":"gpt-4o-mini","draft":"gpt-4o"}}', '1970-01-01T00:00:00+00:00'),
    -- Scraping is admin/schedule-driven (ADR 0011). The scheduler reads
    -- scrape.interval_minutes; runs scrape the union of active users' profile
    -- terms across sources.enabled; active = seen within active_user_window_days.
    ('scrape.interval_minutes', '360', '1970-01-01T00:00:00+00:00'),
    ('scrape.active_user_window_days', '30', '1970-01-01T00:00:00+00:00'),
    ('scrape.last_run_at',   'null', '1970-01-01T00:00:00+00:00'),
    ('sources.enabled',      '["remotive","remoteok","arbeitnow","jobicy","themuse","workingnomads","himalayas","weworkremotely","hackernews","fourdayweek","jobspresso"]', '1970-01-01T00:00:00+00:00'),
    ('sources.default',      '["remotive","remoteok","arbeitnow"]', '1970-01-01T00:00:00+00:00'),
    ('retention.days',       '30', '1970-01-01T00:00:00+00:00'),
    ('maintenance.enabled',  'false', '1970-01-01T00:00:00+00:00')
ON CONFLICT (key) DO NOTHING;
