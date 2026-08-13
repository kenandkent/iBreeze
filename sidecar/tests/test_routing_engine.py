from __future__ import annotations

from decimal import Decimal

import pytest

from ibreeze.routing.classifier import RulesV1Classifier
from ibreeze.routing.context import build_routing_context
from ibreeze.routing.engine import RoutingPolicyEngine, _stable_score_key, capability_gate
from ibreeze.routing.health import HealthState
from ibreeze.routing.policy import validate_routing_policy
from ibreeze.routing.types import DeploymentKey, RouteRole, RoutingMode


def _candidate(cid: str, *, roles: list[str], quality: str = "0.5000", tier: int = 3, **extra):
    item = {
        "candidate_id": cid,
        "company_id": "company-1",
        "provider_release_id": f"provider-{cid}",
        "model_binding_id": f"binding-{cid}",
        "credential_ref": f"credential-{cid}",
        "routing_enabled": True,
        "eligible_roles": roles,
        "routing_tier": tier,
        "quality_prior": quality,
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
    item.update(extra)
    return item


def _policy(mode: str = "smart_single"):
    anchor = "11111111-1111-4111-8111-111111111111"
    second = "22222222-2222-4222-8222-222222222222"
    candidates = [
        {"candidate_id": anchor, "provider_release_id": "33333333-3333-4333-8333-333333333333", "model_binding_id": "44444444-4444-4444-8444-444444444444", "credential_ref": "55555555-5555-4555-8555-555555555555", "enabled": True, "routing_enabled": True, "eligible_roles": ["single", "fallback"]},
        {"candidate_id": second, "provider_release_id": "66666666-6666-4666-8666-666666666666", "model_binding_id": "77777777-7777-4777-8777-777777777777", "credential_ref": "88888888-8888-4888-8888-888888888888", "enabled": True, "routing_enabled": True, "eligible_roles": ["single", "fallback"]},
    ]
    return validate_routing_policy(
        {
            "schema_version": 1,
            "mode": mode,
            "anchor_candidate_id": anchor,
            "candidates": candidates,
            "fallback_order": [anchor, second],
            "ensemble": {"max_proposers": 2, "min_successful_proposers": 2, "proposer_timeout_seconds": 10, "aggregator_timeout_seconds": 10, "proposer_max_retries": 0},
        },
        profile_type="api_model",
    )


def test_capability_gate_reports_hard_rejections() -> None:
    context = build_routing_context(run_id="r", turn_index=1, messages=({"role": "user", "content": "hi"},), context_window_tokens=10)
    tier = RulesV1Classifier().classify(context)
    result = capability_gate(context, tier, (_candidate("a", roles=["fallback"], supports_tools=False),), role=RouteRole.SINGLE)
    assert not result.eligible
    assert result.rejected[0]["reason"] == "role_unavailable"


def test_engine_uses_policy_fallback_and_stable_score() -> None:
    context = build_routing_context(run_id="r", turn_index=1, messages=({"role": "user", "content": "hi"},), context_window_tokens=1000)
    candidates = (_candidate("a", roles=["single", "fallback"], quality="0.5000"), _candidate("b", roles=["single", "fallback"], quality="0.9000"))
    plan = RoutingPolicyEngine().plan(context, RulesV1Classifier().classify(context), candidates, {}, _policy())
    assert plan.selected[0].candidate["candidate_id"] == "b"
    assert [item.candidate["candidate_id"] for item in plan.fallback] == ["a"]
    assert plan.selected[0].score.quantize(Decimal("0.00000001")) == plan.selected[0].score


def test_engine_tie_break_uses_effective_quality_after_local_calibration() -> None:
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


def test_engine_fixed_uses_anchor_and_c0_floor() -> None:
    policy = _policy("fixed")
    context = build_routing_context(
        run_id="r",
        turn_index=1,
        messages=({"role": "user", "content": "repair"},),
        context_window_tokens=1000,
        run_purpose="repair",
    )
    candidates = (
        _candidate(policy.anchor_candidate_id, roles=["single", "fallback"], quality="0.1000", tier=0),
        _candidate(policy.fallback_order[1], roles=["single", "fallback"], quality="0.9000", tier=3),
    )
    classified = RulesV1Classifier().classify(context)
    assert classified.required_tier == "C3"
    plan = RoutingPolicyEngine().plan(context, classified, candidates, {}, policy)
    assert plan.mode is RoutingMode.FIXED
    assert plan.required_tier == "C0"
    assert plan.selected[0].candidate["candidate_id"] == policy.anchor_candidate_id


def test_engine_fixed_uses_policy_fallback_when_anchor_fails_capability_gate() -> None:
    policy = _policy("fixed")
    context = build_routing_context(
        run_id="r",
        turn_index=1,
        messages=({"role": "user", "content": "repair"},),
        context_window_tokens=1000,
        run_purpose="repair",
    )
    candidates = (
        _candidate(policy.anchor_candidate_id, roles=["single", "fallback"], supports_streaming=False),
        _candidate(policy.fallback_order[1], roles=["single", "fallback"], quality="0.9000", tier=0),
    )
    plan = RoutingPolicyEngine().plan(context, RulesV1Classifier().classify(context), candidates, {}, policy)
    assert plan.selected[0].candidate["candidate_id"] == policy.fallback_order[1]


def test_engine_rejects_unhealthy_all_candidates() -> None:
    context = build_routing_context(run_id="r", turn_index=1, messages=({"role": "user", "content": "hi"},), context_window_tokens=1000)
    candidates = (_candidate("a", roles=["single", "fallback"]), _candidate("b", roles=["single", "fallback"]))
    health = {
        DeploymentKey("company-1", "provider-a", "binding-a", "credential-a"): HealthState(availability_state="credential_invalid"),
        DeploymentKey("company-1", "provider-b", "binding-b", "credential-b"): HealthState(availability_state="credential_invalid"),
    }
    with pytest.raises(ValueError, match="MODEL_CAPABILITY_UNAVAILABLE"):
        RoutingPolicyEngine().plan(context, RulesV1Classifier().classify(context), candidates, health, _policy())


def test_engine_selective_ensemble_handles_equal_scores_deterministically() -> None:
    anchor = "11111111-1111-4111-8111-111111111111"
    reviewer = "22222222-2222-4222-8222-222222222222"
    aggregator = "33333333-3333-4333-8333-333333333333"
    policy = validate_routing_policy(
        {
            "schema_version": 1,
            "mode": "selective_ensemble",
            "anchor_candidate_id": anchor,
            "candidates": [
                {
                    "candidate_id": anchor,
                    "provider_release_id": "44444444-4444-4444-8444-444444444444",
                    "model_binding_id": "55555555-5555-4555-8555-555555555555",
                    "credential_ref": "66666666-6666-4666-8666-666666666666",
                    "enabled": True,
                    "routing_enabled": True,
                    "eligible_roles": ["single", "fallback", "proposer"],
                },
                {
                    "candidate_id": reviewer,
                    "provider_release_id": "77777777-7777-4777-8777-777777777777",
                    "model_binding_id": "88888888-8888-4888-8888-888888888888",
                    "credential_ref": "99999999-9999-4999-8999-999999999999",
                    "enabled": True,
                    "routing_enabled": True,
                    "eligible_roles": ["fallback", "proposer"],
                },
                {
                    "candidate_id": aggregator,
                    "provider_release_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    "model_binding_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                    "credential_ref": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                    "enabled": True,
                    "routing_enabled": True,
                    "eligible_roles": ["fallback", "aggregator"],
                },
            ],
            "fallback_order": [anchor, reviewer, aggregator],
            "ensemble": {
                "max_proposers": 2,
                "min_successful_proposers": 2,
                "proposer_timeout_seconds": 10,
                "aggregator_timeout_seconds": 10,
                "proposer_max_retries": 0,
            },
        },
        profile_type="api_model",
    )
    candidates = (
        _candidate(anchor, roles=["single", "fallback", "proposer"]),
        _candidate(reviewer, roles=["fallback", "proposer"]),
        _candidate(aggregator, roles=["fallback", "aggregator"]),
    )
    context = build_routing_context(
        run_id="r",
        turn_index=1,
        messages=({"role": "user", "content": "repair"},),
        context_window_tokens=1000,
        run_purpose="repair",
        verification_failures=1,
    )
    first = RoutingPolicyEngine().plan(context, RulesV1Classifier().classify(context), candidates, {}, policy)
    second = RoutingPolicyEngine().plan(context, RulesV1Classifier().classify(context), candidates, {}, policy)
    assert [item.candidate["candidate_id"] for item in first.selected] == [item.candidate["candidate_id"] for item in second.selected]
    assert first.aggregator is not None


def test_engine_respects_policy_max_proposers() -> None:
    ids = [
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
        "44444444-4444-4444-8444-444444444444",
        "55555555-5555-4555-8555-555555555555",
    ]
    raw_candidates = []
    runtime_candidates = []
    for index, candidate_id in enumerate(ids):
        roles = ["fallback", "proposer"]
        if index == 0:
            roles.append("single")
        if index == 4:
            roles = ["fallback", "aggregator"]
        raw_candidates.append(
            {
                "candidate_id": candidate_id,
                "provider_release_id": f"{index + 6:08x}-6666-4666-8666-{index + 6:012x}",
                "model_binding_id": f"{index + 7:08x}-7777-4777-8777-{index + 7:012x}",
                "credential_ref": f"{index + 8:08x}-8888-4888-8888-{index + 8:012x}",
                "enabled": True,
                "routing_enabled": True,
                "eligible_roles": roles,
            }
        )
        runtime_candidates.append(_candidate(candidate_id, roles=roles, quality="0.7000"))
    policy = validate_routing_policy(
        {
            "schema_version": 1,
            "mode": "selective_ensemble",
            "anchor_candidate_id": ids[0],
            "candidates": raw_candidates,
            "fallback_order": ids,
            "ensemble": {
                "max_proposers": 2,
                "min_successful_proposers": 2,
                "proposer_timeout_seconds": 10,
                "aggregator_timeout_seconds": 10,
                "proposer_max_retries": 0,
            },
        },
        profile_type="api_model",
    )
    context = build_routing_context(
        run_id="r",
        turn_index=1,
        messages=({"role": "user", "content": "repair"},),
        context_window_tokens=1000,
        run_purpose="repair",
        verification_failures=1,
    )
    plan = RoutingPolicyEngine().plan(context, RulesV1Classifier().classify(context), tuple(runtime_candidates), {}, policy)
    assert len(plan.selected) == 2
    assert plan.aggregator is not None


def test_engine_invalid_override_fails_safe_to_fixed() -> None:
    policy = _policy("smart_single")
    context = build_routing_context(
        run_id="r",
        turn_index=1,
        messages=({"role": "user", "content": "hi"},),
        context_window_tokens=1000,
        operator_forced_mode="invalid",
    )
    plan = RoutingPolicyEngine().plan(
        context,
        RulesV1Classifier().classify(context),
        (_candidate(policy.anchor_candidate_id, roles=["single", "fallback"]), _candidate(policy.fallback_order[1], roles=["single", "fallback"])),
        {},
        policy,
    )
    assert plan.mode is RoutingMode.FIXED


def test_engine_force_ensemble_requires_selective_policy() -> None:
    policy = _policy("smart_single")
    context = build_routing_context(
        run_id="r",
        turn_index=1,
        messages=({"role": "user", "content": "hi"},),
        context_window_tokens=1000,
        operator_forced_mode="force_ensemble",
    )
    with pytest.raises(ValueError, match="ROUTING_OVERRIDE_NOT_AVAILABLE"):
        RoutingPolicyEngine().plan(
            context,
            RulesV1Classifier().classify(context),
            (_candidate(policy.anchor_candidate_id, roles=["single", "fallback"]),),
            {},
            policy,
        )
