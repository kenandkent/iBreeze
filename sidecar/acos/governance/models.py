"""治理领域模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class BudgetPolicy:
    policy_id: str = ""
    company_id: str = ""
    name: str = ""
    monthly_limit: int = 0
    per_task_limit: int = 0
    currency: str = "USD"
    on_budget_exceeded: str = "pause"
    version: int = 1


@dataclass
class Approval:
    approval_id: str = ""
    company_id: str = ""
    task_id: Optional[str] = None
    node_id: Optional[str] = None
    run_id: Optional[str] = None
    generation_id: Optional[str] = None
    employee_id: str = ""
    approval_type: str = ""
    status: str = "pending"
    target_hash: Optional[str] = None
    target_snapshot: Optional[str] = None
    risk_reason: Optional[str] = None
    requested_by: str = ""
    approved_by: Optional[str] = None
    resolution: Optional[str] = None
    reason: Optional[str] = None
    expiry: Optional[str] = None
    # 预算审批绑定字段
    currency: Optional[str] = None
    current_limit_micros: Optional[int] = None
    requested_limit_micros: Optional[int] = None
    requested_delta_micros: Optional[int] = None
    usage_watermark_micros: int = 0
    version: int = 1


@dataclass
class ApprovalType:
    approval_type_id: str = ""
    company_id: str = ""
    name: str = ""
    category: str = "other"
    description: Optional[str] = None
    requires_risk_summary: bool = False
    status: str = "active"
    version: int = 1


@dataclass
class ApprovalRequest:
    request_id: str = ""
    company_id: str = ""
    approval_type: str = ""
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    node_id: Optional[str] = None
    generation_id: Optional[str] = None
    target_ref: str = ""
    target_skill: Optional[str] = None
    risk_summary: Optional[str] = None
    target_hash: Optional[str] = None
    target_snapshot: Optional[str] = None
    requested_by: str = ""
    linked_approval_id: Optional[str] = None
    status: str = "pending"
    expiry: Optional[str] = None
    version: int = 1


@dataclass
class BudgetRevisionLock:
    lock_id: str = ""
    company_id: str = ""
    task_id: str = ""
    currency: str = ""
    run_id: Optional[str] = None
    current_limit_micros: int = 0
    requested_limit_micros: int = 0
    requested_delta_micros: int = 0
    usage_watermark_micros: int = 0
    request_hash: str = ""
    linked_approval_id: str = ""
    status: str = "active"


@dataclass
class UsageRecord:
    record_id: str = ""
    company_id: str = ""
    task_id: Optional[str] = None
    employee_id: Optional[str] = None
    provider_id: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_micros: int = 0
    currency: str = "USD"
