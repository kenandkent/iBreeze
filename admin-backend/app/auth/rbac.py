from fastapi import Depends, HTTPException

from app.api.deps import get_current_user
from app.models.admin import AdminUser

ROLE_PERMISSIONS = {
    "super_admin": {"capabilities", "knowledge", "providers", "backends", "governance", "audit", "settings"},
    "platform_admin": {"capabilities", "knowledge", "providers", "backends", "governance", "audit"},
    "company_admin": {"capabilities", "knowledge", "providers", "backends"},
    "viewer": set(),
}


def require_permission(resource: str):
    async def checker(current_user: AdminUser = Depends(get_current_user)) -> AdminUser:
        role = current_user.role
        if resource not in ROLE_PERMISSIONS.get(role, set()):
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return checker
