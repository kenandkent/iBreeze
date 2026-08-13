from __future__ import annotations

import uuid

import pytest

from ibreeze.routing.repository import RoutingRepository
from ibreeze.routing.types import ProviderFailureKind, RouteRole, RoutingMode


@pytest.fixture
def ids() -> dict[str, str]:
    return {
        "decision": str(uuid.uuid4()),
        "run": str(uuid.uuid4()),
        "snapshot": str(uuid.uuid4()),
        "company": str(uuid.uuid4()),
    }


async def _create_decision(repo: RoutingRepository, db, ids: dict[str, str], **overrides) -> None:
    kwargs = dict(
        decision_id=ids["decision"],
        company_id=ids["company"],
        run_id=ids["run"],
        turn_index=1,
        execution_snapshot_id=ids["snapshot"],
        routing_mode=RoutingMode.SMART_SINGLE,
        classifier_version="router-v1",
        input_fingerprint="a" * 64,
        required_tier="C1",
        confidence=0.8,
        selected_kind="single",
        selected_bindings=[{"candidate_id": "cand-x", "role": "single"}],
        policy_trail=[{"rule": "C1", "matched": True}],
    )
    kwargs.update(overrides)
    await repo.create_decision(db, **kwargs)


async def _create_attempt(repo: RoutingRepository, db, ids: dict[str, str], **overrides) -> dict:
    kwargs = dict(
        attempt_id=str(uuid.uuid4()),
        route_decision_id=ids["decision"],
        company_id=ids["company"],
        run_id=ids["run"],
        execution_snapshot_id=ids["snapshot"],
        attempt_sequence=1,
        role=RouteRole.SINGLE,
        candidate_id="cand-x",
        provider_release_id="provider-a",
        model_binding_id="binding-a",
        credential_ref_sha256="b" * 64,
    )
    kwargs.update(overrides)
    return await repo.create_attempt(db, **kwargs)


@pytest.mark.asyncio
async def test_create_decision_rejects_invalid_inputs(local_db, ids) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    with pytest.raises(ValueError, match="ROUTE_DECISION_INVALID"):
        await _create_decision(repo, local_db, ids, confidence=1.5)
    with pytest.raises(ValueError, match="ROUTE_DECISION_INVALID"):
        await _create_decision(repo, local_db, ids, input_fingerprint="short")
    with pytest.raises(ValueError, match="ROUTE_DECISION_TIER_INVALID"):
        await _create_decision(repo, local_db, ids, required_tier="C9")
    with pytest.raises(ValueError, match="ROUTE_SELECTION_INVALID"):
        await _create_decision(repo, local_db, ids, selected_kind="bogus")
    with pytest.raises(ValueError, match="ROUTE_SELECTION_INVALID"):
        await _create_decision(repo, local_db, ids, selected_bindings=[])
    with pytest.raises(ValueError, match="ROUTE_SELECTION_INVALID"):
        await _create_decision(repo, local_db, ids, selected_bindings=[{"candidate_id": "", "role": ""}])


@pytest.mark.asyncio
async def test_create_decision_duplicate_raises_exists(local_db, ids) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    await _create_decision(repo, local_db, ids)
    with pytest.raises(ValueError, match="ROUTE_DECISION_EXISTS"):
        await _create_decision(repo, local_db, ids)


@pytest.mark.asyncio
async def test_transition_decision_rejects_unknown_expected_status(local_db) -> None:
    repo = RoutingRepository()
    with pytest.raises(ValueError, match="ROUTE_DECISION_STATUS_INVALID"):
        await repo.transition_decision(local_db, "missing", "bogus", "succeeded")


@pytest.mark.asyncio
async def test_create_attempt_rejects_invalid_sequence(local_db, ids) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    await _create_decision(repo, local_db, ids)
    with pytest.raises(ValueError, match="ROUTE_ATTEMPT_INVALID"):
        await _create_attempt(repo, local_db, ids, attempt_sequence=0)
    with pytest.raises(ValueError, match="ROUTE_ATTEMPT_INVALID"):
        await _create_attempt(repo, local_db, ids, credential_ref_sha256="short")


@pytest.mark.asyncio
async def test_create_attempt_duplicate_sequence_raises(local_db, ids) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    await _create_decision(repo, local_db, ids)
    await _create_attempt(repo, local_db, ids, attempt_sequence=1)
    with pytest.raises(ValueError, match="ROUTE_ATTEMPT_SEQUENCE_EXISTS"):
        await _create_attempt(repo, local_db, ids, attempt_sequence=1)


@pytest.mark.asyncio
async def test_create_attempt_generic_integrity_error_maps_to_invalid(local_db, ids) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    await _create_decision(repo, local_db, ids)
    with pytest.raises(ValueError, match="ROUTE_ATTEMPT_INVALID"):
        await _create_attempt(repo, local_db, ids, provider_release_id=None)


@pytest.mark.asyncio
async def test_transition_attempt_status_and_usage_validation(local_db, ids) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    with pytest.raises(ValueError, match="ROUTE_ATTEMPT_STATUS_INVALID"):
        await repo.transition_attempt(local_db, "missing", "bogus", "succeeded")
    await _create_decision(repo, local_db, ids)
    attempt = await _create_attempt(repo, local_db, ids)
    with pytest.raises(ValueError, match="ROUTE_ATTEMPT_USAGE_INVALID"):
        await repo.transition_attempt(local_db, attempt["id"], "created", "accepted", latency_ms=-1)


@pytest.mark.asyncio
async def test_transition_attempt_accepts_string_failure_kind(local_db, ids) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    await _create_decision(repo, local_db, ids)
    attempt = await _create_attempt(repo, local_db, ids)
    assert (
        await repo.transition_attempt(
            local_db,
            attempt["id"],
            "created",
            "accepted",
            failure_kind="RATE_LIMITED",
            http_status=429,
        )
        is True
    )


@pytest.mark.asyncio
async def test_bind_attempt_request_validation_and_uniqueness(local_db, ids) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    with pytest.raises(ValueError, match="ROUTE_ATTEMPT_REQUEST_INVALID"):
        await repo.bind_attempt_request(local_db, attempt_id="any", request_id="")
    await _create_decision(repo, local_db, ids)
    first = await _create_attempt(repo, local_db, ids)
    second = await _create_attempt(repo, local_db, ids, attempt_sequence=2)
    assert await repo.bind_attempt_request(local_db, attempt_id=first["id"], request_id="req-shared") is True
    assert await repo.bind_attempt_request(local_db, attempt_id=first["id"], request_id="req-shared") is False
    with pytest.raises(ValueError, match="ROUTE_ATTEMPT_REQUEST_EXISTS"):
        await repo.bind_attempt_request(local_db, attempt_id=second["id"], request_id="req-shared")


@pytest.mark.asyncio
async def test_record_outcome_rejects_out_of_range_score(local_db, ids) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    with pytest.raises(ValueError, match="ROUTE_OUTCOME_SCORE_INVALID"):
        await repo.record_outcome(local_db, str(uuid.uuid4()), ids["decision"], ids["company"], "review", "r1", 1.5, "pass")


@pytest.mark.asyncio
async def test_upsert_health_validation_and_roundtrip(local_db) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    with pytest.raises(ValueError, match="DEPLOYMENT_HEALTH_INVALID"):
        await repo.upsert_health(
            local_db,
            company_id="company-1",
            provider_release_id="provider-1",
            model_binding_id="binding-1",
            credential_ref_sha256="c" * 64,
            availability_state="bogus",
            consecutive_strikes=0,
            benched_until=None,
            last_failure_kind=None,
            last_failure_at=None,
            last_success_at=None,
        )
    with pytest.raises(ValueError, match="DEPLOYMENT_HEALTH_INVALID"):
        await repo.upsert_health(
            local_db,
            company_id="company-1",
            provider_release_id="provider-1",
            model_binding_id="binding-1",
            credential_ref_sha256="c" * 64,
            availability_state="ready",
            consecutive_strikes=-1,
            benched_until=None,
            last_failure_kind=None,
            last_failure_at=None,
            last_success_at=None,
        )
    await repo.upsert_health(
        local_db,
        company_id="company-1",
        provider_release_id="provider-1",
        model_binding_id="binding-1",
        credential_ref_sha256="c" * 64,
        availability_state="ready",
        consecutive_strikes=2,
        benched_until="2099-01-01T00:00:00Z",
        last_failure_kind=ProviderFailureKind.RATE_LIMITED,
        last_failure_at="2026-01-01T00:00:00Z",
        last_success_at=None,
    )
    await repo.upsert_health(
        local_db,
        company_id="company-1",
        provider_release_id="provider-1",
        model_binding_id="binding-1",
        credential_ref_sha256="c" * 64,
        availability_state="ready",
        consecutive_strikes=0,
        benched_until=None,
        last_failure_kind=None,
        last_failure_at=None,
        last_success_at="2026-01-01T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_set_override_validation_and_persist(local_db) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    with pytest.raises(ValueError, match="ROUTING_OVERRIDE_INVALID"):
        await repo.set_override(local_db, "company-1", "run-1", "bogus")
    await repo.set_override(local_db, "company-1", "run-1", None)
    await repo.set_override(local_db, "company-1", "run-1", "force_ensemble")
