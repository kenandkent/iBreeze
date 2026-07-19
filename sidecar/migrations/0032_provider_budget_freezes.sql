-- 0032: Provider 硬预算冻结，设计方案 §6.11。
-- (company_id, provider_id) 只允许一条 active；active→cleared 用 version CAS。

CREATE TABLE IF NOT EXISTS provider_budget_freezes (
    freeze_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    trigger_run_id TEXT NOT NULL,
    reason_code TEXT NOT NULL DEFAULT 'BOUNDED_COST_VIOLATION',
    evidence_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cleared')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    cleared_at TEXT,
    cleared_by TEXT,
    clear_reason TEXT,
    version INTEGER NOT NULL DEFAULT 1
);

-- 同一 (company,provider) 最多一条 active freeze
CREATE UNIQUE INDEX IF NOT EXISTS idx_freeze_active_unique
    ON provider_budget_freezes(company_id, provider_id)
    WHERE status = 'active';

-- 同一异常 run 重放不新建 freeze
CREATE UNIQUE INDEX IF NOT EXISTS idx_freeze_trigger_run
    ON provider_budget_freezes(company_id, provider_id, trigger_run_id);
