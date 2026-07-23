"""Idempotency middleware."""
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp
from sqlalchemy import select

from ibreeze_backend.db.session import async_session_factory
from ibreeze_backend.models.idempotency_key import IdempotencyKey
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
                    select(IdempotencyKey).where(
                        IdempotencyKey.key == idempotency_key
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    if existing.expires_at < datetime.now(timezone.utc):
                        await session.delete(existing)
                        await session.commit()
                    elif existing.response_body and body_hash == existing.response_body:
                        return JSONResponse(
                            status_code=existing.response_status,
                            content=json.loads(existing.response_body),
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

                response_body = await _read_response_body(response)
                try:
                    parsed = json.loads(response_body) if response_body else None
                except (json.JSONDecodeError, ValueError):
                    parsed = None

                entry = IdempotencyKey(
                    id=uuid.uuid4(),
                    key=idempotency_key,
                    response_status=response.status_code,
                    response_body=body_hash,
                    expires_at=datetime.now(timezone.utc) + _IDEMPOTENCY_TTL,
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
