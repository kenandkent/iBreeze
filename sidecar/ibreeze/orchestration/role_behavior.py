"""Role behavior implementations for General Manager, Department Head, and Employee."""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class AgentRole(StrEnum):
    GENERAL_MANAGER = "general_manager"
    DEPARTMENT_HEAD = "department_head"
    EMPLOYEE = "employee"


class RoleBehavior:
    """Base class for role-specific behaviors."""

    def __init__(self, role: AgentRole, employee_id: str, company_id: str) -> None:
        self.role = role
        self.employee_id = employee_id
        self.company_id = company_id

    async def analyze_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Analyze a task and determine approach."""
        raise NotImplementedError


class GeneralManagerBehavior(RoleBehavior):
    """CEO/General Manager: analyze -> plan -> dispatch -> summarize."""

    def __init__(self, employee_id: str, company_id: str) -> None:
        super().__init__(AgentRole.GENERAL_MANAGER, employee_id, company_id)

    async def analyze_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Analyze company-level task and create plan."""
        return {
            "action": "create_plan",
            "task_id": task.get("id"),
            "analysis": f"总经理分析任务: {task.get('title', '')}",
            "requires_plan_confirmation": True,
        }

    async def dispatch_to_departments(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        """Dispatch plan items to relevant departments."""
        dispatches: list[dict[str, Any]] = []
        for section in plan.get("sections", []):
            if section.get("type") == "department_tasks":
                dispatches.append({
                    "department_id": section.get("department_id"),
                    "tasks": section.get("planned_tasks", []),
                })
        return dispatches

    async def summarize_results(
        self, department_reports: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Summarize department results into company report."""
        return {
            "action": "summarize",
            "department_count": len(department_reports),
            "summary": f"汇总 {len(department_reports)} 个部门的执行结果",
        }


class DepartmentHeadBehavior(RoleBehavior):
    """Department Head: organize department work based on responsibilities."""

    def __init__(self, employee_id: str, company_id: str, department_id: str) -> None:
        super().__init__(AgentRole.DEPARTMENT_HEAD, employee_id, company_id)
        self.department_id = department_id

    async def analyze_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Analyze department task and create sub-tasks."""
        return {
            "action": "organize_work",
            "task_id": task.get("id"),
            "department_id": self.department_id,
            "analysis": f"部门负责人组织本部门工作: {task.get('title', '')}",
            "sub_tasks": [],
        }


class EmployeeBehavior(RoleBehavior):
    """Employee: execute assigned tasks."""

    def __init__(self, employee_id: str, company_id: str) -> None:
        super().__init__(AgentRole.EMPLOYEE, employee_id, company_id)

    async def analyze_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Analyze assigned task and execute."""
        return {
            "action": "execute",
            "task_id": task.get("id"),
            "analysis": f"员工执行任务: {task.get('title', '')}",
        }


def create_role_behavior(
    role: str,
    employee_id: str,
    company_id: str,
    department_id: str | None = None,
) -> RoleBehavior:
    """Factory function to create role behavior."""
    if role == AgentRole.GENERAL_MANAGER or role == "general_manager":
        return GeneralManagerBehavior(employee_id, company_id)
    elif role == AgentRole.DEPARTMENT_HEAD or role == "department_head":
        return DepartmentHeadBehavior(employee_id, company_id, department_id or "")
    else:
        return EmployeeBehavior(employee_id, company_id)
