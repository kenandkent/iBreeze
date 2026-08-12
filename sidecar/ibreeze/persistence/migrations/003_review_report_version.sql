-- Review report optimistic-concurrency version used by the aggregate and
-- completion projections. Existing profiles keep their audit rows and gain
-- the same initial version as newly created reports.
ALTER TABLE review_reports
    ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
