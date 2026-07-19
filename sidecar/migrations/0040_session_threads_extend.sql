-- 0040: session_threads 扩展（Phase 7 安全上下文分片 + 状态机 + 单 active turn CAS）
--
-- 0019 已建 session_threads，但 status CHECK 仅允许 (active,dormant,archived)，
-- 不足以支撑 P7-T5 状态机。此处按 SQLite 标准 12 步重建表，扩展状态枚举并补字段。
-- 幂等：整段基于 schema_migrations 仅执行一次（Migrator 保证）；重建逻辑对空表安全。

PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS session_threads_new (
    thread_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    security_context_key TEXT NOT NULL,
    task_id TEXT,
    capability_snapshot_checksum TEXT NOT NULL DEFAULT '',
    provider_id TEXT NOT NULL DEFAULT '',
    model_id TEXT NOT NULL DEFAULT '',
    workspace_policy_hash TEXT NOT NULL DEFAULT '',
    security_policy_hash TEXT NOT NULL DEFAULT '',
    effective_grants_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','running','waiting_backend','waiting_approval','dormant','archived','failed','recovering')),
    primary_thread_id TEXT,
    active_turn_id TEXT,
    transfer_state TEXT NOT NULL DEFAULT 'none',
    resume_mode TEXT NOT NULL DEFAULT '',
    session_json_path TEXT,
    transcript_path TEXT,
    summary_path TEXT,
    backend_id TEXT,
    backend_lease_id TEXT,
    process_token TEXT,
    last_checkpoint_offset INTEGER DEFAULT 0,
    last_event_seq INTEGER NOT NULL DEFAULT 0,
    checkpoint_offset INTEGER NOT NULL DEFAULT 0,
    watermark TEXT NOT NULL DEFAULT '',
    watermark_checksum TEXT NOT NULL DEFAULT '',
    archived_at TEXT,
    transfer_staging_path TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO session_threads_new
    (thread_id, company_id, employee_id, security_context_key, status,
     primary_thread_id, last_checkpoint_offset, transcript_path, version,
     created_at, updated_at)
SELECT thread_id, company_id, employee_id, security_context_key, status,
       primary_thread_id, COALESCE(last_checkpoint_offset, 0), transcript_path, version,
       created_at, updated_at
FROM session_threads;

DROP TABLE session_threads;
ALTER TABLE session_threads_new RENAME TO session_threads;

CREATE INDEX IF NOT EXISTS idx_session_threads_employee_ctx
    ON session_threads(employee_id, security_context_key);
CREATE INDEX IF NOT EXISTS idx_session_threads_company_employee
    ON session_threads(company_id, employee_id);
CREATE INDEX IF NOT EXISTS idx_session_threads_employee_task
    ON session_threads(employee_id, task_id);
CREATE INDEX IF NOT EXISTS idx_session_threads_transfer
    ON session_threads(company_id, transfer_state);

PRAGMA foreign_keys = ON;
