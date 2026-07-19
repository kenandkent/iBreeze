-- 0054: checkpoints（P9-T8，对照 §10.5）
-- 落点：PlanValidator 通过后 / 每个 Worker 完成 / Review 完成 / 每轮 Fix 完成
-- checksum 覆盖除自身外的全部不可变内容

CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    task_cursor INTEGER NOT NULL DEFAULT 0,
    plan_hash TEXT,
    context_hash TEXT,
    generation_id TEXT,
    run_id TEXT,
    event_offset INTEGER NOT NULL DEFAULT 0,
    executor_state TEXT,
    checksum TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_task ON checkpoints(task_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_company ON checkpoints(company_id);
CREATE INDEX IF NOT EXISTS idx_checkpoints_generation ON checkpoints(generation_id);
