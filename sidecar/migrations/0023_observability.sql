CREATE TABLE IF NOT EXISTS task_read_model (
    task_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 5,
    assigned_employee_id TEXT,
    assigned_backend_id TEXT,
    progress_pct REAL DEFAULT 0.0,
    last_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_task_read_company ON task_read_model(company_id);
CREATE INDEX IF NOT EXISTS idx_task_read_status ON task_read_model(status);

CREATE TABLE IF NOT EXISTS dashboard_metrics (
    metric_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    metric_type TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL DEFAULT 0.0,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_dashboard_company ON dashboard_metrics(company_id, metric_type);
