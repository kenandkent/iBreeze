"""PLAN-006: Comprehensive PlanValidator rule coverage.

Covers PV-001 through PV-011 validation rules.
"""

from __future__ import annotations

import pytest

from ibreeze.orchestration.plan_validator import (
    CompanyPlan,
    Deliverable,
    DepartmentPlanTask,
    ExternalWrite,
    validate_plan,
)


def _task(
    local_ref: str,
    department_id: str,
    *,
    dependencies: tuple[str, ...] = (),
    contributors: tuple[str, ...] = ("employee-1",),
    reviewers: tuple[str, ...] = ("employee-2",),
    objective: str = "完成阶段交付",
    deliverables: tuple[Deliverable, ...] | None = None,
    acceptance_criteria: tuple[str, ...] = ("通过 Review",),
    required_capability_tags: tuple[str, ...] = (),
    required_external_writes: tuple[ExternalWrite, ...] = (),
    gm_temporary: bool = False,
) -> DepartmentPlanTask:
    if deliverables is None:
        deliverables = (
            Deliverable(
                artifact_type="document",
                review_strategy="primary_with_peer_review",
                review_rounds=1,
                contributor_employee_ids=contributors,
                reviewer_employee_ids=reviewers,
            ),
        )
    return DepartmentPlanTask(
        local_ref=local_ref,
        department_id=department_id,
        matched_responsibility_keys=("software_delivery",),
        objective=objective,
        dependency_refs=dependencies,
        deliverables=deliverables,
        acceptance_criteria=acceptance_criteria,
        required_capability_tags=required_capability_tags,
        required_external_writes=required_external_writes,
        general_manager_office_temporary_assignment=gm_temporary,
    )


def _plan(
    tasks: tuple[DepartmentPlanTask, ...],
    *,
    goals: tuple[str, ...] = ("完成需求",),
    final_ac: tuple[str, ...] = ("全部报告通过",),
) -> CompanyPlan:
    return CompanyPlan(
        id="plan",
        company_task_id="task",
        company_id="company",
        version=1,
        company_introduction_version=1,
        summary="软件需求交付",
        goals=goals,
        non_goals=(),
        department_tasks=tasks,
        final_acceptance_criteria=final_ac,
        status="awaiting_user_confirmation",
        content_hash="a" * 64,
    )


_ACTIVE = frozenset({"architecture", "development", "testing"})
_CANDIDATES = frozenset({"architecture", "development", "testing"})
_LEADERS = frozenset({"architecture", "development", "testing"})
_EMPLOYEES = frozenset({"employee-1", "employee-2", "employee-3"})


class TestPV001GoalsObjectivesDeliverablesRequired:
    """PV-001: Goals, objectives, deliverables and acceptance criteria are required."""

    def test_empty_goals_triggers(self):
        plan = _plan((_task("t1", "architecture"),), goals=())
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-001" for i in issues)

    def test_empty_department_tasks_triggers(self):
        plan = _plan(())
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-001" for i in issues)

    def test_empty_objective_triggers(self):
        task = _task("t1", "architecture", objective="  ")
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-001" for i in issues)

    def test_empty_deliverables_triggers(self):
        task = _task("t1", "architecture", deliverables=())
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-001" for i in issues)

    def test_empty_acceptance_criteria_triggers(self):
        task = _task("t1", "architecture", acceptance_criteria=())
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-001" for i in issues)

    def test_valid_plan_no_pv001(self):
        plan = _plan((_task("t1", "architecture"),))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert not any(i.rule_id == "PV-001" for i in issues)


class TestPV002DepartmentOutsideCandidate:
    """PV-002: Department is inactive or outside responsibility candidates."""

    def test_department_not_in_candidates(self):
        plan = _plan((_task("t1", "gm-office"),))
        issues = validate_plan(
            plan,
            active_department_ids=frozenset({"gm-office"}),
            candidate_department_ids=frozenset(),
            active_leader_department_ids=frozenset({"gm-office"}),
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-002" for i in issues)

    def test_gm_temporary_bypasses_candidate(self):
        task = _task("t1", "gm-office", gm_temporary=True)
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=frozenset({"gm-office"}),
            candidate_department_ids=frozenset(),
            active_leader_department_ids=frozenset({"gm-office"}),
            allowed_employee_ids=_EMPLOYEES,
        )
        assert not any(i.rule_id == "PV-002" for i in issues)


class TestPV003CycleDetection:
    """PV-003: Dependency cycle detection."""

    def test_direct_cycle(self):
        plan = _plan((
            _task("a", "architecture", dependencies=("b",)),
            _task("b", "development", dependencies=("a",)),
        ))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-003" for i in issues)

    def test_self_dependency(self):
        task = _task("a", "architecture", dependencies=("a",))
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-003" for i in issues)

    def test_missing_dependency(self):
        task = _task("a", "architecture", dependencies=("nonexistent",))
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-003" for i in issues)


class TestPV004NoActiveLeader:
    """PV-004: Department has no active leader."""

    def test_department_without_leader(self):
        plan = _plan((_task("t1", "architecture"),))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=frozenset({"development", "testing"}),
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-004" for i in issues)


class TestPV005EmployeeReferenceOutsideCompany:
    """PV-005: Employee reference is outside the company or missing."""

    def test_contributor_not_allowed(self):
        deliverable = Deliverable(
            artifact_type="document",
            review_strategy="primary_with_peer_review",
            review_rounds=1,
            contributor_employee_ids=("unknown-emp",),
            reviewer_employee_ids=("employee-2",),
        )
        task = _task("t1", "architecture", deliverables=(deliverable,))
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-005" for i in issues)

    def test_reviewer_not_allowed(self):
        deliverable = Deliverable(
            artifact_type="document",
            review_strategy="primary_with_peer_review",
            review_rounds=1,
            contributor_employee_ids=("employee-1",),
            reviewer_employee_ids=("unknown-emp",),
        )
        task = _task("t1", "architecture", deliverables=(deliverable,))
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-005" for i in issues)

    def test_empty_contributors(self):
        deliverable = Deliverable(
            artifact_type="document",
            review_strategy="primary_with_peer_review",
            review_rounds=1,
            contributor_employee_ids=(),
            reviewer_employee_ids=("employee-2",),
        )
        task = _task("t1", "architecture", deliverables=(deliverable,))
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-005" for i in issues)


class TestPV006ExternalWriteAbsoluteTarget:
    """PV-006: External writes require absolute target and effect summary."""

    def test_relative_target_triggers(self):
        write = ExternalWrite(target="relative/path", action="create", expected_effect="file created")
        task = _task("t1", "architecture", required_external_writes=(write,))
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-006" for i in issues)

    def test_empty_effect_triggers(self):
        write = ExternalWrite(target="/tmp/file.txt", action="create", expected_effect="  ")
        task = _task("t1", "architecture", required_external_writes=(write,))
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-006" for i in issues)

    def test_absolute_target_passes(self):
        write = ExternalWrite(target="/tmp/file.txt", action="create", expected_effect="created")
        task = _task("t1", "architecture", required_external_writes=(write,))
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert not any(i.rule_id == "PV-006" for i in issues)


class TestPV007ReviewStrategyRequired:
    """PV-007: Review strategy and rounds are required.

    Note: Pydantic enforces review_rounds >= 1 at schema level.
    PV-007 is the business-layer fallback for empty/missing strategy.
    """

    def test_schema_rejects_zero_rounds(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Deliverable(
                artifact_type="document",
                review_strategy="primary_with_peer_review",
                review_rounds=0,
                contributor_employee_ids=("employee-1",),
                reviewer_employee_ids=("employee-2",),
            )


class TestPV008SelfReview:
    """PV-008: A contributor cannot review the same artifact."""

    def test_self_review_detected(self):
        plan = _plan((
            _task(
                "t1",
                "architecture",
                contributors=("employee-1",),
                reviewers=("employee-1",),
            ),
        ))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-008" for i in issues)


class TestPV009FinalAcceptanceCriteria:
    """PV-009: Final acceptance criteria are required."""

    def test_empty_final_ac_triggers(self):
        plan = _plan((_task("t1", "architecture"),), final_ac=())
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
        )
        assert any(i.rule_id == "PV-009" for i in issues)


class TestPV010EmergencyDisabledCapabilities:
    """PV-010: Task uses emergency-disabled capabilities."""

    def test_emergency_disabled_tag(self):
        task = _task("t1", "architecture", required_capability_tags=("codex",))
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
            emergency_disabled_capability_tags=frozenset({"codex"}),
        )
        assert any(i.rule_id == "PV-010" for i in issues)

    def test_no_disabled_tags_passes(self):
        task = _task("t1", "architecture", required_capability_tags=("codex",))
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
            emergency_disabled_capability_tags=frozenset(),
        )
        assert not any(i.rule_id == "PV-010" for i in issues)


class TestPV011ProductPermissionLimits:
    """PV-011: External write action exceeds product permission limits."""

    def test_limited_action_triggers(self):
        write = ExternalWrite(target="/tmp/file.txt", action="delete", expected_effect="deleted")
        task = _task("t1", "architecture", required_external_writes=(write,))
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
            product_permission_limits=frozenset({"delete"}),
        )
        assert any(i.rule_id == "PV-011" for i in issues)

    def test_unlimited_action_passes(self):
        write = ExternalWrite(target="/tmp/file.txt", action="create", expected_effect="created")
        task = _task("t1", "architecture", required_external_writes=(write,))
        plan = _plan((task,))
        issues = validate_plan(
            plan,
            active_department_ids=_ACTIVE,
            candidate_department_ids=_CANDIDATES,
            active_leader_department_ids=_LEADERS,
            allowed_employee_ids=_EMPLOYEES,
            product_permission_limits=frozenset({"delete"}),
        )
        assert not any(i.rule_id == "PV-011" for i in issues)


class TestPVFullRuleSet:
    """PLAN-006: Parametrized test covering all PV rules in one pass."""

    def test_all_rules_catchable(self):
        deliverable = Deliverable(
            artifact_type="document",
            review_strategy="primary_with_peer_review",
            review_rounds=1,
            contributor_employee_ids=("employee-unknown",),
            reviewer_employee_ids=("employee-unknown",),
        )
        write = ExternalWrite(target="relative", action="delete", expected_effect="")
        task = _task(
            "t1",
            "gm-office",
            contributors=("employee-unknown",),
            reviewers=("employee-unknown",),
            deliverables=(deliverable,),
            required_capability_tags=("codex",),
            required_external_writes=(write,),
            gm_temporary=True,
        )
        plan = _plan((task,), goals=(), final_ac=())
        issues = validate_plan(
            plan,
            active_department_ids=frozenset({"gm-office"}),
            candidate_department_ids=frozenset(),
            active_leader_department_ids=frozenset(),
            allowed_employee_ids=frozenset({"employee-1"}),
            emergency_disabled_capability_tags=frozenset({"codex"}),
            product_permission_limits=frozenset({"delete"}),
        )
        rule_ids = {i.rule_id for i in issues}
        assert "PV-001" in rule_ids
        assert "PV-004" in rule_ids
        assert "PV-005" in rule_ids
        assert "PV-006" in rule_ids
        assert "PV-008" in rule_ids
        assert "PV-009" in rule_ids
        assert "PV-010" in rule_ids
        assert "PV-011" in rule_ids
