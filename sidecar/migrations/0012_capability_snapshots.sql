-- 0012: 能力快照与锁文件

CREATE TABLE IF NOT EXISTS capability_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    capability_id TEXT NOT NULL,
    capability_version INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    dependency_tree TEXT NOT NULL DEFAULT '[]',
    snapshot_checksum TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cap_snapshots_checksum ON capability_snapshots(snapshot_checksum);
