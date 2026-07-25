"""Company and department orchestration primitives."""

from ibreeze.orchestration.availability_checker import (
    AvailabilityReport,
    CheckResult,
    CheckStatus,
    run_availability_checks,
)
from ibreeze.orchestration.collaboration import (
    CollaborationStrategy,
    SubTask,
    create_subtasks,
)
from ibreeze.orchestration.department_matcher import (
    DepartmentCandidate,
    DepartmentResponsibilityProfile,
    match_departments,
)
from ibreeze.orchestration.plan_validator import (
    CompanyPlan,
    DepartmentPlanTask,
    PlanValidationIssue,
    validate_plan,
)
from ibreeze.orchestration.workflow_templates import (
    WorkflowPhase,
    WorkflowStep,
    WorkflowTemplate,
    get_next_steps,
    get_workflow_template,
    list_workflow_templates,
)

__all__ = [
    "AvailabilityReport",
    "CheckResult",
    "CheckStatus",
    "CollaborationStrategy",
    "CompanyPlan",
    "DepartmentCandidate",
    "DepartmentPlanTask",
    "DepartmentResponsibilityProfile",
    "PlanValidationIssue",
    "SubTask",
    "WorkflowPhase",
    "WorkflowStep",
    "WorkflowTemplate",
    "create_subtasks",
    "get_next_steps",
    "get_workflow_template",
    "list_workflow_templates",
    "match_departments",
    "run_availability_checks",
    "validate_plan",
]
