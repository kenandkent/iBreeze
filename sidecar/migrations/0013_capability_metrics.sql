-- 0013: 能力度量（只读聚合）

CREATE TABLE IF NOT EXISTS capability_metrics (
    capability_id TEXT NOT NULL,
    capability_version INTEGER NOT NULL,
    success_rate REAL DEFAULT 0.0,
    avg_cost REAL DEFAULT 0.0,
    review_pass_rate REAL DEFAULT 0.0,
    avg_downgrade_count REAL DEFAULT 0.0,
    over_budget_rate REAL DEFAULT 0.0,
    avg_duration REAL DEFAULT 0.0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (capability_id, capability_version)
);
