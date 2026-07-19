-- 0052: 扩展 task_assignments（P9-T1a，对照 §10.2.1）

ALTER TABLE task_assignments ADD COLUMN generation_id TEXT;
ALTER TABLE task_assignments ADD COLUMN run_id TEXT;
ALTER TABLE task_assignments ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE task_assignments ADD COLUMN updated_at TEXT;
ALTER TABLE task_assignments ADD COLUMN attempt INTEGER NOT NULL DEFAULT 1;
ALTER TABLE task_assignments ADD COLUMN assignment_role TEXT NOT NULL DEFAULT 'worker'
    CHECK (assignment_role IN ('worker', 'reviewer', 'fixer', 'manager'));
ALTER TABLE task_assignments ADD COLUMN active_from TEXT;
ALTER TABLE task_assignments ADD COLUMN active_until TEXT;
ALTER TABLE task_assignments ADD COLUMN department_id_at_assignment TEXT;
ALTER TABLE task_assignments ADD COLUMN granted_by TEXT;
ALTER TABLE task_assignments ADD COLUMN reason TEXT;

-- (node_id, generation_id, assignment_role) 至多一条 active
CREATE UNIQUE INDEX IF NOT EXISTS idx_assignment_unique_active
    ON task_assignments(node_id, generation_id, assignment_role, status)
    WHERE status = 'active';
