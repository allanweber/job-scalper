-- Identity-scoped usage ledger (abuse prevention).
--
-- LLM quotas are counted per user_id in `usage_counters`, which is wiped when an
-- account is deleted; recreating the account then mints a new user_id and resets
-- the count. This ledger is keyed by a salted hash of the Google subject (not
-- user_id) and is deliberately NOT removed on account deletion, so a user can't
-- reset their monthly quota by deleting and recreating their account. It holds
-- no PII — only the hash, the metric, the period, and a count.
CREATE TABLE IF NOT EXISTS usage_ledger (
    subject_hash TEXT NOT NULL,
    metric       TEXT NOT NULL,
    period       TEXT NOT NULL,
    count        INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (subject_hash, metric, period)
);

CREATE INDEX IF NOT EXISTS idx_usage_ledger_period ON usage_ledger(period);
