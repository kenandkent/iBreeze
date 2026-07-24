"""Middleware tests."""

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.middleware.audit import (
    _extract_resource_id,
    _get_client_ip,
    _is_auth_endpoint,
    _resource_type_from_path,
)
from ibreeze_backend.middleware.ratelimit import RateLimitMiddleware
from ibreeze_backend.models.audit_log import AdminAuditLog as AuditLog

# ---------------------------------------------------------------------------
# Audit middleware helpers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_middleware_logs_request(
    client: AsyncClient, admin_tokens: dict, monkeypatch: pytest.MonkeyPatch, db_engine, db_session: AsyncSession
):
    """Test that the audit middleware writes an audit log for API requests."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(
        "ibreeze_backend.middleware.audit.async_session_factory",
        test_factory,
    )

    await client.get(
        "/admin/api/v1/users",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )

    result = await db_session.execute(select(AuditLog))
    logs = result.scalars().all()
    matching = [record for record in logs if "admin" in (record.resource_type or "")]
    assert len(matching) >= 1

    log = matching[0]
    assert log.action is not None
    assert log.resource_type is not None
    assert log.request_id is not None


@pytest.mark.asyncio
async def test_audit_middleware_skips_health(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    db_engine,
):
    """Test that the audit middleware skips health check endpoints."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(
        "ibreeze_backend.middleware.audit.async_session_factory",
        test_factory,
    )

    mock_write = AsyncMock()
    monkeypatch.setattr("ibreeze_backend.middleware.audit.write_audit_log", mock_write)

    await client.get("/health")

    mock_write.assert_not_called()


def test_extract_resource_id():
    assert _extract_resource_id("/api/v1/users/abc-123") == "abc-123"
    assert _extract_resource_id("/api/v1/users") == "users"
    assert _extract_resource_id("/health") is None


def test_resource_type_from_path():
    assert _resource_type_from_path("/admin/api/v1/users") == "admin"
    assert _resource_type_from_path("/health") == "unknown"


def test_is_auth_endpoint():
    assert _is_auth_endpoint("/auth/login") is True
    assert _is_auth_endpoint("/auth/refresh") is True
    assert _is_auth_endpoint("/admin/api/v1/users") is False


def test_get_client_ip():
    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [(b"x-forwarded-for", b"10.0.0.1, 10.0.0.2")],
            "query_string": b"",
            "client": None,
            "server": ("test", 80),
            "scheme": "http",
        }
    )
    assert _get_client_ip(req) == "10.0.0.1"

    req2 = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
            "client": ("192.168.1.1", 12345),
            "server": ("test", 80),
            "scheme": "http",
        }
    )
    assert _get_client_ip(req2) == "192.168.1.1"

    req3 = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
            "client": None,
            "server": ("test", 80),
            "scheme": "http",
        }
    )
    assert _get_client_ip(req3) == ""


# ---------------------------------------------------------------------------
# Rate-limit middleware
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ratelimit_middleware_blocks_excessive_requests():
    """Test that the rate-limit middleware blocks after 5 attempts."""
    middleware = RateLimitMiddleware(None)

    async def ok_response(request):
        from starlette.responses import JSONResponse

        return JSONResponse(status_code=200, content={"ok": True})

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/login",
        "raw_path": b"/auth/login",
        "headers": [(b"host", b"testserver")],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)

    for i in range(5):
        resp = await middleware.dispatch(request, ok_response)
        assert resp.status_code == 200, f"Request {i + 1} should succeed"

    resp = await middleware.dispatch(request, ok_response)
    assert resp.status_code == 429
    body = resp.body.decode()
    assert "RATE_LIMITED" in body


# ---------------------------------------------------------------------------
# Idempotency middleware
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
def patch_middleware_factories(monkeypatch, db_engine):
    """Patch both audit and idempotency middleware to use the test DB."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    test_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(
        "ibreeze_backend.middleware.audit.async_session_factory",
        test_factory,
    )
    monkeypatch.setattr(
        "ibreeze_backend.middleware.idempotency.async_session_factory",
        test_factory,
    )


@pytest.mark.asyncio
async def test_idempotency_middleware_reuses_response(
    client: AsyncClient,
    admin_tokens: dict,
    patch_middleware_factories,
):
    """The same principal/key/body returns the original write response."""
    key = str(uuid.uuid4())
    headers = {
        "Idempotency-Key": key,
        "Authorization": f"Bearer {admin_tokens['access_token']}",
    }
    body = {
        "email": "idempotent@example.com",
        "display_name": "Idempotent User",
        "password": "Pass1234",
        "user_type": "app_user",
    }

    resp1 = await client.post(
        "/admin/api/v1/users",
        json=body,
        headers=headers,
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/admin/api/v1/users",
        json=body,
        headers=headers,
    )
    assert resp2.status_code == 201
    assert resp2.json() == resp1.json()


@pytest.mark.asyncio
async def test_non_auth_write_requires_uuid_idempotency_key(
    client: AsyncClient,
    admin_tokens: dict,
):
    """Non-authentication writes fail before dispatch without a valid key."""
    from ibreeze_backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as raw_client:
        response = await raw_client.post(
            "/admin/api/v1/users",
            json={
                "email": "missing-key@example.com",
                "display_name": "Missing Key",
                "password": "Pass1234",
                "user_type": "app_user",
            },
            headers={"Authorization": (f"Bearer {admin_tokens['access_token']}")},
        )
        invalid = await raw_client.post(
            "/admin/api/v1/users",
            json={
                "email": "invalid-key@example.com",
                "display_name": "Invalid Key",
                "password": "Pass1234",
                "user_type": "app_user",
            },
            headers={
                "Authorization": (f"Bearer {admin_tokens['access_token']}"),
                "Idempotency-Key": "not-a-uuid",
            },
        )

    assert response.status_code == 400
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "IDEMPOTENCY_KEY_INVALID"


@pytest.mark.asyncio
async def test_idempotency_middleware_conflict_on_different_body(
    client: AsyncClient,
    admin_tokens: dict,
    patch_middleware_factories,
):
    """Test that reusing an idempotency key with a different body returns 409."""
    key = str(uuid.uuid4())

    resp1 = await client.post(
        "/admin/api/v1/users",
        json={
            "email": "user_a@example.com",
            "display_name": "User A",
            "password": "Pass1234",
            "user_type": "app_user",
        },
        headers={"Idempotency-Key": key, "Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert resp1.status_code == 201

    resp2 = await client.post(
        "/admin/api/v1/users",
        json={
            "email": "user_b@example.com",
            "display_name": "User B",
            "password": "Pass5678",
            "user_type": "app_user",
        },
        headers={"Idempotency-Key": key, "Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert resp2.status_code == 409
    data = resp2.json()
    assert data["code"] == "IDEMPOTENCY_CONFLICT"
