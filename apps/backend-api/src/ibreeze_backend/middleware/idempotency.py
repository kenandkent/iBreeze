"""Idempotency middleware – aligned with G.3 api_idempotency schema."""
import hashlib
import json
import uuid as _uuid
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp
from sqlalchemy import select

from ibreeze_backend.db.session import async_session_factory
from ibreeze_backend.models.idempotency_key import ApiIdempotency
from ibreeze_backend.observability.logging_config import get_logger

logger = get_logger(__name__)

_IDEMPOTENCY_TTL = timedelta(hours=24)
_SKIP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if request.method in _SKIP_METHODS:
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)

        body_hash = await _hash_body(request)

        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(ApiIdempotency).where(
                        ApiIdempotency.idempotency_key == _uuid.UUID(idempotency_key),
                        ApiIdempotency.method == request.method,
                        ApiIdempotency.path == request.url.path,
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    now_str = datetime.now(UTC).isoformat()
                    if existing.expires_at < now_str:
                        await session.delete(existing)
                        await session.commit()
                    elif existing.request_sha256 == body_hash:
                        return JSONResponse(
                            status_code=existing.response_status or 200,
                            content=json.loads(existing.response_body) if existing.response_body else {},
                        )
                    else:
                        return JSONResponse(
                            status_code=409,
                            content={
                                "type": "about:blank",
                                "title": "Conflict",
                                "status": 409,
                                "code": "IDEMPOTENCY_CONFLICT",
                                "detail": "Idempotency key reused with different request body.",
                            },
                        )

                response = await call_next(request)

                response_body_bytes = await _read_response_body(response)
                response_body_str = response_body_bytes.decode() if response_body_bytes else None

                entry = ApiIdempotency(
                    id=_uuid.uuid4(),
                    principal_user_id=_uuid.UUID("00000000-0000-0000-0000-000000000000"),
                    method=request.method,
                    path=request.url.path,
                    idempotency_key=_uuid.UUID(idempotency_key),
                    request_sha256=body_hash,
                    status="completed",
                    response_status=response.status_code,
                    response_body=response_body_str,
                    created_at=datetime.now(UTC).isoformat(),
                    expires_at=(datetime.now(UTC) + _IDEMPOTENCY_TTL).isoformat(),
                )
                session.add(entry)
                await session.commit()

                return response
        except Exception:
            logger.exception("Idempotency middleware error")
            return await call_next(request)


async def _hash_body(request: Request) -> str:
    body = await request.body()
    return hashlib.sha256(body).hexdigest() if body else ""


async def _read_response_body(response: Response) -> bytes | None:
    if hasattr(response, "body"):
        return response.body
    return None
