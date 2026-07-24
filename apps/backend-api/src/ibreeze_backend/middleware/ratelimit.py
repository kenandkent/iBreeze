"""IP-based rate limiting for auth endpoints."""

import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from ibreeze_backend.observability.logging_config import get_logger

logger = get_logger(__name__)

_AUTH_PATHS = ("/auth/login", "/admin/api/v1/auth/login", "/auth/register")
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 300


# Module-level singleton for test access
_rate_limiter_instance = None


def reset_rate_limiter() -> None:
    if _rate_limiter_instance is not None:
        _rate_limiter_instance._attempts.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._attempts: dict[str, list[float]] = defaultdict(list)
        global _rate_limiter_instance
        _rate_limiter_instance = self

    async def dispatch(self, request: Request, call_next):
        if request.url.path not in _AUTH_PATHS:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.time()
        window_start = now - _WINDOW_SECONDS

        timestamps = self._attempts[client_ip]
        timestamps[:] = [t for t in timestamps if t > window_start]

        if len(timestamps) >= _MAX_ATTEMPTS:
            logger.warning("Rate limit hit for IP: %s", client_ip)
            return JSONResponse(
                status_code=429,
                content={
                    "type": "about:blank",
                    "title": "Too Many Requests",
                    "status": 429,
                    "code": "RATE_LIMITED",
                    "detail": "Too many login attempts. Please try again later.",
                },
            )

        timestamps.append(now)
        response = await call_next(request)
        return response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
