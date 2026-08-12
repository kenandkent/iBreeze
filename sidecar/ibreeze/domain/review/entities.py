from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ReviewAssignment:
    id: UUID
    company_id: UUID
    artifact_id: UUID
    artifact_sha256: str
    reviewer_employee_id: UUID
    state: str
    version: int


@dataclass(frozen=True, slots=True)
class ReviewReport:
    id: UUID
    company_id: UUID
    assignment_id: UUID
    reviewer_run_id: UUID
    reviewed_artifact_id: UUID
    reviewed_sha256: str
    verdict: Literal["pass", "needs_changes", "failed"]
    version: int


@dataclass(frozen=True, slots=True)
class ReviewIssue:
    id: UUID
    company_id: UUID
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
    state: str
    version: int
    assignee_employee_id: UUID | None = None
    evidence_refs: tuple[str, ...] = ()
    verifier_employee_id: UUID | None = None
    rejection_reason: str | None = None
