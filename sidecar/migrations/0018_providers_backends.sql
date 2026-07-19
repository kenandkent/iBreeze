CREATE TABLE IF NOT EXISTS providers (
    provider_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    config TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS provider_models (
    model_id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    model TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    supports TEXT NOT NULL DEFAULT '[]',
    owner_company_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS backends (
    backend_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    name TEXT NOT NULL,
    backend_type TEXT NOT NULL DEFAULT 'local_process',
    status TEXT NOT NULL DEFAULT 'disabled',
    health_status TEXT NOT NULL DEFAULT 'unknown',
    capabilities TEXT NOT NULL DEFAULT '[]',
    workspace_types TEXT NOT NULL DEFAULT '[]',
    workspace_root TEXT NOT NULL DEFAULT '',
    concurrency_limit INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS backend_leases (
    lease_id TEXT PRIMARY KEY,
    backend_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    run_id TEXT,
    session_turn_id TEXT,
    worker_pid INTEGER,
    process_start_token TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    heartbeat_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK ((run_id IS NOT NULL AND session_turn_id IS NULL) OR (run_id IS NULL AND session_turn_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS backend_queue_entries (
    entry_id TEXT PRIMARY KEY,
    backend_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    run_id TEXT,
    session_turn_id TEXT,
    wait_reason TEXT,
    cancel_reason TEXT,
    status TEXT NOT NULL DEFAULT 'waiting',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK ((run_id IS NOT NULL AND session_turn_id IS NULL) OR (run_id IS NULL AND session_turn_id IS NOT NULL))
);
