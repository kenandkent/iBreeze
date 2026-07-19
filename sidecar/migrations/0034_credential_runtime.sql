-- 0034: Credential Broker 元数据 + Runtime session/run 骨架，设计方案 §11.2/§12.3。
-- Sidecar 不持久化凭据明文：credential_refs 只记录 (company_id, provider_id, credential_slot)
-- 的存在性/后端引用，明文由 Rust Keychain 侧持有。

CREATE TABLE IF NOT EXISTS provider_credential_refs (
    company_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    credential_slot TEXT NOT NULL,
    backend TEXT NOT NULL DEFAULT 'keyring',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at TEXT,
    PRIMARY KEY (company_id, provider_id, credential_slot)
);

CREATE INDEX IF NOT EXISTS idx_cred_refs_company ON provider_credential_refs(company_id);

-- Runtime session 骨架：绑定 company/provider/model，承载原生 session id 载体
CREATE TABLE IF NOT EXISTS runtime_sessions (
    session_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    department_id TEXT NOT NULL DEFAULT '',
    employee_id TEXT NOT NULL DEFAULT '',
    provider_id TEXT NOT NULL,
    model TEXT NOT NULL,
    native_session_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_runtime_sessions_company ON runtime_sessions(company_id);

-- Runtime run 骨架：一次 send 的执行记录，承载 run_id/trace_id 与状态
CREATE TABLE IF NOT EXISTS runtime_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    conversation_id TEXT NOT NULL DEFAULT '',
    trace_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'cancelled', 'failed')),
    pricing_version_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_runtime_runs_session ON runtime_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_runtime_runs_company ON runtime_runs(company_id);
