from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from ibreeze.routing.service import AttemptResult, RoutingService
from ibreeze.routing.types import ProviderFailureKind, RouteRole


@dataclass
class _FakeRepository:
    calls: list[tuple[str, tuple[object, ...]]]

    async def create_attempt(self, db, **kwargs):
        self.calls.append(("create", (kwargs["attempt_id"], kwargs["attempt_sequence"])))
        return {"id": kwargs["attempt_id"], "status": "created"}

    async def bind_attempt_request(self, db, **kwargs):
        self.calls.append(("bind", (kwargs["attempt_id"], kwargs["request_id"])))
        return True

    async def transition_attempt(self, db, attempt_id, expected_status, target_status, **kwargs):
        self.calls.append(("transition", (attempt_id, expected_status, target_status)))
        return True


@pytest.mark.asyncio
async def test_execute_attempt_persists_created_accepted_streaming_terminal_in_order():
    repository = _FakeRepository([])
    service = RoutingService(repository)

    async def request(attempt_id, on_accepted, on_streaming):
        await on_accepted("rust-request-1")
        await on_streaming()
        return AttemptResult(status="succeeded", request_id="rust-request-1")

    result = await service.execute_attempt(
        object(),
        decision_id="decision",
        candidate={
            "company_id": "company",
            "run_id": "run",
            "execution_snapshot_id": "snapshot",
            "candidate_id": "candidate",
            "provider_release_id": "provider",
            "model_binding_id": "model",
            "credential_ref": "credential",
        },
        role=RouteRole.SINGLE,
        sequence=1,
        request=request,
    )

    assert result.status == "succeeded"
    assert [call[0] for call in repository.calls] == ["create", "bind", "transition", "transition", "transition"]
    assert repository.calls[2][1][1:] == ("created", "accepted")
    assert repository.calls[3][1][1:] == ("accepted", "streaming")
    assert repository.calls[4][1][1:] == ("streaming", "succeeded")


@pytest.mark.asyncio
async def test_execute_attempt_does_not_call_provider_when_attempt_creation_fails():
    class FailingRepository(_FakeRepository):
        async def create_attempt(self, db, **kwargs):
            raise RuntimeError("WRITE_FAILED")

    called = False
    service = RoutingService(FailingRepository([]))

    async def request(attempt_id):
        nonlocal called
        called = True
        return AttemptResult(status="succeeded")

    with pytest.raises(RuntimeError, match="WRITE_FAILED"):
        await service.execute_attempt(
            object(),
            decision_id="decision",
            candidate={
                "company_id": "company",
                "run_id": "run",
                "execution_snapshot_id": "snapshot",
                "candidate_id": "candidate",
                "provider_release_id": "provider",
                "model_binding_id": "model",
                "credential_ref": "credential",
            },
            role=RouteRole.SINGLE,
            sequence=1,
            request=request,
        )
    assert called is False


@pytest.mark.asyncio
async def test_execute_attempt_normalizes_timeout_and_cancel():
    repository = _FakeRepository([])
    service = RoutingService(repository)

    async def timeout(attempt_id):
        raise TimeoutError

    result = await service.execute_attempt(
        object(),
        decision_id="decision",
        candidate={
            "company_id": "company",
            "run_id": "run",
            "execution_snapshot_id": "snapshot",
            "candidate_id": "candidate",
            "provider_release_id": "provider",
            "model_binding_id": "model",
            "credential_ref": "credential",
        },
        role=RouteRole.SINGLE,
        sequence=1,
        request=timeout,
    )
    assert result.status == "timed_out"
    assert result.failure_kind is ProviderFailureKind.TIMEOUT

    async def cancelled(attempt_id):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await service.execute_attempt(
            object(),
            decision_id="decision-2",
            candidate={
                "company_id": "company",
                "run_id": "run",
                "execution_snapshot_id": "snapshot",
                "candidate_id": "candidate",
                "provider_release_id": "provider",
                "model_binding_id": "model",
                "credential_ref": "credential",
            },
            role=RouteRole.SINGLE,
            sequence=2,
            request=cancelled,
        )
