from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

from ibreeze.routing.health import HealthState, _parse_timestamp, apply_failure, cleanup_expired, load_health_ledger
from ibreeze.routing.types import ProviderFailureKind


def test_parse_timestamp_handles_invalid_and_naive_values() -> None:
    assert _parse_timestamp(None) is None
    assert _parse_timestamp("") is None
    assert _parse_timestamp("not-a-date") is None
    parsed = _parse_timestamp("2026-01-01T00:00:00")
    assert parsed is not None
    assert parsed.tzinfo is not None


class _ReadPool:
    def __init__(self, rows):
        self._rows = rows

    async def query_all(self, _sql, _params):
        return self._rows


def _candidate(cid: str, provider: str = "provider-1", binding: str = "binding-1", credential: str = "credential-1") -> dict:
    return {
        "candidate_id": cid,
        "provider_release_id": provider,
        "model_binding_id": binding,
        "credential_ref": credential,
    }


def test_load_health_ledger_fails_closed_on_corrupt_rows() -> None:
    rows = [
        {
            "provider_release_id": "provider-1",
            "model_binding_id": "binding-1",
            "credential_ref_sha256": hashlib.sha256(b"credential-1").hexdigest(),
            "availability_state": "bogus_state",
            "consecutive_strikes": "abc",
            "benched_until": "not-a-date",
            "last_failure_kind": "BOGUS_KIND",
            "last_failure_at": "2026-01-01T00:00:00",
            "last_success_at": "2026-01-01T00:00:00",
            "version": "abc",
        }
    ]
    states = asyncio.run(
        load_health_ledger(_ReadPool(rows), "company-1", (_candidate("candidate-1"),))
    )
    state = states["candidate-1"]
    assert state.availability_state == "credential_invalid"
    assert state.consecutive_strikes == 0
    assert state.version == 1
    assert state.last_failure_kind is None
    assert state.benched_until is None


def test_load_health_ledger_skips_unmatched_and_empty_ids() -> None:
    matched_sha = hashlib.sha256(b"credential-1").hexdigest()
    rows = [
        {
            "provider_release_id": "provider-other",
            "model_binding_id": "binding-other",
            "credential_ref_sha256": matched_sha,
            "availability_state": "ready",
            "consecutive_strikes": 0,
            "benched_until": None,
            "last_failure_kind": None,
            "last_failure_at": None,
            "last_success_at": None,
            "version": 1,
        },
        {
            "provider_release_id": "provider-1",
            "model_binding_id": "binding-1",
            "credential_ref_sha256": matched_sha,
            "availability_state": "ready",
            "consecutive_strikes": 0,
            "benched_until": None,
            "last_failure_kind": None,
            "last_failure_at": None,
            "last_success_at": None,
            "version": 1,
        },
    ]
    candidates = (
        _candidate("candidate-1"),
        {"provider_release_id": "provider-1", "model_binding_id": "binding-1", "credential_ref": "credential-1"},
    )
    states = asyncio.run(load_health_ledger(_ReadPool(rows), "company-1", candidates))
    assert "candidate-1" in states
    assert len(states) == 1


def test_load_health_ledger_returns_empty_without_candidates() -> None:
    assert asyncio.run(load_health_ledger(_ReadPool([]), "", ())) == {}
    assert asyncio.run(load_health_ledger(_ReadPool([]), "company-1", ())) == {}


def test_apply_failure_no_strike_kinds_do_not_accumulate() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    state = apply_failure(HealthState(), ProviderFailureKind.CONTEXT_OVERFLOW, now=now)
    assert state.consecutive_strikes == 0
    assert state.benched_until is None
    assert state.last_failure_kind is ProviderFailureKind.CONTEXT_OVERFLOW
    state = apply_failure(state, ProviderFailureKind.POLICY_REFUSAL, now=now)
    assert state.consecutive_strikes == 0


def test_apply_failure_rate_limit_clamps_and_default_window() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    state = apply_failure(HealthState(), ProviderFailureKind.RATE_LIMITED, now=now, retry_after_seconds=2000)
    assert state.benched_until == now + timedelta(seconds=900)
    state = apply_failure(HealthState(), ProviderFailureKind.RATE_LIMITED, now=now, retry_after_seconds=0)
    assert state.benched_until == now + timedelta(seconds=1)


def test_cleanup_expired_returns_state_when_not_benched() -> None:
    state = HealthState()
    assert cleanup_expired(state) is state
    future = HealthState(benched_until=datetime(2099, 1, 1, tzinfo=UTC))
    assert cleanup_expired(future, now=datetime(2026, 1, 1, tzinfo=UTC)) is future
