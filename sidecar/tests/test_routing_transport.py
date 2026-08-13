from __future__ import annotations

from decimal import Decimal

from ibreeze.routing.transport import RoutingTransport
from ibreeze.routing.types import ProviderFailureKind
from ibreeze.runtime.model_loop import ModelTurn
from ibreeze.runtime.transport import (
    _effective_route_tier,
    _retry_wait_seconds,
    _stable_score_key,
)


class _Transport:
    def __init__(self, result: ModelTurn | Exception):
        self.result = result

    async def complete(self, _messages, _tools):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def probe(self):
        return True

    def normalize_usage(self, usage):
        return usage


async def _not_used():
    return None


def test_routing_transport_requires_candidates() -> None:
    try:
        RoutingTransport([], {}, run_id="r", session=None, base_transport_factory=lambda _c, _s: _Transport(ModelTurn(content="x")))
    except ValueError as exc:
        assert str(exc) == "ROUTING_CANDIDATES_REQUIRED"
    else:
        raise AssertionError("expected candidate validation")


def test_routing_transport_derives_anchor_from_policy() -> None:
    anchor = "00000000-0000-0000-0000-000000000001"
    transport = RoutingTransport(
        [{"candidate_id": anchor}],
        {"mode": "fixed", "anchor_candidate_id": anchor},
        run_id="run",
        session=None,
    )
    assert transport._anchor_candidate_id == anchor


def test_invalid_run_override_fails_safe_to_fixed_mode() -> None:
    transport = RoutingTransport(
        [{"candidate_id": "candidate-1"}],
        {"mode": "smart_single", "anchor_candidate_id": "candidate-1"},
        run_id="run",
        session=None,
    )
    assert transport._mode_for_override("unexpected") == "fixed"


def test_fixed_mode_preserves_anchor_without_difficulty_classification() -> None:
    assert _effective_route_tier("fixed", "C3") == "C0"
    assert _effective_route_tier("smart_single", "C3") == "C3"


def test_rate_limit_retry_wait_uses_provider_window_or_default() -> None:
    assert _retry_wait_seconds(ProviderFailureKind.RATE_LIMITED, 2500) == 2.5
    assert _retry_wait_seconds(ProviderFailureKind.RATE_LIMITED, None) == 30.0
    assert _retry_wait_seconds(ProviderFailureKind.TIMEOUT, 2500) == 0.0


def test_runtime_score_order_is_decimal_and_matches_policy_tie_break() -> None:
    same_score = [
        (
            Decimal("0.90000000"),
            {
                "candidate_id": "b",
                "model_binding_id": "a",
                "quality_prior": "0.8000",
                "latency_prior_ms": 100,
            },
        ),
        (
            Decimal("0.90000000"),
            {
                "candidate_id": "a",
                "model_binding_id": "b",
                "quality_prior": "0.8000",
                "latency_prior_ms": 100,
            },
        ),
    ]
    assert sorted(same_score, key=_stable_score_key)[0][1]["model_binding_id"] == "a"
    assert _stable_score_key((Decimal("0.900000001"), same_score[1][1])) < _stable_score_key(
        (Decimal("0.900000000"), same_score[0][1])
    )


def test_runtime_tie_break_prefers_effective_quality_after_local_calibration() -> None:
    calibrated = {
        "candidate_id": "a",
        "model_binding_id": "z",
        "quality_prior": "0.5000",
        "_effective_quality": "0.7000",
        "latency_prior_ms": 100,
    }
    uncalibrated = {
        "candidate_id": "b",
        "model_binding_id": "a",
        "quality_prior": "0.6000",
        "_effective_quality": "0.6000",
        "latency_prior_ms": 100,
    }
    assert sorted(
        [(Decimal("0.90000000"), uncalibrated), (Decimal("0.90000000"), calibrated)],
        key=_stable_score_key,
    )[0][1] is calibrated
