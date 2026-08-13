from __future__ import annotations

import uuid

import pytest

from ibreeze.routing.repository import RoutingRepository
from ibreeze.routing.types import ProviderFailureKind, RouteRole, RoutingMode


@pytest.mark.asyncio
async def test_create_decision_attempt_and_cas_transitions(local_db) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    decision_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    snapshot_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    await repo.create_decision(
        local_db,
        decision_id=decision_id,
        company_id=company_id,
        run_id=run_id,
        turn_index=1,
        execution_snapshot_id=snapshot_id,
        routing_mode=RoutingMode.SMART_SINGLE,
        classifier_version="router-v1",
        input_fingerprint="a" * 64,
        required_tier="C1",
        confidence=0.8,
        selected_kind="single",
        selected_bindings=[{"candidate_id": "candidate-a", "role": "single"}],
        policy_trail=[{"rule": "C1", "matched": True}],
    )
    attempt = await repo.create_attempt(
        local_db,
        attempt_id=str(uuid.uuid4()),
        route_decision_id=decision_id,
        company_id=company_id,
        run_id=run_id,
        execution_snapshot_id=snapshot_id,
        attempt_sequence=1,
        role=RouteRole.SINGLE,
        candidate_id="candidate-a",
        provider_release_id="provider-a",
        model_binding_id="binding-a",
        credential_ref_sha256="b" * 64,
    )
    assert attempt["status"] == "created"
    assert await repo.transition_attempt(local_db, attempt["id"], "created", "accepted") is True
    assert await repo.transition_attempt(local_db, attempt["id"], "accepted", "succeeded") is True
    assert await repo.transition_attempt(local_db, attempt["id"], "created", "failed") is False
    assert await repo.transition_decision(local_db, decision_id, "planned", "executing") is True
    assert await repo.transition_decision(local_db, decision_id, "executing", "succeeded") is True
    assert await repo.transition_decision(local_db, decision_id, "planned", "failed") is False


@pytest.mark.asyncio
async def test_attempt_request_id_and_outcome_are_idempotent(local_db) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    repo = RoutingRepository()
    ids = {"decision": str(uuid.uuid4()), "run": str(uuid.uuid4()), "snapshot": str(uuid.uuid4()), "company": str(uuid.uuid4())}
    await repo.create_decision(
        local_db,
        decision_id=ids["decision"],
        company_id=ids["company"],
        run_id=ids["run"],
        turn_index=1,
        execution_snapshot_id=ids["snapshot"],
        routing_mode=RoutingMode.FIXED,
        classifier_version="fixed-v1",
        input_fingerprint="c" * 64,
        required_tier="C0",
        confidence=1.0,
        selected_kind="single",
        selected_bindings=[{"candidate_id": "c", "role": "single"}],
        policy_trail=[],
    )
    await repo.create_attempt(
        local_db,
        attempt_id=str(uuid.uuid4()),
        route_decision_id=ids["decision"],
        company_id=ids["company"],
        run_id=ids["run"],
        execution_snapshot_id=ids["snapshot"],
        attempt_sequence=1,
        role=RouteRole.SINGLE,
        candidate_id="c",
        provider_release_id="p",
        model_binding_id="m",
        credential_ref_sha256="d" * 64,
        request_id="request-1",
    )
    with pytest.raises(ValueError, match="ROUTE_ATTEMPT_REQUEST_EXISTS"):
        await repo.create_attempt(
            local_db,
            attempt_id=str(uuid.uuid4()),
            route_decision_id=ids["decision"],
            company_id=ids["company"],
            run_id=ids["run"],
            execution_snapshot_id=ids["snapshot"],
            attempt_sequence=2,
            role=RouteRole.SINGLE,
            candidate_id="c",
            provider_release_id="p",
            model_binding_id="m",
            credential_ref_sha256="d" * 64,
            request_id="request-1",
        )
    assert await repo.record_outcome(local_db, str(uuid.uuid4()), ids["decision"], ids["company"], "review", "r1", 0.9, "pass") is True
    assert await repo.record_outcome(local_db, str(uuid.uuid4()), ids["decision"], ids["company"], "review", "r1", 0.9, "pass") is False


@pytest.mark.asyncio
async def test_health_upsert_and_failure_enum() -> None:
    assert ProviderFailureKind.RATE_LIMITED.value == "RATE_LIMITED"
    assert RouteRole.AGGREGATOR.value == "aggregator"
    assert RoutingMode.SELECTIVE_ENSEMBLE.value == "selective_ensemble"


@pytest.mark.asyncio
async def test_illegal_terminal_transitions_are_rejected(local_db) -> None:
    repo = RoutingRepository()
    with pytest.raises(ValueError, match="ROUTE_DECISION_TRANSITION_INVALID"):
        await repo.transition_decision(local_db, "missing", "planned", "succeeded")
    with pytest.raises(ValueError, match="ROUTE_ATTEMPT_TRANSITION_INVALID"):
        await repo.transition_attempt(local_db, "missing", "created", "succeeded")
