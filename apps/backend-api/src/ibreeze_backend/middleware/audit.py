"""Audit logging middleware."""

import time
import uuid as _uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ibreeze_backend.db.session import async_session_factory
from ibreeze_backend.observability.audit import write_audit_log
from ibreeze_backend.observability.logging_config import get_logger

logger = get_logger(__name__)

_HEALTH_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")


class AuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in _HEALTH_PREFIXES):
            return await call_next(request)

        request_id = str(_uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        user_id = _extract_user_id(request)
        details: dict = {
            "method": request.method,
            "path": path,
            "status_code": response.status_code,
            "duration_ms": round(duration * 1000, 2),
        }
        if not _is_auth_endpoint(path):
            details["query"] = str(request.query_params)

        action = f"{request.method}:{response.status_code}"
        resource_type = _resource_type_from_path(path)

        try:
            async with async_session_factory() as session:
                await write_audit_log(
                    session,
                    actor_user_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=_safe_uuid(_extract_resource_id(path)),
                    request_id=_uuid.UUID(request_id),
                    outcome="success" if 200 <= response.status_code < 400 else "failed",
                    ip_address=_get_client_ip(request),
                )
                await session.commit()
        except Exception:
            logger.exception("Failed to write audit log")

        return response


def _extract_user_id(request: Request) -> _uuid.UUID | None:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        from ibreeze_backend.auth.service import verify_token

        payload = verify_token(auth[7:])
        if payload and "sub" in payload:
            return _uuid.UUID(payload["sub"])
    except Exception:
        pass
    return None


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _is_auth_endpoint(path: str) -> bool:
    return "/auth" in path


def _resource_type_from_path(path: str) -> str:
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) >= 2:
        return parts[1] if parts[0] == "api" else parts[0]
    return "unknown"


def _extract_resource_id(path: str) -> str | None:
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) >= 3:
        return parts[-1]
    return None


def _safe_uuid(value: str | None) -> _uuid.UUID | None:
    if value is None:
        return None
    try:
        return _uuid.UUID(value)
    except ValueError:
        return None
