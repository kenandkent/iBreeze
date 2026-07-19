-- 0055: dead_letters（P9-T11/P9-T7，对照 §10.4）
-- Fix 轮次超上限或人工干预转人工时落 dead_letter

CREATE TABLE IF NOT EXISTS dead_letters (
    dead_letter_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    node_id TEXT REFERENCES task_nodes(node_id),
    generation_id TEXT,
    reason TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'fix_exhausted'
        CHECK (kind IN ('fix_exhausted', 'escalated_to_human', 'reassign_failed', 'dependency_blocked')),
    payload_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'resolved', 'aborted')),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_dead_letters_task ON dead_letters(task_id);
CREATE INDEX IF NOT EXISTS idx_dead_letters_company ON dead_letters(company_id);
