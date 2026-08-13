-- Intelligent routing persistence epoch 6.
-- Existing snapshots remain readable; only new smart/ensemble runs may use the
-- routing fields and tables below. All writes are serialized by WriteQueue.

ALTER TABLE employee_base_profile_versions
    ADD COLUMN routing_policy_json TEXT NOT NULL DEFAULT '{}'
    CHECK(json_valid(routing_policy_json));

ALTER TABLE execution_snapshots
    ADD COLUMN routing_policy_json TEXT CHECK(routing_policy_json IS NULL OR json_valid(routing_policy_json));
ALTER TABLE execution_snapshots
    ADD COLUMN routing_policy_sha256 TEXT CHECK(routing_policy_sha256 IS NULL OR length(routing_policy_sha256) = 64);
ALTER TABLE execution_snapshots
    ADD COLUMN routing_classifier_version TEXT;
ALTER TABLE execution_snapshots
    ADD COLUMN candidate_bindings_json TEXT CHECK(candidate_bindings_json IS NULL OR json_valid(candidate_bindings_json));
ALTER TABLE execution_snapshots
    ADD COLUMN candidate_bindings_sha256 TEXT CHECK(candidate_bindings_sha256 IS NULL OR length(candidate_bindings_sha256) = 64);
ALTER TABLE employee_task_dispatch_specs
    ADD COLUMN routing_policy_json TEXT NOT NULL DEFAULT '{}'
    CHECK(json_valid(routing_policy_json));

CREATE TABLE route_decisions (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL CHECK(turn_index > 0),
    execution_snapshot_id TEXT NOT NULL,
    routing_mode TEXT NOT NULL CHECK(routing_mode IN ('fixed','smart_single','selective_ensemble')),
    classifier_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint) = 64),
    required_tier TEXT NOT NULL CHECK(required_tier IN ('C0','C1','C2','C3')),
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    selected_kind TEXT NOT NULL CHECK(selected_kind IN ('single','ensemble')),
    selected_bindings_json TEXT NOT NULL CHECK(json_valid(selected_bindings_json)),
    aggregator_candidate_id TEXT,
    policy_trail_json TEXT NOT NULL CHECK(json_valid(policy_trail_json)),
    status TEXT NOT NULL CHECK(status IN ('planned','executing','succeeded','failed','cancelled')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(id, company_id),
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id),
    FOREIGN KEY(execution_snapshot_id, company_id)
        REFERENCES execution_snapshots(id, company_id)
);
CREATE UNIQUE INDEX uq_route_decision_turn ON route_decisions(run_id, turn_index);

CREATE TABLE route_attempts (
    id TEXT PRIMARY KEY,
    route_decision_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    execution_snapshot_id TEXT NOT NULL,
    attempt_sequence INTEGER NOT NULL CHECK(attempt_sequence > 0),
    role TEXT NOT NULL CHECK(role IN ('single','proposer','aggregator','fallback')),
    candidate_id TEXT NOT NULL,
    provider_release_id TEXT NOT NULL,
    model_binding_id TEXT NOT NULL,
    credential_ref_sha256 TEXT NOT NULL CHECK(length(credential_ref_sha256) = 64),
    request_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('created','accepted','streaming','succeeded','failed','cancelled','timed_out')),
    failure_kind TEXT CHECK(failure_kind IS NULL OR failure_kind IN (
        'RATE_LIMITED','PROVIDER_OVERLOADED','TRANSPORT_TRANSIENT','TIMEOUT',
        'CONTEXT_OVERFLOW','AUTH_INVALID','MODEL_NOT_FOUND','UNSUPPORTED_CAPABILITY',
        'INSUFFICIENT_CREDITS','BAD_REQUEST','POLICY_REFUSAL','INVALID_RESPONSE'
    )),
    http_status INTEGER CHECK(http_status IS NULL OR (http_status BETWEEN 100 AND 599)),
    created_at TEXT NOT NULL,
    accepted_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    latency_ms INTEGER CHECK(latency_ms IS NULL OR latency_ms >= 0),
    input_tokens INTEGER CHECK(input_tokens IS NULL OR input_tokens >= 0),
    output_tokens INTEGER CHECK(output_tokens IS NULL OR output_tokens >= 0),
    total_tokens INTEGER CHECK(total_tokens IS NULL OR total_tokens >= 0),
    candidate_truncated INTEGER NOT NULL DEFAULT 0 CHECK(candidate_truncated IN (0,1)),
    UNIQUE(id, company_id),
    FOREIGN KEY(route_decision_id, company_id) REFERENCES route_decisions(id, company_id),
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id),
    FOREIGN KEY(execution_snapshot_id, company_id)
        REFERENCES execution_snapshots(id, company_id)
);
CREATE UNIQUE INDEX uq_route_attempt_sequence ON route_attempts(route_decision_id, attempt_sequence);
CREATE UNIQUE INDEX uq_route_attempt_request ON route_attempts(request_id) WHERE request_id IS NOT NULL;
CREATE INDEX ix_route_attempt_active ON route_attempts(run_id, status);

CREATE TABLE deployment_health (
    company_id TEXT NOT NULL,
    provider_release_id TEXT NOT NULL,
    model_binding_id TEXT NOT NULL,
    credential_ref_sha256 TEXT NOT NULL CHECK(length(credential_ref_sha256) = 64),
    availability_state TEXT NOT NULL CHECK(availability_state IN ('ready','credential_invalid')),
    consecutive_strikes INTEGER NOT NULL DEFAULT 0 CHECK(consecutive_strikes >= 0),
    benched_until TEXT,
    last_failure_kind TEXT,
    last_failure_at TEXT,
    last_success_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(company_id, provider_release_id, model_binding_id, credential_ref_sha256)
);
CREATE INDEX ix_deployment_health_bench ON deployment_health(benched_until);

CREATE TABLE route_outcomes (
    id TEXT PRIMARY KEY,
    route_decision_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    outcome_type TEXT NOT NULL CHECK(outcome_type IN ('tool_result','verification','artifact','review','task_terminal')),
    source_id TEXT NOT NULL,
    score REAL NOT NULL CHECK(score >= 0 AND score <= 1),
    label TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE(route_decision_id, outcome_type, source_id),
    FOREIGN KEY(route_decision_id, company_id) REFERENCES route_decisions(id, company_id)
);

CREATE TABLE routing_run_controls (
    company_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    override_mode TEXT CHECK(override_mode IS NULL OR override_mode IN ('force_fixed','force_single','force_ensemble')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(company_id, run_id),
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id)
);

CREATE TRIGGER route_decision_immutable_selection
BEFORE UPDATE ON route_decisions
WHEN OLD.turn_index IS NOT NEW.turn_index
  OR OLD.execution_snapshot_id IS NOT NEW.execution_snapshot_id
  OR OLD.routing_mode IS NOT NEW.routing_mode
  OR OLD.classifier_version IS NOT NEW.classifier_version
  OR OLD.input_fingerprint IS NOT NEW.input_fingerprint
  OR OLD.required_tier IS NOT NEW.required_tier
  OR OLD.confidence IS NOT NEW.confidence
  OR OLD.selected_kind IS NOT NEW.selected_kind
  OR OLD.selected_bindings_json IS NOT NEW.selected_bindings_json
  OR OLD.aggregator_candidate_id IS NOT NEW.aggregator_candidate_id
  OR OLD.policy_trail_json IS NOT NEW.policy_trail_json
BEGIN
    SELECT RAISE(ABORT, 'route decision selection is immutable');
END;

CREATE TRIGGER route_attempt_identity_immutable
BEFORE UPDATE ON route_attempts
WHEN OLD.route_decision_id IS NOT NEW.route_decision_id
  OR OLD.company_id IS NOT NEW.company_id
  OR OLD.run_id IS NOT NEW.run_id
  OR OLD.execution_snapshot_id IS NOT NEW.execution_snapshot_id
  OR OLD.attempt_sequence IS NOT NEW.attempt_sequence
  OR OLD.role IS NOT NEW.role
  OR OLD.candidate_id IS NOT NEW.candidate_id
  OR OLD.provider_release_id IS NOT NEW.provider_release_id
  OR OLD.model_binding_id IS NOT NEW.model_binding_id
  OR OLD.credential_ref_sha256 IS NOT NEW.credential_ref_sha256
BEGIN
    SELECT RAISE(ABORT, 'route attempt identity is immutable');
END;

CREATE TRIGGER route_attempt_parent_guard
BEFORE INSERT ON route_attempts
WHEN EXISTS (
    SELECT 1 FROM route_decisions d
    WHERE d.id = NEW.route_decision_id
      AND (d.company_id <> NEW.company_id OR d.run_id <> NEW.run_id
           OR d.execution_snapshot_id <> NEW.execution_snapshot_id)
)
  OR NOT EXISTS (
    SELECT 1
    FROM json_each((SELECT selected_bindings_json FROM route_decisions WHERE id = NEW.route_decision_id)) item
    WHERE json_extract(item.value, '$.candidate_id') = NEW.candidate_id
      AND json_extract(item.value, '$.role') = NEW.role
)
BEGIN
    SELECT RAISE(ABORT, 'route attempt parent or candidate mismatch');
END;

DROP TRIGGER IF EXISTS employee_profile_version_published_guard;
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
        AND NEW.routing_policy_json IS OLD.routing_policy_json
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
