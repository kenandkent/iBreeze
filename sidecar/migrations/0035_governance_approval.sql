-- 0035: 治理审批基础设施扩展
-- 扩展 approvals 表（统一审批字段 + 预算审批绑定字段），新增 approval_types 表

-- 扩展 approvals 表（design §12.2 统一审批字段）
CREATE TABLE IF NOT EXISTS approvals_new (
    approval_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    task_id TEXT,
    node_id TEXT,
    run_id TEXT,
    generation_id TEXT,
    employee_id TEXT NOT NULL,
    approval_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    target_hash TEXT,
    target_snapshot TEXT,
    risk_reason TEXT,
    requested_by TEXT NOT NULL,
    approved_by TEXT,
    resolution TEXT,
    reason TEXT,
    expiry TEXT,
    -- 预算审批不可变绑定字段
    currency TEXT,
    current_limit_micros INTEGER,
    requested_limit_micros INTEGER,
    requested_delta_micros INTEGER,
    usage_watermark_micros INTEGER DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO approvals_new
    (approval_id, company_id, task_id, employee_id, approval_type, status,
     requested_by, approved_by, reason, version, created_at, updated_at)
SELECT
    approval_id, company_id, task_id, employee_id, approval_type, status,
    requested_by, approved_by, reason, version, created_at, updated_at
FROM approvals;

DROP TABLE IF EXISTS approvals;
ALTER TABLE approvals_new RENAME TO approvals;

CREATE INDEX IF NOT EXISTS idx_approvals_company ON approvals(company_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_approvals_type ON approvals(approval_type);
CREATE INDEX IF NOT EXISTS idx_approvals_task ON approvals(task_id);

-- 审批类型定义表
CREATE TABLE IF NOT EXISTS approval_types (
    approval_type_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('tool_call', 'plan_approval', 'budget_approval', 'other')),
    description TEXT,
    requires_risk_summary INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_approval_types_company ON approval_types(company_id);
CREATE INDEX IF NOT EXISTS idx_approval_types_category ON approval_types(category);
