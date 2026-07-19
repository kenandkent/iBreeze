-- 0058: 证据链与工具调用表（P9-T1，对照 §10.1.3）
-- 四类证据对象：artifacts / reports / review_findings / fix_items
-- tool_calls / workspace_changes（append-only）

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    node_id TEXT REFERENCES task_nodes(node_id),
    run_id TEXT,
    employee_id TEXT,
    capability_snapshot_checksum TEXT,
    artifact_hash TEXT,
    artifact_ref TEXT,
    source_node_id TEXT,
    trace_id TEXT,
    status TEXT NOT NULL DEFAULT 'available'
        CHECK (status IN ('available', 'unavailable', 'deleted')),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    node_id TEXT REFERENCES task_nodes(node_id),
    run_id TEXT,
    employee_id TEXT,
    capability_snapshot_checksum TEXT,
    artifact_hash TEXT,
    source_node_id TEXT,
    trace_id TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'final')),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS review_findings (
    finding_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    node_id TEXT REFERENCES task_nodes(node_id),
    review_node_id TEXT,
    reviewer_employee_id TEXT,
    worker_employee_id TEXT,
    lens TEXT NOT NULL,
    finding_fingerprint TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'major', 'minor')),
    capability_snapshot_checksum TEXT,
    artifact_hash TEXT,
    source_node_id TEXT,
    run_id TEXT,
    trace_id TEXT,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'accepted', 'rejected', 'resolved')),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS fix_items (
    fix_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    node_id TEXT REFERENCES task_nodes(node_id),
    finding_id TEXT REFERENCES review_findings(finding_id),
    run_id TEXT,
    employee_id TEXT,
    capability_snapshot_checksum TEXT,
    artifact_hash TEXT,
    source_node_id TEXT,
    trace_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'fixed', 'failed', 'wont_fix', 'cancelled')),
    resolution_ref TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tool_calls (
    tool_call_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    node_id TEXT REFERENCES task_nodes(node_id),
    run_id TEXT,
    employee_id TEXT,
    tool_name TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    side_effect_state TEXT,
    result_ref TEXT,
    approval_id TEXT,
    authorization_audit_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'authorized', 'executed', 'blocked', 'failed')),
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workspace_changes (
    change_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    node_id TEXT REFERENCES task_nodes(node_id),
    tool_call_id TEXT REFERENCES tool_calls(tool_call_id),
    change_type TEXT NOT NULL,
    path_hash TEXT NOT NULL,
    before_hash TEXT,
    after_hash TEXT,
    artifact_ref TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_artifacts_task ON artifacts(task_id);
CREATE INDEX IF NOT EXISTS idx_reports_task ON reports(task_id);
CREATE INDEX IF NOT EXISTS idx_review_findings_task ON review_findings(task_id);
CREATE INDEX IF NOT EXISTS idx_fix_items_task ON fix_items(task_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_task ON tool_calls(task_id);
CREATE INDEX IF NOT EXISTS idx_workspace_changes_task ON workspace_changes(task_id);
