CREATE TABLE IF NOT EXISTS employee_drains (
    drain_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('transfer', 'suspend', 'archive')),
    target_department_id TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'failed', 'aborted_by_dissolution')),
    intervention_id TEXT,
    timeout_seconds INTEGER NOT NULL DEFAULT 600,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_emp_drains_company ON employee_drains(company_id);
