-- 0051: 扩展 task_node（P9-T1，对照 §10.2）
-- node_type 扩展为：agent_step/merge/fix/review_task/manual_task/condition
-- 该迁移在全新 DB 上随其它迁移单次执行（Migrator 已去重）。

ALTER TABLE task_nodes ADD COLUMN generation_id TEXT;
ALTER TABLE task_nodes ADD COLUMN backend_id TEXT;
ALTER TABLE task_nodes ADD COLUMN depends_on TEXT NOT NULL DEFAULT '[]';
ALTER TABLE task_nodes ADD COLUMN workspace_strategy TEXT;
ALTER TABLE task_nodes ADD COLUMN outputs_schema TEXT;
ALTER TABLE task_nodes ADD COLUMN goal TEXT;

CREATE INDEX IF NOT EXISTS idx_task_nodes_generation ON task_nodes(generation_id);
