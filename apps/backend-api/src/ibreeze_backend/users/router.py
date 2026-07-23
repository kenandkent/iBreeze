"""Admin user management router."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.user import User
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

router = APIRouter(prefix="/admin/api/v1/users", tags=["admin-users"])


@router.post(
    "", response_model=UserAdminResponse, status_code=status.HTTP_201_CREATED
)
async def create_user_endpoint(
    user_in: UserAdminCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> User:
    try:
        user = await create_admin_user(
            db,
            email=user_in.email,
            password=user_in.password,
            user_type=user_in.user_type,
            admin_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    return user


@router.get("", response_model=UserAdminListResponse)
async def list_users_endpoint(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user_type: str | None = Query(default=None, pattern="^(admin|app_user)$"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    users, next_cursor, total = await list_users_admin(
        db, cursor=cursor, limit=limit, user_type_filter=user_type
    )
    return {"users": users, "next_cursor": next_cursor, "total": total}


@router.get("/{user_id}", response_model=UserAdminResponse)
async def get_user_endpoint(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> User:
    from ibreeze_backend.services.user_service import get_user

    user = await get_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.patch("/{user_id}", response_model=UserAdminResponse)
async def update_user_endpoint(
    user_id: uuid.UUID,
    user_in: UserAdminUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> User:
    try:
        user = await update_admin_user(
            db,
            user_id=user_id,
            email=user_in.email,
            role=user_in.role,
            is_active=user_in.is_active,
            admin_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_endpoint(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        await delete_admin_user(db, user_id=user_id, admin_user=current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )


@router.post(
    "/{user_id}/reset-password", response_model=UserAdminResponse
)
async def reset_password_endpoint(
    user_id: uuid.UUID,
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> User:
    try:
        user = await reset_password(
            db,
            user_id=user_id,
            new_password=request.new_password,
            admin_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    return user


@router.post("/{user_id}/revoke-sessions")
async def revoke_sessions_endpoint(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        await revoke_sessions(db, user_id=user_id, admin_user=current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    return {"ok": True}
