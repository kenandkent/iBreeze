"""Deterministic orchestration matching and validation tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ibreeze.orchestration import (
    CompanyPlan,
    DepartmentPlanTask,
    DepartmentResponsibilityProfile,
    match_departments,
    validate_plan,
)
from ibreeze.orchestration.plan_validator import Deliverable


def _task(
    local_ref: str,
    department_id: str,
    *,
    dependencies: tuple[str, ...] = (),
    contributors: tuple[str, ...] = ("employee-1",),
    reviewers: tuple[str, ...] = ("employee-2",),
) -> DepartmentPlanTask:
    return DepartmentPlanTask(
        local_ref=local_ref,
        department_id=department_id,
        matched_responsibility_keys=("software_delivery",),
        objective="完成阶段交付",
        dependency_refs=dependencies,
        deliverables=(
            Deliverable(
                artifact_type="document",
                review_strategy="primary_with_peer_review",
                review_rounds=1,
                contributor_employee_ids=contributors,
                reviewer_employee_ids=reviewers,
            ),
        ),
        acceptance_criteria=("通过 Review",),
    )


def _plan(tasks: tuple[DepartmentPlanTask, ...]) -> CompanyPlan:
    return CompanyPlan(
        id="plan",
        company_task_id="task",
        company_id="company",
        version=1,
        company_introduction_version=1,
        summary="软件需求交付",
        goals=("完成需求",),
        non_goals=(),
        department_tasks=tasks,
        final_acceptance_criteria=("全部报告通过",),
        status="awaiting_user_confirmation",
        content_hash="a" * 64,
    )


def test_department_score_formula_threshold_and_tie_break() -> None:
    now = datetime.now(UTC)
    profiles = [
        DepartmentResponsibilityProfile(
            department_id="later",
            responsibility_key="delivery",
            accepted_task_types=frozenset({"software"}),
            capability_tags=frozenset({"code"}),
            deliverable_types=frozenset({"source"}),
            quality_gates=frozenset({"unit_test"}),
            created_at=now,
        ),
        DepartmentResponsibilityProfile(
            department_id="earlier",
            responsibility_key="delivery",
            accepted_task_types=frozenset({"software"}),
            capability_tags=frozenset({"code"}),
            deliverable_types=frozenset({"source"}),
            quality_gates=frozenset({"unit_test"}),
            created_at=now - timedelta(days=1),
        ),
        DepartmentResponsibilityProfile(
            department_id="below-threshold",
            responsibility_key="unrelated",
            accepted_task_types=frozenset(),
            capability_tags=frozenset({"code"}),
            deliverable_types=frozenset(),
            quality_gates=frozenset(),
            created_at=now,
        ),
    ]
    candidates = match_departments(
        profiles,
        task_type="software",
        required_capabilities=frozenset({"code"}),
        required_deliverables=frozenset({"source"}),
        required_quality_gates=frozenset({"unit_test"}),
    )
    assert [candidate.department_id for candidate in candidates] == [
        "earlier",
        "later",
    ]
    assert [candidate.score for candidate in candidates] == [100, 100]


def test_valid_plan_has_no_issues() -> None:
    plan = _plan(
        (
            _task("architecture", "architecture"),
            _task(
                "development",
                "development",
                dependencies=("architecture",),
            ),
        )
    )
    issues = validate_plan(
        plan,
        active_department_ids=frozenset({"architecture", "development"}),
        candidate_department_ids=frozenset({"architecture", "development"}),
        active_leader_department_ids=frozenset(
            {"architecture", "development"}
        ),
        allowed_employee_ids=frozenset({"employee-1", "employee-2"}),
    )
    assert issues == ()


def test_validator_reports_cycle_and_self_review_stably() -> None:
    plan = _plan(
        (
            _task(
                "one",
                "department",
                dependencies=("two",),
                reviewers=("employee-1",),
            ),
            _task("two", "department", dependencies=("one",)),
        )
    )
    issues = validate_plan(
        plan,
        active_department_ids=frozenset({"department"}),
        candidate_department_ids=frozenset({"department"}),
        active_leader_department_ids=frozenset({"department"}),
        allowed_employee_ids=frozenset({"employee-1", "employee-2"}),
    )
    assert [issue.rule_id for issue in issues] == [
        "PV-003",
        "PV-008",
    ]


def test_candidate_escape_requires_explicit_gm_temporary_assignment() -> None:
    task = _task("delivery", "gm-office")
    issues = validate_plan(
        _plan((task,)),
        active_department_ids=frozenset({"gm-office"}),
        candidate_department_ids=frozenset(),
        active_leader_department_ids=frozenset({"gm-office"}),
        allowed_employee_ids=frozenset({"employee-1", "employee-2"}),
    )
    assert [issue.rule_id for issue in issues] == ["PV-002"]
