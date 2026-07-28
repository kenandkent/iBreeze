-- 001_initial.sql: iBreeze Profile Schema Epoch 1
-- schema_migrations ledger is bootstrapped by migrator.py
-- All evidence tables are immutable (UPDATE/DELETE blocked by triggers)

-- local_profile (H.2)
CREATE TABLE local_profile (
    id TEXT PRIMARY KEY,
    schema_epoch INTEGER NOT NULL DEFAULT 1 CHECK(schema_epoch = 1),
    created_by_app_version TEXT NOT NULL,
    backend_origin TEXT NOT NULL,
    app_user_id TEXT NOT NULL,
    masked_identifier TEXT NOT NULL,
    device_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_opened_at TEXT NOT NULL,
    UNIQUE(backend_origin, app_user_id)
);

-- settings (key-value)
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL CHECK(json_valid(value_json)),
    updated_at TEXT NOT NULL
);

-- local_preferences (H.2)
CREATE TABLE local_preferences (
    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
    cli_global_concurrency INTEGER NOT NULL DEFAULT 4
        CHECK(cli_global_concurrency BETWEEN 1 AND 16),
    log_retention_days INTEGER NOT NULL DEFAULT 30
        CHECK(log_retention_days BETWEEN 1 AND 365),
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)
);
INSERT INTO local_preferences(
    singleton_id, cli_global_concurrency, log_retention_days, updated_at, version
) VALUES (1, 4, 30, strftime('%Y-%m-%dT%H:%M:%fZ','now'), 1);

-- employee_base_profiles (H.2)
CREATE TABLE employee_base_profiles (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    normalized_name TEXT NOT NULL,
    description TEXT NOT NULL,
    current_version_id TEXT REFERENCES employee_base_profile_versions(id)
        DEFERRABLE INITIALLY DEFERRED,
    status TEXT NOT NULL CHECK(status IN ('active', 'retired')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    UNIQUE(company_id, normalized_name)
);

-- employee_base_profile_versions (H.2)
CREATE TABLE employee_base_profile_versions (
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
    catalog_release_id TEXT NOT NULL REFERENCES catalog_cache_releases(release_id),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    status TEXT NOT NULL CHECK(status IN ('draft', 'published', 'retired')),
    created_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(profile_id, version_number),
    CHECK((status = 'draft' AND published_at IS NULL)
       OR (status IN ('published', 'retired') AND published_at IS NOT NULL))
);
CREATE UNIQUE INDEX uq_employee_profile_single_draft
    ON employee_base_profile_versions(profile_id) WHERE status = 'draft';

-- profile_skill_bindings (H.2)
CREATE TABLE profile_skill_bindings (
    profile_version_id TEXT NOT NULL REFERENCES employee_base_profile_versions(id),
    skill_id TEXT NOT NULL,
    skill_version_id TEXT NOT NULL,
    skill_version TEXT NOT NULL,
    package_sha256 TEXT NOT NULL CHECK(length(package_sha256) = 64),
    load_order INTEGER NOT NULL CHECK(load_order >= 0),
    PRIMARY KEY(profile_version_id, skill_version_id),
    UNIQUE(profile_version_id, load_order)
);

-- catalog_trust_keys (H.2)
CREATE TABLE catalog_trust_keys (
    key_id TEXT PRIMARY KEY,
    public_key_base64 TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'retired')),
    introduced_by_keyset_sha256 TEXT NOT NULL CHECK(length(introduced_by_keyset_sha256) = 64),
    trusted_at TEXT NOT NULL
);

-- auth_verification_keys (H.2)
CREATE TABLE auth_verification_keys (
    key_id TEXT PRIMARY KEY,
    public_key_base64 TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'retired')),
    signed_keyset_sha256 TEXT NOT NULL CHECK(length(signed_keyset_sha256) = 64),
    not_before TEXT NOT NULL,
    retire_after TEXT,
    cached_at TEXT NOT NULL
);

-- catalog_cache_releases (H.2)
CREATE TABLE catalog_cache_releases (
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
CREATE UNIQUE INDEX uq_active_catalog_release
    ON catalog_cache_releases(status) WHERE status = 'active';

-- catalog_cache_resources (H.2)
CREATE TABLE catalog_cache_resources (
    release_id TEXT NOT NULL REFERENCES catalog_cache_releases(release_id),
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    resource_version_id TEXT NOT NULL,
    content_json TEXT NOT NULL CHECK(json_valid(content_json)),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    PRIMARY KEY(release_id, resource_type, resource_id, resource_version_id)
);

-- installed_skill_versions (H.2)
CREATE TABLE installed_skill_versions (
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

-- emergency_disable_cache (H.2)
CREATE TABLE emergency_disable_cache (
    sequence INTEGER PRIMARY KEY CHECK(sequence > 0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64),
    signature TEXT NOT NULL,
    signing_key_id TEXT NOT NULL,
    activated_at TEXT NOT NULL
);

-- catalog_cache (runtime catalog cache)
CREATE TABLE catalog_cache (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL CHECK(json_valid(value_json)),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    cached_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- profile_revisions (profile revision history)
CREATE TABLE profile_revisions (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES local_profile(id),
    revision_number INTEGER NOT NULL CHECK(revision_number > 0),
    backend_origin TEXT NOT NULL,
    app_user_id TEXT NOT NULL,
    masked_identifier TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    created_at TEXT NOT NULL,
    UNIQUE(profile_id, revision_number)
);

-- companies (H.3)
CREATE TABLE companies (
    id TEXT PRIMARY KEY,
    normalized_name TEXT NOT NULL UNIQUE,
    current_revision_id TEXT NOT NULL,
    general_manager_office_id TEXT NOT NULL,
    general_manager_employee_id TEXT NOT NULL,
    company_conversation_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    FOREIGN KEY(current_revision_id, id) REFERENCES company_revisions(id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(general_manager_office_id, id) REFERENCES departments(id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(general_manager_employee_id, id) REFERENCES employees(id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(company_conversation_id, id) REFERENCES conversations(id, company_id)
        DEFERRABLE INITIALLY DEFERRED
);

-- company_revisions (H.3)
CREATE TABLE company_revisions (
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

-- departments (H.3)
CREATE TABLE departments (
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
    UNIQUE(company_id, normalized_name),
    FOREIGN KEY(current_revision_id, id, company_id)
        REFERENCES department_revisions(id, department_id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(leader_employee_id, company_id) REFERENCES employees(id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(department_conversation_id, company_id)
        REFERENCES conversations(id, company_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE UNIQUE INDEX uq_company_gm_office
    ON departments(company_id) WHERE department_type = 'general_manager_office';

-- department_revisions (H.3)
CREATE TABLE department_revisions (
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

-- department_responsibilities (H.3)
CREATE TABLE department_responsibilities (
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

-- employees (H.3)
CREATE TABLE employees (
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

-- conversations (H.4)
CREATE TABLE conversations (
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

-- domain_events (H.4)
CREATE TABLE domain_events (
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
CREATE INDEX ix_domain_events_company_sequence
    ON domain_events(company_id, row_sequence);
CREATE INDEX ix_domain_events_aggregate
    ON domain_events(aggregate_type, aggregate_id, aggregate_version);

-- outbox_events (H.4)
CREATE TABLE outbox_events (
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
CREATE INDEX ix_outbox_ready ON outbox_events(status, next_attempt_at, created_at);

-- projection_offsets (H.4)
CREATE TABLE projection_offsets (
    projection_name TEXT PRIMARY KEY,
    last_row_sequence INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

-- conversation_messages (H.4)
CREATE TABLE conversation_messages (
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
    FOREIGN KEY(task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(sender_employee_id, company_id) REFERENCES employees(id, company_id)
);
CREATE INDEX ix_messages_conversation_time
    ON conversation_messages(conversation_id, created_at, id);

-- idempotency (H.4)
CREATE TABLE idempotency (
    idempotency_key TEXT NOT NULL,
    request_sha256 TEXT NOT NULL CHECK(length(request_sha256) = 64),
    status TEXT NOT NULL CHECK(status IN ('processing', 'completed', 'failed')),
    response_json TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY(idempotency_key)
);

-- company_tasks (H.6)
CREATE TABLE company_tasks (
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
    ceo_confirmed_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(id, company_id),
    FOREIGN KEY(company_conversation_id, company_id)
        REFERENCES conversations(id, company_id),
    FOREIGN KEY(user_message_event_id, company_id)
        REFERENCES domain_events(event_id, company_id),
    FOREIGN KEY(supersedes_task_id, company_id)
        REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(active_plan_id, id, company_id)
        REFERENCES company_plan_versions(id, company_task_id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    CHECK((status IN ('waiting_dependency','waiting_resource','waiting_permission','paused')
           AND resume_state IS NOT NULL)
       OR (status NOT IN ('waiting_dependency','waiting_resource','waiting_permission','paused')
           AND resume_state IS NULL)),
    CHECK(supersedes_task_id IS NULL OR supersedes_task_id <> id)
);

-- company_plan_versions (H.6)
CREATE TABLE company_plan_versions (
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
    FOREIGN KEY(generated_by_run_id, company_id) REFERENCES agent_runs(id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    UNIQUE(id, company_task_id, company_id),
    UNIQUE(company_task_id, version_number)
);

-- task_context_snapshots (H.6)
CREATE TABLE task_context_snapshots (
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
    FOREIGN KEY(company_revision_id, company_id)
        REFERENCES company_revisions(id, company_id),
    FOREIGN KEY(plan_version_id, company_task_id, company_id)
        REFERENCES company_plan_versions(id, company_task_id, company_id),
    UNIQUE(company_task_id)
);

-- department_tasks (H.6)
CREATE TABLE department_tasks (
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
        'paused','cancelled','failed'
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
    UNIQUE(id, company_task_id, company_id),
    UNIQUE(company_task_id, stage_key),
    CHECK((status IN ('waiting_dependency','waiting_resource','waiting_permission','paused')
           AND resume_state IS NOT NULL)
       OR (status NOT IN ('waiting_dependency','waiting_resource','waiting_permission','paused')
           AND resume_state IS NULL))
);

-- department_task_dependencies (H.6)
CREATE TABLE department_task_dependencies (
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

-- department_task_deliverables (H.6)
CREATE TABLE department_task_deliverables (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    department_task_id TEXT NOT NULL,
    deliverable_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'published', 'cancelled')),
    published_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(department_task_id, company_id) REFERENCES department_tasks(id, company_id),
    UNIQUE(id, company_id)
);

-- employee_tasks (H.6)
CREATE TABLE employee_tasks (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    department_task_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    task_kind TEXT NOT NULL CHECK(task_kind IN ('standard', 'merge')),
    objective TEXT NOT NULL,
    acceptance_criteria_json TEXT NOT NULL CHECK(json_valid(acceptance_criteria_json)),
    status TEXT NOT NULL CHECK(status IN (
        'assigned','ready','running','submitted','peer_reviewing',
        'changes_requested','accepted','needs_review','needs_rework',
        'waiting_resource','paused','cancelled','failed'
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
    CHECK((status IN ('waiting_resource','paused') AND resume_state IS NOT NULL)
       OR (status NOT IN ('waiting_resource','paused') AND resume_state IS NULL))
);

-- employee_availability_snapshots (H.6)
CREATE TABLE employee_availability_snapshots (
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
    FOREIGN KEY(department_task_id, company_id)
        REFERENCES department_tasks(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id),
    UNIQUE(id, company_id)
);

-- execution_snapshots (H.6)
CREATE TABLE execution_snapshots (
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
    FOREIGN KEY(department_task_id, company_id) REFERENCES department_tasks(id, company_id),
    FOREIGN KEY(employee_task_id, company_id) REFERENCES employee_tasks(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id),
    FOREIGN KEY(task_workspace_id, company_task_id, company_id)
        REFERENCES task_workspaces(id, company_task_id, company_id),
    FOREIGN KEY(company_revision_id, company_id)
        REFERENCES company_revisions(id, company_id),
    FOREIGN KEY(department_revision_id, department_id, company_id)
        REFERENCES department_revisions(id, department_id, company_id),
    UNIQUE(id, company_id),
    UNIQUE(snapshot_purpose, work_item_id, employee_id, content_sha256),
    CHECK((snapshot_purpose = 'task_execution' AND employee_task_id IS NOT NULL)
       OR snapshot_purpose <> 'task_execution')
);

-- runtime_queue (H.10)
CREATE TABLE runtime_queue (
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
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    CHECK((work_item_type = 'knowledge_index' AND run_id IS NULL)
       OR (work_item_type <> 'knowledge_index' AND run_id IS NOT NULL)),
    UNIQUE(id, job_id, company_id)
);
CREATE UNIQUE INDEX uq_runtime_queue_active_work_item
    ON runtime_queue(work_item_type, work_item_id)
    WHERE status IN ('ready', 'leased');

-- runtime_company_fairness (H.10)
CREATE TABLE runtime_company_fairness (
    company_id TEXT PRIMARY KEY REFERENCES companies(id),
    last_dispatched_at TEXT NOT NULL
);

-- runtime_leases (H.10)
CREATE TABLE runtime_leases (
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
    FOREIGN KEY(queue_id, job_id, company_id) REFERENCES runtime_queue(id, job_id, company_id),
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id),
    FOREIGN KEY(conversation_id, company_id) REFERENCES conversations(id, company_id),
    CHECK((run_id IS NULL AND employee_id IS NULL AND conversation_id IS NULL)
       OR (run_id IS NOT NULL AND employee_id IS NOT NULL AND conversation_id IS NOT NULL))
);

-- agent_runs (H.11)
CREATE TABLE agent_runs (
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
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(department_task_id, company_id) REFERENCES department_tasks(id, company_id),
    FOREIGN KEY(employee_task_id, company_id) REFERENCES employee_tasks(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id),
    FOREIGN KEY(conversation_id, company_id) REFERENCES conversations(id, company_id),
    FOREIGN KEY(availability_snapshot_id, company_id)
        REFERENCES employee_availability_snapshots(id, company_id),
    FOREIGN KEY(execution_snapshot_id, company_id)
        REFERENCES execution_snapshots(id, company_id),
    UNIQUE(id, company_id),
    CHECK(
        (run_purpose IN ('task_execution','merge')
            AND department_task_id IS NOT NULL
            AND employee_task_id IS NOT NULL
            AND work_item_id = employee_task_id)
        OR
        (run_purpose IN ('company_plan','summary')
            AND department_task_id IS NULL
            AND employee_task_id IS NULL
            AND work_item_id = company_task_id)
        OR
        (run_purpose = 'interactive_turn'
            AND department_task_id IS NULL
            AND employee_task_id IS NULL
            AND work_item_id = conversation_id)
        OR
        (run_purpose IN ('review','verification','repair'))
    ),
    CHECK((status IN ('waiting_approval','waiting_resource') AND resume_state IS NOT NULL)
       OR (status NOT IN ('waiting_approval','waiting_resource') AND resume_state IS NULL)),
    CHECK((process_pid IS NULL AND process_group_id IS NULL AND process_started_at IS NULL)
       OR (process_pid > 0 AND process_group_id > 0 AND process_started_at IS NOT NULL))
);

-- agent_run_events (H.11)
CREATE TABLE agent_run_events (
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

-- checkpoints (H.11)
CREATE TABLE checkpoints (
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

-- tool_executions (H.11)
CREATE TABLE tool_executions (
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
    UNIQUE(run_id, tool_call_id),
    FOREIGN KEY(approval_id, run_id) REFERENCES human_approvals(id, run_id)
);

-- human_approvals (H.11)
CREATE TABLE human_approvals (
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
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id),
    UNIQUE(id, run_id),
    CHECK(
        (status = 'pending' AND resolved_at IS NULL AND consumed_at IS NULL)
        OR
        (status IN ('allowed','denied','expired') AND resolved_at IS NOT NULL AND consumed_at IS NULL)
        OR
        (status = 'consumed' AND resolved_at IS NOT NULL AND consumed_at IS NOT NULL)
    )
);

-- verification_results (H.11)
CREATE TABLE verification_results (
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
    UNIQUE(run_id, round_number, command_argv_json),
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id),
    FOREIGN KEY(stdout_artifact_id, company_id) REFERENCES artifacts(id, company_id),
    FOREIGN KEY(stderr_artifact_id, company_id) REFERENCES artifacts(id, company_id)
);

-- workspace_grants (H.11)
CREATE TABLE workspace_grants (
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
CREATE UNIQUE INDEX uq_workspace_active_path
    ON workspace_grants(normalized_path) WHERE status = 'active';

-- task_workspaces (H.11)
CREATE TABLE task_workspaces (
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
    UNIQUE(id, company_task_id, company_id),
    UNIQUE(company_task_id)
);

-- artifacts (H.12)
CREATE TABLE artifacts (
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
    is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1)),
    created_by_type TEXT NOT NULL CHECK(created_by_type IN ('user', 'agent', 'system')),
    created_by_run_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(id, company_id),
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(department_task_id, company_id) REFERENCES department_tasks(id, company_id),
    FOREIGN KEY(employee_task_id, company_id) REFERENCES employee_tasks(id, company_id),
    FOREIGN KEY(supersedes_artifact_id, company_id) REFERENCES artifacts(id, company_id),
    FOREIGN KEY(created_by_run_id, company_id) REFERENCES agent_runs(id, company_id),
    CHECK((created_by_type = 'agent' AND created_by_run_id IS NOT NULL)
       OR (created_by_type <> 'agent' AND created_by_run_id IS NULL))
);
CREATE INDEX ix_artifacts_task_type
    ON artifacts(company_task_id, artifact_type, created_at);

CREATE TRIGGER artifacts_supersede_is_current
BEFORE INSERT ON artifacts
WHEN NEW.supersedes_artifact_id IS NOT NULL
BEGIN
    UPDATE artifacts SET is_current = 0
    WHERE id = NEW.supersedes_artifact_id
    AND company_id = NEW.company_id;
END;

-- artifact_contributors (H.12)
CREATE TABLE artifact_contributors (
    artifact_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    PRIMARY KEY(artifact_id, employee_id),
    FOREIGN KEY(artifact_id, company_id) REFERENCES artifacts(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id)
);

-- artifact_versions (H.12)
CREATE TABLE artifact_versions (
    id TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    version_number INTEGER NOT NULL CHECK(version_number > 0),
    object_sha256 TEXT NOT NULL CHECK(length(object_sha256) = 64),
    object_size INTEGER NOT NULL CHECK(object_size >= 0),
    metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)),
    is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0, 1)),
    created_at TEXT NOT NULL,
    FOREIGN KEY(artifact_id, company_id) REFERENCES artifacts(id, company_id),
    UNIQUE(artifact_id, version_number)
);

-- review_assignments (H.12)
CREATE TABLE review_assignments (
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

-- review_reports (H.12)
CREATE TABLE review_reports (
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

-- review_issues (H.12)
CREATE TABLE review_issues (
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
    superseded_by_artifact_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(id, company_id),
    CHECK(status <> 'rejected' OR (severity IN ('medium','low') AND rejection_reason IS NOT NULL)),
    FOREIGN KEY(review_report_id, company_id) REFERENCES review_reports(id, company_id),
    FOREIGN KEY(assignee_employee_id, company_id) REFERENCES employees(id, company_id),
    FOREIGN KEY(verifier_employee_id, company_id) REFERENCES employees(id, company_id),
    FOREIGN KEY(superseded_by_artifact_id, company_id) REFERENCES artifacts(id, company_id)
);

-- rework_attempts (H.12)
CREATE TABLE rework_attempts (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_task_id TEXT,
    attempt_no INTEGER NOT NULL CHECK(attempt_no >= 1),
    status TEXT NOT NULL
        CHECK(status IN ('planned','running','completed','cancelled','failed')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    UNIQUE(id, company_id),
    FOREIGN KEY(company_task_id, company_id)
        REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(department_task_id, company_id)
        REFERENCES department_tasks(id, company_id),
    CHECK(
        (status IN ('completed','cancelled','failed') AND completed_at IS NOT NULL)
        OR
        (status IN ('planned','running') AND completed_at IS NULL)
    )
);
CREATE UNIQUE INDEX ux_rework_attempt_scope_no
    ON rework_attempts(
        company_id,
        company_task_id,
        COALESCE(department_task_id, ''),
        attempt_no
    );
CREATE UNIQUE INDEX ux_rework_attempt_active_scope
    ON rework_attempts(
        company_id,
        company_task_id,
        COALESCE(department_task_id, '')
    )
    WHERE status IN ('planned','running');

-- rework_attempt_issues (H.12)
CREATE TABLE rework_attempt_issues (
    company_id TEXT NOT NULL,
    rework_attempt_id TEXT NOT NULL,
    review_issue_id TEXT NOT NULL,
    PRIMARY KEY(rework_attempt_id, review_issue_id),
    FOREIGN KEY(rework_attempt_id, company_id)
        REFERENCES rework_attempts(id, company_id),
    FOREIGN KEY(review_issue_id, company_id)
        REFERENCES review_issues(id, company_id)
);

-- approvals
CREATE TABLE approvals (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    approval_type TEXT NOT NULL CHECK(approval_type IN ('task_completion', 'external_write', 'tool_execution')),
    target_json TEXT NOT NULL CHECK(json_valid(target_json)),
    target_sha256 TEXT NOT NULL CHECK(length(target_sha256) = 64),
    status TEXT NOT NULL CHECK(status IN ('pending','allowed','denied','expired','consumed')),
    requested_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    resolved_at TEXT,
    consumed_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id),
    UNIQUE(id, run_id),
    CHECK(
        (status = 'pending' AND resolved_at IS NULL AND consumed_at IS NULL)
        OR
        (status IN ('allowed','denied','expired') AND resolved_at IS NOT NULL AND consumed_at IS NULL)
        OR
        (status = 'consumed' AND resolved_at IS NOT NULL AND consumed_at IS NOT NULL)
    )
);

-- verifications
CREATE TABLE verifications (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    verification_type TEXT NOT NULL CHECK(verification_type IN ('review', 'test', 'audit')),
    status TEXT NOT NULL CHECK(status IN ('pending', 'passed', 'failed', 'error')),
    result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json)),
    completed_at TEXT,
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id),
    FOREIGN KEY(artifact_id, company_id) REFERENCES artifacts(id, company_id),
    UNIQUE(id, company_id)
);

-- domain_event_store (domain event registry)
CREATE TABLE domain_event_store (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    aggregate_version INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    trace_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE(id, company_id)
);

-- outbox
CREATE TABLE outbox (
    id TEXT PRIMARY KEY,
    domain_event_id TEXT NOT NULL UNIQUE,
    topic TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    status TEXT NOT NULL CHECK(status IN ('pending', 'processing', 'delivered', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL,
    last_error TEXT,
    created_at TEXT NOT NULL,
    delivered_at TEXT
);
CREATE INDEX ix_outbox_ready_pending ON outbox(status, next_attempt_at, created_at)
    WHERE status IN ('pending', 'processing');

-- projections
CREATE TABLE projections (
    name TEXT PRIMARY KEY,
    last_row_sequence INTEGER NOT NULL DEFAULT 0,
    state_json TEXT CHECK(state_json IS NULL OR json_valid(state_json)),
    updated_at TEXT NOT NULL
);

-- knowledge_sources
CREATE TABLE knowledge_sources (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    name TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('artifact', 'message', 'file', 'manual')),
    source_ref TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    status TEXT NOT NULL CHECK(status IN ('pending', 'indexed', 'failed')),
    created_at TEXT NOT NULL,
    indexed_at TEXT,
    UNIQUE(id, company_id)
);

-- knowledge_chunks
CREATE TABLE knowledge_chunks (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL CHECK(chunk_index >= 0),
    content TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256) = 64),
    embedding_generation_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(source_id, company_id) REFERENCES knowledge_sources(id, company_id),
    UNIQUE(source_id, chunk_index)
);

-- knowledge_items (H.13)
CREATE TABLE knowledge_items (
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
    FOREIGN KEY(source_artifact_id, company_id) REFERENCES artifacts(id, company_id),
    FOREIGN KEY(source_message_event_id, company_id) REFERENCES domain_events(event_id, company_id),
    FOREIGN KEY(owner_employee_id, company_id) REFERENCES employees(id, company_id),
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id),
    FOREIGN KEY(task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(embedding_generation_id, company_id) REFERENCES embedding_generations(id, company_id),
    CHECK((source_artifact_id IS NULL) <> (source_message_event_id IS NULL)),
    CHECK(
        (visibility = 'company' AND department_id IS NULL AND task_id IS NULL AND owner_employee_id IS NULL)
        OR (visibility = 'department' AND department_id IS NOT NULL AND task_id IS NULL AND owner_employee_id IS NULL)
        OR (visibility = 'task' AND task_id IS NOT NULL AND owner_employee_id IS NULL)
        OR (visibility = 'private' AND owner_employee_id IS NOT NULL)
    )
);

-- knowledge_fts (H.13)
CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    knowledge_id UNINDEXED,
    company_id UNINDEXED,
    generation_id UNINDEXED,
    title,
    content,
    tokenize='unicode61'
);

-- embedding_generations (H.13)
CREATE TABLE embedding_generations (
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
CREATE UNIQUE INDEX uq_active_embedding_generation
    ON embedding_generations(company_id) WHERE status = 'active';
CREATE INDEX ix_knowledge_items_unindexed
    ON knowledge_items(company_id, id) WHERE embedding_generation_id IS NULL;

-- index_generations
CREATE TABLE index_generations (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    generation_type TEXT NOT NULL CHECK(generation_type IN ('embedding', 'keyword', 'hybrid')),
    model_key TEXT NOT NULL,
    vector_dimension INTEGER CHECK(vector_dimension IS NULL OR vector_dimension > 0),
    status TEXT NOT NULL CHECK(status IN ('building', 'active', 'retired', 'failed')),
    source_event_sequence INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    activated_at TEXT,
    UNIQUE(id, company_id)
);

-- knowledge_access_logs (H.13)
CREATE TABLE knowledge_access_logs (
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
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id)
);
CREATE INDEX ix_knowledge_access_run
    ON knowledge_access_logs(run_id, row_sequence);

-- backup_records (H.13.1)
CREATE TABLE backup_records (
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

-- audit_logs (H.14)
CREATE TABLE audit_logs (
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
    created_at TEXT NOT NULL,
    hash TEXT NOT NULL DEFAULT '',
    prev_hash TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(company_id) REFERENCES companies(id)
);
CREATE INDEX ix_audit_company_sequence ON audit_logs(company_id, row_sequence);

CREATE TRIGGER audit_logs_no_update
BEFORE UPDATE ON audit_logs
BEGIN SELECT RAISE(ABORT, 'audit log is immutable'); END;

CREATE TRIGGER audit_logs_no_delete
BEFORE DELETE ON audit_logs
BEGIN SELECT RAISE(ABORT, 'audit log is immutable'); END;

-- ── Immutability triggers (evidence tables) ────────────────────────────

CREATE TRIGGER company_revisions_no_update
BEFORE UPDATE ON company_revisions
BEGIN SELECT RAISE(ABORT, 'company revision is immutable'); END;

CREATE TRIGGER company_revisions_no_delete
BEFORE DELETE ON company_revisions
BEGIN SELECT RAISE(ABORT, 'company revision is immutable'); END;

CREATE TRIGGER review_reports_no_update
BEFORE UPDATE ON review_reports
BEGIN SELECT RAISE(ABORT, 'review report is immutable'); END;

CREATE TRIGGER review_reports_no_delete
BEFORE DELETE ON review_reports
BEGIN SELECT RAISE(ABORT, 'review report is immutable'); END;

CREATE TRIGGER domain_event_store_no_update
BEFORE UPDATE ON domain_event_store
BEGIN SELECT RAISE(ABORT, 'domain event store is immutable'); END;

CREATE TRIGGER domain_event_store_no_delete
BEFORE DELETE ON domain_event_store
BEGIN SELECT RAISE(ABORT, 'domain event store is immutable'); END;

CREATE TRIGGER profile_revisions_no_update
BEFORE UPDATE ON profile_revisions
BEGIN SELECT RAISE(ABORT, 'profile revision is immutable'); END;

CREATE TRIGGER profile_revisions_no_delete
BEFORE DELETE ON profile_revisions
BEGIN SELECT RAISE(ABORT, 'profile revision is immutable'); END;

CREATE TRIGGER knowledge_chunks_no_update
BEFORE UPDATE ON knowledge_chunks
BEGIN SELECT RAISE(ABORT, 'knowledge chunk is immutable'); END;

CREATE TRIGGER knowledge_chunks_no_delete
BEFORE DELETE ON knowledge_chunks
BEGIN SELECT RAISE(ABORT, 'knowledge chunk is immutable'); END;

CREATE TRIGGER knowledge_sources_no_delete
BEFORE DELETE ON knowledge_sources
WHEN OLD.status IN ('indexed')
BEGIN SELECT RAISE(ABORT, 'indexed knowledge source is immutable'); END;

CREATE TRIGGER backup_records_no_update
BEFORE UPDATE ON backup_records
WHEN OLD.status IN ('completed', 'failed')
BEGIN SELECT RAISE(ABORT, 'terminal backup record is immutable'); END;

CREATE TRIGGER artifact_versions_no_update
BEFORE UPDATE ON artifact_versions
BEGIN SELECT RAISE(ABORT, 'artifact version is immutable'); END;

CREATE TRIGGER artifact_versions_no_delete
BEFORE DELETE ON artifact_versions
BEGIN SELECT RAISE(ABORT, 'artifact version is immutable'); END;

CREATE TRIGGER rework_attempts_no_update
BEFORE UPDATE ON rework_attempts
WHEN OLD.status IN ('completed', 'cancelled', 'failed')
BEGIN SELECT RAISE(ABORT, 'terminal rework attempt is immutable'); END;

-- Profile version content immutability guards
CREATE TRIGGER employee_profile_version_published_guard
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

CREATE TRIGGER employee_profile_version_no_delete
BEFORE DELETE ON employee_base_profile_versions
WHEN OLD.status IN ('published','retired')
BEGIN SELECT RAISE(ABORT, 'published profile version is immutable'); END;

CREATE TRIGGER profile_skill_bindings_insert_guard
BEFORE INSERT ON profile_skill_bindings
WHEN (SELECT status FROM employee_base_profile_versions WHERE id=NEW.profile_version_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'only draft profile version skills are mutable'); END;

CREATE TRIGGER profile_skill_bindings_update_guard
BEFORE UPDATE ON profile_skill_bindings
WHEN (SELECT status FROM employee_base_profile_versions WHERE id=OLD.profile_version_id) <> 'draft'
   OR (SELECT status FROM employee_base_profile_versions WHERE id=NEW.profile_version_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'only draft profile version skills are mutable'); END;

CREATE TRIGGER profile_skill_bindings_delete_guard
BEFORE DELETE ON profile_skill_bindings
WHEN (SELECT status FROM employee_base_profile_versions WHERE id=OLD.profile_version_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'only draft profile version skills are mutable'); END;

-- Final verification
PRAGMA foreign_key_check;
PRAGMA integrity_check;
