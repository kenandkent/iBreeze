CREATE TABLE IF NOT EXISTS employees (
    employee_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    department_id TEXT NOT NULL,
    template_id TEXT NOT NULL,
    capability_snapshot TEXT NOT NULL DEFAULT '{}',
    name TEXT NOT NULL,
    role_name TEXT NOT NULL DEFAULT '',
    employee_type TEXT NOT NULL DEFAULT 'employee',
    reports_to_employee_id TEXT,
    stability_level INTEGER NOT NULL DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'created',
    session_transfer_state TEXT NOT NULL DEFAULT 'none',
    primary_session_thread_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_employees_company ON employees(company_id);
CREATE INDEX IF NOT EXISTS idx_employees_department ON employees(department_id);
