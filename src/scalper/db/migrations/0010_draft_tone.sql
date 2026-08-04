-- Draft quality: per-draft tone and the skills the draft leaned on.
--
-- `tone` steers the cover-letter/summary voice on (re)generation; null means the
-- default professional tone. `matched_skills` is a JSON array of the profile
-- skills the posting matched at generation time, surfaced as "why this draft".
ALTER TABLE drafts ADD COLUMN tone TEXT;
ALTER TABLE drafts ADD COLUMN matched_skills TEXT;
