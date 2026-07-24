"""Request logging middleware."""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from ibreeze_backend.observability.logging_config import get_logger

logger = get_logger("ibreeze.request")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        start = time.monotonic()
        method = request.method
        path = request.url.path
        query = str(request.url.query) if request.url.query else ""

        logger.info(
            "request_start",
            extra={"request_id": request_id, "method": method, "path": path, "query": query},
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "request_exception",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "elapsed_ms": round(elapsed * 1000),
                    "error": str(exc),
                },
            )
            raise

        elapsed = time.monotonic() - start
        logger.info(
            "request_end",
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "status": response.status_code,
                "elapsed_ms": round(elapsed * 1000),
            },
        )
        return response
