"""组织模型。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Company:
    company_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    status: str = "initializing"
    root_department_id: Optional[str] = None
    default_provider_policy: dict = field(default_factory=dict)
    default_budget_policy: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    version: int = 1


@dataclass
class Department:
    department_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    parent_department_id: Optional[str] = None
    name: str = ""
    description: str = ""
    responsibilities: list[str] = field(default_factory=list)
    leader_employee_id: Optional[str] = None
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    version: int = 1


@dataclass
class EmployeeTemplate:
    template_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    template_scope: str = "company"
    company_id: Optional[str] = None
    provider_type: str = "openai"
    provider_id: str = "openai"
    model: str = "gpt-4"
    capability_id: str = ""
    capability_version: int = 0
    capability_snapshot: dict = field(default_factory=dict)
    default_role: str = ""
    version: int = 1
    status: str = "draft"


@dataclass
class Employee:
    employee_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    department_id: str = ""
    template_id: str = ""
    capability_snapshot: dict = field(default_factory=dict)
    name: str = ""
    role_name: str = ""
    employee_type: str = "employee"
    reports_to_employee_id: Optional[str] = None
    stability_level: int = 5
    status: str = "created"
    session_transfer_state: str = "none"
    primary_session_thread_id: Optional[str] = None
    version: int = 1


@dataclass
class AccessGrant:
    grant_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    employee_id: str = ""
    target_type: str = ""
    target_id: str = ""
    permission: str = ""
    status: str = "active"
    expires_at: str = ""
    approved_by: str = ""
    version: int = 1


@dataclass
class EmployeeDrain:
    drain_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    employee_id: str = ""
    operation: str = ""
    target_department_id: Optional[str] = None
    status: str = "active"
    intervention_id: Optional[str] = None
    timeout_seconds: int = 600
