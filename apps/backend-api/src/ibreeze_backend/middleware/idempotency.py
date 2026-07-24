"""Transactional idempotency for every non-authentication write request."""

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from ibreeze_backend.auth.service import verify_token
from ibreeze_backend.db.session import async_session_factory, request_session
from ibreeze_backend.models.idempotency_key import ApiIdempotency

_IDEMPOTENCY_TTL = timedelta(days=30)
_PROCESSING_TIMEOUT = timedelta(minutes=10)
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _problem(status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "type": "about:blank",
            "title": "Conflict" if status == 409 else "Bad Request",
            "status": status,
            "code": code,
            "detail": detail,
        },
    )


def _is_auth_path(path: str) -> bool:
    return path.startswith("/api/v1/auth/") or path.startswith("/admin/api/v1/auth/")


def _principal_id(request: Request) -> uuid.UUID | None:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    payload = verify_token(authorization[7:])
    if payload is None:
        return None
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        if request.method in _READ_METHODS or _is_auth_path(request.url.path):
            return await call_next(request)

        raw_key = request.headers.get("Idempotency-Key")
        if raw_key is None:
            return _problem(
                400,
                "IDEMPOTENCY_KEY_REQUIRED",
                "Idempotency-Key UUID header is required.",
            )
        try:
            idempotency_key = uuid.UUID(raw_key)
        except ValueError:
            return _problem(
                400,
                "IDEMPOTENCY_KEY_INVALID",
                "Idempotency-Key must be a UUID.",
            )

        principal_user_id = _principal_id(request)
        if principal_user_id is None:
            return _problem(
                400,
                "IDEMPOTENCY_PRINCIPAL_REQUIRED",
                "A valid authenticated principal is required.",
            )

        request_hash = hashlib.sha256(await request.body()).hexdigest()
        now = datetime.now(UTC)
        identity = {
            "principal_user_id": principal_user_id,
            "method": request.method,
            "path": request.url.path,
            "idempotency_key": idempotency_key,
        }

        async with async_session_factory() as session:
            async with session.begin():
                inserted = await session.execute(
                    insert(ApiIdempotency)
                    .values(
                        **identity,
                        request_sha256=request_hash,
                        status="processing",
                        created_at=now,
                        expires_at=now + _IDEMPOTENCY_TTL,
                    )
                    .on_conflict_do_nothing()
                )
                entry = (
                    await session.execute(
                        select(ApiIdempotency)
                        .where(*[getattr(ApiIdempotency, field) == value for field, value in identity.items()])
                        .with_for_update()
                    )
                ).scalar_one()
                is_new = inserted.rowcount == 1

                if not is_new:
                    if entry.request_sha256 != request_hash:
                        return _problem(
                            409,
                            "IDEMPOTENCY_CONFLICT",
                            "Idempotency key was reused with a different request.",
                        )
                    if entry.status in {"completed", "failed"}:
                        return _cached_response(entry)
                    if now - entry.created_at >= _PROCESSING_TIMEOUT:
                        entry.status = "failed"
                        entry.response_status = 500
                        entry.response_content_type = "application/json"
                        entry.response_body = {"code": "IDEMPOTENCY_PROCESSING_ABANDONED"}
                        return _cached_response(entry)
                    return _problem(
                        409,
                        "IDEMPOTENCY_IN_PROGRESS",
                        "The request with this idempotency key is still processing.",
                    )

                token = request_session.set(session)
                try:
                    response = await call_next(request)
                finally:
                    request_session.reset(token)

                body, response = await _materialize_response(response)
                entry.status = "completed" if response.status_code < 500 else "failed"
                entry.response_status = response.status_code
                entry.response_content_type = response.headers.get("content-type", "application/json")[:100]
                entry.response_body = _json_value(body)
                return response


def _json_value(body: bytes) -> object:
    if not body:
        return None
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body.decode("utf-8", errors="replace")


def _cached_response(entry: ApiIdempotency) -> Response:
    body = entry.response_body
    if body is None:
        content = b""
    elif isinstance(body, str):
        content = body.encode("utf-8")
    else:
        content = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Response(
        content=content,
        status_code=entry.response_status or 500,
        media_type=entry.response_content_type or "application/json",
    )


async def _materialize_response(
    response: Response,
) -> tuple[bytes, Response]:
    body = getattr(response, "body", None)
    if body is not None:
        return body, response

    body_iterator = getattr(response, "body_iterator", None)
    if body_iterator is None:
        return b"", response
    chunks = [chunk async for chunk in body_iterator]
    body = b"".join(chunk.encode("utf-8") if isinstance(chunk, str) else chunk for chunk in chunks)
    rebuilt = Response(
        content=body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
        background=response.background,
    )
    return body, rebuilt
