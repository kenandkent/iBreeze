CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    department_id TEXT,
    created_by_employee_id TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'created' CHECK (status IN ('created', 'planning', 'running', 'paused', 'completed', 'failed', 'cancelled')),
    assigned_backend_id TEXT,
    assigned_capability_id TEXT,
    assigned_capability_version INTEGER,
    assigned_capability_checksum TEXT,
    deadline_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_company ON tasks(company_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

CREATE TABLE IF NOT EXISTS task_nodes (
    node_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    company_id TEXT NOT NULL,
    node_type TEXT NOT NULL DEFAULT 'agent_step',
    status TEXT NOT NULL DEFAULT 'pending',
    assignee_employee_id TEXT,
    max_concurrency INTEGER NOT NULL DEFAULT 1,
    timeout_seconds INTEGER,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_task_nodes_task ON task_nodes(task_id);

CREATE TABLE IF NOT EXISTS task_runs (
    run_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL REFERENCES task_nodes(node_id),
    task_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    backend_id TEXT,
    lease_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    capability_checksum TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_task_runs_node ON task_runs(node_id);
CREATE INDEX IF NOT EXISTS idx_task_runs_task ON task_runs(task_id);

CREATE TABLE IF NOT EXISTS task_assignments (
    assignment_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    node_id TEXT REFERENCES task_nodes(node_id),
    employee_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'assignee',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_task_assignments_employee ON task_assignments(employee_id);
