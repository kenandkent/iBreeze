"""任务工作流模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Task:
    task_id: str = ""
    company_id: str = ""
    department_id: Optional[str] = None
    created_by_employee_id: Optional[str] = None
    title: str = ""
    description: str = ""
    priority: int = 5
    status: str = "created"
    assigned_backend_id: Optional[str] = None
    assigned_capability_id: Optional[str] = None
    assigned_capability_version: Optional[int] = None
    assigned_capability_checksum: Optional[str] = None
    deadline_at: Optional[str] = None
    version: int = 1


@dataclass
class TaskNode:
    node_id: str = ""
    task_id: str = ""
    company_id: str = ""
    node_type: str = "agent_step"
    status: str = "pending"
    assignee_employee_id: Optional[str] = None
    max_concurrency: int = 1
    timeout_seconds: Optional[int] = None
    version: int = 1


@dataclass
class TaskRun:
    run_id: str = ""
    node_id: str = ""
    task_id: str = ""
    company_id: str = ""
    backend_id: Optional[str] = None
    lease_id: Optional[str] = None
    status: str = "pending"
    capability_checksum: Optional[str] = None
    version: int = 1


@dataclass
class TaskAssignment:
    assignment_id: str = ""
    task_id: str = ""
    node_id: Optional[str] = None
    employee_id: str = ""
    company_id: str = ""
    role: str = "assignee"
    status: str = "active"
