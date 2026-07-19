-- 0053: plan_generations（P9-T3，对照 §10.2.2）
-- 每次规划新增一代；初始 draft，replan 后旧代 superseded；
-- 仅通过校验/审批的新代能 CAS 成为 tasks.active_generation_id。

CREATE TABLE IF NOT EXISTS plan_generations (
    generation_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    company_id TEXT NOT NULL,
    generation_no INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'planning', 'validated', 'approved', 'active', 'superseded', 'rejected')),
    plan_hash TEXT NOT NULL,
    dag_json TEXT NOT NULL DEFAULT '[]',
    risk_summary TEXT,
    created_by_employee_id TEXT,
    parent_generation_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_plan_generations_task ON plan_generations(task_id);
CREATE INDEX IF NOT EXISTS idx_plan_generations_company ON plan_generations(company_id);
