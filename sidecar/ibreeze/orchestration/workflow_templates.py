"""Standard workflow templates for common task types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkflowPhase(StrEnum):
    ANALYSIS = "analysis"
    ARCHITECTURE = "architecture"
    DEVELOPMENT = "development"
    TESTING = "testing"
    FIRST_TEST = "first_test"
    FIXING = "fixing"
    FINAL_TEST = "final_test"
    GM_REVIEW = "gm_review"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    phase: WorkflowPhase
    name: str
    description: str
    required_roles: tuple[str, ...]
    parallel_with: tuple[WorkflowPhase, ...] = ()
    dependencies: tuple[WorkflowPhase, ...] = ()
    quality_gates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkflowTemplate:
    name: str
    description: str
    steps: tuple[WorkflowStep, ...]


SOFTWARE_REQUIREMENT_DELIVERY = WorkflowTemplate(
    name="software_requirement_delivery",
    description="Standard software requirement delivery workflow",
    steps=(
        WorkflowStep(
            phase=WorkflowPhase.ANALYSIS,
            name="Requirement Analysis",
            description="Analyze and decompose the software requirement",
            required_roles=("department_leader",),
            quality_gates=(
                "requirement_clarity",
                "scope_defined",
            ),
        ),
        WorkflowStep(
            phase=WorkflowPhase.ARCHITECTURE,
            name="Architecture Design",
            description="Design system architecture and component interfaces",
            required_roles=("department_leader", "member"),
            dependencies=(WorkflowPhase.ANALYSIS,),
            quality_gates=(
                "architecture_review",
                "interface_defined",
            ),
        ),
        WorkflowStep(
            phase=WorkflowPhase.DEVELOPMENT,
            name="Implementation",
            description="Implement the designed components",
            required_roles=("member",),
            dependencies=(WorkflowPhase.ARCHITECTURE,),
            quality_gates=(
                "code_review",
                "unit_tests_pass",
            ),
        ),
        WorkflowStep(
            phase=WorkflowPhase.TESTING,
            name="Testing",
            description="Run comprehensive tests",
            required_roles=("member",),
            parallel_with=(WorkflowPhase.DEVELOPMENT,),
            dependencies=(WorkflowPhase.ARCHITECTURE,),
            quality_gates=(
                "integration_tests_pass",
                "coverage_threshold",
            ),
        ),
        WorkflowStep(
            phase=WorkflowPhase.FIRST_TEST,
            name="First Integration Test",
            description="First integration test cycle",
            required_roles=("member",),
            dependencies=(
                WorkflowPhase.DEVELOPMENT,
                WorkflowPhase.TESTING,
            ),
            quality_gates=("all_tests_pass",),
        ),
        WorkflowStep(
            phase=WorkflowPhase.FIXING,
            name="Bug Fixes",
            description="Fix issues found during testing",
            required_roles=("member",),
            dependencies=(WorkflowPhase.FIRST_TEST,),
            quality_gates=("all_issues_resolved",),
        ),
        WorkflowStep(
            phase=WorkflowPhase.FINAL_TEST,
            name="Final Test",
            description="Final validation test cycle",
            required_roles=("member",),
            dependencies=(WorkflowPhase.FIXING,),
            quality_gates=(
                "all_tests_pass",
                "no_critical_issues",
            ),
        ),
        WorkflowStep(
            phase=WorkflowPhase.GM_REVIEW,
            name="GM Final Review",
            description="General Manager final review and approval",
            required_roles=("general_manager",),
            dependencies=(WorkflowPhase.FINAL_TEST,),
            quality_gates=("gm_approval",),
        ),
    ),
)

WORKFLOW_TEMPLATES: dict[str, WorkflowTemplate] = {
    "software_requirement_delivery": SOFTWARE_REQUIREMENT_DELIVERY,
}


def get_workflow_template(name: str) -> WorkflowTemplate | None:
    """Get a workflow template by name."""
    return WORKFLOW_TEMPLATES.get(name)


def list_workflow_templates() -> list[WorkflowTemplate]:
    """List all available workflow templates."""
    return list(WORKFLOW_TEMPLATES.values())


def get_next_steps(
    template: WorkflowTemplate,
    completed_phases: set[WorkflowPhase],
) -> list[WorkflowStep]:
    """Get the next actionable steps based on completed phases."""
    next_steps = []
    for step in template.steps:
        if step.phase in completed_phases:
            continue
        deps_met = all(dep in completed_phases for dep in step.dependencies)
        if deps_met:
            next_steps.append(step)
    return next_steps
