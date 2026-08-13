from __future__ import annotations

from decimal import Decimal

import pytest

from ibreeze.routing.classifier import RulesV1Classifier
from ibreeze.routing.context import build_routing_context
from ibreeze.routing.engine import CapabilityGate, RoutingPolicyEngine, _as_decimal, capability_gate, score_candidate
from ibreeze.routing.policy import validate_routing_policy
from ibreeze.routing.types import RouteRole, RoutingMode


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


def _selective_policy():
    anchor = "11111111-1111-4111-8111-111111111111"
    reviewer = "22222222-2222-4222-8222-222222222222"
    aggregator = "33333333-3333-4333-8333-333333333333"
    raw_candidates = [
        {"candidate_id": anchor, "provider_release_id": "44444444-4444-4444-8444-444444444444", "model_binding_id": "55555555-5555-4555-8555-555555555555", "credential_ref": "66666666-6666-4666-8666-666666666666", "enabled": True, "routing_enabled": True, "eligible_roles": ["single", "fallback", "proposer"]},
        {"candidate_id": reviewer, "provider_release_id": "77777777-7777-4777-8777-777777777777", "model_binding_id": "88888888-8888-4888-8888-888888888888", "credential_ref": "99999999-9999-4999-8999-999999999999", "enabled": True, "routing_enabled": True, "eligible_roles": ["fallback", "proposer"]},
        {"candidate_id": aggregator, "provider_release_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "model_binding_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "credential_ref": "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "enabled": True, "routing_enabled": True, "eligible_roles": ["fallback", "aggregator"]},
    ]
    return validate_routing_policy(
        {
            "schema_version": 1,
            "mode": "selective_ensemble",
            "anchor_candidate_id": anchor,
            "candidates": raw_candidates,
            "fallback_order": [anchor, reviewer, aggregator],
            "ensemble": {"max_proposers": 2, "min_successful_proposers": 2, "proposer_timeout_seconds": 10, "aggregator_timeout_seconds": 10, "proposer_max_retries": 0},
        },
        profile_type="api_model",
    )


def _context(**kwargs):
    defaults = {"run_id": "r", "turn_index": 1, "messages": ({"role": "user", "content": "hi"},), "context_window_tokens": 1000}
    defaults.update(kwargs)
    return build_routing_context(**defaults)


def test_as_decimal_falls_back_on_invalid_value() -> None:
    assert _as_decimal(object(), "0.5") == Decimal("0.5")
    context = _context()
    score = score_candidate({"candidate_id": "x", "quality_prior": "bogus", "tool_reliability_prior": "also-bogus", "latency_prior_ms": 100, "routing_tier": 3}, required_tier="C1", context=context)
    assert score >= Decimal("0")


@pytest.mark.parametrize(
    "candidate, kwargs, reason",
    [
        (lambda: _candidate("a", roles=["single"], routing_enabled=False), {}, "routing_disabled"),
        (lambda: _candidate("a", roles=["single"], tier=0), {"run_purpose": "repair"}, "tier_unavailable"),
        (lambda: _candidate("a", roles=["single"], supports_tools=False), {"tool_count": 1}, "tools_unavailable"),
        (lambda: _candidate("a", roles=["single"], supports_vision=False), {"attachment_types": ("image",)}, "vision_unavailable"),
        (lambda: _candidate("a", roles=["single"], context_window=100, max_output_tokens=1000), {}, "context_overflow"),
    ],
)
def test_capability_gate_hard_rejection_reasons(candidate, kwargs, reason: str) -> None:
    context = _context(**kwargs)
    tier = RulesV1Classifier().classify(context)
    result = capability_gate(context, tier, (candidate(),), role=RouteRole.SINGLE)
    assert not result.eligible
    assert result.rejected[0]["reason"] == reason


def test_capability_gate_class_wrapper() -> None:
    context = _context()
    tier = RulesV1Classifier().classify(context)
    result = CapabilityGate().filter(context, tier, (_candidate("a", roles=["single"]),), RouteRole.SINGLE)
    assert result.eligible


def test_engine_force_fixed_and_force_single_overrides() -> None:
    candidates = (
        _candidate("11111111-1111-4111-8111-111111111111", roles=["single", "fallback"]),
        _candidate("22222222-2222-4222-8222-222222222222", roles=["single", "fallback"]),
    )
    fixed_context = _context(operator_forced_mode="force_fixed")
    plan = RoutingPolicyEngine().plan(fixed_context, RulesV1Classifier().classify(fixed_context), candidates, {}, _policy("smart_single"))
    assert plan.mode is RoutingMode.FIXED

    single_context = _context(operator_forced_mode="force_single")
    plan = RoutingPolicyEngine().plan(single_context, RulesV1Classifier().classify(single_context), candidates, {}, _selective_policy())
    assert plan.mode is RoutingMode.SMART_SINGLE


def test_engine_fixed_raises_when_no_capable_candidate() -> None:
    context = _context(run_purpose="repair")
    candidates = (
        _candidate("11111111-1111-4111-8111-111111111111", roles=["single", "fallback"], supports_streaming=False),
        _candidate("22222222-2222-4222-8222-222222222222", roles=["single", "fallback"], supports_streaming=False),
    )
    with pytest.raises(ValueError, match="MODEL_CAPABILITY_UNAVAILABLE"):
        RoutingPolicyEngine().plan(context, RulesV1Classifier().classify(context), candidates, {}, _policy("fixed"))


def test_engine_selective_without_trigger_stays_single() -> None:
    context = _context()
    candidates = (
        _candidate("11111111-1111-4111-8111-111111111111", roles=["single", "fallback", "proposer"]),
        _candidate("22222222-2222-4222-8222-222222222222", roles=["fallback", "proposer"]),
        _candidate("33333333-3333-4333-8333-333333333333", roles=["fallback", "aggregator"]),
    )
    plan = RoutingPolicyEngine().plan(context, RulesV1Classifier().classify(context), candidates, {}, _selective_policy())
    assert plan.selected_kind == "single"
    assert plan.aggregator is None
