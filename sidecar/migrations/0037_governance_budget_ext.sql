-- 0037: task_budgets 表（预算修订锁的目标 limit 事实源）+ budget_policies 索引

-- 任务级预算（预算修订锁批准的 limit 落此处；无记录时回退公司默认策略）
CREATE TABLE IF NOT EXISTS task_budgets (
    task_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    limit_micros INTEGER NOT NULL DEFAULT 0,
    token_limit INTEGER,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_task_budgets_company ON task_budgets(company_id);

-- budget_policies 索引（版本化状态查询加速）
CREATE INDEX IF NOT EXISTS idx_budget_policies_company_status ON budget_policies(company_id, status);
CREATE INDEX IF NOT EXISTS idx_budget_policies_currency ON budget_policies(currency);
