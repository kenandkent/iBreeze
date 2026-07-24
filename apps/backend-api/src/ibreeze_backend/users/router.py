"""Admin user management router."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.user import User
from ibreeze_backend.observability.logging_config import get_logger
from ibreeze_backend.users.schemas import (
    ResetPasswordRequest,
    UserAdminCreate,
    UserAdminListResponse,
    UserAdminResponse,
    UserAdminUpdate,
)
from ibreeze_backend.users.service import (
    create_admin_user,
    delete_admin_user,
    list_users_admin,
    reset_password,
    revoke_sessions,
    update_admin_user,
)

logger = get_logger("ibreeze.users")
router = APIRouter(prefix="/admin/api/v1/users", tags=["admin-users"])


@router.post("", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_user_endpoint(
    user_in: UserAdminCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> User:
    logger.info(
        "create_user_endpoint_start",
        extra={
            "user_type": user_in.user_type,
            "admin_id": str(current_user.id),
        },
    )
    try:
        user = await create_admin_user(
            db,
            user_type=user_in.user_type,
            username=user_in.username,
            email=str(user_in.email) if user_in.email is not None else None,
            display_name=user_in.display_name,
            password=user_in.password,
            admin_user=current_user,
        )
    except ValueError as e:
        logger.warning("create_user_endpoint_failed", extra={"reason": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.info("create_user_endpoint_success", extra={"user_id": str(user.id)})
    return user


@router.get("", response_model=UserAdminListResponse)
async def list_users_endpoint(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user_type: str | None = Query(default=None, pattern="^(admin|app_user)$"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    logger.info(
        "list_users_endpoint_start",
        extra={"cursor": cursor, "limit": limit, "user_type": user_type, "admin_id": str(current_user.id)},
    )
    users, next_cursor, total = await list_users_admin(db, cursor=cursor, limit=limit, user_type_filter=user_type)
    logger.info("list_users_endpoint_success", extra={"count": len(users), "total": total})
    return {"users": users, "next_cursor": next_cursor, "total": total}


@router.get("/{user_id}", response_model=UserAdminResponse)
async def get_user_endpoint(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> User:
    logger.info("get_user_endpoint_start", extra={"user_id": str(user_id), "admin_id": str(current_user.id)})
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("get_user_endpoint_not_found", extra={"user_id": str(user_id)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserAdminResponse)
async def update_user_endpoint(
    user_id: uuid.UUID,
    user_in: UserAdminUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> User:
    logger.info("update_user_endpoint_start", extra={"user_id": str(user_id), "admin_id": str(current_user.id)})
    try:
        user = await update_admin_user(
            db,
            user_id=user_id,
            username=user_in.username,
            email=str(user_in.email) if user_in.email is not None else None,
            display_name=user_in.display_name,
            status=user_in.status,
            admin_user=current_user,
        )
    except ValueError as e:
        logger.warning("update_user_endpoint_failed", extra={"reason": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.info("update_user_endpoint_success", extra={"user_id": str(user.id)})
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> None:
    logger.info("delete_user_endpoint_start", extra={"user_id": str(user_id), "admin_id": str(current_user.id)})
    try:
        await delete_admin_user(db, user_id=user_id, admin_user=current_user)
    except ValueError as e:
        logger.warning("delete_user_endpoint_failed", extra={"reason": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.info("delete_user_endpoint_success", extra={"user_id": str(user_id)})


@router.post("/{user_id}/reset-password", response_model=UserAdminResponse)
async def reset_password_endpoint(
    user_id: uuid.UUID,
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> User:
    logger.info("reset_password_endpoint_start", extra={"user_id": str(user_id), "admin_id": str(current_user.id)})
    try:
        user = await reset_password(
            db,
            user_id=user_id,
            new_password=request.new_password,
            admin_user=current_user,
        )
    except ValueError as e:
        logger.warning("reset_password_endpoint_failed", extra={"reason": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.info("reset_password_endpoint_success", extra={"user_id": str(user.id)})
    return user


@router.post("/{user_id}/revoke-sessions")
async def revoke_sessions_endpoint(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, bool]:
    logger.info("revoke_sessions_endpoint_start", extra={"user_id": str(user_id), "admin_id": str(current_user.id)})
    try:
        await revoke_sessions(db, user_id=user_id, admin_user=current_user)
    except ValueError as e:
        logger.warning("revoke_sessions_endpoint_failed", extra={"reason": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.info("revoke_sessions_endpoint_success", extra={"user_id": str(user_id)})
    return {"ok": True}
