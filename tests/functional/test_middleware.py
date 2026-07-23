"""Middleware tests — audit middleware, idempotency middleware.

Covers design spec sections:
- G.13 Middleware (audit logging, idempotency)
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAuditMiddleware:
    """Audit logging middleware."""

    @pytest.mark.asyncio
    async def test_audit_middleware_records_request(self):
        from ibreeze_backend.middleware.audit import AuditMiddleware

        app = MagicMock()
        middleware = AuditMiddleware(app)

        request = MagicMock()
        request.url.path = "/api/v1/users"
        request.method = "GET"
        request.headers = {"authorization": "Bearer test.token"}
        request.query_params = ""
        request.client.host = "127.0.0.1"
        request.state = MagicMock()

        response = MagicMock()
        response.status_code = 200

        call_next = AsyncMock(return_value=response)

        with patch("ibreeze_backend.middleware.audit.async_session_factory") as mock_factory, \
             patch("ibreeze_backend.middleware.audit.write_audit_log") as mock_write:
            mock_session = AsyncMock()
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await middleware.dispatch(request, call_next)

            assert result.status_code == 200
            mock_write.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_audit_middleware_skips_health(self):
        from ibreeze_backend.middleware.audit import AuditMiddleware

        app = MagicMock()
        middleware = AuditMiddleware(app)

        request = MagicMock()
        request.url.path = "/health"
        request.method = "GET"
        request.state = MagicMock()

        response = MagicMock()
        response.status_code = 200

        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)
        assert result.status_code == 200


class TestIdempotencyMiddleware:
    """Idempotency middleware."""

    @pytest.mark.asyncio
    async def test_idempotency_middleware_first_request(self):
        from ibreeze_backend.middleware.idempotency import IdempotencyMiddleware

        app = MagicMock()
        middleware = IdempotencyMiddleware(app)

        request = MagicMock()
        request.method = "POST"
        request.headers = {"Idempotency-Key": "key-123"}
        request.url.path = "/api/test"
        request.body = AsyncMock(return_value=b'{"data": "test"}')

        response = MagicMock()
        response.status_code = 200

        call_next = AsyncMock(return_value=response)

        with patch("ibreeze_backend.middleware.idempotency.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await middleware.dispatch(request, call_next)
            assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_idempotency_middleware_duplicate_request_returns_409(self):
        from ibreeze_backend.middleware.idempotency import IdempotencyMiddleware

        app = MagicMock()
        middleware = IdempotencyMiddleware(app)

        request = MagicMock()
        request.method = "POST"
        request.headers = {"Idempotency-Key": "key-123"}
        request.url.path = "/api/test"

        existing = MagicMock()
        existing.key = "key-123"
        existing.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        existing.response_body = "different_hash"
        existing.response_status = 200

        with patch("ibreeze_backend.middleware.idempotency.async_session_factory") as mock_factory, \
             patch("ibreeze_backend.middleware.idempotency._hash_body") as mock_hash:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = existing
            mock_session.execute.return_value = mock_result
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_hash.return_value = "different_hash_2"

            result = await middleware.dispatch(request, AsyncMock())
            assert result.status_code == 409

    @pytest.mark.asyncio
    async def test_idempotency_middleware_different_body_different_key(self):
        from ibreeze_backend.middleware.idempotency import IdempotencyMiddleware

        app = MagicMock()
        middleware = IdempotencyMiddleware(app)

        request = MagicMock()
        request.method = "POST"
        request.headers = {"Idempotency-Key": "key-456"}
        request.url.path = "/api/test"
        request.body = AsyncMock(return_value=b'{"data": "new"}')

        response = MagicMock()
        response.status_code = 200

        call_next = AsyncMock(return_value=response)

        with patch("ibreeze_backend.middleware.idempotency.async_session_factory") as mock_factory:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await middleware.dispatch(request, call_next)
            assert result.status_code == 200
