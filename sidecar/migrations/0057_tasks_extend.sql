-- 0057: 扩展 tasks 表（P9-T1c，对照 §10.2.3）
-- 原表 status CHECK 不含 cancelling，且需新增多个列；采用 SQLite 安全重建模式。

CREATE TABLE IF NOT EXISTS tasks_new (
    task_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    department_id TEXT,
    created_by_employee_id TEXT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'created'
        CHECK (status IN ('created', 'planning', 'running', 'paused', 'completed', 'failed', 'cancelled', 'cancelling')),
    assigned_backend_id TEXT,
    assigned_capability_id TEXT,
    assigned_capability_version INTEGER,
    assigned_capability_checksum TEXT,
    deadline_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    manager_employee_id TEXT,
    manager_scope TEXT,
    active_generation_id TEXT,
    budget_currency TEXT,
    budget_limit_micros INTEGER,
    token_limit INTEGER,
    goal TEXT,
    acceptance TEXT,
    inputs_json TEXT
);

INSERT INTO tasks_new (
    task_id, company_id, department_id, created_by_employee_id, title, description,
    priority, status, assigned_backend_id, assigned_capability_id,
    assigned_capability_version, assigned_capability_checksum, deadline_at,
    version, created_at, updated_at
)
SELECT
    task_id, company_id, department_id, created_by_employee_id, title, description,
    priority, status, assigned_backend_id, assigned_capability_id,
    assigned_capability_version, assigned_capability_checksum, deadline_at,
    version, created_at, updated_at
FROM tasks;

DROP TABLE tasks;
ALTER TABLE tasks_new RENAME TO tasks;

CREATE INDEX IF NOT EXISTS idx_tasks_company ON tasks(company_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_active_gen ON tasks(active_generation_id);

-- 触发：active_generation_id 变更时 version++
CREATE TRIGGER IF NOT EXISTS trg_tasks_version
AFTER UPDATE OF active_generation_id ON tasks
FOR EACH ROW
BEGIN
    UPDATE tasks SET version = version + 1 WHERE task_id = NEW.task_id;
END;

-- 触发：status 进入终态时记录 finished_at（用 updated_at 近似）
CREATE TRIGGER IF NOT EXISTS trg_tasks_finish
AFTER UPDATE OF status ON tasks
FOR EACH ROW
WHEN NEW.status IN ('completed', 'failed', 'cancelled')
BEGIN
    UPDATE tasks SET updated_at = datetime('now') WHERE task_id = NEW.task_id;
END;
