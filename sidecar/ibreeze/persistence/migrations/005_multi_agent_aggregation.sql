-- Multi-agent collaboration aggregation and reviewer verdict fusion.
--
-- Six new tables, appended only (no ALTER of existing tables):
--   1) employee_task_dependencies     - sequential_refinement chain edges
--   2) employee_task_dispatch_specs   - frozen runtime binding for lazy dispatch
--   3) deliverable_review_specs       - per-deliverable review strategy / rounds
--   4) review_verdicts                - fused verdict per current artifact (upsert)
--   5) reviewer_stats                 - reviewer historical accuracy ledger
--   6) review_report_scores           - idempotent per-report scoring ledger
--
-- review_reports stays immutable (001 triggers forbid UPDATE/DELETE); fused
-- verdicts and per-report scores live in the tables below instead.

-- 1) Sub-task dependency edges (sequential_refinement / chained strategies).
CREATE TABLE IF NOT EXISTS employee_task_dependencies (
    employee_task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (employee_task_id, depends_on_task_id),
    FOREIGN KEY (employee_task_id, company_id)
        REFERENCES employee_tasks(id, company_id),
    FOREIGN KEY (depends_on_task_id, company_id)
        REFERENCES employee_tasks(id, company_id)
);
CREATE INDEX IF NOT EXISTS idx_employee_task_dependencies_dep
    ON employee_task_dependencies(company_id, depends_on_task_id, employee_task_id);

-- 2) Frozen dispatch spec per employee task: captured at confirm time so lazy
-- dispatch reuses the exact profile/binding/revision resolved during the
-- confirm transaction (deterministic, no second parse).
CREATE TABLE IF NOT EXISTS employee_task_dispatch_specs (
    employee_task_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_task_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    profile_version_id TEXT NOT NULL,
    catalog_release_id TEXT NOT NULL,
    runtime_binding_json TEXT NOT NULL CHECK(json_valid(runtime_binding_json)),
    adapter_type TEXT NOT NULL,
    model_id TEXT NOT NULL,
    task_workspace_id TEXT NOT NULL,
    company_revision_id TEXT NOT NULL,
    department_revision_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    workspace_repository_root TEXT NOT NULL,
    workspace_grant_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (employee_task_id, company_id)
        REFERENCES employee_tasks(id, company_id)
);

-- 3) Per-deliverable review spec: drives lazy round-1 assignment creation,
-- auto-rerun and fusion confidence threshold.  plan_validator already bounds
-- review_rounds to 1..10.
CREATE TABLE IF NOT EXISTS deliverable_review_specs (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_task_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    review_strategy TEXT NOT NULL CHECK(review_strategy IN (
        'independent_drafts', 'section_partition',
        'primary_with_peer_review', 'sequential_refinement'
    )),
    contributor_employee_ids_json TEXT NOT NULL CHECK(json_valid(contributor_employee_ids_json)),
    reviewer_employee_ids_json TEXT NOT NULL CHECK(json_valid(reviewer_employee_ids_json)),
    review_rounds INTEGER NOT NULL DEFAULT 2 CHECK(review_rounds BETWEEN 1 AND 10),
    confidence_threshold REAL NOT NULL DEFAULT 0.7,
    created_at TEXT NOT NULL,
    UNIQUE(company_id, company_task_id, artifact_type),
    FOREIGN KEY (department_task_id, company_id)
        REFERENCES department_tasks(id, company_id)
);

-- 4) Fused verdict per current artifact (upsert on each review.submit).
CREATE TABLE IF NOT EXISTS review_verdicts (
    company_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK(verdict IN ('pass', 'needs_changes', 'failed')),
    confidence REAL NOT NULL DEFAULT 0.0,
    hard_veto_triggered INTEGER NOT NULL DEFAULT 0,
    rerun_exhausted INTEGER NOT NULL DEFAULT 0,
    score_json TEXT NOT NULL CHECK(json_valid(score_json)),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (company_id, artifact_id),
    FOREIGN KEY (artifact_id, company_id) REFERENCES artifacts(id, company_id)
);
CREATE INDEX IF NOT EXISTS idx_review_verdicts_sha
    ON review_verdicts(artifact_sha256);

-- 5) Reviewer historical statistics (data flywheel, updated inside submit txn).
CREATE TABLE IF NOT EXISTS reviewer_stats (
    company_id TEXT NOT NULL,
    reviewer_employee_id TEXT NOT NULL,
    reviews_completed INTEGER NOT NULL DEFAULT 0,
    reviews_with_issues INTEGER NOT NULL DEFAULT 0,
    accuracy REAL NOT NULL DEFAULT 0.0,
    sample_count INTEGER NOT NULL DEFAULT 0,
    last_review_at TEXT NOT NULL,
    PRIMARY KEY (company_id, reviewer_employee_id),
    FOREIGN KEY (reviewer_employee_id, company_id)
        REFERENCES employees(id, company_id)
);

-- 6) Idempotent per-report scoring ledger (review_reports is immutable).
--   credited flag guarantees each report is accounted exactly once.
CREATE TABLE IF NOT EXISTS review_report_scores (
    report_id TEXT PRIMARY KEY,
    assignment_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    reviewer_employee_id TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK(verdict IN ('pass', 'needs_changes', 'failed')),
    severity_max TEXT NOT NULL,
    issue_count INTEGER NOT NULL DEFAULT 0,
    weight REAL NOT NULL DEFAULT 0.5,
    accuracy_contribution REAL,
    credited INTEGER NOT NULL DEFAULT 0,
    scored_at TEXT NOT NULL,
    FOREIGN KEY (report_id, company_id) REFERENCES review_reports(id, company_id),
    FOREIGN KEY (assignment_id, company_id) REFERENCES review_assignments(id, company_id),
    FOREIGN KEY (artifact_id, company_id) REFERENCES artifacts(id, company_id),
    FOREIGN KEY (reviewer_employee_id, company_id) REFERENCES employees(id, company_id)
);
CREATE INDEX IF NOT EXISTS idx_report_scores_artifact
    ON review_report_scores(company_id, artifact_id);
CREATE INDEX IF NOT EXISTS idx_report_scores_reviewer
    ON review_report_scores(company_id, reviewer_employee_id);
