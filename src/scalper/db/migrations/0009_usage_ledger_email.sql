-- Rekey the usage ledger from subject_hash to email (supersedes 0008).
--
-- 0008 created usage_ledger keyed by a salted subject hash. We switched to a
-- simpler email key, but 0008 had already been applied in some environments, so
-- editing it wouldn't take effect. The ledger holds only current-period abuse
-- counters (they reset monthly), so dropping and recreating loses nothing
-- meaningful. Idempotent on a fresh database too.
DROP TABLE IF EXISTS usage_ledger;

CREATE TABLE IF NOT EXISTS usage_ledger (
    email      TEXT NOT NULL,
    metric     TEXT NOT NULL,
    period     TEXT NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (email, metric, period)
);

CREATE INDEX IF NOT EXISTS idx_usage_ledger_period ON usage_ledger(period);
