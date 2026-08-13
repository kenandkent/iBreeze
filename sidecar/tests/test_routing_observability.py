from __future__ import annotations

import pytest

from ibreeze.observability.routing import RoutingMetrics


def test_routing_metrics_record_only_bounded_labels() -> None:
    metrics = RoutingMetrics()
    metrics.record_decision(mode="smart_single", tier="C1", kind="single", status="succeeded", latency_ms=12)
    metrics.record_attempt(role="single", provider="provider-a", model="binding-a", status="succeeded", latency_ms=9)
    metrics.record_fallback(mode="smart_single", hops=1)
    metrics.record_outcome(purpose="task_execution", model="binding-a", score=1)
    snapshot = metrics.snapshot()
    assert snapshot.counters["routing_decisions_total{kind=single,mode=smart_single,status=succeeded,tier=C1}"] == 1
    assert snapshot.counters["routing_fallback_hops_total{mode=smart_single}"] == 1
    assert snapshot.observations["routing_outcome_score{model=binding-a,purpose=task_execution}"] == (1.0,)


@pytest.mark.parametrize(
    "operation",
    [
        lambda m: m.inc("routing_decisions_total", labels={"prompt": "secret"}),
        lambda m: m.record_attempt(
            role="single", provider="provider", model="model", status="failed", failure_kind="Authorization: secret"
        ),
        lambda m: m.record_outcome(purpose="task_execution", model="model", score=2),
    ],
)
def test_routing_metrics_reject_sensitive_or_invalid_values(operation) -> None:
    with pytest.raises(ValueError):
        operation(RoutingMetrics())
