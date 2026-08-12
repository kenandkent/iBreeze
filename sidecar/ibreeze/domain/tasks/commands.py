from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AcceptEmployeeTask:
    company_id: UUID
    task_id: UUID
    expected_version: int


@dataclass(frozen=True, slots=True)
class SubmitEmployeeTask:
    company_id: UUID
    task_id: UUID
    run_id: UUID
    expected_version: int


@dataclass(frozen=True, slots=True)
class StartEmployeeTask:
    company_id: UUID
    task_id: UUID
    expected_version: int


@dataclass(frozen=True, slots=True)
class CompleteDepartmentTask:
    company_id: UUID
    task_id: UUID
    expected_version: int


@dataclass(frozen=True, slots=True)
class CompleteCompanyTask:
    company_id: UUID
    task_id: UUID
    expected_version: int


@dataclass(frozen=True, slots=True)
class RequestDepartmentRework:
    company_id: UUID
    department_task_id: UUID
    source_review_issue_ids: tuple[UUID, ...]
    expected_version: int


@dataclass(frozen=True, slots=True)
class RequestCompanyRework:
    company_id: UUID
    company_task_id: UUID
    department_task_id: UUID | None
    source_review_issue_ids: tuple[UUID, ...]
    expected_version: int
