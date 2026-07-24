"""Pydantic V2 schemas for iBreeze Sidecar domain entities.

Aligns with design doc appendices E, H.3–H.14, J (RPC).
All timestamps are RFC 3339 UTC with 'Z' suffix.
All IDs are UUID v4 strings.
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ── 枚举定义 ──────────────────────────────────────────────────────────────


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class DepartmentType(StrEnum):
    GENERAL_MANAGER_OFFICE = "general_manager_office"
    STANDARD = "standard"


class ConversationType(StrEnum):
    COMPANY = "company"
    DEPARTMENT = "department"


class WorkflowRole(StrEnum):
    GENERAL_MANAGER = "general_manager"
    DEPARTMENT_LEADER = "department_leader"
    MEMBER = "member"


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    DRAINING = "draining"
    INACTIVE = "inactive"
    UNAVAILABLE = "unavailable"


class ProfileType(StrEnum):
    AGENT_CLI = "agent_cli"
    API_MODEL = "api_model"


class ProfileVersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"


class CompanyTaskStatus(StrEnum):
    DRAFT = "draft"
    ANALYZING = "analyzing"
    AWAITING_USER_CONFIRMATION = "awaiting_user_confirmation"
    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"
    REJECTED = "rejected"
    DISPATCHING = "dispatching"
    CHECKING_RESOURCES = "checking_resources"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    FIXING = "fixing"
    FINAL_REVIEW = "final_review"
    COMPLETED = "completed"
    WAITING_DEPENDENCY = "waiting_dependency"
    WAITING_RESOURCE = "waiting_resource"
    WAITING_PERMISSION = "waiting_permission"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PlanVersionStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_USER_CONFIRMATION = "awaiting_user_confirmation"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class DepartmentTaskStatus(StrEnum):
    DRAFT = "draft"
    CHECKING_RESOURCES = "checking_resources"
    READY = "ready"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    FIXING = "fixing"
    COMPLETED = "completed"
    WAITING_DEPENDENCY = "waiting_dependency"
    WAITING_RESOURCE = "waiting_resource"
    WAITING_PERMISSION = "waiting_permission"
    CANCELLED = "cancelled"
    FAILED = "failed"


class EmployeeTaskStatus(StrEnum):
    ASSIGNED = "assigned"
    READY = "ready"
    RUNNING = "running"
    SUBMITTED = "submitted"
    PEER_REVIEWING = "peer_reviewing"
    CHANGES_REQUESTED = "changes_requested"
    ACCEPTED = "accepted"
    WAITING_RESOURCE = "waiting_resource"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TaskKind(StrEnum):
    STANDARD = "standard"
    MERGE = "merge"


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    PROBING = "probing"
    STARTING = "starting"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    VERIFYING = "verifying"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    WAITING_RESOURCE = "waiting_resource"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    LOST = "lost"


class RunPurpose(StrEnum):
    INTERACTIVE_TURN = "interactive_turn"
    COMPANY_PLAN = "company_plan"
    TASK_EXECUTION = "task_execution"
    REVIEW = "review"
    VERIFICATION = "verification"
    REPAIR = "repair"
    MERGE = "merge"
    SUMMARY = "summary"
    KNOWLEDGE_INDEX = "knowledge_index"


class AdapterType(StrEnum):
    CODEX_CLI = "codex_cli"
    CLAUDE_CODE = "claude_code"
    OPENCODE = "opencode"
    API_MODEL = "api_model"


class WorkItemType(StrEnum):
    INTERACTIVE_TURN = "interactive_turn"
    COMPANY_PLAN = "company_plan"
    EMPLOYEE_TASK = "employee_task"
    REVIEW = "review"
    VERIFICATION = "verification"
    REPAIR = "repair"
    MERGE = "merge"
    SUMMARY = "summary"
    KNOWLEDGE_INDEX = "knowledge_index"


class QueuePriority(IntEnum):
    HIGH = 0
    NORMAL = 10
    LOW = 20
    BACKGROUND = 30


class QueueItemStatus(StrEnum):
    READY = "ready"
    LEASED = "leased"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ToolExecutionStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


class ApprovalType(StrEnum):
    EXTERNAL_WRITE = "external_write"
    UNCERTAIN_RECOVERY = "uncertain_recovery"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    ALLOWED = "allowed"
    DENIED = "denied"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class VerificationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class ArtifactType(StrEnum):
    SOURCE_CODE_PATCH = "source_code_patch"
    DOCUMENT = "document"
    TEST_CASE = "test_case"
    TEST_RESULT = "test_result"
    REVIEW_REPORT = "review_report"
    EXECUTION_REPORT = "execution_report"
    DEPARTMENT_REPORT = "department_report"
    FINAL_REPORT = "final_report"
    LOG = "log"
    DIFF = "diff"
    CHECKPOINT = "checkpoint"
    TRANSCRIPT = "transcript"
    DIAGNOSTIC = "diagnostic"
    IMPORTED_FILE = "imported_file"
    MERGE_REPORT = "merge_report"
    GIT_BUNDLE = "git_bundle"
    MANIFEST = "manifest"


class CreatedByType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class ReviewAssignmentStatus(StrEnum):
    ASSIGNED = "assigned"
    IN_REVIEW = "in_review"
    SUBMITTED = "submitted"
    STALE = "stale"
    CANCELLED = "cancelled"


class ReviewVerdict(StrEnum):
    PASS = "pass"
    NEEDS_CHANGES = "needs_changes"
    FAILED = "failed"


class ReviewIssueSeverity(StrEnum):
    BLOCKER = "blocker"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewIssueStatus(StrEnum):
    OPEN = "open"
    FIXING = "fixing"
    RESOLVED = "resolved"
    VERIFIED = "verified"
    CLOSED = "closed"
    REJECTED = "rejected"


class WorkspaceGrantStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    STALE = "stale"


class PathType(StrEnum):
    CODE_REPOSITORY = "code_repository"
    IMPORT_SOURCE = "import_source"


class TaskWorkspaceStatus(StrEnum):
    PREPARING = "preparing"
    ACTIVE = "active"
    READY_TO_APPLY = "ready_to_apply"
    APPLIED = "applied"
    ABANDONED = "abandoned"


class KnowledgeVisibility(StrEnum):
    COMPANY = "company"
    DEPARTMENT = "department"
    TASK = "task"
    PRIVATE = "private"


class EmbeddingStatus(StrEnum):
    BUILDING = "building"
    ACTIVE = "active"
    RETIRED = "retired"
    FAILED = "failed"


class BackupType(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MANUAL = "manual"
    PRE_UPGRADE = "pre_upgrade"


class BackupStatus(StrEnum):
    CREATING = "creating"
    COMPLETED = "completed"
    FAILED = "failed"
    DELETED = "deleted"


class AuditActorType(StrEnum):
    USER = "user"
    EMPLOYEE = "employee"
    SYSTEM = "system"


class AuditOutcome(StrEnum):
    SUCCESS = "success"
    DENIED = "denied"
    FAILED = "failed"


class CatalogCacheReleaseStatus(StrEnum):
    STAGING = "staging"
    ACTIVE = "active"
    RETIRED = "retired"
    INVALID = "invalid"


class InstalledSkillStatus(StrEnum):
    INSTALLED = "installed"
    DISABLED = "disabled"
    CORRUPT = "corrupt"


class CheckpointStorageType(StrEnum):
    SQLITE_BLOB = "sqlite_blob"
    FILE = "file"


class SnapshotPurpose(StrEnum):
    INTERACTIVE_TURN = "interactive_turn"
    COMPANY_PLAN = "company_plan"
    TASK_EXECUTION = "task_execution"
    REVIEW = "review"
    VERIFICATION = "verification"
    REPAIR = "repair"
    MERGE = "merge"
    SUMMARY = "summary"


# ── 工作区配置 ────────────────────────────────────────────────────────────


class StrictModel(BaseModel):
    """所有 schema 的基类，禁止额外字段"""

    model_config = ConfigDict(extra="forbid")


# ── Company ───────────────────────────────────────────────────────────────


class CompanyCreate(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    introduction: Annotated[str, Field(min_length=1, max_length=20000)]
    general_manager_name: Annotated[
        str,
        Field(min_length=1, max_length=100),
    ]
    base_profile_version_id: str


class CompanyUpdate(StrictModel):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=100)]
    introduction: Annotated[
        str | None,
        Field(default=None, min_length=1, max_length=20000),
    ]
    expected_version: Annotated[int, Field(ge=1)]


class CompanyRevision(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    revision_number: int
    name: str
    introduction: str
    content_sha256: str
    created_by_type: CreatedByType
    created_at: datetime


class CompanyResponse(StrictModel):
    """Company aggregate response defined by H.3."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    normalized_name: str
    current_revision_id: str
    general_manager_office_id: str
    general_manager_employee_id: str
    company_conversation_id: str
    status: CompanyStatus
    created_at: datetime
    updated_at: datetime
    version: int


# ── Department ────────────────────────────────────────────────────────────


class DepartmentCreate(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    function_description: Annotated[str, Field(min_length=1, max_length=10000)]
    leader_name: Annotated[str, Field(min_length=1, max_length=100)]
    base_profile_version_id: str


class DepartmentUpdate(StrictModel):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=100)]
    function_description: Annotated[str | None, Field(default=None, min_length=1, max_length=10000)]
    expected_version: Annotated[int, Field(ge=1)]


class DepartmentRevision(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    department_id: str
    company_id: str
    revision_number: int
    name: str
    function_description: str
    content_sha256: str
    created_at: datetime


class DepartmentResponsibility(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    department_id: str
    company_id: str
    responsibility_key: str
    name: str
    description: str
    accepted_task_types_json: str
    required_capability_tags_json: str
    deliverable_types_json: str
    quality_gates_json: str
    upstream_keys_json: str
    downstream_keys_json: str
    created_at: datetime
    updated_at: datetime


class DepartmentResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    department_type: DepartmentType
    normalized_name: str
    current_revision_id: str
    leader_employee_id: str
    department_conversation_id: str
    status: CompanyStatus
    created_at: datetime
    updated_at: datetime
    version: int


# ── Employee ──────────────────────────────────────────────────────────────


class EmployeeCreate(StrictModel):
    display_name: Annotated[str, Field(min_length=1, max_length=100)]
    base_profile_version_id: str
    workflow_role: WorkflowRole


class EmployeeUpdateDisplay(StrictModel):
    display_name: Annotated[str, Field(min_length=1, max_length=100)]
    expected_version: Annotated[int, Field(ge=1)]


class EmployeeResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    department_id: str
    display_name: str
    normalized_display_name: str
    base_profile_version_id: str
    workflow_role: WorkflowRole
    status: EmployeeStatus
    created_at: datetime
    updated_at: datetime
    version: int


# ── Conversation ──────────────────────────────────────────────────────────


class ConversationResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    conversation_type: ConversationType
    department_id: str | None
    status: CompanyStatus
    created_at: datetime


# ── Message ───────────────────────────────────────────────────────────────


class MessageCreate(StrictModel):
    content: Annotated[str, Field(min_length=1)]
    task_id: str | None = None
    artifact_refs_json: str = "[]"


class SubmitUserMessageRequest(StrictModel):
    company_id: str
    conversation_id: str
    content: Annotated[str, Field(min_length=1)]
    target_task_id: str | None = None
    supersedes_task_id: str | None = None


class SubmitUserMessageResponse(StrictModel):
    message_id: str
    company_task_id: str
    task_status: Literal["draft", "revision_requested"]
    intake_mode: Literal["new_task", "plan_revision", "superseding_task"]
    analysis_queued: Literal[True]


class MessageResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    conversation_id: str
    task_id: str | None
    source_event_id: str
    sender_type: str
    sender_employee_id: str | None
    message_type: str
    content: str
    artifact_refs_json: str
    created_at: datetime


# ── DomainEvent ───────────────────────────────────────────────────────────


class DomainEventResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    row_sequence: int
    event_id: str
    company_id: str
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    event_type: str
    payload_json: str
    trace_id: str
    occurred_at: datetime


# ── CompanyTask ───────────────────────────────────────────────────────────


class CompanyTaskCreate(StrictModel):
    title: Annotated[str, Field(min_length=1)]


class CompanyTaskResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    supersedes_task_id: str | None
    company_conversation_id: str
    user_message_event_id: str
    title: str
    status: CompanyTaskStatus
    resume_state: str | None
    active_plan_id: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: str | None
    version: int


class CompanyTaskUpdate(StrictModel):
    expected_version: Annotated[int, Field(ge=1)]


# ── CompanyPlanVersion ────────────────────────────────────────────────────


class PlanConfirm(StrictModel):
    plan_id: str
    version_number: int
    content_sha256: str


class PlanVersionResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_task_id: str
    company_id: str
    version_number: int
    canonical_json: str
    content_sha256: str
    generated_by_run_id: str
    status: PlanVersionStatus
    created_at: datetime
    confirmed_at: str | None


# ── TaskContextSnapshot ───────────────────────────────────────────────────


class TaskContextSnapshotResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_task_id: str
    company_id: str
    company_revision_id: str
    plan_version_id: str
    department_revision_map_json: str
    catalog_release_id: str
    content_sha256: str
    created_at: datetime


# ── DepartmentTask ────────────────────────────────────────────────────────


class DepartmentTaskCreate(StrictModel):
    department_id: str
    stage_key: str
    objective: str
    deliverables_json: str = "[]"
    acceptance_criteria_json: str = "[]"


class DepartmentTaskResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    company_task_id: str
    department_id: str
    stage_key: str
    objective: str
    deliverables_json: str
    acceptance_criteria_json: str
    status: DepartmentTaskStatus
    resume_state: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: str | None
    version: int


# ── EmployeeTask ──────────────────────────────────────────────────────────


class EmployeeTaskCreate(StrictModel):
    employee_id: str
    task_kind: TaskKind
    objective: str
    acceptance_criteria_json: str = "[]"


class EmployeeTaskResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    department_task_id: str
    employee_id: str
    task_kind: TaskKind
    objective: str
    acceptance_criteria_json: str
    status: EmployeeTaskStatus
    resume_state: str | None
    created_at: datetime
    updated_at: datetime
    version: int


# ── EmployeeBaseProfile ───────────────────────────────────────────────────


class EmployeeBaseProfileResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    normalized_name: str
    description: str
    current_version_id: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    version: int


class EmployeeBaseProfileVersionResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    version_number: int
    name: str
    description: str
    profile_type: ProfileType
    runtime_binding_json: str
    system_prompt: str
    capability_tags_json: str
    tool_policy_json: str
    timeout_seconds: int
    max_retries: int
    workspace_policy: str
    catalog_release_id: str
    content_sha256: str
    status: ProfileVersionStatus
    created_at: datetime
    published_at: str | None


class ProfileSkillBindingResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    profile_version_id: str
    skill_id: str
    skill_version_id: str
    skill_version: str
    package_sha256: str
    load_order: int


# ── AgentRun ──────────────────────────────────────────────────────────────


class AgentRunResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    company_task_id: str
    department_task_id: str | None
    employee_task_id: str | None
    work_item_id: str
    employee_id: str
    conversation_id: str
    availability_snapshot_id: str
    execution_snapshot_id: str
    run_purpose: RunPurpose
    adapter_type: AdapterType
    native_session_id: str | None
    process_pid: int | None
    process_group_id: int | None
    process_started_at: str | None
    run_spec_json: str
    run_spec_sha256: str
    status: AgentRunStatus
    resume_state: str | None
    attempt: int
    started_at: str | None
    completed_at: str | None
    exit_code: int | None
    failure_code: str | None
    created_at: datetime
    updated_at: datetime
    version: int


class AgentRunEventResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    event_id: str
    sequence: int
    event_type: str
    payload_json: str
    native_event_json: str | None
    trace_id: str
    occurred_at: datetime


# ── Runtime Queue & Lease ─────────────────────────────────────────────────


class RuntimeQueueResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    work_item_type: WorkItemType
    work_item_id: str
    job_id: str
    run_id: str | None
    priority: QueuePriority
    status: QueueItemStatus
    queued_at: datetime
    leased_at: str | None


class RuntimeLeaseResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    queue_id: str
    job_id: str
    run_id: str | None
    employee_id: str | None
    company_id: str
    conversation_id: str | None
    acquired_at: datetime
    heartbeat_at: datetime
    expires_at: datetime


# ── Checkpoint ────────────────────────────────────────────────────────────


class CheckpointResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    sequence: int
    boundary_type: str
    storage_type: CheckpointStorageType
    compressed_blob: bytes | None
    file_path: str | None
    uncompressed_size: int
    sha256: str
    created_at: datetime


# ── ToolExecution ─────────────────────────────────────────────────────────


class ToolExecutionResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    tool_call_id: str
    tool_name: str
    input_json: str
    input_sha256: str
    status: ToolExecutionStatus
    result_json: str | None
    result_sha256: str | None
    approval_id: str | None
    started_at: str | None
    completed_at: str | None


# ── HumanApproval ─────────────────────────────────────────────────────────


class HumanApprovalResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    run_id: str
    approval_type: ApprovalType
    target_json: str
    target_sha256: str
    status: ApprovalStatus
    requested_at: datetime
    expires_at: datetime
    resolved_at: str | None
    consumed_at: str | None
    version: int


# ── VerificationResult ────────────────────────────────────────────────────


class VerificationResultResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    run_id: str
    round_number: int
    command_argv_json: str
    exit_code: int
    stdout_artifact_id: str | None
    stderr_artifact_id: str | None
    status: VerificationStatus
    started_at: datetime
    completed_at: datetime


# ── Artifact ──────────────────────────────────────────────────────────────


class ArtifactCreate(StrictModel):
    company_task_id: str
    department_task_id: str | None = None
    employee_task_id: str | None = None
    artifact_type: ArtifactType
    logical_name: str
    object_sha256: str
    object_size: int
    media_type: str
    metadata_json: str = "{}"
    supersedes_artifact_id: str | None = None
    created_by_type: CreatedByType
    created_by_run_id: str | None = None


class ArtifactResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    company_task_id: str
    department_task_id: str | None
    employee_task_id: str | None
    artifact_type: ArtifactType
    logical_name: str
    object_sha256: str
    object_size: int
    media_type: str
    metadata_json: str
    supersedes_artifact_id: str | None
    created_by_type: CreatedByType
    created_by_run_id: str | None
    created_at: datetime


# ── Review ────────────────────────────────────────────────────────────────


class ReviewAssignmentResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    artifact_id: str
    reviewer_employee_id: str
    review_round: int
    reviewed_sha256: str
    status: ReviewAssignmentStatus
    assigned_at: datetime
    submitted_at: str | None


class ReviewReportResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    assignment_id: str
    reviewer_run_id: str
    verdict: ReviewVerdict
    report_artifact_id: str
    created_at: datetime


class ReviewIssueResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    review_report_id: str
    severity: ReviewIssueSeverity
    category: str
    description: str
    expected: str
    actual: str
    suggested_fix: str
    evidence_refs_json: str
    status: ReviewIssueStatus
    assignee_employee_id: str | None
    verifier_employee_id: str | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
    version: int


# ── WorkspaceGrant & TaskWorkspace ────────────────────────────────────────


class WorkspaceGrantCreate(StrictModel):
    normalized_path: str
    security_bookmark: bytes
    path_type: PathType


class WorkspaceGrantResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    normalized_path: str
    security_bookmark: bytes
    path_type: PathType
    status: WorkspaceGrantStatus
    created_at: datetime
    last_resolved_at: str | None


class TaskWorkspaceResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    company_task_id: str
    workspace_grant_id: str
    repository_root: str
    baseline_commit_sha: str
    user_branch_name: str
    integration_branch_name: str
    integration_worktree_path: str
    status: TaskWorkspaceStatus
    applied_commit_sha: str | None
    cleaned_at: str | None
    created_at: datetime
    updated_at: datetime
    version: int


# ── Knowledge ─────────────────────────────────────────────────────────────


class KnowledgeItemCreate(StrictModel):
    title: Annotated[str, Field(min_length=1)]
    content: Annotated[str, Field(min_length=1)]
    visibility: KnowledgeVisibility
    department_id: str | None = None
    task_id: str | None = None
    owner_employee_id: str | None = None
    source_artifact_id: str | None = None
    source_message_event_id: str | None = None

    @model_validator(mode="after")
    def validate_source_and_scope(self) -> KnowledgeItemCreate:
        if (self.source_artifact_id is None) == (
            self.source_message_event_id is None
        ):
            raise ValueError("exactly one knowledge source is required")
        scope = (
            self.department_id,
            self.task_id,
            self.owner_employee_id,
        )
        allowed = {
            KnowledgeVisibility.COMPANY: (None, None, None),
            KnowledgeVisibility.DEPARTMENT: (self.department_id, None, None),
            KnowledgeVisibility.TASK: (None, self.task_id, None),
            KnowledgeVisibility.PRIVATE: (None, None, self.owner_employee_id),
        }
        expected = allowed[self.visibility]
        if scope != expected or (
            self.visibility is not KnowledgeVisibility.COMPANY
            and all(value is None for value in expected)
        ):
            raise ValueError("knowledge visibility scope is invalid")
        return self


class KnowledgeItemResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    source_artifact_id: str | None
    source_message_event_id: str | None
    owner_employee_id: str | None
    department_id: str | None
    task_id: str | None
    visibility: KnowledgeVisibility
    title: str
    content: str
    content_sha256: str
    embedding_generation_id: str | None
    created_at: datetime
    version: int


class EmbeddingGenerationResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    model_key: str
    vector_dimension: int
    source_event_sequence: int
    status: EmbeddingStatus
    created_at: datetime
    activated_at: str | None


# ── CatalogCache ──────────────────────────────────────────────────────────


class CatalogCacheReleaseResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    release_id: str
    release_sequence: int
    manifest_json: str
    manifest_sha256: str
    signature: str
    signing_key_id: str
    status: CatalogCacheReleaseStatus
    downloaded_at: datetime
    activated_at: str | None


class InstalledSkillVersionResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    skill_version_id: str
    skill_id: str
    version: str
    package_path: str
    package_sha256: str
    catalog_release_id: str
    status: InstalledSkillStatus
    installed_at: datetime


# ── BackupRecord ──────────────────────────────────────────────────────────


class BackupRecordResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    backup_type: BackupType
    archive_path: str
    archive_size: int
    archive_sha256: str
    manifest_json: str
    status: BackupStatus
    created_at: datetime
    completed_at: str | None
    error_code: str | None


# ── AuditLog ──────────────────────────────────────────────────────────────


class AuditLogResponse(StrictModel):
    model_config = ConfigDict(from_attributes=True)

    row_sequence: int
    id: str
    company_id: str | None
    actor_type: AuditActorType
    actor_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: AuditOutcome
    detail_json: str
    trace_id: str
    created_at: datetime


# ── 分页 ──────────────────────────────────────────────────────────────────


class PaginationParams(StrictModel):
    cursor: str | None = None
    limit: Annotated[int, Field(default=50, ge=1, le=200)]


class PaginatedResponse(StrictModel):
    items: list[object] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


# ── RPC Idempotency ───────────────────────────────────────────────────────


class IdempotencyKey(StrictModel):
    idempotency_key: str


# ── RPC command/query params ──────────────────────────────────────────────


class ScopedGetRequest(StrictModel):
    id: str
    company_id: str


class ScopedListRequest(StrictModel):
    company_id: str
    filter: dict[str, object] = Field(default_factory=dict)
    cursor: str | None = None
    limit: Annotated[int, Field(default=50, ge=1, le=200)]


class CompanyListRequest(StrictModel):
    filter: dict[str, object] = Field(default_factory=dict)
    cursor: str | None = None
    limit: Annotated[int, Field(default=50, ge=1, le=200)]


class CompanyArchiveRequest(StrictModel):
    company_id: str
    expected_version: Annotated[int, Field(ge=1)]


class CompanyUpdateRequest(CompanyUpdate):
    company_id: str


class DepartmentCreateRequest(DepartmentCreate):
    company_id: str


class DepartmentUpdateRequest(DepartmentUpdate):
    company_id: str
    department_id: str


class DepartmentSetLeaderRequest(StrictModel):
    company_id: str
    department_id: str
    employee_id: str
    expected_version: Annotated[int, Field(ge=1)]


class EmployeeCreateRequest(EmployeeCreate):
    company_id: str
    department_id: str


class EmployeeUpdateDisplayRequest(EmployeeUpdateDisplay):
    company_id: str
    employee_id: str


class EmployeeUpdateBaseProfileRequest(StrictModel):
    company_id: str
    employee_id: str
    base_profile_version_id: str
    expected_version: Annotated[int, Field(ge=1)]


class EmployeeUpdateStatusRequest(StrictModel):
    company_id: str
    employee_id: str
    status: EmployeeStatus
    expected_version: Annotated[int, Field(ge=1)]


class ListMessagesRequest(StrictModel):
    company_id: str
    conversation_id: str
    cursor: str | None = None
    limit: Annotated[int, Field(default=50, ge=1, le=200)]


class DepartmentConversationRequest(StrictModel):
    company_id: str
    department_id: str
