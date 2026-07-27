"""Tests for in-memory request metrics."""

from __future__ import annotations

import importlib
import time

import pytest

import ibreeze_backend.observability.metrics as metrics_mod


@pytest.fixture(autouse=True)
def reset_metrics():
    importlib.reload(metrics_mod)


class TestMetrics:
    def test_get_metrics_empty(self):
        result = metrics_mod.get_metrics()
        assert result["total_requests"] == 0
        assert result["status_codes"] == {}
        assert result["by_endpoint"] == {}
        assert result["uptime_seconds"] >= 0

    def test_record_single_request(self):
        metrics_mod.record_request(duration=0.5, method="GET", path="/api/test", status_code=200)
        result = metrics_mod.get_metrics()
        assert result["total_requests"] == 1
        assert result["status_codes"] == {200: 1}
        assert result["by_endpoint"]["GET /api/test"]["count"] == 1
        assert result["by_endpoint"]["GET /api/test"]["avg_duration_ms"] == 500.0

    def test_multiple_requests_same_endpoint(self):
        metrics_mod.record_request(duration=0.2, method="POST", path="/api/data", status_code=201)
        metrics_mod.record_request(duration=0.4, method="POST", path="/api/data", status_code=201)
        result = metrics_mod.get_metrics()
        assert result["total_requests"] == 2
        assert result["by_endpoint"]["POST /api/data"]["count"] == 2
        assert result["by_endpoint"]["POST /api/data"]["avg_duration_ms"] == 300.0

    def test_different_endpoints(self):
        metrics_mod.record_request(duration=0.1, method="GET", path="/a", status_code=200)
        metrics_mod.record_request(duration=0.2, method="POST", path="/b", status_code=201)
        result = metrics_mod.get_metrics()
        assert result["total_requests"] == 2
        assert len(result["by_endpoint"]) == 2
        assert result["by_endpoint"]["GET /a"]["count"] == 1
        assert result["by_endpoint"]["POST /b"]["count"] == 1

    def test_status_codes_aggregation(self):
        metrics_mod.record_request(duration=0.1, method="GET", path="/api/test", status_code=200)
        metrics_mod.record_request(duration=0.1, method="GET", path="/api/test", status_code=200)
        metrics_mod.record_request(duration=0.1, method="GET", path="/api/test", status_code=500)
        result = metrics_mod.get_metrics()
        assert result["status_codes"] == {200: 2, 500: 1}

    def test_avg_duration_rounding(self):
        metrics_mod.record_request(duration=0.12345, method="GET", path="/api/test", status_code=200)
        result = metrics_mod.get_metrics()
        assert result["by_endpoint"]["GET /api/test"]["avg_duration_ms"] == 123.45

    def test_uptime_increases(self):
        result1 = metrics_mod.get_metrics()
        time.sleep(0.01)
        result2 = metrics_mod.get_metrics()
        assert result2["uptime_seconds"] >= result1["uptime_seconds"]

    def test_return_type_structure(self):
        metrics_mod.record_request(duration=0.5, method="PUT", path="/api/item", status_code=204)
        result = metrics_mod.get_metrics()
        assert "uptime_seconds" in result
        assert "total_requests" in result
        assert "status_codes" in result
        assert "by_endpoint" in result
        assert isinstance(result["uptime_seconds"], float)
        assert isinstance(result["total_requests"], int)
        assert isinstance(result["status_codes"], dict)
        assert isinstance(result["by_endpoint"], dict)
