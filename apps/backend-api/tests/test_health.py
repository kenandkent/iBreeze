"""Health check endpoint tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestHealthEndpoints:
    async def test_liveness(self, client: AsyncClient):
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_readiness(self, client: AsyncClient):
        resp = await client.get("/health/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ready"
        assert body["database"] == "connected"

    async def test_readiness_no_auth_required(self, client: AsyncClient):
        resp = await client.get("/health/ready")
        assert resp.status_code == 200

    async def test_liveness_no_auth_required(self, client: AsyncClient):
        resp = await client.get("/health/live")
        assert resp.status_code == 200
