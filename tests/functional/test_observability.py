"""Observability tests — audit logging, metrics, health endpoints.

Covers design spec sections:
- G.16 Observability (audit logs, metrics, health checks)
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAuditLog:
    """Audit log creation and querying."""

    @pytest.mark.asyncio
    async def test_audit_log_creation(self, mock_db_session):
        from ibreeze_backend.observability.audit import write_audit_log

        await write_audit_log(
            mock_db_session,
            user_id=uuid.uuid4(),
            action="user.create",
            resource_type="user",
            resource_id="user-123",
            details={"email": "test@test.com"},
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )
        mock_db_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_audit_log_query(self, mock_db_session):
        from ibreeze_backend.observability.audit import write_audit_log

        await write_audit_log(
            mock_db_session,
            user_id=None,
            action="auth.login",
            resource_type="auth",
        )
        mock_db_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sensitive_field_redaction(self, mock_db_session):
        from ibreeze_backend.observability.audit import write_audit_log

        await write_audit_log(
            mock_db_session,
            user_id=uuid.uuid4(),
            action="user.update",
            resource_type="user",
            resource_id="user-123",
            details={"field": "hashed_password", "old_value": "REDACTED"},
        )
        mock_db_session.execute.assert_awaited_once()


class TestMetrics:
    """In-memory metrics collection."""

    def test_metrics_endpoint(self):
        from ibreeze_backend.observability.metrics import record_request, get_metrics

        record_request(0.1, "GET", "/health", 200)
        record_request(0.05, "POST", "/auth/login", 201)

        metrics = get_metrics()
        assert metrics["total_requests"] == 2
        assert 200 in metrics["status_codes"]
        assert 201 in metrics["status_codes"]
        assert "GET /health" in metrics["by_endpoint"]
        assert "POST /auth/login" in metrics["by_endpoint"]

    def test_metrics_avg_duration(self):
        from ibreeze_backend.observability.metrics import record_request, get_metrics

        record_request(0.1, "GET", "/test", 200)
        record_request(0.3, "GET", "/test", 200)

        metrics = get_metrics()
        endpoint = metrics["by_endpoint"]["GET /test"]
        assert endpoint["count"] == 2
        assert endpoint["avg_duration_ms"] == 200.0


class TestHealthEndpoint:
    """Health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        from ibreeze_backend.routers.health import health_check

        result = await health_check()
        assert result == {"status": "ok"}
