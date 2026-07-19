-- 0005: 人工干预项表

CREATE TABLE IF NOT EXISTS human_interventions (
    intervention_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    task_id TEXT,
    node_id TEXT,
    run_id TEXT,
    subtype TEXT NOT NULL CHECK (subtype IN ('approval', 'manual_task', 'dead_letter', 'employee_drain', 'company_dissolution', 'backend_recovery')),
    target_ref TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    allowed_actions TEXT NOT NULL DEFAULT '[]',
    resolution_ref TEXT,
    resolved_at TEXT,
    resolved_by TEXT,
    trace_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_human_interventions_open ON human_interventions(company_id, subtype, target_ref, status);
CREATE INDEX IF NOT EXISTS idx_human_interventions_company ON human_interventions(company_id, status);
