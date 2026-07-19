"""Context Pipeline - 按固定序拼装上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContextSection:
    name: str
    content: str
    order: int


class ContextBuilder:
    FIXED_ORDER = [
        "employee_identity",
        "workflow_context",
        "capability_context",
        "retrieved_knowledge",
        "runtime_variables",
        "user_input",
    ]

    def build(
        self,
        employee: dict,
        task_context: dict,
        capability_snapshot: dict,
        retrieved_knowledge: list[dict],
    ) -> list[ContextSection]:
        """按固定序拼装上下文。"""
        sections: dict[str, ContextSection] = {}

        sections["employee_identity"] = ContextSection(
            name="employee_identity",
            content=self._format_employee(employee),
            order=self.FIXED_ORDER.index("employee_identity"),
        )

        sections["workflow_context"] = ContextSection(
            name="workflow_context",
            content=self._format_workflow(task_context),
            order=self.FIXED_ORDER.index("workflow_context"),
        )

        sections["capability_context"] = ContextSection(
            name="capability_context",
            content=self._format_capability(capability_snapshot),
            order=self.FIXED_ORDER.index("capability_context"),
        )

        sections["retrieved_knowledge"] = ContextSection(
            name="retrieved_knowledge",
            content=self._format_knowledge(retrieved_knowledge),
            order=self.FIXED_ORDER.index("retrieved_knowledge"),
        )

        runtime_vars = task_context.get("runtime_variables", {})
        sections["runtime_variables"] = ContextSection(
            name="runtime_variables",
            content=self._format_runtime_vars(runtime_vars),
            order=self.FIXED_ORDER.index("runtime_variables"),
        )

        user_input = task_context.get("user_input", "")
        sections["user_input"] = ContextSection(
            name="user_input",
            content=str(user_input),
            order=self.FIXED_ORDER.index("user_input"),
        )

        return [sections[name] for name in self.FIXED_ORDER]

    def _format_employee(self, employee: dict) -> str:
        parts = []
        if employee.get("employee_id"):
            parts.append(f"Employee ID: {employee['employee_id']}")
        if employee.get("name"):
            parts.append(f"Name: {employee['name']}")
        if employee.get("role"):
            parts.append(f"Role: {employee['role']}")
        if employee.get("department_id"):
            parts.append(f"Department: {employee['department_id']}")
        if employee.get("company_id"):
            parts.append(f"Company: {employee['company_id']}")
        return "; ".join(parts)

    def _format_workflow(self, task_context: dict) -> str:
        parts = []
        if task_context.get("task_id"):
            parts.append(f"Task ID: {task_context['task_id']}")
        if task_context.get("conversation_id"):
            parts.append(f"Conversation: {task_context['conversation_id']}")
        if task_context.get("workflow_step"):
            parts.append(f"Step: {task_context['workflow_step']}")
        return "; ".join(parts)

    def _format_capability(self, capability_snapshot: dict) -> str:
        parts = []
        if capability_snapshot.get("capability_id"):
            parts.append(f"Capability: {capability_snapshot['capability_id']}")
        if capability_snapshot.get("version"):
            parts.append(f"Version: {capability_snapshot['version']}")
        if capability_snapshot.get("skills"):
            skill_ids = [s.get("skill_id", "") for s in capability_snapshot["skills"]]
            parts.append(f"Skills: {', '.join(skill_ids)}")
        return "; ".join(parts)

    def _format_knowledge(self, retrieved_knowledge: list[dict]) -> str:
        if not retrieved_knowledge:
            return ""
        parts = []
        for item in retrieved_knowledge:
            kid = item.get("knowledge_id", "")
            score = item.get("score", "")
            snippet = item.get("snippet", "")
            parts.append(f"[{kid}] score={score}: {snippet}")
        return "\n".join(parts)

    def _format_runtime_vars(self, runtime_vars: dict) -> str:
        if not runtime_vars:
            return ""
        return "; ".join(f"{k}={v}" for k, v in runtime_vars.items())
