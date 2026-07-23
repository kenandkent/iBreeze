"""Authentication routers."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.auth.schemas import (
    AdminLoginResponse,
    AuthKeysResponse,
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from ibreeze_backend.auth.service import (
    admin_login,
    change_password,
    get_auth_keys,
    login,
    logout,
    logout_all,
    refresh_tokens,
    register,
)
from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])
admin_router = APIRouter(prefix="/admin/api/v1/auth", tags=["admin-auth"])


def _extract_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )
    return auth[7:]


@router.post(
    "/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED
)
async def register_endpoint(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    if request.password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match",
        )
    try:
        await register(db, request.email, request.password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    result = await login(db, request.email, request.password, "app")
    return {
        "access_token": result["access_token"],
        "token_type": result["token_type"],
    }


@router.post("/login", response_model=LoginResponse)
async def login_endpoint(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        return await login(db, request.email, request.password, "app")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_endpoint(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        result = await refresh_tokens(db, request.refresh_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    return {
        "access_token": result["access_token"],
        "token_type": result["token_type"],
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> None:
    token = _extract_token(request)
    await logout(db, token)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all_endpoint(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
) -> None:
    await logout_all(db, current_user.id)


@router.post("/change-password", response_model=TokenResponse)
async def change_password_endpoint(
    request: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
) -> dict:
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match",
        )
    try:
        return await change_password(
            db, current_user.id, request.old_password, request.new_password
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/keys", response_model=AuthKeysResponse)
async def get_keys_endpoint(
    _current_user=Depends(get_current_user),
) -> dict:
    return get_auth_keys()


# Admin endpoints


@admin_router.post("/login", response_model=AdminLoginResponse)
async def admin_login_endpoint(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        return await admin_login(db, request.email, request.password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@admin_router.post("/refresh", response_model=TokenResponse)
async def admin_refresh_endpoint(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    try:
        result = await refresh_tokens(db, request.refresh_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    return {
        "access_token": result["access_token"],
        "token_type": result["token_type"],
    }


@admin_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def admin_logout_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    _current_user=Depends(get_current_user),
) -> None:
    token = _extract_token(request)
    await logout(db, token)


@admin_router.post("/change-password", response_model=TokenResponse)
async def admin_change_password_endpoint(
    request: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
) -> dict:
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match",
        )
    try:
        return await change_password(
            db, current_user.id, request.old_password, request.new_password
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
