-- Push notifications: registered devices, per-user preferences, and a dedup
-- marker so a given match is pushed at most once.
--
-- A user can have several devices; the FCM registration token is the natural
-- key (one row per device). Preferences default to the product promise —
-- alerts on, notify at score >= 90 — so a user who opts in during onboarding
-- and registers a device is covered without any extra setup. `notified_at` on
-- the overlay records that we've already pushed a user about a posting.
--
-- Run-once (tracked in schema_migrations); valid on both sqlite and Postgres.

CREATE TABLE IF NOT EXISTS push_devices (
    token        TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform     TEXT,
    created_at   TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_push_devices_user ON push_devices(user_id);

CREATE TABLE IF NOT EXISTS notification_prefs (
    user_id      TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    match_alerts INTEGER NOT NULL DEFAULT 1,
    min_score    INTEGER NOT NULL DEFAULT 90,
    updated_at   TEXT NOT NULL
);

ALTER TABLE user_posting_overlay ADD COLUMN notified_at TEXT;
