-- Review assignment optimistic-concurrency version.
-- Kept as a separate migration so existing v1 profiles are upgraded without
-- rebuilding their review history.
ALTER TABLE review_assignments
    ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
