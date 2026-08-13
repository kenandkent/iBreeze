from __future__ import annotations

from dataclasses import dataclass

import pytest

from ibreeze.routing.context import build_routing_context
from ibreeze.routing.policy import validate_routing_policy
from ibreeze.routing.service import AttemptResult, RoutingService
from ibreeze.routing.types import ProviderFailureKind, RouteRole


class _KindError(Exception):
    def __init__(self, kind: str, *, http_status: int | None = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.http_status = http_status


def _candidate(cid: str, *, roles: list[str]) -> dict:
    return {
        "candidate_id": cid,
        "company_id": "company-1",
        "execution_snapshot_id": "snapshot-1",
        "run_id": "run-1",
        "provider_release_id": f"provider-{cid}",
        "model_binding_id": f"binding-{cid}",
        "credential_ref": f"credential-{cid}",
        "routing_enabled": True,
        "eligible_roles": roles,
        "routing_tier": 3,
        "quality_prior": "0.7000",
        "tool_reliability_prior": "0.9000",
        "latency_prior_ms": 100,
        "context_window": 100000,
        "max_output_tokens": 1000,
        "supports_tools": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_reasoning": True,
        "reasoning_levels": ["low", "medium", "high"],
    }


def _selective_policy():
    anchor = "11111111-1111-4111-8111-111111111111"
    reviewer = "22222222-2222-4222-8222-222222222222"
    aggregator = "33333333-3333-4333-8333-333333333333"
    return validate_routing_policy(
        {
            "schema_version": 1,
            "mode": "selective_ensemble",
            "anchor_candidate_id": anchor,
            "candidates": [
                {"candidate_id": anchor, "provider_release_id": "44444444-4444-4444-8444-444444444444", "model_binding_id": "55555555-5555-4555-8555-555555555555", "credential_ref": "66666666-6666-4666-8666-666666666666", "enabled": True, "routing_enabled": True, "eligible_roles": ["single", "fallback", "proposer"]},
                {"candidate_id": reviewer, "provider_release_id": "77777777-7777-4777-8777-777777777777", "model_binding_id": "88888888-8888-4888-8888-888888888888", "credential_ref": "99999999-9999-4999-8999-999999999999", "enabled": True, "routing_enabled": True, "eligible_roles": ["fallback", "proposer"]},
                {"candidate_id": aggregator, "provider_release_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "model_binding_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "credential_ref": "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "enabled": True, "routing_enabled": True, "eligible_roles": ["fallback", "aggregator"]},
            ],
            "fallback_order": [anchor, reviewer, aggregator],
            "ensemble": {"max_proposers": 2, "min_successful_proposers": 2, "proposer_timeout_seconds": 10, "aggregator_timeout_seconds": 10, "proposer_max_retries": 0},
        },
        profile_type="api_model",
    )


def _smart_single_policy():
    anchor = "11111111-1111-4111-8111-111111111111"
    second = "22222222-2222-4222-8222-222222222222"
    return validate_routing_policy(
        {
            "schema_version": 1,
            "mode": "smart_single",
            "anchor_candidate_id": anchor,
            "candidates": [
                {"candidate_id": anchor, "provider_release_id": "33333333-3333-4333-8333-333333333333", "model_binding_id": "44444444-4444-4444-8444-444444444444", "credential_ref": "55555555-5555-4555-8555-555555555555", "enabled": True, "routing_enabled": True, "eligible_roles": ["single", "fallback"]},
                {"candidate_id": second, "provider_release_id": "66666666-6666-4666-8666-666666666666", "model_binding_id": "77777777-7777-4777-8777-777777777777", "credential_ref": "88888888-8888-4888-8888-888888888888", "enabled": True, "routing_enabled": True, "eligible_roles": ["single", "fallback"]},
            ],
            "fallback_order": [anchor, second],
            "ensemble": {"max_proposers": 2, "min_successful_proposers": 2, "proposer_timeout_seconds": 10, "aggregator_timeout_seconds": 10, "proposer_max_retries": 0},
        },
        profile_type="api_model",
    )


@dataclass
class _FakeRepository:
    calls: list
    transition_result: bool = True

    async def create_attempt(self, db, **kwargs):
        self.calls.append(("create_attempt", kwargs))
        return {"id": kwargs["attempt_id"], "status": "created"}

    async def create_decision(self, db, **kwargs):
        self.calls.append(("create_decision", kwargs))
        return {"id": kwargs["decision_id"], "status": "planned"}

    async def bind_attempt_request(self, db, **kwargs):
        self.calls.append(("bind", kwargs))
        return True

    async def transition_attempt(self, db, attempt_id, expected_status, target_status, **kwargs):
        self.calls.append(("transition", (attempt_id, expected_status, target_status)))
        return self.transition_result


def _context(**kwargs):
    defaults = {
        "run_id": "run-1",
        "turn_index": 1,
        "messages": ({"role": "user", "content": "repair"},),
        "context_window_tokens": 1000,
        "run_purpose": "repair",
        "verification_failures": 1,
    }
    defaults.update(kwargs)
    return build_routing_context(**defaults)


@pytest.mark.asyncio
async def test_plan_and_persist_persists_ensemble_selection() -> None:
    repository = _FakeRepository([])
    service = RoutingService(repository)
    context = _context()
    policy = _selective_policy()
    candidates = (
        _candidate("11111111-1111-4111-8111-111111111111", roles=["single", "fallback", "proposer"]),
        _candidate("22222222-2222-4222-8222-222222222222", roles=["fallback", "proposer"]),
        _candidate("33333333-3333-4333-8333-333333333333", roles=["fallback", "aggregator"]),
    )
    decision_id, plan = await service.plan_and_persist(object(), context=context, candidates=candidates, policy=policy)
    assert decision_id
    assert plan.selected_kind == "ensemble"
    decision_call = next(call for call in repository.calls if call[0] == "create_decision")[1]
    assert decision_call["selected_kind"] == "ensemble"
    assert decision_call["aggregator_candidate_id"] == "33333333-3333-4333-8333-333333333333"
    assert any(entry["role"] == "aggregator" for entry in decision_call["selected_bindings"])
    assert decision_call["required_tier"] == plan.required_tier


@pytest.mark.asyncio
async def test_plan_and_persist_single_plan_has_no_aggregator() -> None:
    repository = _FakeRepository([])
    service = RoutingService(repository)
    context = build_routing_context(
        run_id="run-1",
        turn_index=1,
        messages=({"role": "user", "content": "hi"},),
        context_window_tokens=1000,
    )
    policy = _smart_single_policy()
    candidates = (
        _candidate("11111111-1111-4111-8111-111111111111", roles=["single", "fallback"]),
        _candidate("22222222-2222-4222-8222-222222222222", roles=["single", "fallback"]),
    )
    decision_id, plan = await service.plan_and_persist(object(), context=context, candidates=candidates, policy=policy)
    assert decision_id
    assert plan.selected_kind == "single"
    assert plan.aggregator is None
    decision_call = next(call for call in repository.calls if call[0] == "create_decision")[1]
    assert decision_call["aggregator_candidate_id"] is None


@pytest.mark.asyncio
async def test_execute_attempt_dedupes_callbacks() -> None:
    repository = _FakeRepository([])
    service = RoutingService(repository)

    async def request(attempt_id, on_accepted, on_streaming):
        await on_accepted("rust-request-1")
        await on_accepted("rust-request-1")
        await on_streaming()
        await on_streaming()
        return AttemptResult(status="succeeded", request_id="rust-request-1")

    result = await service.execute_attempt(
        object(),
        decision_id="decision",
        candidate=_candidate("a", roles=["single"]),
        role=RouteRole.SINGLE,
        sequence=1,
        request=request,
    )
    assert result.status == "succeeded"
    transitions = [call[1] for call in repository.calls if call[0] == "transition"]
    assert ("accepted", "streaming") in [t[1:] for t in transitions]


@pytest.mark.asyncio
async def test_execute_attempt_streaming_before_accepted_closes_gap() -> None:
    repository = _FakeRepository([])
    service = RoutingService(repository)

    async def request(attempt_id, on_accepted, on_streaming):
        await on_streaming()
        await on_accepted("rust-request-1")
        return AttemptResult(status="succeeded", request_id="rust-request-1")

    result = await service.execute_attempt(
        object(),
        decision_id="decision",
        candidate=_candidate("a", roles=["single"]),
        role=RouteRole.SINGLE,
        sequence=1,
        request=request,
    )
    assert result.status == "succeeded"
    binds = [call for call in repository.calls if call[0] == "bind"]
    assert binds == []
    transitions = [call[1] for call in repository.calls if call[0] == "transition"]
    assert [t[1:] for t in transitions] == [("created", "accepted"), ("accepted", "streaming"), ("streaming", "succeeded")]


@pytest.mark.asyncio
async def test_execute_attempt_normalizes_failure_kinds() -> None:
    repository = _FakeRepository([])
    service = RoutingService(repository)

    async def known_failure(*_args):
        raise _KindError("RATE_LIMITED", http_status=429)

    result = await service.execute_attempt(
        object(),
        decision_id="decision",
        candidate=_candidate("a", roles=["single"]),
        role=RouteRole.SINGLE,
        sequence=1,
        request=known_failure,
    )
    assert result.status == "failed"
    assert result.failure_kind is ProviderFailureKind.RATE_LIMITED
    assert result.http_status == 429

    async def unknown_failure(*_args):
        raise _KindError("BOGUS_KIND")

    result = await service.execute_attempt(
        object(),
        decision_id="decision-2",
        candidate=_candidate("a", roles=["single"]),
        role=RouteRole.SINGLE,
        sequence=1,
        request=unknown_failure,
    )
    assert result.status == "failed"
    assert result.failure_kind is ProviderFailureKind.INVALID_RESPONSE

    async def plain_failure(*_args):
        raise RuntimeError("boom")

    result = await service.execute_attempt(
        object(),
        decision_id="decision-3",
        candidate=_candidate("a", roles=["single"]),
        role=RouteRole.SINGLE,
        sequence=1,
        request=plain_failure,
    )
    assert result.status == "failed"
    assert result.failure_kind is ProviderFailureKind.INVALID_RESPONSE


@pytest.mark.asyncio
async def test_execute_attempt_legacy_request_returns_terminal() -> None:
    repository = _FakeRepository([])
    service = RoutingService(repository)

    async def request(attempt_id):
        return AttemptResult(status="succeeded", request_id="rust-request-9")

    result = await service.execute_attempt(
        object(),
        decision_id="decision",
        candidate=_candidate("a", roles=["single"]),
        role=RouteRole.SINGLE,
        sequence=1,
        request=request,
    )
    assert result.status == "succeeded"
    binds = [call for call in repository.calls if call[0] == "bind"]
    assert binds and binds[0][1]["request_id"] == "rust-request-9"
    transitions = [call[1] for call in repository.calls if call[0] == "transition"]
    assert ("streaming", "succeeded") in [t[1:] for t in transitions]


@pytest.mark.asyncio
async def test_execute_attempt_loops_all_statuses_when_transitions_fail() -> None:
    repository = _FakeRepository([], transition_result=False)
    service = RoutingService(repository)

    async def request(attempt_id):
        return AttemptResult(status="succeeded")

    result = await service.execute_attempt(
        object(),
        decision_id="decision",
        candidate=_candidate("a", roles=["single"]),
        role=RouteRole.SINGLE,
        sequence=1,
        request=request,
    )
    assert result.status == "succeeded"
    transitions = [call[1] for call in repository.calls if call[0] == "transition"]
    expected = [
        ("created", "accepted"),
        ("accepted", "streaming"),
        ("streaming", "succeeded"),
        ("accepted", "succeeded"),
        ("created", "succeeded"),
    ]
    assert [t[1:] for t in transitions] == expected
