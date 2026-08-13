"""Coverage tests for ibreeze/observability/routing.py (uncovered branches)."""

from __future__ import annotations

import pytest

from ibreeze.observability.routing import (
    RoutingMetrics,
    _default_metrics,
    get_routing_metrics,
)


class TestRoutingMetricsCoverage:
    def test_inc_unknown_metric_raises(self) -> None:
        with pytest.raises(ValueError, match="ROUTING_METRIC_UNKNOWN"):
            RoutingMetrics().inc("bogus_metric")

    def test_inc_negative_value_raises(self) -> None:
        with pytest.raises(ValueError, match="ROUTING_METRIC_VALUE_INVALID"):
            RoutingMetrics().inc("routing_decisions_total", -1, labels={"mode": "auto"})

    def test_observe_negative_value_raises(self) -> None:
        with pytest.raises(ValueError, match="ROUTING_METRIC_VALUE_INVALID"):
            RoutingMetrics().observe(
                "routing_decision_latency_ms",
                -0.5,
                labels={"mode": "auto", "tier": "fast"},
            )

    def test_observe_memory_is_bounded(self) -> None:
        metrics = RoutingMetrics()
        key = "routing_provider_latency_ms{model=m,provider=p}"
        metrics._observations[key] = [1.0] * 5000
        for _ in range(100):
            metrics.observe("routing_provider_latency_ms", 2.0, labels={"provider": "p", "model": "m"})
        assert len(metrics._observations[key]) == 4096

    def test_record_attempt_without_latency(self) -> None:
        metrics = RoutingMetrics()
        metrics.record_attempt(role="primary", provider="p", model="m", status="accepted")
        snapshot = metrics.snapshot()
        assert snapshot.counters["routing_attempts_total{failure_kind=none,model=m,provider=p,role=primary,status=accepted}"] == 1
        assert "routing_provider_latency_ms" not in snapshot.observations

    def test_record_fallback_negative_hops_raises(self) -> None:
        with pytest.raises(ValueError, match="ROUTING_METRIC_VALUE_INVALID"):
            RoutingMetrics().record_fallback(mode="auto", hops=-1)

    def test_record_quorum_failure(self) -> None:
        metrics = RoutingMetrics()
        metrics.record_quorum_failure(mode="auto")
        assert metrics.snapshot().counters["routing_ensemble_quorum_failures_total{mode=auto}"] == 1


def test_get_routing_metrics_returns_default_registry() -> None:
    assert get_routing_metrics() is _default_metrics
