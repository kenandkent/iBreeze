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
from ibreeze.orchestration.confirm_plan import ConfirmPlanCommand, confirm_and_dispatch
from ibreeze.orchestration.department_matcher import (
    DepartmentCandidate,
    DepartmentResponsibilityProfile,
    match_departments,
)
from ibreeze.orchestration.plan_generator import generate_company_plan
from ibreeze.orchestration.plan_validator import (
    CompanyPlan,
    DepartmentPlanTask,
    PlanValidationIssue,
    validate_plan,
)
from ibreeze.orchestration.report_generator import (
    generate_company_review,
    generate_department_report,
    generate_final_report,
)
from ibreeze.orchestration.role_behavior import (
    AgentRole,
    DepartmentHeadBehavior,
    EmployeeBehavior,
    GeneralManagerBehavior,
    RoleBehavior,
    create_role_behavior,
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
    "AgentRole",
    "AvailabilityReport",
    "CheckResult",
    "CheckStatus",
    "CollaborationStrategy",
    "CompanyPlan",
    "DepartmentCandidate",
    "DepartmentHeadBehavior",
    "DepartmentPlanTask",
    "DepartmentResponsibilityProfile",
    "EmployeeBehavior",
    "GeneralManagerBehavior",
    "PlanValidationIssue",
    "RoleBehavior",
    "SubTask",
    "WorkflowPhase",
    "WorkflowStep",
    "WorkflowTemplate",
    "ConfirmPlanCommand",
    "confirm_and_dispatch",
    "create_role_behavior",
    "create_subtasks",
    "generate_company_plan",
    "generate_company_review",
    "generate_department_report",
    "generate_final_report",
    "get_next_steps",
    "get_workflow_template",
    "list_workflow_templates",
    "match_departments",
    "run_availability_checks",
    "validate_plan",
]
