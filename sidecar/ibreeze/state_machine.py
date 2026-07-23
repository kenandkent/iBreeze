"""状态机：不可变迁移表 + 泛型状态转换函数。

对齐设计文档 H.7 全部状态迁移表。
禁止直接设置任意状态——所有状态变更必须通过 transition() 函数。
"""
from __future__ import annotations

from enum import Enum
from typing import TypeVar

S = TypeVar("S", bound=Enum)


class StateTransitionError(Exception):
    """非法状态迁移。"""

    def __init__(self, entity: str, current: str, target: str) -> None:
        self.entity = entity
        self.current = current
        self.target = target
        super().__init__(
            f"STATE_TRANSITION_INVALID: {entity} cannot move from "
            f"'{current}' to '{target}'"
        )


# ── CompanyTask 状态迁移表（H.7）─────────────────────────────────────────

class CompanyTaskState(str, Enum):
    DRAFT = "draft"
    ANALYZING = "analyzing"
    AWAITING_USER_CONFIRMATION = "awaiting_user_confirmation"
    REVISION_REQUESTED = "revision_requested"
    APPROVED = "approved"
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


_COMPANY_TASK_TRANSITIONS: dict[CompanyTaskState, frozenset[CompanyTaskState]] = {
    CompanyTaskState.DRAFT: frozenset({
        CompanyTaskState.ANALYZING,
        CompanyTaskState.CANCELLING,
    }),
    CompanyTaskState.ANALYZING: frozenset({
        CompanyTaskState.AWAITING_USER_CONFIRMATION,
        CompanyTaskState.WAITING_RESOURCE,
        CompanyTaskState.CANCELLING,
        CompanyTaskState.FAILED,
    }),
    CompanyTaskState.AWAITING_USER_CONFIRMATION: frozenset({
        CompanyTaskState.APPROVED,
        CompanyTaskState.REVISION_REQUESTED,
        CompanyTaskState.REJECTED,
        CompanyTaskState.CANCELLING,
    }),
    CompanyTaskState.REVISION_REQUESTED: frozenset({
        CompanyTaskState.ANALYZING,
        CompanyTaskState.REJECTED,
        CompanyTaskState.CANCELLING,
    }),
    CompanyTaskState.APPROVED: frozenset({
        CompanyTaskState.DISPATCHING,
        CompanyTaskState.CANCELLING,
    }),
    CompanyTaskState.DISPATCHING: frozenset({
        CompanyTaskState.CHECKING_RESOURCES,
        CompanyTaskState.WAITING_DEPENDENCY,
        CompanyTaskState.WAITING_RESOURCE,
        CompanyTaskState.CANCELLING,
        CompanyTaskState.FAILED,
    }),
    CompanyTaskState.CHECKING_RESOURCES: frozenset({
        CompanyTaskState.EXECUTING,
        CompanyTaskState.WAITING_DEPENDENCY,
        CompanyTaskState.WAITING_RESOURCE,
        CompanyTaskState.WAITING_PERMISSION,
        CompanyTaskState.CANCELLING,
        CompanyTaskState.FAILED,
    }),
    CompanyTaskState.EXECUTING: frozenset({
        CompanyTaskState.REVIEWING,
        CompanyTaskState.WAITING_DEPENDENCY,
        CompanyTaskState.WAITING_RESOURCE,
        CompanyTaskState.WAITING_PERMISSION,
        CompanyTaskState.PAUSED,
        CompanyTaskState.CANCELLING,
        CompanyTaskState.FAILED,
    }),
    CompanyTaskState.REVIEWING: frozenset({
        CompanyTaskState.FIXING,
        CompanyTaskState.FINAL_REVIEW,
        CompanyTaskState.WAITING_RESOURCE,
        CompanyTaskState.WAITING_PERMISSION,
        CompanyTaskState.PAUSED,
        CompanyTaskState.CANCELLING,
        CompanyTaskState.FAILED,
    }),
    CompanyTaskState.FIXING: frozenset({
        CompanyTaskState.REVIEWING,
        CompanyTaskState.WAITING_RESOURCE,
        CompanyTaskState.WAITING_PERMISSION,
        CompanyTaskState.PAUSED,
        CompanyTaskState.CANCELLING,
        CompanyTaskState.FAILED,
    }),
    CompanyTaskState.FINAL_REVIEW: frozenset({
        CompanyTaskState.COMPLETED,
        CompanyTaskState.FIXING,
        CompanyTaskState.WAITING_RESOURCE,
        CompanyTaskState.WAITING_PERMISSION,
        CompanyTaskState.PAUSED,
        CompanyTaskState.CANCELLING,
        CompanyTaskState.FAILED,
    }),
    CompanyTaskState.WAITING_DEPENDENCY: frozenset({
        CompanyTaskState.CANCELLING,
        CompanyTaskState.FAILED,
    }),
    CompanyTaskState.WAITING_RESOURCE: frozenset({
        CompanyTaskState.CANCELLING,
        CompanyTaskState.FAILED,
    }),
    CompanyTaskState.WAITING_PERMISSION: frozenset({
        CompanyTaskState.CANCELLING,
        CompanyTaskState.FAILED,
    }),
    CompanyTaskState.PAUSED: frozenset({
        CompanyTaskState.CANCELLING,
        CompanyTaskState.FAILED,
    }),
    CompanyTaskState.CANCELLING: frozenset({
        CompanyTaskState.CANCELLED,
        CompanyTaskState.FAILED,
    }),
    CompanyTaskState.REJECTED: frozenset(),
    CompanyTaskState.COMPLETED: frozenset(),
    CompanyTaskState.CANCELLED: frozenset(),
    CompanyTaskState.FAILED: frozenset(),
}


# ── DepartmentTask 状态迁移表（H.7）──────────────────────────────────────

class DepartmentTaskState(str, Enum):
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


_DEPARTMENT_TASK_TRANSITIONS: dict[
    DepartmentTaskState, frozenset[DepartmentTaskState]
] = {
    DepartmentTaskState.DRAFT: frozenset({
        DepartmentTaskState.CHECKING_RESOURCES,
        DepartmentTaskState.CANCELLED,
    }),
    DepartmentTaskState.CHECKING_RESOURCES: frozenset({
        DepartmentTaskState.READY,
        DepartmentTaskState.WAITING_RESOURCE,
        DepartmentTaskState.WAITING_PERMISSION,
        DepartmentTaskState.CANCELLED,
        DepartmentTaskState.FAILED,
    }),
    DepartmentTaskState.READY: frozenset({
        DepartmentTaskState.EXECUTING,
        DepartmentTaskState.WAITING_DEPENDENCY,
        DepartmentTaskState.WAITING_RESOURCE,
        DepartmentTaskState.WAITING_PERMISSION,
        DepartmentTaskState.CANCELLED,
        DepartmentTaskState.FAILED,
    }),
    DepartmentTaskState.EXECUTING: frozenset({
        DepartmentTaskState.REVIEWING,
        DepartmentTaskState.WAITING_RESOURCE,
        DepartmentTaskState.WAITING_PERMISSION,
        DepartmentTaskState.CANCELLED,
        DepartmentTaskState.FAILED,
    }),
    DepartmentTaskState.REVIEWING: frozenset({
        DepartmentTaskState.FIXING,
        DepartmentTaskState.COMPLETED,
        DepartmentTaskState.WAITING_RESOURCE,
        DepartmentTaskState.WAITING_PERMISSION,
        DepartmentTaskState.CANCELLED,
        DepartmentTaskState.FAILED,
    }),
    DepartmentTaskState.FIXING: frozenset({
        DepartmentTaskState.REVIEWING,
        DepartmentTaskState.WAITING_RESOURCE,
        DepartmentTaskState.WAITING_PERMISSION,
        DepartmentTaskState.CANCELLED,
        DepartmentTaskState.FAILED,
    }),
    DepartmentTaskState.WAITING_DEPENDENCY: frozenset({
        DepartmentTaskState.CANCELLED,
        DepartmentTaskState.FAILED,
    }),
    DepartmentTaskState.WAITING_RESOURCE: frozenset({
        DepartmentTaskState.CANCELLED,
        DepartmentTaskState.FAILED,
    }),
    DepartmentTaskState.WAITING_PERMISSION: frozenset({
        DepartmentTaskState.CANCELLED,
        DepartmentTaskState.FAILED,
    }),
    DepartmentTaskState.COMPLETED: frozenset(),
    DepartmentTaskState.CANCELLED: frozenset(),
    DepartmentTaskState.FAILED: frozenset(),
}


# ── EmployeeTask 状态迁移表（H.7）────────────────────────────────────────

class EmployeeTaskState(str, Enum):
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


_EMPLOYEE_TASK_TRANSITIONS: dict[
    EmployeeTaskState, frozenset[EmployeeTaskState]
] = {
    EmployeeTaskState.ASSIGNED: frozenset({
        EmployeeTaskState.READY,
        EmployeeTaskState.WAITING_RESOURCE,
        EmployeeTaskState.CANCELLED,
        EmployeeTaskState.FAILED,
    }),
    EmployeeTaskState.READY: frozenset({
        EmployeeTaskState.RUNNING,
        EmployeeTaskState.WAITING_RESOURCE,
        EmployeeTaskState.CANCELLED,
        EmployeeTaskState.FAILED,
    }),
    EmployeeTaskState.RUNNING: frozenset({
        EmployeeTaskState.SUBMITTED,
        EmployeeTaskState.WAITING_RESOURCE,
        EmployeeTaskState.CANCELLED,
        EmployeeTaskState.FAILED,
    }),
    EmployeeTaskState.SUBMITTED: frozenset({
        EmployeeTaskState.PEER_REVIEWING,
        EmployeeTaskState.FAILED,
    }),
    EmployeeTaskState.PEER_REVIEWING: frozenset({
        EmployeeTaskState.CHANGES_REQUESTED,
        EmployeeTaskState.ACCEPTED,
        EmployeeTaskState.FAILED,
    }),
    EmployeeTaskState.CHANGES_REQUESTED: frozenset({
        EmployeeTaskState.READY,
        EmployeeTaskState.WAITING_RESOURCE,
        EmployeeTaskState.CANCELLED,
        EmployeeTaskState.FAILED,
    }),
    EmployeeTaskState.WAITING_RESOURCE: frozenset({
        EmployeeTaskState.CANCELLED,
        EmployeeTaskState.FAILED,
    }),
    EmployeeTaskState.ACCEPTED: frozenset(),
    EmployeeTaskState.CANCELLED: frozenset(),
    EmployeeTaskState.FAILED: frozenset(),
}


# ── AgentRun 状态迁移表（H.7）────────────────────────────────────────────

class AgentRunState(str, Enum):
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


_AGENT_RUN_TRANSITIONS: dict[AgentRunState, frozenset[AgentRunState]] = {
    AgentRunState.QUEUED: frozenset({
        AgentRunState.PROBING,
        AgentRunState.CANCELLED,
    }),
    AgentRunState.PROBING: frozenset({
        AgentRunState.STARTING,
        AgentRunState.WAITING_RESOURCE,
        AgentRunState.CANCELLED,
        AgentRunState.FAILED,
    }),
    AgentRunState.STARTING: frozenset({
        AgentRunState.RUNNING,
        AgentRunState.RETRYING,
        AgentRunState.WAITING_RESOURCE,
        AgentRunState.CANCELLED,
        AgentRunState.TIMED_OUT,
        AgentRunState.FAILED,
    }),
    AgentRunState.RUNNING: frozenset({
        AgentRunState.WAITING_APPROVAL,
        AgentRunState.VERIFYING,
        AgentRunState.RETRYING,
        AgentRunState.WAITING_RESOURCE,
        AgentRunState.CANCELLED,
        AgentRunState.TIMED_OUT,
        AgentRunState.FAILED,
        AgentRunState.LOST,
    }),
    AgentRunState.WAITING_APPROVAL: frozenset({
        AgentRunState.CANCELLED,
        AgentRunState.TIMED_OUT,
        AgentRunState.FAILED,
    }),
    AgentRunState.WAITING_RESOURCE: frozenset({
        AgentRunState.CANCELLED,
        AgentRunState.TIMED_OUT,
        AgentRunState.FAILED,
    }),
    AgentRunState.VERIFYING: frozenset({
        AgentRunState.SUCCEEDED,
        AgentRunState.RETRYING,
        AgentRunState.WAITING_APPROVAL,
        AgentRunState.WAITING_RESOURCE,
        AgentRunState.CANCELLED,
        AgentRunState.TIMED_OUT,
        AgentRunState.FAILED,
    }),
    AgentRunState.RETRYING: frozenset({
        AgentRunState.STARTING,
        AgentRunState.CANCELLED,
        AgentRunState.TIMED_OUT,
        AgentRunState.FAILED,
    }),
    AgentRunState.LOST: frozenset({
        AgentRunState.RETRYING,
        AgentRunState.WAITING_APPROVAL,
        AgentRunState.CANCELLED,
        AgentRunState.FAILED,
    }),
    AgentRunState.SUCCEEDED: frozenset(),
    AgentRunState.CANCELLED: frozenset(),
    AgentRunState.TIMED_OUT: frozenset(),
    AgentRunState.FAILED: frozenset(),
}


# ── ReviewAssignment 状态迁移表（H.7）────────────────────────────────────

class ReviewAssignmentState(str, Enum):
    ASSIGNED = "assigned"
    IN_REVIEW = "in_review"
    SUBMITTED = "submitted"
    STALE = "stale"
    CANCELLED = "cancelled"


_REVIEW_ASSIGNMENT_TRANSITIONS: dict[
    ReviewAssignmentState, frozenset[ReviewAssignmentState]
] = {
    ReviewAssignmentState.ASSIGNED: frozenset({
        ReviewAssignmentState.IN_REVIEW,
        ReviewAssignmentState.STALE,
        ReviewAssignmentState.CANCELLED,
    }),
    ReviewAssignmentState.IN_REVIEW: frozenset({
        ReviewAssignmentState.SUBMITTED,
        ReviewAssignmentState.STALE,
        ReviewAssignmentState.CANCELLED,
    }),
    ReviewAssignmentState.SUBMITTED: frozenset({
        ReviewAssignmentState.STALE,
    }),
    ReviewAssignmentState.STALE: frozenset(),
    ReviewAssignmentState.CANCELLED: frozenset(),
}


# ── ReviewIssue 状态迁移表（H.7）─────────────────────────────────────────

class ReviewIssueState(str, Enum):
    OPEN = "open"
    FIXING = "fixing"
    RESOLVED = "resolved"
    VERIFIED = "verified"
    CLOSED = "closed"
    REJECTED = "rejected"


_REVIEW_ISSUE_TRANSITIONS: dict[ReviewIssueState, frozenset[ReviewIssueState]] = {
    ReviewIssueState.OPEN: frozenset({
        ReviewIssueState.FIXING,
        ReviewIssueState.REJECTED,
    }),
    ReviewIssueState.FIXING: frozenset({
        ReviewIssueState.RESOLVED,
    }),
    ReviewIssueState.RESOLVED: frozenset({
        ReviewIssueState.VERIFIED,
        ReviewIssueState.FIXING,
    }),
    ReviewIssueState.VERIFIED: frozenset({
        ReviewIssueState.CLOSED,
        ReviewIssueState.FIXING,
    }),
    ReviewIssueState.CLOSED: frozenset(),
    ReviewIssueState.REJECTED: frozenset(),
}


# ── CompanyPlanVersion 状态迁移表（H.7）─────────────────────────────────

class CompanyPlanVersionState(str, Enum):
    DRAFT = "draft"
    AWAITING_USER_CONFIRMATION = "awaiting_user_confirmation"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


_COMPANY_PLAN_VERSION_TRANSITIONS: dict[
    CompanyPlanVersionState, frozenset[CompanyPlanVersionState]
] = {
    CompanyPlanVersionState.DRAFT: frozenset({
        CompanyPlanVersionState.AWAITING_USER_CONFIRMATION,
        CompanyPlanVersionState.REJECTED,
    }),
    CompanyPlanVersionState.AWAITING_USER_CONFIRMATION: frozenset({
        CompanyPlanVersionState.APPROVED,
        CompanyPlanVersionState.SUPERSEDED,
        CompanyPlanVersionState.REJECTED,
    }),
    CompanyPlanVersionState.APPROVED: frozenset(),
    CompanyPlanVersionState.SUPERSEDED: frozenset(),
    CompanyPlanVersionState.REJECTED: frozenset(),
}


# ── TaskWorkspace 状态迁移表（H.7）──────────────────────────────────────

class TaskWorkspaceState(str, Enum):
    PREPARING = "preparing"
    ACTIVE = "active"
    READY_TO_APPLY = "ready_to_apply"
    APPLIED = "applied"
    ABANDONED = "abandoned"


_TASK_WORKSPACE_TRANSITIONS: dict[
    TaskWorkspaceState, frozenset[TaskWorkspaceState]
] = {
    TaskWorkspaceState.PREPARING: frozenset({
        TaskWorkspaceState.ACTIVE,
        TaskWorkspaceState.ABANDONED,
    }),
    TaskWorkspaceState.ACTIVE: frozenset({
        TaskWorkspaceState.READY_TO_APPLY,
        TaskWorkspaceState.ABANDONED,
    }),
    TaskWorkspaceState.READY_TO_APPLY: frozenset({
        TaskWorkspaceState.APPLIED,
        TaskWorkspaceState.ABANDONED,
    }),
    TaskWorkspaceState.APPLIED: frozenset(),
    TaskWorkspaceState.ABANDONED: frozenset(),
}


# ── HumanApproval 状态迁移表（H.7）──────────────────────────────────────

class HumanApprovalState(str, Enum):
    PENDING = "pending"
    ALLOWED = "allowed"
    DENIED = "denied"
    EXPIRED = "expired"
    CONSUMED = "consumed"


_HUMAN_APPROVAL_TRANSITIONS: dict[
    HumanApprovalState, frozenset[HumanApprovalState]
] = {
    HumanApprovalState.PENDING: frozenset({
        HumanApprovalState.ALLOWED,
        HumanApprovalState.DENIED,
        HumanApprovalState.EXPIRED,
    }),
    HumanApprovalState.ALLOWED: frozenset({
        HumanApprovalState.CONSUMED,
        HumanApprovalState.EXPIRED,
    }),
    HumanApprovalState.DENIED: frozenset(),
    HumanApprovalState.EXPIRED: frozenset(),
    HumanApprovalState.CONSUMED: frozenset(),
}


# ── 迁移表注册 ────────────────────────────────────────────────────────────

_TRANSITION_TABLES: dict[str, dict] = {
    "CompanyTask": _COMPANY_TASK_TRANSITIONS,
    "DepartmentTask": _DEPARTMENT_TASK_TRANSITIONS,
    "EmployeeTask": _EMPLOYEE_TASK_TRANSITIONS,
    "AgentRun": _AGENT_RUN_TRANSITIONS,
    "ReviewAssignment": _REVIEW_ASSIGNMENT_TRANSITIONS,
    "ReviewIssue": _REVIEW_ISSUE_TRANSITIONS,
    "CompanyPlanVersion": _COMPANY_PLAN_VERSION_TRANSITIONS,
    "TaskWorkspace": _TASK_WORKSPACE_TRANSITIONS,
    "HumanApproval": _HUMAN_APPROVAL_TRANSITIONS,
}


# ── 泛型状态转换函数 ──────────────────────────────────────────────────────

def is_terminal(entity: str, state: str) -> bool:
    """判断是否为终态（无出边）。"""
    table = _TRANSITION_TABLES.get(entity)
    if table is None:
        raise ValueError(f"Unknown entity type: {entity}")
    for s, targets in table.items():
        if s.value == state:
            return len(targets) == 0
    raise ValueError(f"Unknown state '{state}' for entity '{entity}'")


def can_transition(entity: str, current: str, target: str) -> bool:
    """检查是否允许从 current 迁移到 target。"""
    table = _TRANSITION_TABLES.get(entity)
    if table is None:
        raise ValueError(f"Unknown entity type: {entity}")
    for s, targets in table.items():
        if s.value == current:
            return any(t.value == target for t in targets)
    raise ValueError(f"Unknown state '{current}' for entity '{entity}'")


def get_allowed_targets(entity: str, current: str) -> frozenset[str]:
    """获取当前状态允许的目标状态集合。"""
    table = _TRANSITION_TABLES.get(entity)
    if table is None:
        raise ValueError(f"Unknown entity type: {entity}")
    for s, targets in table.items():
        if s.value == current:
            return frozenset(t.value for t in targets)
    raise ValueError(f"Unknown state '{current}' for entity '{entity}'")


def transition(
    entity: str,
    current: str,
    target: str,
    *,
    resume_state: str | None = None,
) -> str | None:
    """执行状态迁移校验。

    对于等待态 (waiting_*) 进入时，需传入 resume_state。
    对于离开等待态，返回 resume_state 供调用方清空。

    Returns:
        离开等待态时返回被清空的 resume_state 值，否则返回 None。

    Raises:
        StateTransitionError: 非法迁移。
    """
    if not can_transition(entity, current, target):
        raise StateTransitionError(entity, current, target)

    waiting_states = {
        "waiting_dependency",
        "waiting_resource",
        "waiting_permission",
        "paused",
        "waiting_approval",
    }

    if target in waiting_states:
        if resume_state is None:
            raise ValueError(
                f"resume_state required when entering waiting state '{target}'"
            )
        return None

    if current in waiting_states:
        return resume_state

    return None


def validate_resume_state(
    entity: str, current: str, resume_state: str | None
) -> None:
    """校验 resume_state 与当前等待态的一致性。"""
    waiting_states = {
        "waiting_dependency",
        "waiting_resource",
        "waiting_permission",
        "paused",
        "waiting_approval",
    }
    if current in waiting_states and resume_state is None:
        raise ValueError(
            f"resume_state required for entity '{entity}' in waiting state '{current}'"
        )
    if current not in waiting_states and resume_state is not None:
        raise ValueError(
            f"resume_state must be null for entity '{entity}' in non-waiting state '{current}'"
        )
