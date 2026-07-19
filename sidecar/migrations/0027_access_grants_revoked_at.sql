-- 0027: access_grants 表补充 revoked_at 列（幂等）

ALTER TABLE access_grants ADD COLUMN revoked_at TEXT;
