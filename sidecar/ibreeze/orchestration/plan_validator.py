"""Closed CompanyPlan schema and deterministic validation rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExternalWrite(PlanModel):
    target: str
    action: Literal["create", "replace", "delete", "move"]
    expected_effect: str


class Deliverable(PlanModel):
    artifact_type: str
    review_strategy: Literal[
        "independent_drafts",
        "section_partition",
        "primary_with_peer_review",
        "sequential_refinement",
    ]
    review_rounds: Annotated[int, Field(ge=1, le=10)]
    contributor_employee_ids: tuple[str, ...]
    reviewer_employee_ids: tuple[str, ...]


class DepartmentPlanTask(PlanModel):
    local_ref: str
    department_id: str
    matched_responsibility_keys: tuple[str, ...]
    general_manager_office_temporary_assignment: bool = False
    objective: str
    dependency_refs: tuple[str, ...] = ()
    deliverables: tuple[Deliverable, ...]
    acceptance_criteria: tuple[str, ...]
    required_capability_tags: tuple[str, ...] = ()
    required_external_writes: tuple[ExternalWrite, ...] = ()


class CompanyPlan(PlanModel):
    id: str
    company_task_id: str
    company_id: str
    version: Annotated[int, Field(ge=1)]
    company_introduction_version: Annotated[int, Field(ge=1)]
    summary: str
    goals: tuple[str, ...]
    non_goals: tuple[str, ...]
    department_tasks: tuple[DepartmentPlanTask, ...]
    final_acceptance_criteria: tuple[str, ...]
    status: Literal["awaiting_user_confirmation"]
    content_hash: str


@dataclass(frozen=True, slots=True)
class PlanValidationIssue:
    rule_id: str
    path: str
    message: str


def validate_plan(
    plan: CompanyPlan,
    *,
    active_department_ids: frozenset[str],
    candidate_department_ids: frozenset[str],
    active_leader_department_ids: frozenset[str],
    allowed_employee_ids: frozenset[str],
) -> tuple[PlanValidationIssue, ...]:
    issues: list[PlanValidationIssue] = []
    if (
        not plan.goals
        or not plan.department_tasks
        or any(
            not task.objective.strip()
            or not task.deliverables
            or not task.acceptance_criteria
            for task in plan.department_tasks
        )
    ):
        issues.append(
            PlanValidationIssue(
                "PV-001",
                "department_tasks",
                "Goals, objectives, deliverables and acceptance criteria are required.",
            )
        )

    references = [task.local_ref for task in plan.department_tasks]
    reference_set = set(references)
    if len(reference_set) != len(references):
        issues.append(
            PlanValidationIssue(
                "PV-003",
                "department_tasks.local_ref",
                "Task references must be unique.",
            )
        )
    for task in plan.department_tasks:
        if (
            task.department_id not in active_department_ids
            or (
                task.department_id not in candidate_department_ids
                and not task.general_manager_office_temporary_assignment
            )
        ):
            issues.append(
                PlanValidationIssue(
                    "PV-002",
                    f"department_tasks.{task.local_ref}.department_id",
                    "Department is inactive or outside the responsibility candidates.",
                )
            )
        if task.department_id not in active_leader_department_ids:
            issues.append(
                PlanValidationIssue(
                    "PV-004",
                    f"department_tasks.{task.local_ref}.department_id",
                    "Department has no active leader.",
                )
            )
        if any(
            dependency not in reference_set or dependency == task.local_ref
            for dependency in task.dependency_refs
        ):
            issues.append(
                PlanValidationIssue(
                    "PV-003",
                    f"department_tasks.{task.local_ref}.dependency_refs",
                    "Dependency is missing or self-referential.",
                )
            )
        for index, deliverable in enumerate(task.deliverables):
            contributors = set(deliverable.contributor_employee_ids)
            reviewers = set(deliverable.reviewer_employee_ids)
            if (
                not contributors
                or not reviewers
                or not (contributors | reviewers) <= allowed_employee_ids
            ):
                issues.append(
                    PlanValidationIssue(
                        "PV-005",
                        f"department_tasks.{task.local_ref}.deliverables.{index}",
                        "Employee reference is outside the company or missing.",
                    )
                )
            if contributors & reviewers:
                issues.append(
                    PlanValidationIssue(
                        "PV-008",
                        f"department_tasks.{task.local_ref}.deliverables.{index}",
                        "A contributor cannot review the same artifact.",
                    )
                )
        for index, write in enumerate(task.required_external_writes):
            if not write.target.startswith("/") or not write.expected_effect.strip():
                issues.append(
                    PlanValidationIssue(
                        "PV-006",
                        f"department_tasks.{task.local_ref}.required_external_writes.{index}",
                        "External writes require an absolute target and effect summary.",
                    )
                )

    if _has_cycle(plan.department_tasks):
        issues.append(
            PlanValidationIssue(
                "PV-003",
                "department_tasks.dependency_refs",
                "Department task dependencies contain a cycle.",
            )
        )
    if not plan.final_acceptance_criteria:
        issues.append(
            PlanValidationIssue(
                "PV-009",
                "final_acceptance_criteria",
                "Final acceptance criteria are required.",
            )
        )
    return tuple(
        sorted(
            issues,
            key=lambda issue: (issue.rule_id, issue.path, issue.message),
        )
    )


def _has_cycle(tasks: tuple[DepartmentPlanTask, ...]) -> bool:
    graph = {
        task.local_ref: tuple(task.dependency_refs)
        for task in tasks
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(dependency in graph and visit(dependency) for dependency in graph[node]):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)
