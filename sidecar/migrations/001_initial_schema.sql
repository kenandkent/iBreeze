-- iBreeze Sidecar 本地 Profile 数据库 - 完整 DDL 迁移
-- 对齐设计文档 H.1-H.14
-- 所有 id 由应用生成 UUID v4，所有时间以 UTC RFC 3339 文本保存

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;

-- ============================================================
-- H.1 迁移记录
-- ============================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    script_sha256 TEXT NOT NULL CHECK(length(script_sha256) = 64),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')),
    error_message TEXT
);

-- ============================================================
-- H.2 Profile、偏好、底座、目录缓存
-- ============================================================

CREATE TABLE IF NOT EXISTS local_profile (
    id TEXT PRIMARY KEY,
    backend_origin TEXT NOT NULL,
    app_user_id TEXT NOT NULL,
    masked_identifier TEXT NOT NULL,
    device_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_opened_at TEXT NOT NULL,
    UNIQUE(backend_origin, app_user_id)
);

CREATE TABLE IF NOT EXISTS local_preferences (
    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
    cli_global_concurrency INTEGER NOT NULL DEFAULT 4
        CHECK(cli_global_concurrency BETWEEN 1 AND 16),
    log_retention_days INTEGER NOT NULL DEFAULT 30
        CHECK(log_retention_days BETWEEN 1 AND 365),
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)
);

INSERT OR IGNORE INTO local_preferences(
    singleton_id, cli_global_concurrency, log_retention_days, updated_at, version
) VALUES (1, 4, 30, strftime('%Y-%m-%dT%H:%M:%fZ','now'), 1);

CREATE TABLE IF NOT EXISTS employee_base_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    normalized_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    current_version_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('active', 'retired')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)
);

CREATE TABLE IF NOT EXISTS employee_base_profile_versions (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES employee_base_profiles(id),
    version_number INTEGER NOT NULL CHECK(version_number > 0),
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    description TEXT NOT NULL,
    profile_type TEXT NOT NULL CHECK(profile_type IN ('agent_cli', 'api_model')),
    runtime_binding_json TEXT NOT NULL CHECK(json_valid(runtime_binding_json)),
    system_prompt TEXT NOT NULL,
    capability_tags_json TEXT NOT NULL CHECK(json_valid(capability_tags_json)),
    tool_policy_json TEXT NOT NULL CHECK(json_valid(tool_policy_json)),
    timeout_seconds INTEGER NOT NULL CHECK(timeout_seconds BETWEEN 1 AND 86400),
    max_retries INTEGER NOT NULL CHECK(max_retries BETWEEN 0 AND 5),
    workspace_policy TEXT NOT NULL CHECK(workspace_policy = 'workspace_rw_external_ro'),
    catalog_release_id TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    status TEXT NOT NULL CHECK(status IN ('draft', 'published', 'retired')),
    created_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(profile_id, version_number),
    CHECK((status = 'draft' AND published_at IS NULL)
       OR (status IN ('published', 'retired') AND published_at IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_employee_profile_single_draft
    ON employee_base_profile_versions(profile_id) WHERE status = 'draft';

CREATE TABLE IF NOT EXISTS profile_skill_bindings (
    profile_version_id TEXT NOT NULL REFERENCES employee_base_profile_versions(id),
    skill_id TEXT NOT NULL,
    skill_version_id TEXT NOT NULL,
    skill_version TEXT NOT NULL,
    package_sha256 TEXT NOT NULL CHECK(length(package_sha256) = 64),
    load_order INTEGER NOT NULL CHECK(load_order >= 0),
    PRIMARY KEY(profile_version_id, skill_version_id),
    UNIQUE(profile_version_id, load_order)
);

CREATE TABLE IF NOT EXISTS catalog_trust_keys (
    key_id TEXT PRIMARY KEY,
    public_key_base64 TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'retired')),
    introduced_by_keyset_sha256 TEXT NOT NULL CHECK(length(introduced_by_keyset_sha256) = 64),
    trusted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_verification_keys (
    key_id TEXT PRIMARY KEY,
    public_key_base64 TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'retired')),
    signed_keyset_sha256 TEXT NOT NULL CHECK(length(signed_keyset_sha256) = 64),
    not_before TEXT NOT NULL,
    retire_after TEXT,
    cached_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_cache_releases (
    release_id TEXT PRIMARY KEY,
    release_sequence INTEGER NOT NULL UNIQUE CHECK(release_sequence > 0),
    manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
    manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256) = 64),
    signature TEXT NOT NULL,
    signing_key_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('staging', 'active', 'retired', 'invalid')),
    downloaded_at TEXT NOT NULL,
    activated_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_catalog_release
    ON catalog_cache_releases(status) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS catalog_cache_resources (
    release_id TEXT NOT NULL REFERENCES catalog_cache_releases(release_id),
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    resource_version_id TEXT NOT NULL,
    content_json TEXT NOT NULL CHECK(json_valid(content_json)),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    PRIMARY KEY(release_id, resource_type, resource_id, resource_version_id)
);

CREATE TABLE IF NOT EXISTS installed_skill_versions (
    skill_version_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    version TEXT NOT NULL,
    package_path TEXT NOT NULL,
    package_sha256 TEXT NOT NULL CHECK(length(package_sha256) = 64),
    catalog_release_id TEXT NOT NULL REFERENCES catalog_cache_releases(release_id),
    status TEXT NOT NULL CHECK(status IN ('installed', 'disabled', 'corrupt')),
    installed_at TEXT NOT NULL,
    UNIQUE(skill_id, version)
);

CREATE TABLE IF NOT EXISTS emergency_disable_cache (
    sequence INTEGER PRIMARY KEY CHECK(sequence > 0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
    signature TEXT NOT NULL,
    signing_key_id TEXT NOT NULL,
    activated_at TEXT NOT NULL
);

-- ============================================================
-- H.3 公司、部门、职员
-- ============================================================

CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    normalized_name TEXT NOT NULL UNIQUE,
    current_revision_id TEXT NOT NULL,
    general_manager_office_id TEXT NOT NULL,
    general_manager_employee_id TEXT NOT NULL,
    company_conversation_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)
);

CREATE TABLE IF NOT EXISTS company_revisions (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    revision_number INTEGER NOT NULL CHECK(revision_number > 0),
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    introduction TEXT NOT NULL CHECK(length(introduction) BETWEEN 1 AND 20000),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    created_by_type TEXT NOT NULL CHECK(created_by_type IN ('user', 'system')),
    created_at TEXT NOT NULL,
    UNIQUE(id, company_id),
    UNIQUE(company_id, revision_number)
);

CREATE TABLE IF NOT EXISTS departments (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    department_type TEXT NOT NULL CHECK(department_type IN ('general_manager_office', 'standard')),
    normalized_name TEXT NOT NULL,
    current_revision_id TEXT NOT NULL,
    leader_employee_id TEXT NOT NULL,
    department_conversation_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    UNIQUE(id, company_id),
    UNIQUE(company_id, normalized_name)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_company_gm_office
    ON departments(company_id) WHERE department_type = 'general_manager_office';

CREATE TABLE IF NOT EXISTS department_revisions (
    id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL,
    company_id TEXT NOT NULL REFERENCES companies(id),
    revision_number INTEGER NOT NULL CHECK(revision_number > 0),
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    function_description TEXT NOT NULL CHECK(length(function_description) BETWEEN 1 AND 10000),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    created_at TEXT NOT NULL,
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id),
    UNIQUE(id, department_id, company_id),
    UNIQUE(department_id, revision_number)
);

CREATE TABLE IF NOT EXISTS department_responsibilities (
    id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    responsibility_key TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    accepted_task_types_json TEXT NOT NULL CHECK(json_valid(accepted_task_types_json)),
    required_capability_tags_json TEXT NOT NULL CHECK(json_valid(required_capability_tags_json)),
    deliverable_types_json TEXT NOT NULL CHECK(json_valid(deliverable_types_json)),
    quality_gates_json TEXT NOT NULL CHECK(json_valid(quality_gates_json)),
    upstream_keys_json TEXT NOT NULL CHECK(json_valid(upstream_keys_json)),
    downstream_keys_json TEXT NOT NULL CHECK(json_valid(downstream_keys_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id),
    UNIQUE(department_id, responsibility_key)
);

CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    department_id TEXT NOT NULL,
    display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 1 AND 100),
    normalized_display_name TEXT NOT NULL,
    base_profile_version_id TEXT NOT NULL REFERENCES employee_base_profile_versions(id),
    workflow_role TEXT NOT NULL
        CHECK(workflow_role IN ('general_manager', 'department_leader', 'member')),
    status TEXT NOT NULL CHECK(status IN ('active', 'draining', 'inactive', 'unavailable')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id),
    UNIQUE(id, company_id),
    UNIQUE(department_id, normalized_display_name)
);

-- ============================================================
-- H.4 会话、事件、幂等
-- ============================================================

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    conversation_type TEXT NOT NULL CHECK(conversation_type IN ('company', 'department')),
    department_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    UNIQUE(id, company_id),
    UNIQUE(company_id, conversation_type, department_id),
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id)
);

CREATE TABLE IF NOT EXISTS domain_events (
    row_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    company_id TEXT NOT NULL REFERENCES companies(id),
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    aggregate_version INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    trace_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE(event_id, company_id)
);

CREATE INDEX IF NOT EXISTS ix_domain_events_company_sequence
    ON domain_events(company_id, row_sequence);
CREATE INDEX IF NOT EXISTS ix_domain_events_aggregate
    ON domain_events(aggregate_type, aggregate_id, aggregate_version);

CREATE TABLE IF NOT EXISTS outbox_events (
    id TEXT PRIMARY KEY,
    domain_event_id TEXT NOT NULL REFERENCES domain_events(event_id),
    topic TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    status TEXT NOT NULL CHECK(status IN ('pending', 'processing', 'delivered', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL,
    last_error TEXT,
    created_at TEXT NOT NULL,
    delivered_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_outbox_ready ON outbox_events(status, next_attempt_at, created_at);

CREATE TABLE IF NOT EXISTS projection_offsets (
    projection_name TEXT PRIMARY KEY,
    last_row_sequence INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    task_id TEXT,
    source_event_id TEXT NOT NULL UNIQUE,
    sender_type TEXT NOT NULL CHECK(sender_type IN ('user', 'employee', 'system')),
    sender_employee_id TEXT,
    message_type TEXT NOT NULL,
    content TEXT NOT NULL,
    artifact_refs_json TEXT NOT NULL CHECK(json_valid(artifact_refs_json)),
    created_at TEXT NOT NULL,
    UNIQUE(id, company_id),
    FOREIGN KEY(conversation_id, company_id) REFERENCES conversations(id, company_id),
    FOREIGN KEY(source_event_id, company_id) REFERENCES domain_events(event_id, company_id),
    FOREIGN KEY(sender_employee_id, company_id) REFERENCES employees(id, company_id)
);

CREATE INDEX IF NOT EXISTS ix_messages_conversation_time
    ON conversation_messages(conversation_id, created_at, id);

CREATE TABLE IF NOT EXISTS rpc_idempotency (
    method TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
    status TEXT NOT NULL CHECK(status IN ('processing', 'completed', 'failed')),
    response_json TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY(method, idempotency_key)
);

-- ============================================================
-- H.6 任务与计划
-- ============================================================

CREATE TABLE IF NOT EXISTS company_tasks (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    supersedes_task_id TEXT,
    company_conversation_id TEXT NOT NULL,
    user_message_event_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'draft','analyzing','awaiting_user_confirmation','approved',
        'revision_requested','rejected','dispatching','checking_resources',
        'executing','reviewing','fixing','final_review','completed',
        'waiting_dependency','waiting_resource','waiting_permission','paused',
        'cancelling','cancelled','failed'
    )),
    resume_state TEXT CHECK(resume_state IS NULL OR resume_state IN (
        'analyzing','dispatching','checking_resources','executing','reviewing','fixing','final_review'
    )),
    active_plan_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(id, company_id),
    FOREIGN KEY(company_conversation_id, company_id)
        REFERENCES conversations(id, company_id),
    CHECK(supersedes_task_id IS NULL OR supersedes_task_id <> id),
    CHECK((status IN ('waiting_dependency','waiting_resource','waiting_permission','paused')
           AND resume_state IS NOT NULL)
       OR (status NOT IN ('waiting_dependency','waiting_resource','waiting_permission','paused')
           AND resume_state IS NULL))
);

CREATE TABLE IF NOT EXISTS company_plan_versions (
    id TEXT PRIMARY KEY,
    company_task_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    canonical_json TEXT NOT NULL CHECK(json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    generated_by_run_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'draft', 'awaiting_user_confirmation', 'approved', 'superseded', 'rejected'
    )),
    created_at TEXT NOT NULL,
    confirmed_at TEXT,
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    UNIQUE(id, company_task_id, company_id),
    UNIQUE(company_task_id, version_number)
);

CREATE TABLE IF NOT EXISTS task_context_snapshots (
    id TEXT PRIMARY KEY,
    company_task_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    company_revision_id TEXT NOT NULL,
    plan_version_id TEXT NOT NULL,
    department_revision_map_json TEXT NOT NULL CHECK(json_valid(department_revision_map_json)),
    catalog_release_id TEXT NOT NULL REFERENCES catalog_cache_releases(release_id),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    created_at TEXT NOT NULL,
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    UNIQUE(company_task_id)
);

CREATE TABLE IF NOT EXISTS department_tasks (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_id TEXT NOT NULL,
    stage_key TEXT NOT NULL,
    objective TEXT NOT NULL,
    deliverables_json TEXT NOT NULL CHECK(json_valid(deliverables_json)),
    acceptance_criteria_json TEXT NOT NULL CHECK(json_valid(acceptance_criteria_json)),
    status TEXT NOT NULL CHECK(status IN (
        'draft','checking_resources','ready','executing','reviewing','fixing',
        'completed','waiting_dependency','waiting_resource','waiting_permission',
        'cancelled','failed'
    )),
    resume_state TEXT CHECK(resume_state IS NULL OR resume_state IN (
        'checking_resources','ready','executing','reviewing','fixing'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id),
    UNIQUE(id, company_id),
    UNIQUE(company_task_id, stage_key),
    CHECK((status IN ('waiting_dependency','waiting_resource','waiting_permission')
           AND resume_state IS NOT NULL)
       OR (status NOT IN ('waiting_dependency','waiting_resource','waiting_permission')
           AND resume_state IS NULL))
);

CREATE TABLE IF NOT EXISTS department_task_dependencies (
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    PRIMARY KEY(department_task_id, depends_on_task_id),
    FOREIGN KEY(department_task_id, company_task_id, company_id)
        REFERENCES department_tasks(id, company_task_id, company_id),
    FOREIGN KEY(depends_on_task_id, company_task_id, company_id)
        REFERENCES department_tasks(id, company_task_id, company_id),
    CHECK(department_task_id <> depends_on_task_id)
);

CREATE TABLE IF NOT EXISTS employee_tasks (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    department_task_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    task_kind TEXT NOT NULL CHECK(task_kind IN ('standard', 'merge')),
    objective TEXT NOT NULL,
    acceptance_criteria_json TEXT NOT NULL CHECK(json_valid(acceptance_criteria_json)),
    status TEXT NOT NULL CHECK(status IN (
        'assigned','ready','running','submitted','peer_reviewing',
        'changes_requested','accepted','waiting_resource','cancelled','failed'
    )),
    resume_state TEXT CHECK(resume_state IS NULL OR resume_state IN (
        'assigned','ready','running','changes_requested'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(department_task_id, company_id)
        REFERENCES department_tasks(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id),
    UNIQUE(id, company_id),
    CHECK((status = 'waiting_resource' AND resume_state IS NOT NULL)
       OR (status <> 'waiting_resource' AND resume_state IS NULL))
);

CREATE TABLE IF NOT EXISTS employee_availability_snapshots (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_task_id TEXT,
    work_item_type TEXT NOT NULL CHECK(work_item_type IN (
        'interactive_turn','company_plan','task_execution','review',
        'verification','repair','merge','summary'
    )),
    work_item_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    base_profile_version_id TEXT NOT NULL REFERENCES employee_base_profile_versions(id),
    prospective_execution_sha256 TEXT NOT NULL CHECK(length(prospective_execution_sha256) = 64),
    catalog_release_id TEXT NOT NULL REFERENCES catalog_cache_releases(release_id),
    checks_json TEXT NOT NULL CHECK(json_valid(checks_json)),
    overall_status TEXT NOT NULL CHECK(overall_status IN ('available', 'unavailable')),
    checked_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(company_task_id, company_id)
        REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id),
    UNIQUE(id, company_id)
);

CREATE TABLE IF NOT EXISTS execution_snapshots (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_id TEXT NOT NULL,
    department_task_id TEXT,
    employee_task_id TEXT,
    employee_id TEXT NOT NULL,
    task_workspace_id TEXT,
    snapshot_purpose TEXT NOT NULL CHECK(snapshot_purpose IN (
        'interactive_turn','company_plan','task_execution','review',
        'verification','repair','merge','summary'
    )),
    work_item_id TEXT NOT NULL,
    company_revision_id TEXT NOT NULL,
    department_revision_id TEXT NOT NULL,
    base_profile_version_id TEXT NOT NULL REFERENCES employee_base_profile_versions(id),
    catalog_release_id TEXT NOT NULL REFERENCES catalog_cache_releases(release_id),
    runtime_binding_json TEXT NOT NULL CHECK(json_valid(runtime_binding_json)),
    skill_lock_json TEXT NOT NULL CHECK(json_valid(skill_lock_json)),
    tool_policy_json TEXT NOT NULL CHECK(json_valid(tool_policy_json)),
    workspace_policy_json TEXT NOT NULL CHECK(json_valid(workspace_policy_json)),
    verification_commands_json TEXT NOT NULL CHECK(json_valid(verification_commands_json)),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    created_at TEXT NOT NULL,
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id),
    UNIQUE(id, company_id),
    UNIQUE(snapshot_purpose, work_item_id, employee_id, content_sha256),
    CHECK((snapshot_purpose = 'task_execution' AND employee_task_id IS NOT NULL)
       OR snapshot_purpose <> 'task_execution')
);

-- ============================================================
-- H.10 Runtime 队列与 Lease
-- ============================================================

CREATE TABLE IF NOT EXISTS runtime_queue (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    work_item_type TEXT NOT NULL CHECK(work_item_type IN (
        'interactive_turn','company_plan','employee_task','review',
        'verification','repair','merge','summary','knowledge_index'
    )),
    work_item_id TEXT NOT NULL,
    job_id TEXT NOT NULL UNIQUE,
    run_id TEXT UNIQUE,
    priority INTEGER NOT NULL CHECK(priority IN (0, 10, 20, 30)),
    status TEXT NOT NULL CHECK(status IN ('ready', 'leased', 'completed', 'cancelled')),
    queued_at TEXT NOT NULL,
    leased_at TEXT,
    UNIQUE(id, job_id, company_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_runtime_queue_active_work_item
    ON runtime_queue(work_item_type, work_item_id)
    WHERE status IN ('ready', 'leased');

CREATE TABLE IF NOT EXISTS runtime_company_fairness (
    company_id TEXT PRIMARY KEY REFERENCES companies(id),
    last_dispatched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_leases (
    id TEXT PRIMARY KEY,
    queue_id TEXT NOT NULL UNIQUE REFERENCES runtime_queue(id),
    job_id TEXT NOT NULL UNIQUE,
    run_id TEXT UNIQUE,
    employee_id TEXT,
    company_id TEXT NOT NULL REFERENCES companies(id),
    conversation_id TEXT,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    CHECK((run_id IS NULL AND employee_id IS NULL AND conversation_id IS NULL)
       OR (run_id IS NOT NULL AND employee_id IS NOT NULL AND conversation_id IS NOT NULL))
);

-- ============================================================
-- H.11 AgentRun、事件、Checkpoint
-- ============================================================

CREATE TABLE IF NOT EXISTS agent_runs (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_task_id TEXT,
    employee_task_id TEXT,
    work_item_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    availability_snapshot_id TEXT NOT NULL,
    execution_snapshot_id TEXT NOT NULL,
    run_purpose TEXT NOT NULL CHECK(run_purpose IN (
        'interactive_turn','company_plan','task_execution','review','verification',
        'repair','merge','summary'
    )),
    adapter_type TEXT NOT NULL CHECK(adapter_type IN ('codex_cli','claude_code','opencode','api_model')),
    native_session_id TEXT,
    process_pid INTEGER,
    process_group_id INTEGER,
    process_started_at TEXT,
    run_spec_json TEXT NOT NULL CHECK(json_valid(run_spec_json)),
    run_spec_sha256 TEXT NOT NULL CHECK(length(run_spec_sha256) = 64),
    status TEXT NOT NULL CHECK(status IN (
        'queued','probing','starting','running','waiting_approval','verifying',
        'retrying','succeeded','waiting_resource','cancelled','timed_out','failed','lost'
    )),
    resume_state TEXT CHECK(resume_state IS NULL OR resume_state IN (
        'probing','starting','running','verifying','retrying'
    )),
    attempt INTEGER NOT NULL CHECK(attempt BETWEEN 1 AND 6),
    started_at TEXT,
    completed_at TEXT,
    exit_code INTEGER,
    failure_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(id, company_id),
    CHECK((status IN ('waiting_approval','waiting_resource') AND resume_state IS NOT NULL)
       OR (status NOT IN ('waiting_approval','waiting_resource') AND resume_state IS NULL)),
    CHECK((process_pid IS NULL AND process_group_id IS NULL AND process_started_at IS NULL)
       OR (process_pid > 0 AND process_group_id > 0 AND process_started_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS agent_run_events (
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    event_id TEXT NOT NULL UNIQUE,
    sequence INTEGER NOT NULL CHECK(sequence > 0),
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    native_event_json TEXT CHECK(native_event_json IS NULL OR json_valid(native_event_json)),
    trace_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    PRIMARY KEY(run_id, sequence)
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    sequence INTEGER NOT NULL,
    boundary_type TEXT NOT NULL,
    storage_type TEXT NOT NULL CHECK(storage_type IN ('sqlite_blob', 'file')),
    compressed_blob BLOB,
    file_path TEXT,
    uncompressed_size INTEGER NOT NULL,
    sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
    created_at TEXT NOT NULL,
    CHECK(
        (storage_type = 'sqlite_blob' AND compressed_blob IS NOT NULL AND file_path IS NULL)
        OR
        (storage_type = 'file' AND compressed_blob IS NULL AND file_path IS NOT NULL)
    ),
    UNIQUE(run_id, sequence)
);

CREATE TABLE IF NOT EXISTS tool_executions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    tool_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    input_json TEXT NOT NULL CHECK(json_valid(input_json)),
    input_sha256 TEXT NOT NULL CHECK(length(input_sha256) = 64),
    status TEXT NOT NULL CHECK(status IN ('requested','approved','started','completed','failed','uncertain')),
    result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json)),
    result_sha256 TEXT,
    approval_id TEXT,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(run_id, tool_call_id)
);

CREATE TABLE IF NOT EXISTS human_approvals (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    approval_type TEXT NOT NULL CHECK(approval_type IN ('external_write', 'uncertain_recovery')),
    target_json TEXT NOT NULL CHECK(json_valid(target_json)),
    target_sha256 TEXT NOT NULL CHECK(length(target_sha256) = 64),
    status TEXT NOT NULL CHECK(status IN ('pending','allowed','denied','expired','consumed')),
    requested_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    resolved_at TEXT,
    consumed_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    UNIQUE(id, run_id),
    CHECK(
        (status = 'pending' AND resolved_at IS NULL AND consumed_at IS NULL)
        OR
        (status IN ('allowed','denied','expired') AND resolved_at IS NOT NULL AND consumed_at IS NULL)
        OR
        (status = 'consumed' AND resolved_at IS NOT NULL AND consumed_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS verification_results (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    round_number INTEGER NOT NULL CHECK(round_number BETWEEN 1 AND 6),
    command_argv_json TEXT NOT NULL CHECK(json_valid(command_argv_json)),
    exit_code INTEGER NOT NULL,
    stdout_artifact_id TEXT,
    stderr_artifact_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('passed', 'failed', 'timed_out')),
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    UNIQUE(run_id, round_number, command_argv_json)
);

CREATE TABLE IF NOT EXISTS workspace_grants (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    normalized_path TEXT NOT NULL,
    security_bookmark BLOB NOT NULL,
    path_type TEXT NOT NULL CHECK(path_type IN ('code_repository', 'import_source')),
    status TEXT NOT NULL CHECK(status IN ('active', 'revoked', 'stale')),
    created_at TEXT NOT NULL,
    last_resolved_at TEXT,
    UNIQUE(id, company_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_workspace_active_path
    ON workspace_grants(normalized_path) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS task_workspaces (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    workspace_grant_id TEXT NOT NULL,
    repository_root TEXT NOT NULL,
    baseline_commit_sha TEXT NOT NULL CHECK(length(baseline_commit_sha) IN (40, 64)),
    user_branch_name TEXT NOT NULL,
    integration_branch_name TEXT NOT NULL,
    integration_worktree_path TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN (
        'preparing','active','ready_to_apply','applied','abandoned'
    )),
    applied_commit_sha TEXT,
    cleaned_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(workspace_grant_id, company_id) REFERENCES workspace_grants(id, company_id),
    UNIQUE(id, company_id),
    UNIQUE(company_task_id)
);

-- ============================================================
-- H.12 Artifact 与 Review
-- ============================================================

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_task_id TEXT,
    employee_task_id TEXT,
    artifact_type TEXT NOT NULL CHECK(artifact_type IN (
        'source_code_patch','document','test_case','test_result','review_report',
        'execution_report','department_report','final_report','log','diff',
        'checkpoint','transcript','diagnostic','imported_file','merge_report','git_bundle','manifest'
    )),
    logical_name TEXT NOT NULL,
    object_sha256 TEXT NOT NULL CHECK(length(object_sha256) = 64),
    object_size INTEGER NOT NULL CHECK(object_size >= 0),
    media_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)),
    supersedes_artifact_id TEXT,
    created_by_type TEXT NOT NULL CHECK(created_by_type IN ('user', 'agent', 'system')),
    created_by_run_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(id, company_id),
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    CHECK((created_by_type = 'agent' AND created_by_run_id IS NOT NULL)
       OR (created_by_type <> 'agent' AND created_by_run_id IS NULL))
);

CREATE INDEX IF NOT EXISTS ix_artifacts_task_type
    ON artifacts(company_task_id, artifact_type, created_at);

CREATE TABLE IF NOT EXISTS artifact_contributors (
    artifact_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    PRIMARY KEY(artifact_id, employee_id),
    FOREIGN KEY(artifact_id, company_id) REFERENCES artifacts(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id)
);

CREATE TABLE IF NOT EXISTS review_assignments (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    reviewer_employee_id TEXT NOT NULL,
    review_round INTEGER NOT NULL CHECK(review_round > 0),
    reviewed_sha256 TEXT NOT NULL CHECK(length(reviewed_sha256) = 64),
    status TEXT NOT NULL CHECK(status IN ('assigned','in_review','submitted','stale','cancelled')),
    assigned_at TEXT NOT NULL,
    submitted_at TEXT,
    FOREIGN KEY(artifact_id, company_id) REFERENCES artifacts(id, company_id),
    FOREIGN KEY(reviewer_employee_id, company_id) REFERENCES employees(id, company_id),
    UNIQUE(id, company_id),
    UNIQUE(artifact_id, reviewer_employee_id, review_round)
);

CREATE TABLE IF NOT EXISTS review_reports (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    assignment_id TEXT NOT NULL UNIQUE,
    reviewer_run_id TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK(verdict IN ('pass', 'needs_changes', 'failed')),
    report_artifact_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(id, company_id),
    FOREIGN KEY(assignment_id, company_id) REFERENCES review_assignments(id, company_id),
    FOREIGN KEY(reviewer_run_id, company_id) REFERENCES agent_runs(id, company_id),
    FOREIGN KEY(report_artifact_id, company_id) REFERENCES artifacts(id, company_id)
);

CREATE TABLE IF NOT EXISTS review_issues (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    review_report_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('blocker', 'high', 'medium', 'low')),
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    expected TEXT NOT NULL,
    actual TEXT NOT NULL,
    suggested_fix TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL CHECK(json_valid(evidence_refs_json)),
    status TEXT NOT NULL CHECK(status IN ('open','fixing','resolved','verified','closed','rejected')),
    assignee_employee_id TEXT,
    verifier_employee_id TEXT,
    rejection_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(id, company_id),
    CHECK(status <> 'rejected' OR (severity IN ('medium','low') AND rejection_reason IS NOT NULL))
);

-- ============================================================
-- H.13 知识
-- ============================================================

CREATE TABLE IF NOT EXISTS knowledge_items (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    source_artifact_id TEXT,
    source_message_event_id TEXT,
    owner_employee_id TEXT,
    department_id TEXT,
    task_id TEXT,
    visibility TEXT NOT NULL CHECK(visibility IN ('company', 'department', 'task', 'private')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    embedding_generation_id TEXT,
    created_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    UNIQUE(id, company_id),
    CHECK((source_artifact_id IS NULL) <> (source_message_event_id IS NULL)),
    CHECK(
        (visibility = 'company' AND department_id IS NULL AND task_id IS NULL AND owner_employee_id IS NULL)
        OR (visibility = 'department' AND department_id IS NOT NULL AND task_id IS NULL AND owner_employee_id IS NULL)
        OR (visibility = 'task' AND task_id IS NOT NULL AND owner_employee_id IS NULL)
        OR (visibility = 'private' AND owner_employee_id IS NOT NULL)
    )
);

CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
    knowledge_id UNINDEXED,
    company_id UNINDEXED,
    generation_id UNINDEXED,
    title,
    content,
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS embedding_generations (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    model_key TEXT NOT NULL,
    vector_dimension INTEGER NOT NULL CHECK(vector_dimension = 384),
    source_event_sequence INTEGER NOT NULL CHECK(source_event_sequence >= 0),
    status TEXT NOT NULL CHECK(status IN ('building', 'active', 'retired', 'failed')),
    created_at TEXT NOT NULL,
    activated_at TEXT,
    UNIQUE(id, company_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_embedding_generation
    ON embedding_generations(company_id) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS ix_knowledge_items_unindexed
    ON knowledge_items(company_id, id) WHERE embedding_generation_id IS NULL;

CREATE TABLE IF NOT EXISTS knowledge_access_logs (
    row_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    company_id TEXT NOT NULL REFERENCES companies(id),
    run_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    query_sha256 TEXT NOT NULL CHECK(length(query_sha256) = 64),
    visibility_scope_json TEXT NOT NULL CHECK(json_valid(visibility_scope_json)),
    candidate_ids_json TEXT NOT NULL CHECK(json_valid(candidate_ids_json)),
    selected_ids_json TEXT NOT NULL CHECK(json_valid(selected_ids_json)),
    context_pack_sha256 TEXT NOT NULL CHECK(length(context_pack_sha256) = 64),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_knowledge_access_run
    ON knowledge_access_logs(run_id, row_sequence);

-- ============================================================
-- H.13.1 备份记录
-- ============================================================

CREATE TABLE IF NOT EXISTS backup_records (
    id TEXT PRIMARY KEY,
    backup_type TEXT NOT NULL CHECK(backup_type IN ('daily', 'weekly', 'manual', 'pre_upgrade')),
    archive_path TEXT NOT NULL UNIQUE,
    archive_size INTEGER NOT NULL CHECK(archive_size > 0),
    archive_sha256 TEXT NOT NULL CHECK(length(archive_sha256) = 64),
    manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
    status TEXT NOT NULL CHECK(status IN ('creating', 'completed', 'failed', 'deleted')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    error_code TEXT
);

-- ============================================================
-- H.14 本地审计
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_logs (
    row_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    company_id TEXT,
    actor_type TEXT NOT NULL CHECK(actor_type IN ('user', 'employee', 'system')),
    actor_id TEXT,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    outcome TEXT NOT NULL CHECK(outcome IN ('success', 'denied', 'failed')),
    detail_json TEXT NOT NULL CHECK(json_valid(detail_json)),
    trace_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_audit_company_sequence ON audit_logs(company_id, row_sequence);

-- ============================================================
-- 不可变性触发器
-- ============================================================

CREATE TRIGGER IF NOT EXISTS company_revisions_no_update
BEFORE UPDATE ON company_revisions
BEGIN SELECT RAISE(ABORT, 'company revision is immutable'); END;

CREATE TRIGGER IF NOT EXISTS company_revisions_no_delete
BEFORE DELETE ON company_revisions
BEGIN SELECT RAISE(ABORT, 'company revision is immutable'); END;

CREATE TRIGGER IF NOT EXISTS department_revisions_no_update
BEFORE UPDATE ON department_revisions
BEGIN SELECT RAISE(ABORT, 'department revision is immutable'); END;

CREATE TRIGGER IF NOT EXISTS department_revisions_no_delete
BEFORE DELETE ON department_revisions
BEGIN SELECT RAISE(ABORT, 'department revision is immutable'); END;

CREATE TRIGGER IF NOT EXISTS domain_events_no_update
BEFORE UPDATE ON domain_events
BEGIN SELECT RAISE(ABORT, 'domain event is immutable'); END;

CREATE TRIGGER IF NOT EXISTS domain_events_no_delete
BEFORE DELETE ON domain_events
BEGIN SELECT RAISE(ABORT, 'domain event is immutable'); END;

CREATE TRIGGER IF NOT EXISTS task_context_snapshots_no_update
BEFORE UPDATE ON task_context_snapshots
BEGIN SELECT RAISE(ABORT, 'task context snapshot is immutable'); END;

CREATE TRIGGER IF NOT EXISTS task_context_snapshots_no_delete
BEFORE DELETE ON task_context_snapshots
BEGIN SELECT RAISE(ABORT, 'task context snapshot is immutable'); END;

CREATE TRIGGER IF NOT EXISTS availability_snapshots_no_update
BEFORE UPDATE ON employee_availability_snapshots
BEGIN SELECT RAISE(ABORT, 'availability snapshot is immutable'); END;

CREATE TRIGGER IF NOT EXISTS availability_snapshots_no_delete
BEFORE DELETE ON employee_availability_snapshots
BEGIN SELECT RAISE(ABORT, 'availability snapshot is immutable'); END;

CREATE TRIGGER IF NOT EXISTS execution_snapshots_no_update
BEFORE UPDATE ON execution_snapshots
BEGIN SELECT RAISE(ABORT, 'execution snapshot is immutable'); END;

CREATE TRIGGER IF NOT EXISTS execution_snapshots_no_delete
BEFORE DELETE ON execution_snapshots
BEGIN SELECT RAISE(ABORT, 'execution snapshot is immutable'); END;

CREATE TRIGGER IF NOT EXISTS agent_run_events_no_update
BEFORE UPDATE ON agent_run_events
BEGIN SELECT RAISE(ABORT, 'agent run event is immutable'); END;

CREATE TRIGGER IF NOT EXISTS agent_run_events_no_delete
BEFORE DELETE ON agent_run_events
WHEN OLD.event_type <> 'model.output.delta'
BEGIN SELECT RAISE(ABORT, 'non-delta agent run event is immutable'); END;

CREATE TRIGGER IF NOT EXISTS artifacts_no_update
BEFORE UPDATE ON artifacts
BEGIN SELECT RAISE(ABORT, 'artifact is immutable'); END;

CREATE TRIGGER IF NOT EXISTS artifacts_no_delete
BEFORE DELETE ON artifacts
BEGIN SELECT RAISE(ABORT, 'artifact is immutable'); END;

CREATE TRIGGER IF NOT EXISTS knowledge_access_logs_no_update
BEFORE UPDATE ON knowledge_access_logs
BEGIN SELECT RAISE(ABORT, 'knowledge access log is immutable'); END;

CREATE TRIGGER IF NOT EXISTS knowledge_access_logs_no_delete
BEFORE DELETE ON knowledge_access_logs
BEGIN SELECT RAISE(ABORT, 'knowledge access log is immutable'); END;

CREATE TRIGGER IF NOT EXISTS audit_logs_no_update
BEFORE UPDATE ON audit_logs
BEGIN SELECT RAISE(ABORT, 'audit log is immutable'); END;

CREATE TRIGGER IF NOT EXISTS audit_logs_no_delete
BEFORE DELETE ON audit_logs
BEGIN SELECT RAISE(ABORT, 'audit log is immutable'); END;

CREATE TRIGGER IF NOT EXISTS employee_profile_version_published_guard
BEFORE UPDATE ON employee_base_profile_versions
WHEN OLD.status IN ('published','retired')
BEGIN
    SELECT CASE WHEN OLD.status='published' AND NEW.status='retired'
        AND NEW.id IS OLD.id
        AND NEW.profile_id IS OLD.profile_id
        AND NEW.version_number IS OLD.version_number
        AND NEW.name IS OLD.name
        AND NEW.description IS OLD.description
        AND NEW.profile_type IS OLD.profile_type
        AND NEW.runtime_binding_json IS OLD.runtime_binding_json
        AND NEW.system_prompt IS OLD.system_prompt
        AND NEW.capability_tags_json IS OLD.capability_tags_json
        AND NEW.tool_policy_json IS OLD.tool_policy_json
        AND NEW.timeout_seconds IS OLD.timeout_seconds
        AND NEW.max_retries IS OLD.max_retries
        AND NEW.workspace_policy IS OLD.workspace_policy
        AND NEW.catalog_release_id IS OLD.catalog_release_id
        AND NEW.content_sha256 IS OLD.content_sha256
        AND NEW.created_at IS OLD.created_at
        AND NEW.published_at IS OLD.published_at
      THEN NULL
      ELSE RAISE(ABORT, 'published profile version content is immutable')
    END;
END;

CREATE TRIGGER IF NOT EXISTS employee_profile_version_no_delete
BEFORE DELETE ON employee_base_profile_versions
WHEN OLD.status IN ('published','retired')
BEGIN SELECT RAISE(ABORT, 'published profile version is immutable'); END;

CREATE TRIGGER IF NOT EXISTS profile_skill_bindings_insert_guard
BEFORE INSERT ON profile_skill_bindings
WHEN (SELECT status FROM employee_base_profile_versions WHERE id=NEW.profile_version_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'only draft profile version skills are mutable'); END;

CREATE TRIGGER IF NOT EXISTS profile_skill_bindings_update_guard
BEFORE UPDATE ON profile_skill_bindings
WHEN (SELECT status FROM employee_base_profile_versions WHERE id=OLD.profile_version_id) <> 'draft'
   OR (SELECT status FROM employee_base_profile_versions WHERE id=NEW.profile_version_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'only draft profile version skills are mutable'); END;

CREATE TRIGGER IF NOT EXISTS profile_skill_bindings_delete_guard
BEFORE DELETE ON profile_skill_bindings
WHEN (SELECT status FROM employee_base_profile_versions WHERE id=OLD.profile_version_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'only draft profile version skills are mutable'); END;
