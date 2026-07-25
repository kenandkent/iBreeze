"""Role-based access control."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


_PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {
        "company.create", "company.read", "company.update", "company.archive",
        "department.create", "department.read", "department.update", "department.archive",
        "employee.create", "employee.read", "employee.update", "employee.transfer",
        "task.read", "task.update", "task.cancel",
        "review.read", "review.submit", "review.resolve",
        "knowledge.read", "knowledge.import", "knowledge.remove",
        "artifact.read", "artifact.create",
        "backup.create", "backup.restore", "backup.read",
        "settings.read", "settings.update",
        "audit.read", "admin.*",
    },
    Role.USER: {
        "company.read",
        "department.read", "department.create", "department.update", "department.delete",
        "employee.read", "employee.create", "employee.update", "employee.delete",
        "employee.transfer", "employee.pause", "employee.resume",
        "task.read", "task.create", "task.update", "task.cancel", "task.confirm",
        "review.read", "review.submit", "review.assign", "review.resolve",
        "knowledge.read", "knowledge.import", "knowledge.archive",
        "artifact.read", "artifact.create",
        "backup.read", "backup.create", "backup.restore",
        "workspace.read", "workspace.create",
        "settings.read", "settings.update",
        "audit.read",
    },
    Role.GUEST: {
        "company.read",
        "department.read",
        "knowledge.read",
    },
}


def check_permission(role: Role, action: str) -> bool:
    """Check if role has permission for action."""
    perms = _PERMISSIONS.get(role, set())
    if action in perms:
        return True
    resource = action.split(".")[0]
    return f"{resource}.*" in perms


def require_permission(role: Role, action: str) -> None:
    """Raise PermissionError if role lacks permission."""
    if not check_permission(role, action):
        raise PermissionError(f"Role {role.value} lacks permission for {action}")
