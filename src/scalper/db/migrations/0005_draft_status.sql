-- Draft lifecycle status so a draft can be shown the instant it's requested.
-- 'pending' while the worker is drafting, 'ready' once the content is stored,
-- 'failed' if drafting errored (with the reason in `error`). Existing rows
-- predate the column and already carry content, so they default to 'ready'.
ALTER TABLE drafts ADD COLUMN status TEXT NOT NULL DEFAULT 'ready';
ALTER TABLE drafts ADD COLUMN error TEXT;
