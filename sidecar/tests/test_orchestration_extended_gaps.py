"""Tests for workflow_templates and department_matcher orchestration modules."""

from __future__ import annotations

from datetime import datetime

import pytest

from ibreeze.orchestration.department_matcher import (
    DepartmentResponsibilityProfile,
    _coverage,
    match_departments,
)
from ibreeze.orchestration.workflow_templates import (
    SOFTWARE_REQUIREMENT_DELIVERY,
    WorkflowPhase,
    WorkflowStep,
    get_next_steps,
    get_workflow_template,
    list_workflow_templates,
)

# ── workflow_templates ────────────────────────────────────────────────


def test_get_workflow_template_exists() -> None:
    t = get_workflow_template("software_requirement_delivery")
    assert t is not None
    assert t.name == "software_requirement_delivery"


def test_get_workflow_template_missing() -> None:
    assert get_workflow_template("nonexistent") is None


def test_list_workflow_templates() -> None:
    templates = list_workflow_templates()
    assert len(templates) >= 1
    assert any(t.name == "software_requirement_delivery" for t in templates)


def test_template_has_steps() -> None:
    assert len(SOFTWARE_REQUIREMENT_DELIVERY.steps) >= 8


def test_workflow_phase_enum() -> None:
    assert WorkflowPhase.ANALYSIS == "analysis"
    assert WorkflowPhase.GM_REVIEW == "gm_review"
    assert WorkflowPhase.COMPLETED == "completed"


def test_workflow_step_frozen() -> None:
    step = SOFTWARE_REQUIREMENT_DELIVERY.steps[0]
    assert isinstance(step, WorkflowStep)
    with pytest.raises(AttributeError):
        step.phase = WorkflowPhase.TESTING  # type: ignore[misc]


def test_workflow_template_frozen() -> None:
    with pytest.raises(AttributeError):
        SOFTWARE_REQUIREMENT_DELIVERY.name = "changed"  # type: ignore[misc]


def test_get_next_steps_initial() -> None:
    steps = get_next_steps(SOFTWARE_REQUIREMENT_DELIVERY, set())
    assert len(steps) >= 1
    assert steps[0].phase == WorkflowPhase.ANALYSIS


def test_get_next_steps_after_analysis() -> None:
    steps = get_next_steps(
        SOFTWARE_REQUIREMENT_DELIVERY,
        {WorkflowPhase.ANALYSIS},
    )
    phases = [s.phase for s in steps]
    assert WorkflowPhase.ANALYSIS not in phases
    assert WorkflowPhase.ARCHITECTURE in phases


def test_get_next_steps_after_architecture() -> None:
    steps = get_next_steps(
        SOFTWARE_REQUIREMENT_DELIVERY,
        {WorkflowPhase.ANALYSIS, WorkflowPhase.ARCHITECTURE},
    )
    phases = [s.phase for s in steps]
    assert WorkflowPhase.DEVELOPMENT in phases
    assert WorkflowPhase.TESTING in phases


def test_get_next_steps_parallel_development_testing() -> None:
    completed = {
        WorkflowPhase.ANALYSIS,
        WorkflowPhase.ARCHITECTURE,
        WorkflowPhase.DEVELOPMENT,
        WorkflowPhase.TESTING,
        WorkflowPhase.FIRST_TEST,
        WorkflowPhase.FIXING,
        WorkflowPhase.FINAL_TEST,
    }
    steps = get_next_steps(SOFTWARE_REQUIREMENT_DELIVERY, completed)
    assert len(steps) == 1
    assert steps[0].phase == WorkflowPhase.GM_REVIEW


def test_get_next_steps_all_completed() -> None:
    all_phases = {s.phase for s in SOFTWARE_REQUIREMENT_DELIVERY.steps}
    steps = get_next_steps(SOFTWARE_REQUIREMENT_DELIVERY, all_phases)
    assert steps == []


def test_step_dependencies_and_quality_gates() -> None:
    for step in SOFTWARE_REQUIREMENT_DELIVERY.steps:
        assert step.name
        assert step.description
        assert len(step.required_roles) > 0


# ── department_matcher ────────────────────────────────────────────────


def _make_profile(
    dept_id: str = "dept-1",
    key: str = "coding",
    task_types: frozenset[str] = frozenset({"feature", "bugfix"}),
    caps: frozenset[str] = frozenset({"python", "testing"}),
    deliverables: frozenset[str] = frozenset({"patch", "document"}),
    gates: frozenset[str] = frozenset({"code_review"}),
    created: datetime | None = None,
) -> DepartmentResponsibilityProfile:
    return DepartmentResponsibilityProfile(
        department_id=dept_id,
        responsibility_key=key,
        accepted_task_types=task_types,
        capability_tags=caps,
        deliverable_types=deliverables,
        quality_gates=gates,
        created_at=created or datetime(2026, 1, 1),
    )


def test_coverage_full() -> None:
    assert _coverage(frozenset({"a", "b"}), frozenset({"a", "b", "c"})) == 1.0


def test_coverage_partial() -> None:
    assert _coverage(frozenset({"a", "b"}), frozenset({"a"})) == 0.5


def test_coverage_empty_required() -> None:
    assert _coverage(frozenset(), frozenset({"a"})) == 1.0


def test_coverage_no_match() -> None:
    assert _coverage(frozenset({"x"}), frozenset({"a"})) == 0.0


def test_match_departments_basic() -> None:
    profile = _make_profile()
    candidates = match_departments(
        [profile],
        task_type="feature",
        required_capabilities=frozenset({"python"}),
        required_deliverables=frozenset({"patch"}),
        required_quality_gates=frozenset({"code_review"}),
    )
    assert len(candidates) == 1
    assert candidates[0].department_id == "dept-1"
    assert candidates[0].score == 100.0


def test_match_departments_low_score_filtered() -> None:
    profile = _make_profile(
        task_types=frozenset({"unrelated"}),
        caps=frozenset({"java"}),
        deliverables=frozenset({"binary"}),
        gates=frozenset({"qa"}),
    )
    candidates = match_departments(
        [profile],
        task_type="feature",
        required_capabilities=frozenset({"python"}),
        required_deliverables=frozenset({"patch"}),
        required_quality_gates=frozenset({"code_review"}),
    )
    assert len(candidates) == 0


def test_match_departments_partial_match() -> None:
    profile = _make_profile(caps=frozenset({"python", "java"}))
    candidates = match_departments(
        [profile],
        task_type="feature",
        required_capabilities=frozenset({"python", "rust"}),
        required_deliverables=frozenset({"patch"}),
        required_quality_gates=frozenset({"code_review"}),
    )
    assert len(candidates) == 1
    assert candidates[0].matched_capabilities == ("python",)
    assert candidates[0].score < 100.0


def test_match_departments_sorted_by_score() -> None:
    p1 = _make_profile(dept_id="low", caps=frozenset({"python"}))
    p2 = _make_profile(dept_id="high", caps=frozenset({"python", "testing"}))
    candidates = match_departments(
        [p1, p2],
        task_type="feature",
        required_capabilities=frozenset({"python", "testing"}),
        required_deliverables=frozenset({"patch"}),
        required_quality_gates=frozenset({"code_review"}),
    )
    assert candidates[0].department_id == "high"
    assert candidates[0].score >= candidates[1].score


def test_match_departments_empty_profiles() -> None:
    candidates = match_departments(
        [],
        task_type="feature",
        required_capabilities=frozenset({"python"}),
        required_deliverables=frozenset({"patch"}),
        required_quality_gates=frozenset({"code_review"}),
    )
    assert candidates == []


def test_match_departments_no_task_match() -> None:
    profile = _make_profile(
        task_types=frozenset({"audit"}),
        caps=frozenset({"java"}),
        deliverables=frozenset({"binary"}),
        gates=frozenset({"qa"}),
    )
    candidates = match_departments(
        [profile],
        task_type="feature",
        required_capabilities=frozenset({"python"}),
        required_deliverables=frozenset({"patch"}),
        required_quality_gates=frozenset({"code_review"}),
    )
    assert len(candidates) == 0


def test_match_departments_tiebreak_by_created_at() -> None:
    early = datetime(2025, 1, 1)
    late = datetime(2026, 6, 1)
    p1 = _make_profile(dept_id="first", created=early)
    p2 = _make_profile(dept_id="second", created=late)
    candidates = match_departments(
        [p2, p1],
        task_type="feature",
        required_capabilities=frozenset({"python"}),
        required_deliverables=frozenset({"patch"}),
        required_quality_gates=frozenset({"code_review"}),
    )
    assert candidates[0].department_id == "first"
    assert candidates[1].department_id == "second"
