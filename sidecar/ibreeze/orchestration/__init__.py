"""Company and department orchestration primitives."""

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

__all__ = [
    "CompanyPlan",
    "DepartmentCandidate",
    "DepartmentPlanTask",
    "DepartmentResponsibilityProfile",
    "PlanValidationIssue",
    "match_departments",
    "validate_plan",
]
