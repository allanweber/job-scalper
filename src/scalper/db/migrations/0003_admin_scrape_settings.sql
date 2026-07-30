-- Admin-configurable scrape controls (hot settings). ON CONFLICT DO NOTHING so
-- re-running is a no-op and admin edits are never clobbered.

INSERT INTO settings (key, value, updated_at) VALUES
    -- Only ingest postings published within this many days. null = no limit
    -- (postings without a published date are always kept).
    ('scrape.freshness_days', 'null', '1970-01-01T00:00:00+00:00'),
    -- Search terms a scheduled scrape uses when there are no active user
    -- profiles yet, so the pool still fills with relevant jobs.
    ('scrape.default_terms',
     '["software engineer","backend developer","frontend developer","data engineer","product manager"]',
     '1970-01-01T00:00:00+00:00')
ON CONFLICT (key) DO NOTHING;
