from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class StartReview:
    company_id: UUID
    assignment_id: UUID
    expected_version: int


@dataclass(frozen=True, slots=True)
class ReviewIssueInput:
    client_issue_id: UUID
    severity: Literal["blocker", "high", "medium", "low"]
    category: Literal[
        "functional",
        "security",
        "performance",
        "reliability",
        "maintainability",
        "documentation",
        "test",
        "contract",
        "review_execution",
    ]
    description: str
    expected: str
    actual: str
    evidence_refs: tuple[UUID, ...]
    suggested_fix: str
    assignee_employee_id: UUID | None


@dataclass(frozen=True, slots=True)
class SubmitReview:
    company_id: UUID
    assignment_id: UUID
    reviewer_run_id: UUID
    reviewed_artifact_id: UUID
    reviewed_sha256: str
    report_artifact_id: UUID
    verdict: Literal["pass", "needs_changes", "failed"]
    issues: tuple[ReviewIssueInput, ...]
    expected_assignment_version: int


@dataclass(frozen=True, slots=True)
class StartIssueFix:
    company_id: UUID
    issue_id: UUID
    expected_version: int


@dataclass(frozen=True, slots=True)
class ResolveIssue:
    company_id: UUID
    issue_id: UUID
    resolution_artifact_sha256: str
    fix_run_id: UUID
    retest_result_id: UUID
    resolution_summary: str
    expected_version: int


@dataclass(frozen=True, slots=True)
class VerifyIssue:
    company_id: UUID
    issue_id: UUID
    verifier_employee_id: UUID
    expected_version: int


@dataclass(frozen=True, slots=True)
class CloseIssue:
    company_id: UUID
    issue_id: UUID
    expected_version: int


@dataclass(frozen=True, slots=True)
class RejectIssue:
    company_id: UUID
    issue_id: UUID
    rejection_reason: str
    expected_version: int
