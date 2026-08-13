from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from ibreeze.routing.health import HealthState, apply_failure, apply_success, cleanup_expired, load_health_ledger
from ibreeze.routing.types import ProviderFailureKind


def test_health_strikes_bench_and_success_reset() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    state = HealthState()
    for _ in range(3):
        state = apply_failure(state, ProviderFailureKind.PROVIDER_OVERLOADED, now=now)
    assert state.consecutive_strikes == 3
    assert state.benched_until == now + timedelta(seconds=30)
    assert not state.is_eligible(now)
    assert cleanup_expired(state, now=now + timedelta(seconds=31)).benched_until is None
    state = apply_failure(HealthState(), ProviderFailureKind.AUTH_INVALID, now=now)
    assert state.availability_state == "credential_invalid"
    assert state.consecutive_strikes == 0
    assert apply_success(state, now=now).availability_state == "ready"


def test_rate_limit_bench_uses_retry_after_and_defaults_to_thirty_seconds() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    limited = apply_failure(
        HealthState(),
        ProviderFailureKind.RATE_LIMITED,
        now=now,
        retry_after_seconds=5,
    )
    assert limited.benched_until == now + timedelta(seconds=5)
    defaulted = apply_failure(HealthState(), ProviderFailureKind.RATE_LIMITED, now=now)
    assert defaulted.benched_until == now + timedelta(seconds=30)


async def test_load_health_ledger_restores_persisted_bench_for_matching_deployment() -> None:
    class ReadPool:
        async def query_all(self, _sql: str, _params: tuple[object, ...]) -> list[dict[str, object]]:
            return [
                {
                    "provider_release_id": "provider-1",
                    "model_binding_id": "binding-1",
                    "credential_ref_sha256": hashlib.sha256(b"credential-1").hexdigest(),
                    "availability_state": "ready",
                    "consecutive_strikes": 3,
                    "benched_until": "2099-01-01T00:00:00Z",
                    "last_failure_kind": "PROVIDER_OVERLOADED",
                    "last_failure_at": "2026-01-01T00:00:00Z",
                    "last_success_at": None,
                    "version": 4,
                }
            ]

    states = await load_health_ledger(
        ReadPool(),
        "company-1",
        (
            {
                "candidate_id": "candidate-1",
                "provider_release_id": "provider-1",
                "model_binding_id": "binding-1",
                "credential_ref": "credential-1",
            },
        ),
    )
    assert states["candidate-1"].consecutive_strikes == 3
    assert states["candidate-1"].version == 4
    assert not states["candidate-1"].is_eligible(datetime(2026, 1, 2, tzinfo=UTC))


async def test_load_health_ledger_fails_closed_without_persistence() -> None:
    import pytest

    with pytest.raises(RuntimeError, match="ROUTING_HEALTH_UNAVAILABLE"):
        await load_health_ledger(
            None,
            "company-1",
            ({"candidate_id": "candidate-1"},),
        )
