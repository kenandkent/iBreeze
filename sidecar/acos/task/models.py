"""任务工作流数据模型与仓储（P9-T1/T1a/T1b）。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ── 状态机（对照 §10.2 / §10.2.2） ──

TASK_TRANSITIONS: dict[str, set[str]] = {
    "created": {"planning", "running", "cancelled", "cancelling"},
    "planning": {"running", "cancelled", "cancelling"},
    "running": {"paused", "completed", "failed", "cancelled", "cancelling"},
    "paused": {"running", "cancelled", "cancelling"},
    "cancelling": {"cancelled"},
    "completed": set(),
    "failed": {"running", "cancelling"},
    "cancelled": set(),
}

NODE_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"ready", "cancelled"},
    "ready": {"running", "cancelled", "waiting_approval"},
    "running": {"completed", "failed", "waiting_approval", "dead_letter", "cancelled"},
    "waiting_approval": {"running", "cancelled", "dead_letter"},
    "completed": set(),
    "failed": {"running", "dead_letter", "cancelled"},
    "dead_letter": {"running", "cancelled"},
    "cancelled": set(),
}

RUN_TRANSITIONS: dict[str, set[str]] = {
    "created": {"waiting_backend", "cancelled"},
    "waiting_backend": {"running", "cancelled"},
    "running": {"succeeded", "failed", "waiting_approval", "cancelled"},
    "waiting_approval": {"running", "cancelled", "failed"},
    "succeeded": set(),
    "failed": {"running", "cancelled"},
    "cancelled": set(),
}

GENERATION_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"planning", "rejected"},
    "planning": {"validated", "rejected", "superseded"},
    "validated": {"approved", "rejected", "superseded"},
    "approved": {"active", "superseded"},
    "active": {"superseded"},
    "rejected": set(),
    "superseded": set(),
}


@dataclass
class Task:
    task_id: str
    company_id: str
    title: str
    status: str = "created"
    department_id: Optional[str] = None
    created_by_employee_id: Optional[str] = None
    description: str = ""
    priority: int = 5
    manager_employee_id: Optional[str] = None
    manager_scope: str = "dept"
    active_generation_id: Optional[str] = None
    assigned_backend_id: Optional[str] = None
    budget_currency: Optional[str] = None
    budget_limit_micros: Optional[int] = None
    token_limit: Optional[int] = None
    goal: Optional[str] = None
    acceptance: Optional[str] = None
    inputs_json: Optional[str] = None
    deadline_at: Optional[str] = None
    version: int = 1


@dataclass
class TaskNode:
    node_id: str
    task_id: str
    company_id: str
    node_type: str = "agent_step"
    status: str = "pending"
    assignee_employee_id: Optional[str] = None
    generation_id: Optional[str] = None
    backend_id: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)
    workspace_strategy: Optional[str] = None
    outputs_schema: Optional[str] = None
    goal: Optional[str] = None
    max_concurrency: int = 1
    timeout_seconds: Optional[int] = None
    version: int = 1


@dataclass
class TaskAssignment:
    assignment_id: str
    task_id: str
    employee_id: str
    company_id: str
    node_id: Optional[str] = None
    generation_id: Optional[str] = None
    run_id: Optional[str] = None
    attempt: int = 1
    assignment_role: str = "worker"
    department_id_at_assignment: Optional[str] = None
    granted_by: Optional[str] = None
    reason: Optional[str] = None
    active_from: Optional[str] = None
    active_until: Optional[str] = None
    status: str = "active"
    version: int = 1


@dataclass
class PlanGeneration:
    generation_id: str
    task_id: str
    company_id: str
    plan_hash: str
    generation_no: int = 1
    status: str = "draft"
    dag_json: str = "[]"
    risk_summary: Optional[str] = None
    created_by_employee_id: Optional[str] = None
    parent_generation_id: Optional[str] = None
    version: int = 1


@dataclass
class Checkpoint:
    checkpoint_id: str
    company_id: str
    task_id: str
    task_cursor: int
    checksum: str
    plan_hash: Optional[str] = None
    context_hash: Optional[str] = None
    generation_id: Optional[str] = None
    run_id: Optional[str] = None
    event_offset: int = 0
    executor_state: Optional[str] = None
