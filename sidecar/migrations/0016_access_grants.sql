CREATE TABLE IF NOT EXISTS access_grants (
    grant_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('department', 'task')),
    target_id TEXT NOT NULL,
    permission TEXT NOT NULL CHECK (permission IN ('department_read', 'task_read')),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired')),
    expires_at TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_access_grants_company ON access_grants(company_id);
CREATE INDEX IF NOT EXISTS idx_access_grants_employee ON access_grants(employee_id);
