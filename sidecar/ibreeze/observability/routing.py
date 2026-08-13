"""In-process metrics for the intelligent routing subsystem.

The desktop application does not require a Prometheus dependency.  This
module provides a small, deterministic counter/histogram registry which can
be exported by the existing health endpoint or inspected in tests.  It only
accepts bounded identifiers/enumerations as labels; prompts, model output,
credentials and arbitrary provider payloads are rejected before they can
reach metrics or logs.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock

ROUTING_METRICS = (
    "routing_decisions_total",
    "routing_attempts_total",
    "routing_decision_latency_ms",
    "routing_provider_latency_ms",
    "routing_fallback_hops_total",
    "routing_ensemble_quorum_failures_total",
    "routing_outcome_score",
)

_ALLOWED_LABELS = {
    "routing_decisions_total": {"mode", "tier", "kind", "status"},
    "routing_attempts_total": {"role", "provider", "model", "status", "failure_kind"},
    "routing_decision_latency_ms": {"mode", "tier"},
    "routing_provider_latency_ms": {"provider", "model"},
    "routing_fallback_hops_total": {"mode"},
    "routing_ensemble_quorum_failures_total": {"mode"},
    "routing_outcome_score": {"purpose", "model"},
}


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    counters: Mapping[str, float]
    observations: Mapping[str, tuple[float, ...]]


def _key(name: str, labels: Mapping[str, str]) -> str:
    suffix = ",".join(f"{k}={labels[k]}" for k in sorted(labels))
    return f"{name}{{{suffix}}}" if suffix else name


class RoutingMetrics:
    """Thread-safe, bounded metric registry for one Sidecar process."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: defaultdict[str, float] = defaultdict(float)
        self._observations: defaultdict[str, list[float]] = defaultdict(list)

    def _labels(self, name: str, labels: Mapping[str, str] | None) -> dict[str, str]:
        if name not in ROUTING_METRICS:
            raise ValueError("ROUTING_METRIC_UNKNOWN")
        normalized = {str(k): str(v) for k, v in (labels or {}).items()}
        if set(normalized) - _ALLOWED_LABELS[name]:
            raise ValueError("ROUTING_METRIC_LABEL_INVALID")
        for value in normalized.values():
            lowered = value.casefold()
            if (
                not value
                or len(value) > 128
                or any(ch in value for ch in "\r\n{}")
                or any(secret_word in lowered for secret_word in ("authorization", "api_key", "bearer", "secret", "prompt", "credential"))
            ):
                raise ValueError("ROUTING_METRIC_LABEL_INVALID")
        return normalized

    def inc(self, name: str, value: float = 1, *, labels: Mapping[str, str] | None = None) -> None:
        if value < 0:
            raise ValueError("ROUTING_METRIC_VALUE_INVALID")
        key = _key(name, self._labels(name, labels))
        with self._lock:
            self._counters[key] += float(value)

    def observe(self, name: str, value: float, *, labels: Mapping[str, str] | None = None) -> None:
        if value < 0:
            raise ValueError("ROUTING_METRIC_VALUE_INVALID")
        key = _key(name, self._labels(name, labels))
        with self._lock:
            values = self._observations[key]
            values.append(float(value))
            # Keep memory bounded while preserving recent latency/outcome data.
            if len(values) > 4096:
                del values[: len(values) - 4096]

    def record_decision(self, *, mode: str, tier: str, kind: str, status: str, latency_ms: float) -> None:
        labels = {"mode": mode, "tier": tier, "kind": kind, "status": status}
        self.inc("routing_decisions_total", labels=labels)
        self.observe("routing_decision_latency_ms", latency_ms, labels={"mode": mode, "tier": tier})

    def record_attempt(
        self, *, role: str, provider: str, model: str, status: str, failure_kind: str = "none", latency_ms: float | None = None
    ) -> None:
        labels = {"role": role, "provider": provider, "model": model, "status": status, "failure_kind": failure_kind}
        self.inc("routing_attempts_total", labels=labels)
        if latency_ms is not None:
            self.observe("routing_provider_latency_ms", latency_ms, labels={"provider": provider, "model": model})

    def record_fallback(self, *, mode: str, hops: int) -> None:
        if hops < 0:
            raise ValueError("ROUTING_METRIC_VALUE_INVALID")
        self.inc("routing_fallback_hops_total", float(hops), labels={"mode": mode})

    def record_quorum_failure(self, *, mode: str) -> None:
        self.inc("routing_ensemble_quorum_failures_total", labels={"mode": mode})

    def record_outcome(self, *, purpose: str, model: str, score: float) -> None:
        if not 0 <= score <= 1:
            raise ValueError("ROUTING_METRIC_VALUE_INVALID")
        self.observe("routing_outcome_score", score, labels={"purpose": purpose, "model": model})

    def snapshot(self) -> MetricSnapshot:
        with self._lock:
            return MetricSnapshot(
                counters=dict(self._counters),
                observations={key: tuple(values) for key, values in self._observations.items()},
            )


_default_metrics = RoutingMetrics()


def get_routing_metrics() -> RoutingMetrics:
    """Return the process-wide registry used by production routing code."""

    return _default_metrics
