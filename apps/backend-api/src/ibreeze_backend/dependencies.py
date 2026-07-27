"""Authentication dependency for FastAPI."""

import uuid

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.api.errors import raise_problem
from ibreeze_backend.auth.service import (
    ADMIN_AUDIENCE,
    APP_AUDIENCE,
    verify_access_token,
)
from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.models.token_family import RefreshTokenFamily
from ibreeze_backend.models.user import User

security = HTTPBearer()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db_session),
) -> User:
    """Get the current authenticated user from JWT token."""
    audience = ADMIN_AUDIENCE if request.url.path.startswith("/admin/api/v1/") else APP_AUDIENCE
    payload = verify_access_token(credentials.credentials, audience)
    if not payload:
        raise_problem(401, "AUTH_TOKEN_EXPIRED", "Invalid or expired token")
    assert payload is not None

    user_id = payload.get("sub")
    if not user_id:
        raise_problem(401, "AUTH_TOKEN_INVALID", "Invalid token payload")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or user.status != "active":
        raise_problem(401, "AUTH_USER_DISABLED", "User not found or inactive")
    assert user is not None

    expected_type = "admin" if audience == ADMIN_AUDIENCE else "app_user"
    if user.user_type != expected_type:
        raise_problem(401, "AUTH_TOKEN_INVALID", "Invalid token audience")

    password_gate_exempt = request.url.path.endswith(("/change-password", "/logout"))
    if user.must_change_password and not password_gate_exempt:
        raise_problem(403, "AUTH_PASSWORD_CHANGE_REQUIRED", "Password change is required")

    if (
        audience == ADMIN_AUDIENCE
        and request.method not in {"GET", "HEAD"}
        and not request.url.path.endswith(("/login", "/refresh"))
    ):
        family_result = await db.execute(
            select(RefreshTokenFamily.id).where(
                RefreshTokenFamily.id == uuid.UUID(payload["sid"]),
                RefreshTokenFamily.user_id == user.id,
                RefreshTokenFamily.revoked_at.is_(None),
            )
        )
        if family_result.scalar_one_or_none() is None:
            raise_problem(401, "AUTH_SESSION_REVOKED", "Session revoked")

    return user
