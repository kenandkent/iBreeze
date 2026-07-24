"""Canonical closed-schema validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ibreeze.schemas import (
    CompanyCreate,
    CompanyUpdate,
    EmployeeCreate,
    KnowledgeItemCreate,
    KnowledgeVisibility,
    PaginationParams,
    ScopedGetRequest,
    SubmitUserMessageRequest,
    SubmitUserMessageResponse,
    WorkflowRole,
)


def test_company_create_requires_runtime_identity() -> None:
    company = CompanyCreate(
        name="iBreeze",
        introduction="模拟公司式 Agent 工作流",
        general_manager_name="总经理",
        base_profile_version_id="profile-version",
    )
    assert company.general_manager_name == "总经理"
    with pytest.raises(ValidationError):
        CompanyCreate(
            name="iBreeze",
            introduction="缺少总经理和底座",
        )


def test_updates_require_optimistic_lock_version() -> None:
    update = CompanyUpdate(name="新名称", expected_version=3)
    assert update.expected_version == 3
    with pytest.raises(ValidationError):
        CompanyUpdate(name="无版本")


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ScopedGetRequest(
            id="resource",
            company_id="company",
            leaked_company="other",
        )


def test_employee_role_is_explicit() -> None:
    employee = EmployeeCreate(
        display_name="工程师",
        base_profile_version_id="profile-version",
        workflow_role=WorkflowRole.MEMBER,
    )
    assert employee.workflow_role is WorkflowRole.MEMBER


def test_message_intake_disallows_empty_content() -> None:
    with pytest.raises(ValidationError):
        SubmitUserMessageRequest(
            company_id="company",
            conversation_id="conversation",
            content="",
        )


def test_message_response_is_closed_and_has_no_run_id() -> None:
    response = SubmitUserMessageResponse(
        message_id="message",
        company_task_id="task",
        task_status="draft",
        intake_mode="new_task",
        analysis_queued=True,
    )
    assert "run_id" not in response.model_dump()
    with pytest.raises(ValidationError):
        SubmitUserMessageResponse(
            message_id="message",
            company_task_id="task",
            task_status="running",
            intake_mode="new_task",
            analysis_queued=True,
        )


@pytest.mark.parametrize(
    ("visibility", "scope"),
    [
        (KnowledgeVisibility.COMPANY, {}),
        (KnowledgeVisibility.DEPARTMENT, {"department_id": "department"}),
        (KnowledgeVisibility.TASK, {"task_id": "task"}),
        (KnowledgeVisibility.PRIVATE, {"owner_employee_id": "employee"}),
    ],
)
def test_knowledge_scope_shapes_are_representable(
    visibility: KnowledgeVisibility,
    scope: dict[str, str],
) -> None:
    item = KnowledgeItemCreate(
        title="规范",
        content="正文",
        visibility=visibility,
        source_message_event_id="event",
        **scope,
    )
    assert item.visibility is visibility


def test_knowledge_requires_one_stable_source_and_exact_scope() -> None:
    with pytest.raises(ValidationError):
        KnowledgeItemCreate(
            title="无来源",
            content="正文",
            visibility=KnowledgeVisibility.COMPANY,
        )
    with pytest.raises(ValidationError):
        KnowledgeItemCreate(
            title="越权范围",
            content="正文",
            visibility=KnowledgeVisibility.COMPANY,
            department_id="department",
            source_message_event_id="event",
        )


def test_pagination_limits() -> None:
    assert PaginationParams().limit == 50
    with pytest.raises(ValidationError):
        PaginationParams(limit=0)
    with pytest.raises(ValidationError):
        PaginationParams(limit=201)
