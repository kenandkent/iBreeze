-- 0036: 审批请求、预算修订锁、治理审计表

-- 审批请求：创建审批请求，绑定 target_ref/risk_summary
CREATE TABLE IF NOT EXISTS approval_requests (
    request_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    approval_type TEXT NOT NULL,
    task_id TEXT,
    run_id TEXT,
    node_id TEXT,
    generation_id TEXT,
    target_ref TEXT NOT NULL,
    target_skill TEXT,
    risk_summary TEXT,
    target_hash TEXT,
    target_snapshot TEXT,
    requested_by TEXT NOT NULL,
    linked_approval_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    expiry TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_company ON approval_requests(company_id);
CREATE INDEX IF NOT EXISTS idx_approval_requests_status ON approval_requests(status);
CREATE INDEX IF NOT EXISTS idx_approval_requests_task ON approval_requests(task_id);

-- 预算修订锁：pending 期间阻塞同任务同币种新 reservation
CREATE TABLE IF NOT EXISTS budget_revision_locks (
    lock_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    run_id TEXT,
    current_limit_micros INTEGER NOT NULL,
    requested_limit_micros INTEGER NOT NULL,
    requested_delta_micros INTEGER NOT NULL,
    usage_watermark_micros INTEGER NOT NULL DEFAULT 0,
    request_hash TEXT NOT NULL,
    linked_approval_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'released')),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_budget_rev_lock_task_currency ON budget_revision_locks(task_id, currency);
CREATE INDEX IF NOT EXISTS idx_budget_rev_lock_company ON budget_revision_locks(company_id);

-- 治理审计表（append-only）
CREATE TABLE IF NOT EXISTS governance_audit (
    audit_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('budget', 'approval', 'approval_type', 'budget_revision')),
    aggregate_id TEXT NOT NULL,
    action TEXT NOT NULL,
    before_snapshot TEXT,
    after_snapshot TEXT,
    operator TEXT NOT NULL,
    reason TEXT,
    trace_id TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_governance_audit_company ON governance_audit(company_id);
CREATE INDEX IF NOT EXISTS idx_governance_audit_category ON governance_audit(category);
CREATE INDEX IF NOT EXISTS idx_governance_audit_aggregate ON governance_audit(category, aggregate_id);

-- 用量预留（预留—结算模式；P9-T1b 若已建则复用，此处幂等）
CREATE TABLE IF NOT EXISTS usage_reservations (
    reservation_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    run_id TEXT,
    node_id TEXT,
    currency TEXT NOT NULL,
    reserved_micros INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'held' CHECK (status IN ('held', 'settled', 'released', 'violated')),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_usage_reservations_task ON usage_reservations(task_id);
CREATE INDEX IF NOT EXISTS idx_usage_reservations_status ON usage_reservations(status);
