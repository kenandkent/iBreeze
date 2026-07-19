"""Tool Binding 四步校验链。"""

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

    async def validate_tool_call(
        self,
        employee: Any,
        workspace: Any,
        capability_snapshot: dict[str, Any],
        tool_call: dict[str, Any],
    ) -> ToolCallResult:
        """执行四步校验。

        1. ACL 校验（检查员工是否有工具访问权限）
        2. Workspace 校验（检查工具是否在工作区白名单中）
        3. Capability 校验（工具是否在 snapshot 中）
        4. Runtime Policy 校验（返回 requires_approval + hash）
        """
        # Step 1: ACL 校验
        acl_result = await self._check_acl(employee, tool_call)
        if not acl_result.allowed:
            return acl_result

        # Step 2: Workspace 校验
        ws_result = await self._check_workspace(workspace, tool_call)
        if not ws_result.allowed:
            return ws_result

        # Step 3: Capability 校验
        cap_result = await self._check_capability(capability_snapshot, tool_call)
        if not cap_result.allowed:
            return cap_result

        # Step 4: Runtime Policy 校验
        return await self._check_runtime_policy(tool_call)

    async def _check_acl(self, employee: Any, tool_call: dict[str, Any]) -> ToolCallResult:
        """ACL 校验：检查员工状态和工具访问权限。"""
        if employee is None:
            return ToolCallResult(
                allowed=False,
                error_code="AUTH-NO-EMPLOYEE",
                matched_rule="acl_check",
            )
        employee_status = getattr(employee, "status", None)
        if employee_status and employee_status not in ("active", "suspended"):
            return ToolCallResult(
                allowed=False,
                error_code="AUTH-EMPLOYEE-INACTIVE",
                matched_rule="acl_check",
            )
        tool_name = tool_call.get("tool_name", "")
        allowed_tools = getattr(employee, "allowed_tools", None)
        if allowed_tools is not None and tool_name not in allowed_tools:
            return ToolCallResult(
                allowed=False,
                error_code="AUTH-TOOL-DENIED",
                matched_rule="acl_check",
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
