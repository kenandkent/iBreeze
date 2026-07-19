-- 0028: Backend Registry 补充表（默认映射、健康检查结果、变更审计）
-- 幂等：所有对象 IF NOT EXISTS

CREATE TABLE IF NOT EXISTS company_backend_defaults (
    default_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    backend_id TEXT NOT NULL,
    is_archived INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (company_id, backend_id)
);

CREATE INDEX IF NOT EXISTS idx_backend_defaults_company ON company_backend_defaults(company_id);
CREATE INDEX IF NOT EXISTS idx_backend_defaults_backend ON company_backend_defaults(backend_id);

CREATE TABLE IF NOT EXISTS backend_health_checks (
    check_id TEXT PRIMARY KEY,
    backend_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    trigger TEXT NOT NULL DEFAULT 'manual',
    operator TEXT NOT NULL DEFAULT 'system',
    health_status TEXT NOT NULL,
    reason TEXT,
    workspace_writable INTEGER,
    worker_handshake_ok INTEGER,
    process_pool_ok INTEGER,
    git_cli_ok INTEGER,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_health_checks_backend ON backend_health_checks(backend_id);
CREATE INDEX IF NOT EXISTS idx_health_checks_company ON backend_health_checks(company_id);

CREATE TABLE IF NOT EXISTS backend_change_audit (
    audit_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    backend_id TEXT,
    action TEXT NOT NULL,
    actor_type TEXT NOT NULL DEFAULT 'LocalOwner',
    actor_id TEXT NOT NULL DEFAULT 'system',
    before_snapshot TEXT NOT NULL DEFAULT '{}',
    after_snapshot TEXT NOT NULL DEFAULT '{}',
    idempotency_key TEXT,
    request_hash TEXT,
    trace_id TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_backend_change_audit_company ON backend_change_audit(company_id);
CREATE INDEX IF NOT EXISTS idx_backend_change_audit_backend ON backend_change_audit(backend_id);
