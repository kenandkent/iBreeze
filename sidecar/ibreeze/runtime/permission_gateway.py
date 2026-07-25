"""Tool permission decision gateway."""

from __future__ import annotations

from typing import Any


class PermissionDecision:
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


# Default permission rules by tool category.
DEFAULT_RULES: dict[str, str] = {
    "read": PermissionDecision.ALLOW,
    "write": PermissionDecision.ALLOW,
    "edit": PermissionDecision.ALLOW,
    "glob": PermissionDecision.ALLOW,
    "grep": PermissionDecision.ALLOW,
    "bash": PermissionDecision.ASK,
    "shell": PermissionDecision.ASK,
    "delete": PermissionDecision.ASK,
    "exec": PermissionDecision.ASK,
}


def check_permission(
    tool_name: str,
    *,
    company_id: str | None = None,
    workspace_path: str | None = None,
    custom_rules: dict[str, str] | None = None,
) -> str:
    """Check if a tool call is allowed."""
    rules = {**DEFAULT_RULES, **(custom_rules or {})}

    # Exact match
    if tool_name in rules:
        return rules[tool_name]

    # Prefix match
    for prefix, decision in rules.items():
        if tool_name.startswith(prefix):
            return decision

    # Default: ask
    return PermissionDecision.ASK


def is_denied(tool_name: str, **kwargs: Any) -> bool:
    """Check if a tool is explicitly denied."""
    return check_permission(tool_name, **kwargs) == PermissionDecision.DENY


def requires_approval(tool_name: str, **kwargs: Any) -> bool:
    """Check if a tool requires user approval."""
    return check_permission(tool_name, **kwargs) == PermissionDecision.ASK
