-- Application pipeline stage on the per-user overlay, extending the simple
-- "applied" boolean into a mini funnel the user drives from the Applications
-- tab: applied -> interviewing -> offer, with rejected as an off-ramp. NULL
-- means not applied (the default and the state every existing row starts in).
--
-- Rows already marked applied (applied_at set) predate this column, so they're
-- backfilled to 'applied' to preserve their state. `applied` stays derivable
-- from applied_at everywhere it's shown; application_status adds the stage.
--
-- Run-once (tracked in schema_migrations); ADD COLUMN + a backfill UPDATE are
-- valid on both sqlite and Postgres.
ALTER TABLE user_posting_overlay ADD COLUMN application_status TEXT;
UPDATE user_posting_overlay SET application_status = 'applied' WHERE applied_at IS NOT NULL;
