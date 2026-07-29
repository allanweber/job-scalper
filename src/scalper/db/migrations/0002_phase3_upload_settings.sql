-- Phase 3: hot settings for resume uploads (admin-configurable; see DESIGN.md).
-- INSERT OR IGNORE so re-running is a no-op and admin edits are never clobbered.

INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES
    -- Max accepted resume upload size, bytes (5 MB default).
    ('upload.max_bytes', '5000000', '1970-01-01T00:00:00+00:00'),
    -- Accepted upload content types (PDF / markdown / plain text). Empty => allow any.
    ('upload.allowed_content_types',
     '["application/pdf","text/plain","text/markdown","text/x-markdown"]',
     '1970-01-01T00:00:00+00:00');
