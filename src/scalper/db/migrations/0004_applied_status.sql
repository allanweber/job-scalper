-- "Applied" status: the user manually marks a job as applied from the draft
-- detail screen. It lives on the per-user overlay (not the draft) so it's
-- visible everywhere a posting appears — feed, detail, saved — and joins to
-- drafts by posting_id for the Applications list. null => not applied; a
-- timestamp => applied at that time.
--
-- Run-once (tracked in schema_migrations); a plain ADD COLUMN is valid on both
-- sqlite and Postgres.
ALTER TABLE user_posting_overlay ADD COLUMN applied_at TEXT;
