-- 0004: 本机唯一身份主体

CREATE TABLE IF NOT EXISTS local_owner (
    owner_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT 'Local Owner',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_local_owner_single ON local_owner(owner_id);
