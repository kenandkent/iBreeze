CREATE TABLE IF NOT EXISTS rpc_idempotency_records (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    method TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'succeeded', 'failed')),
    response_ref TEXT,
    error_ref TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_idempotency_unique ON rpc_idempotency_records(company_id, actor_type, actor_id, method, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON rpc_idempotency_records(expires_at);
