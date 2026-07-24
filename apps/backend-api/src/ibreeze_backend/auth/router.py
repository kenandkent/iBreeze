"""Authentication HTTP routes defined by design section G.11."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.api.schemas import success_response
from ibreeze_backend.auth.schemas import (
    AuthKeysResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    SessionResponse,
)
from ibreeze_backend.auth.service import (
    ADMIN_AUDIENCE,
    APP_AUDIENCE,
    SESSION_SECONDS,
    admin_login,
    change_password,
    get_auth_keys,
    login,
    logout,
    logout_all,
    refresh_tokens,
    register,
    user_payload,
    verify_access_token,
)
from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.user import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
admin_router = APIRouter(prefix="/admin/api/v1/auth", tags=["admin-auth"])

_ADMIN_REFRESH_COOKIE = "ibreeze_admin_refresh"


def _request_id(request: Request) -> str:
    return str(request.state.request_id)


def _set_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _extract_access_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )
    return authorization[7:]


def _session_id(request: Request, audience: str) -> uuid.UUID:
    payload = verify_access_token(_extract_access_token(request), audience)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return uuid.UUID(payload["sid"])


def _set_admin_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=_ADMIN_REFRESH_COOKIE,
        value=refresh_token,
        max_age=SESSION_SECONDS,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/admin/api/v1/auth",
    )


def _clear_admin_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_ADMIN_REFRESH_COOKIE,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/admin/api/v1/auth",
    )


def _admin_public_session(result: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in result.items() if key not in {"refresh_token", "refresh_token_expires_in"}}


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_endpoint(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    try:
        user = await register(db, str(body.email), body.password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return success_response(
        {"user": user_payload(user)},
        _request_id(request),
    )


@router.post(
    "/login",
    response_model=SessionResponse,
    response_model_exclude_none=True,
)
async def login_endpoint(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    try:
        result = await login(
            db,
            body.identifier,
            body.password,
            APP_AUDIENCE,
            body.device_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    _set_no_store(response)
    return success_response(result, _request_id(request))


@router.post(
    "/refresh",
    response_model=SessionResponse,
    response_model_exclude_none=True,
)
async def refresh_endpoint(
    body: RefreshRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    try:
        result = await refresh_tokens(db, body.refresh_token, APP_AUDIENCE)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    _set_no_store(response)
    return success_response(result, _request_id(request))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> None:
    await logout(db, _extract_access_token(request), APP_AUDIENCE)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all_endpoint(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> None:
    await logout_all(db, current_user.id)


@router.post(
    "/change-password",
    response_model=SessionResponse,
    response_model_exclude_none=True,
)
async def change_password_endpoint(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    try:
        result = await change_password(
            db,
            current_user.id,
            body.current_password,
            body.new_password,
            _session_id(request, APP_AUDIENCE),
            APP_AUDIENCE,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    _set_no_store(response)
    return success_response(result, _request_id(request))


@router.get("/keys", response_model=AuthKeysResponse)
async def get_keys_endpoint(request: Request) -> dict[str, object]:
    return success_response(get_auth_keys(), _request_id(request))


@admin_router.post(
    "/login",
    response_model=SessionResponse,
    response_model_exclude_none=True,
)
async def admin_login_endpoint(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    try:
        result = await admin_login(
            db,
            body.identifier,
            body.password,
            body.device_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    _set_admin_refresh_cookie(response, str(result["refresh_token"]))
    _set_no_store(response)
    return success_response(_admin_public_session(result), _request_id(request))


@admin_router.post(
    "/refresh",
    response_model=SessionResponse,
    response_model_exclude_none=True,
)
async def admin_refresh_endpoint(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    refresh_token = request.cookies.get(_ADMIN_REFRESH_COOKIE)
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )
    try:
        result = await refresh_tokens(db, refresh_token, ADMIN_AUDIENCE)
    except ValueError as exc:
        _clear_admin_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    _set_admin_refresh_cookie(response, str(result["refresh_token"]))
    _set_no_store(response)
    return success_response(_admin_public_session(result), _request_id(request))


@admin_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def admin_logout_endpoint(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    _current_user: User = Depends(get_current_user),
) -> None:
    await logout(db, _extract_access_token(request), ADMIN_AUDIENCE)
    _clear_admin_refresh_cookie(response)


@admin_router.post(
    "/change-password",
    response_model=SessionResponse,
    response_model_exclude_none=True,
)
async def admin_change_password_endpoint(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    try:
        result = await change_password(
            db,
            current_user.id,
            body.current_password,
            body.new_password,
            _session_id(request, ADMIN_AUDIENCE),
            ADMIN_AUDIENCE,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    _set_admin_refresh_cookie(response, str(result["refresh_token"]))
    _set_no_store(response)
    return success_response(_admin_public_session(result), _request_id(request))
