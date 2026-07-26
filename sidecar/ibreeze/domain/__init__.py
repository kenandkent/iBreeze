"""域事件注册表 — 所有业务事件的类型、版本、来源聚合的集中登记。

对齐设计文档 H.4 域事件体系:
- 每个事件以 event_type 标识, 格式: {aggregate_type}.{action}
- 所有事件写 domain_events 表 + outbox_events 表
- 不可变, 仅追加
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class DomainEventType(StrEnum):
    """所有业务域事件类型的枚举注册表。

    格式: {aggregate_type}.{action}
    """

    # ── Company ────────────────────────────────────────────────────────────
    COMPANY_CREATED = "company.created"
    COMPANY_RENAMED = "company.renamed"
    COMPANY_UPDATED = "company.updated"
    COMPANY_ARCHIVED = "company.archived"

    # ── Department ─────────────────────────────────────────────────────────
    DEPARTMENT_CREATED = "department.created"
    DEPARTMENT_UPDATED = "department.updated"
    DEPARTMENT_LEADER_CHANGED = "department.leader_changed"

    # ── Employee ───────────────────────────────────────────────────────────
    EMPLOYEE_CREATED = "employee.created"
    EMPLOYEE_UPDATED = "employee.updated"
    EMPLOYEE_STATUS_CHANGED = "employee.status_changed"
    EMPLOYEE_TRANSFERRED = "employee.transferred"

    # ── CompanyTask ────────────────────────────────────────────────────────
    COMPANY_TASK_CREATED = "company_task.created"
    COMPANY_TASK_REVISION_REQUESTED = "company_task.revision_requested"
    COMPANY_TASK_ANALYSIS_REQUESTED = "company_task.analysis.requested"
    COMPANY_TASK_ANALYZED = "company_task.analyzed"
    COMPANY_TASK_AWAITING_CONFIRMATION = "company_task.awaiting_confirmation"
    COMPANY_TASK_APPROVED = "company_task.approved"
    COMPANY_TASK_DISPATCHED = "company_task.dispatched"
    COMPANY_TASK_COMPLETED = "company_task.completed"
    COMPANY_TASK_CANCELLED = "company_task.cancelled"
    COMPANY_TASK_FAILED = "company_task.failed"
    COMPANY_TASK_PAUSED = "company_task.paused"
    COMPANY_TASK_RESUMED = "company_task.resumed"

    # ── Conversation ──────────────────────────────────────────────────────
    CONVERSATION_USER_MESSAGE_SUBMITTED = "conversation.user_message_submitted"
    CONVERSATION_EMPLOYEE_MESSAGE_SUBMITTED = "conversation.employee_message_submitted"

    # ── Plan ───────────────────────────────────────────────────────────────
    PLAN_GENERATED = "plan.generated"
    PLAN_AWAITING_CONFIRMATION = "plan.awaiting_confirmation"
    PLAN_APPROVED = "plan.approved"
    PLAN_REJECTED = "plan.rejected"
    PLAN_SUPERSEDED = "plan.superseded"

    # ── Review ─────────────────────────────────────────────────────────────
    REVIEW_ASSIGNMENT_CREATED = "review.assignment_created"
    REVIEW_STARTED = "review.started"
    REVIEW_SUBMITTED = "review.submitted"
    REVIEW_ISSUE_CREATED = "review.issue_created"
    REVIEW_ISSUE_RESOLVED = "review.issue_resolved"

    # ── AgentRun ───────────────────────────────────────────────────────────
    RUN_PROBING = "run.probing"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    RUN_TIMED_OUT = "run.timed_out"
    RUN_LOST = "run.lost"


@dataclass(frozen=True, slots=True)
class DomainEventSpec:
    """域事件定义: 类型、来源聚合、描述。"""

    event_type: DomainEventType
    aggregate_type: str
    description: str
    version: int = 1


# 注册表: 所有标准域事件的定义
EVENT_REGISTRY: dict[DomainEventType, DomainEventSpec] = {
    DomainEventType.COMPANY_CREATED: DomainEventSpec(
        DomainEventType.COMPANY_CREATED, "company", "公司创建"
    ),
    DomainEventType.COMPANY_RENAMED: DomainEventSpec(
        DomainEventType.COMPANY_RENAMED, "company", "公司改名"
    ),
    DomainEventType.COMPANY_UPDATED: DomainEventSpec(
        DomainEventType.COMPANY_UPDATED, "company", "公司信息更新"
    ),
    DomainEventType.COMPANY_ARCHIVED: DomainEventSpec(
        DomainEventType.COMPANY_ARCHIVED, "company", "公司归档"
    ),
    DomainEventType.DEPARTMENT_CREATED: DomainEventSpec(
        DomainEventType.DEPARTMENT_CREATED, "department", "部门创建"
    ),
    DomainEventType.DEPARTMENT_UPDATED: DomainEventSpec(
        DomainEventType.DEPARTMENT_UPDATED, "department", "部门信息更新"
    ),
    DomainEventType.DEPARTMENT_LEADER_CHANGED: DomainEventSpec(
        DomainEventType.DEPARTMENT_LEADER_CHANGED, "department", "部门负责人变更"
    ),
    DomainEventType.EMPLOYEE_CREATED: DomainEventSpec(
        DomainEventType.EMPLOYEE_CREATED, "employee", "职员创建"
    ),
    DomainEventType.EMPLOYEE_UPDATED: DomainEventSpec(
        DomainEventType.EMPLOYEE_UPDATED, "employee", "职员信息更新"
    ),
    DomainEventType.EMPLOYEE_STATUS_CHANGED: DomainEventSpec(
        DomainEventType.EMPLOYEE_STATUS_CHANGED, "employee", "职员状态变更"
    ),
    DomainEventType.EMPLOYEE_TRANSFERRED: DomainEventSpec(
        DomainEventType.EMPLOYEE_TRANSFERRED, "employee", "职员调岗"
    ),
    # ── CompanyTask ────────────────────────────────────────────────────
    DomainEventType.COMPANY_TASK_CREATED: DomainEventSpec(
        DomainEventType.COMPANY_TASK_CREATED, "company_task", "公司任务创建"
    ),
    DomainEventType.COMPANY_TASK_REVISION_REQUESTED: DomainEventSpec(
        DomainEventType.COMPANY_TASK_REVISION_REQUESTED, "company_task", "公司任务修订请求"
    ),
    DomainEventType.COMPANY_TASK_ANALYSIS_REQUESTED: DomainEventSpec(
        DomainEventType.COMPANY_TASK_ANALYSIS_REQUESTED, "company_task", "公司任务分析请求"
    ),
    DomainEventType.COMPANY_TASK_ANALYZED: DomainEventSpec(
        DomainEventType.COMPANY_TASK_ANALYZED, "company_task", "公司任务分析完成"
    ),
    DomainEventType.COMPANY_TASK_AWAITING_CONFIRMATION: DomainEventSpec(
        DomainEventType.COMPANY_TASK_AWAITING_CONFIRMATION, "company_task", "公司任务等待确认"
    ),
    DomainEventType.COMPANY_TASK_APPROVED: DomainEventSpec(
        DomainEventType.COMPANY_TASK_APPROVED, "company_task", "公司任务已批准"
    ),
    DomainEventType.COMPANY_TASK_DISPATCHED: DomainEventSpec(
        DomainEventType.COMPANY_TASK_DISPATCHED, "company_task", "公司任务已分派"
    ),
    DomainEventType.COMPANY_TASK_COMPLETED: DomainEventSpec(
        DomainEventType.COMPANY_TASK_COMPLETED, "company_task", "公司任务已完成"
    ),
    DomainEventType.COMPANY_TASK_CANCELLED: DomainEventSpec(
        DomainEventType.COMPANY_TASK_CANCELLED, "company_task", "公司任务已取消"
    ),
    DomainEventType.COMPANY_TASK_FAILED: DomainEventSpec(
        DomainEventType.COMPANY_TASK_FAILED, "company_task", "公司任务已失败"
    ),
    DomainEventType.COMPANY_TASK_PAUSED: DomainEventSpec(
        DomainEventType.COMPANY_TASK_PAUSED, "company_task", "公司任务已暂停"
    ),
    DomainEventType.COMPANY_TASK_RESUMED: DomainEventSpec(
        DomainEventType.COMPANY_TASK_RESUMED, "company_task", "公司任务已恢复"
    ),
    DomainEventType.CONVERSATION_USER_MESSAGE_SUBMITTED: DomainEventSpec(
        DomainEventType.CONVERSATION_USER_MESSAGE_SUBMITTED, "conversation", "用户消息提交"
    ),
    DomainEventType.CONVERSATION_EMPLOYEE_MESSAGE_SUBMITTED: DomainEventSpec(
        DomainEventType.CONVERSATION_EMPLOYEE_MESSAGE_SUBMITTED, "conversation", "职员消息提交"
    ),
    # ── Plan ───────────────────────────────────────────────────────────
    DomainEventType.PLAN_GENERATED: DomainEventSpec(
        DomainEventType.PLAN_GENERATED, "company_plan", "计划已生成"
    ),
    DomainEventType.PLAN_AWAITING_CONFIRMATION: DomainEventSpec(
        DomainEventType.PLAN_AWAITING_CONFIRMATION, "company_plan", "计划等待确认"
    ),
    DomainEventType.PLAN_APPROVED: DomainEventSpec(
        DomainEventType.PLAN_APPROVED, "company_plan", "计划已批准"
    ),
    DomainEventType.PLAN_REJECTED: DomainEventSpec(
        DomainEventType.PLAN_REJECTED, "company_plan", "计划已拒绝"
    ),
    DomainEventType.PLAN_SUPERSEDED: DomainEventSpec(
        DomainEventType.PLAN_SUPERSEDED, "company_plan", "计划已替代"
    ),
    # ── Review ─────────────────────────────────────────────────────────
    DomainEventType.REVIEW_ASSIGNMENT_CREATED: DomainEventSpec(
        DomainEventType.REVIEW_ASSIGNMENT_CREATED, "review", "审查分配已创建"
    ),
    DomainEventType.REVIEW_STARTED: DomainEventSpec(
        DomainEventType.REVIEW_STARTED, "review", "审查已开始"
    ),
    DomainEventType.REVIEW_SUBMITTED: DomainEventSpec(
        DomainEventType.REVIEW_SUBMITTED, "review", "审查已提交"
    ),
    DomainEventType.REVIEW_ISSUE_CREATED: DomainEventSpec(
        DomainEventType.REVIEW_ISSUE_CREATED, "review", "审查问题已创建"
    ),
    DomainEventType.REVIEW_ISSUE_RESOLVED: DomainEventSpec(
        DomainEventType.REVIEW_ISSUE_RESOLVED, "review", "审查问题已解决"
    ),
    DomainEventType.RUN_PROBING: DomainEventSpec(
        DomainEventType.RUN_PROBING, "agent_run", "运行探测"
    ),
    DomainEventType.RUN_STARTED: DomainEventSpec(
        DomainEventType.RUN_STARTED, "agent_run", "运行开始"
    ),
    DomainEventType.RUN_COMPLETED: DomainEventSpec(
        DomainEventType.RUN_COMPLETED, "agent_run", "运行完成"
    ),
    DomainEventType.RUN_FAILED: DomainEventSpec(
        DomainEventType.RUN_FAILED, "agent_run", "运行失败"
    ),
    DomainEventType.RUN_CANCELLED: DomainEventSpec(
        DomainEventType.RUN_CANCELLED, "agent_run", "运行取消"
    ),
    DomainEventType.RUN_TIMED_OUT: DomainEventSpec(
        DomainEventType.RUN_TIMED_OUT, "agent_run", "运行超时"
    ),
    DomainEventType.RUN_LOST: DomainEventSpec(
        DomainEventType.RUN_LOST, "agent_run", "运行丢失"
    ),
}


def get_event_spec(event_type: str) -> DomainEventSpec | None:
    """按事件类型名称查找事件定义。"""
    try:
        key = DomainEventType(event_type)
        return EVENT_REGISTRY.get(key)
    except ValueError:
        return None


def list_event_types(aggregate_type: str | None = None) -> list[DomainEventSpec]:
    """列出全部或指定聚合的事件类型。"""
    if aggregate_type is None:
        return list(EVENT_REGISTRY.values())
    return [spec for spec in EVENT_REGISTRY.values() if spec.aggregate_type == aggregate_type]
