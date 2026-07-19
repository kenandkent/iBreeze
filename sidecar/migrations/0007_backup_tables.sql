-- 0007: 备份快照表

CREATE TABLE IF NOT EXISTS snapshot_epochs (
    snapshot_epoch INTEGER PRIMARY KEY AUTOINCREMENT,
    state TEXT NOT NULL DEFAULT 'creating' CHECK (state IN ('creating', 'ready', 'failed')),
    sqlite_event_watermark TEXT,
    outbox_delivery_watermark TEXT,
    lancedb_generation_map_json TEXT DEFAULT '{}',
    session_watermarks_json TEXT DEFAULT '{}',
    barrier_started_at TEXT NOT NULL,
    captured_at TEXT,
    failure_code TEXT
);

CREATE TABLE IF NOT EXISTS backup_manifests (
    backup_id TEXT PRIMARY KEY,
    snapshot_epoch INTEGER NOT NULL REFERENCES snapshot_epochs(snapshot_epoch),
    kind TEXT NOT NULL DEFAULT 'full',
    app_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    archive_path TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    encrypted_archive_sha256 TEXT,
    wrapped_dek TEXT,
    file_count INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'creating' CHECK (status IN ('creating', 'available', 'deleted')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    deleted_at TEXT,
    delete_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_backup_status ON backup_manifests(status);
CREATE INDEX IF NOT EXISTS idx_backup_epoch ON backup_manifests(snapshot_epoch);
