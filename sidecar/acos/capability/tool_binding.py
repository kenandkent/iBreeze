"""Tool Binding 四步校验链（对接 PermissionEngine）。

设计 §11.4：ACL → Workspace → Capability → Runtime Policy。
Step 1 现在真正调用 PermissionEngine.authorize() 执行结构化 ACL 判断，
而非仅读 employee.allowed_tools。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCallResult:
    allowed: bool
    error_code: str = ""
    tool_call_hash: str = ""
    matched_rule: str = ""
    requires_approval: bool = False


class ToolBindingValidator:
    """四步校验链：ACL → Workspace → Capability → Runtime Policy。"""

    def __init__(self, permission_engine: Any = None) -> None:
        """permission_engine: PermissionEngine 实例（可选，缺省走轻量本地检查）。"""
        self._perm = permission_engine

    async def validate_tool_call(
        self,
        employee: Any,
        workspace: Any,
        capability_snapshot: dict[str, Any],
        tool_call: dict[str, Any],
        company_id: str = "",
        resource_type: str = "tool",
        resource_id: str = "",
    ) -> ToolCallResult:
        """执行四步校验。"""
        acl_result = await self._check_acl(
            employee, tool_call, company_id, resource_type, resource_id,
        )
        if not acl_result.allowed:
            return acl_result

        ws_result = await self._check_workspace(workspace, tool_call)
        if not ws_result.allowed:
            return ws_result

        cap_result = await self._check_capability(capability_snapshot, tool_call)
        if not cap_result.allowed:
            return cap_result

        return await self._check_runtime_policy(tool_call)

    async def _check_acl(
        self,
        employee: Any,
        tool_call: dict[str, Any],
        company_id: str = "",
        resource_type: str = "tool",
        resource_id: str = "",
    ) -> ToolCallResult:
        """ACL 校验：优先走 PermissionEngine.authorize()，降级走本地轻量检查。"""
        if employee is None:
            return ToolCallResult(
                allowed=False, error_code="AUTH-NO-EMPLOYEE", matched_rule="acl_check",
            )

        employee_status = getattr(employee, "status", None)
        if employee_status and employee_status not in ("active", "suspended"):
            return ToolCallResult(
                allowed=False, error_code="AUTH-EMPLOYEE-INACTIVE", matched_rule="acl_check",
            )

        tool_name = tool_call.get("tool_name", "")

        # 有 PermissionEngine 时走结构化授权
        if self._perm is not None and company_id:
            employee_id = getattr(employee, "employee_id", "") or getattr(employee, "id", "")
            target_id = resource_id or tool_name
            try:
                result = await self._perm.authorize(
                    employee_id=employee_id,
                    company_id=company_id,
                    resource_type=resource_type,
                    resource_id=target_id,
                    action="execute",
                )
                if result.get("decision") != "allow":
                    return ToolCallResult(
                        allowed=False,
                        error_code="AUTH-TOOL-DENIED",
                        matched_rule=result.get("matched_rule", "perm_engine_deny"),
                    )
                return ToolCallResult(
                    allowed=True,
                    matched_rule=result.get("matched_rule", "perm_engine_allow"),
                )
            except Exception:
                pass  # 降级到轻量本地检查

        # 降级：employee.allowed_tools 列表
        allowed_tools = getattr(employee, "allowed_tools", None)
        if allowed_tools is not None and tool_name not in allowed_tools:
            return ToolCallResult(
                allowed=False, error_code="AUTH-TOOL-DENIED", matched_rule="acl_check",
            )
        return ToolCallResult(allowed=True, matched_rule="acl_check")

    async def _check_workspace(self, workspace: Any, tool_call: dict[str, Any]) -> ToolCallResult:
        """Workspace 校验：检查工具是否在工作区白名单中。"""
        if workspace is None:
            return ToolCallResult(allowed=True, matched_rule="workspace_check")
        tool_name = tool_call.get("tool_name", "")
        allowed_tools = getattr(workspace, "allowed_tools", None)
        if allowed_tools is not None and tool_name not in allowed_tools:
            return ToolCallResult(
                allowed=False,
                error_code="WS-TOOL-NOT-IN-WHITELIST",
                matched_rule="workspace_check",
            )
        return ToolCallResult(allowed=True, matched_rule="workspace_check")

    async def _check_capability(
        self,
        capability_snapshot: dict[str, Any],
        tool_call: dict[str, Any],
    ) -> ToolCallResult:
        """Capability 校验：工具是否在 snapshot 中。"""
        tool_name = tool_call.get("tool_name", "")
        allowed_tools = capability_snapshot.get("allowed_tools", [])
        if tool_name not in allowed_tools:
            return ToolCallResult(
                allowed=False,
                error_code="CAP-TOOL-NOT-ALLOWED",
                matched_rule="capability_check",
            )
        return ToolCallResult(allowed=True, matched_rule="capability_check")

    async def _check_runtime_policy(self, tool_call: dict[str, Any]) -> ToolCallResult:
        """Runtime Policy 校验。"""
        tool_call_hash = hashlib.sha256(
            json.dumps(tool_call, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        requires_approval = tool_call.get("requires_approval", False)
        return ToolCallResult(
            allowed=True,
            tool_call_hash=tool_call_hash,
            matched_rule="runtime_policy",
            requires_approval=requires_approval,
        )
