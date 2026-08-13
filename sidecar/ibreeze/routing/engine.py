"""Capability gate and deterministic candidate scoring."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from ibreeze.routing.classifier import TierDecision
from ibreeze.routing.context import RoutingContext
from ibreeze.routing.health import HealthState
from ibreeze.routing.policy import ValidatedRoutingPolicy
from ibreeze.routing.types import DeploymentKey, RouteRole, RoutingMode


@dataclass(frozen=True, slots=True)
class GateResult:
    eligible: tuple[dict[str, Any], ...]
    rejected: tuple[dict[str, str], ...]


@dataclass(frozen=True, slots=True)
class PlannedDeployment:
    candidate: dict[str, Any]
    score: Decimal
    role: RouteRole


@dataclass(frozen=True, slots=True)
class RoutePlan:
    mode: RoutingMode
    selected_kind: str
    selected: tuple[PlannedDeployment, ...]
    fallback: tuple[PlannedDeployment, ...]
    aggregator: PlannedDeployment | None
    required_tier: str
    confidence: Decimal
    policy_trail: tuple[dict[str, object], ...]


def _as_decimal(value: object, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _effective_quality(candidate: Mapping[str, Any], calibration: Decimal = Decimal("0")) -> Decimal:
    """Return the bounded quality used by both scoring and tie-breaking."""
    stored = candidate.get("_effective_quality")
    value = _as_decimal(stored if stored is not None else candidate.get("quality_prior"), "0.5")
    if stored is None:
        value += calibration
    return min(Decimal("1"), max(Decimal("0"), value))


def _stable_score_key(item: tuple[Decimal, Mapping[str, Any]]) -> tuple[object, ...]:
    """Match the documented deterministic score tie-break order."""
    score, candidate = item
    return (
        -score,
        -_effective_quality(candidate),
        int(candidate.get("latency_prior_ms", 3000)),
        str(candidate.get("model_binding_id", "")),
        str(candidate.get("candidate_id", "")),
    )


def _health_for(candidate: Mapping[str, Any], health: Mapping[DeploymentKey, HealthState]) -> HealthState:
    key = DeploymentKey(
        company_id=str(candidate.get("company_id", "")),
        provider_release_id=str(candidate.get("provider_release_id", "")),
        model_binding_id=str(candidate.get("model_binding_id", "")),
        credential_ref=str(candidate.get("credential_ref", "")),
    )
    return health.get(key, HealthState())


def capability_gate(
    context: RoutingContext,
    tier: TierDecision,
    candidates: tuple[dict[str, Any], ...],
    *,
    role: RouteRole,
    health: Mapping[DeploymentKey, HealthState] | None = None,
    allow_anchor_disabled: bool = False,
) -> GateResult:
    health = health or {}
    required = int(tier.required_tier[1:])
    result: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for candidate in candidates:
        cid = str(candidate.get("candidate_id", ""))
        roles = set(candidate.get("eligible_roles", ()))
        reason: str | None = None
        if not candidate.get("routing_enabled", False) and not allow_anchor_disabled:
            reason = "routing_disabled"
        elif role.value not in roles:
            reason = "role_unavailable"
        elif int(candidate.get("routing_tier", 0)) < required:
            reason = "tier_unavailable"
        elif context.tool_count and not candidate.get("supports_tools", False):
            reason = "tools_unavailable"
        elif context.attachment_types and not candidate.get("supports_vision", False):
            reason = "vision_unavailable"
        elif not candidate.get("supports_streaming", False):
            reason = "streaming_unavailable"
        elif context.estimated_input_tokens + int(candidate.get("max_output_tokens", 0)) > int(candidate.get("context_window", 0)):
            reason = "context_overflow"
        elif not _health_for(candidate, health).is_eligible():
            reason = "deployment_unhealthy"
        if reason:
            rejected.append({"candidate_id": cid, "reason": reason})
        else:
            result.append(candidate)
    return GateResult(tuple(result), tuple(rejected))


def score_candidate(
    candidate: Mapping[str, Any],
    *,
    required_tier: str,
    context: RoutingContext,
    health: HealthState | None = None,
    calibration: Decimal = Decimal("0"),
) -> Decimal:
    health = health or HealthState()
    tier = int(required_tier[1:])
    quality = _effective_quality(candidate, calibration)
    reliability = _as_decimal(candidate.get("tool_reliability_prior"), "0.5") if context.tool_count else Decimal("1")
    reliability = min(Decimal("1"), max(Decimal("0"), reliability))
    affinity = max(Decimal("0"), Decimal("1") - abs(int(candidate.get("routing_tier", 0)) - tier) / Decimal("3"))
    health_score = Decimal("1") if health.consecutive_strikes == 0 else Decimal("0.5")
    latency = Decimal("1") / (Decimal("1") + _as_decimal(candidate.get("latency_prior_ms"), "3000") / Decimal("1000"))
    score = (
        Decimal("0.40") * quality
        + Decimal("0.20") * reliability
        + Decimal("0.15") * affinity
        + Decimal("0.15") * health_score
        + Decimal("0.10") * latency
    )
    return score.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


class CapabilityGate:
    def filter(
        self,
        context: RoutingContext,
        tier: TierDecision,
        candidates: tuple[dict[str, Any], ...],
        role: RouteRole,
        health: Mapping[DeploymentKey, HealthState] | None = None,
    ) -> GateResult:
        return capability_gate(context, tier, candidates, role=role, health=health)


class RoutingPolicyEngine:
    def plan(
        self,
        context: RoutingContext,
        tier: TierDecision,
        candidates: tuple[dict[str, Any], ...],
        health: Mapping[DeploymentKey, HealthState],
        policy: ValidatedRoutingPolicy,
    ) -> RoutePlan:
        mode = policy.mode
        effective_mode = mode
        if context.operator_forced_mode not in {None, "force_fixed", "force_single", "force_ensemble"}:
            effective_mode = RoutingMode.FIXED
        elif context.operator_forced_mode == "force_ensemble" and mode != RoutingMode.SELECTIVE_ENSEMBLE:
            raise ValueError("ROUTING_OVERRIDE_NOT_AVAILABLE")
        elif context.operator_forced_mode == "force_fixed":
            effective_mode = RoutingMode.FIXED
        elif context.operator_forced_mode == "force_single" and mode == RoutingMode.SELECTIVE_ENSEMBLE:
            effective_mode = RoutingMode.SMART_SINGLE
        # Fixed mode is a compatibility path: it does not classify task
        # difficulty.  Hard capability checks still run, but a C2/C3
        # classifier result must not disqualify the configured Anchor.
        effective_tier = tier
        if effective_mode == RoutingMode.FIXED:
            effective_tier = TierDecision("C0", tier.confidence, tier.rules, tier.policy_trail)
        single_gate = capability_gate(
            context,
            effective_tier,
            candidates,
            role=RouteRole.SINGLE,
            health=health,
            allow_anchor_disabled=effective_mode == RoutingMode.FIXED,
        )
        fallback_gate = capability_gate(context, effective_tier, candidates, role=RouteRole.FALLBACK, health=health)
        proposer_gate = capability_gate(context, effective_tier, candidates, role=RouteRole.PROPOSER, health=health)
        aggregator_gate = capability_gate(context, effective_tier, candidates, role=RouteRole.AGGREGATOR, health=health)
        if effective_mode == RoutingMode.FIXED:
            # A fixed run may use its policy-defined fallback chain when the
            # Anchor fails a hard capability check.  It must never silently
            # switch to an arbitrary smart-ranked single candidate.
            anchor = next(
                (
                    candidate
                    for candidate in single_gate.eligible
                    if str(candidate.get("candidate_id")) == policy.anchor_candidate_id
                ),
                None,
            )
            if anchor is None:
                fallback_candidates = {
                    str(candidate.get("candidate_id")): candidate for candidate in fallback_gate.eligible
                }
                anchor = next(
                    (fallback_candidates[candidate_id] for candidate_id in policy.fallback_order if candidate_id in fallback_candidates),
                    None,
                )
            if anchor is None:
                raise ValueError("MODEL_CAPABILITY_UNAVAILABLE")
            single_gate = GateResult((anchor,), single_gate.rejected)
        elif not single_gate.eligible:
            raise ValueError("MODEL_CAPABILITY_UNAVAILABLE")
        ranked = sorted(
            (
                (
                    score_candidate(c, required_tier=effective_tier.required_tier, context=context, health=_health_for(c, health)),
                    c,
                )
                for c in single_gate.eligible
            ),
            key=_stable_score_key,
        )
        primary_score, primary_candidate = ranked[0]
        if effective_mode == RoutingMode.FIXED:
            anchor = next(
                (
                    candidate
                    for candidate in single_gate.eligible
                    if str(candidate.get("candidate_id")) == policy.anchor_candidate_id
                ),
                None,
            )
            if anchor is not None:
                primary_candidate = anchor
                primary_score = score_candidate(
                    anchor,
                    required_tier=effective_tier.required_tier,
                    context=context,
                    health=_health_for(anchor, health),
                )
        primary = PlannedDeployment(primary_candidate, primary_score, RouteRole.SINGLE)
        fallback_scores = {
            str(candidate.get("candidate_id")): score
            for score, candidate in (
                (
                    score_candidate(c, required_tier=effective_tier.required_tier, context=context, health=_health_for(c, health)),
                    c,
                )
                for c in fallback_gate.eligible
            )
        }
        fallback_by_id = {str(candidate.get("candidate_id")): candidate for candidate in fallback_gate.eligible}
        ordered_fallback_ids = list(policy.fallback_order) + [
            str(candidate.get("candidate_id"))
            for _score, candidate in ranked
            if str(candidate.get("candidate_id")) not in policy.fallback_order
        ]
        fallback = tuple(
            PlannedDeployment(fallback_by_id[candidate_id], fallback_scores[candidate_id], RouteRole.FALLBACK)
            for candidate_id in ordered_fallback_ids
            if candidate_id in fallback_by_id and candidate_id != primary_candidate.get("candidate_id")
        )
        selected: tuple[PlannedDeployment, ...] = (primary,)
        aggregator = None
        selected_kind = "single"
        if effective_mode == RoutingMode.SELECTIVE_ENSEMBLE and context.input_origin in {"production", "evaluation"}:
            proposer_scored = [
                (
                    score_candidate(c, required_tier=effective_tier.required_tier, context=context, health=_health_for(c, health)),
                    c,
                )
                for c in proposer_gate.eligible
            ]
            proposer_scored.sort(key=_stable_score_key)
            aggregator_scored = [
                (
                    score_candidate(c, required_tier=effective_tier.required_tier, context=context, health=_health_for(c, health)),
                    c,
                )
                for c in aggregator_gate.eligible
            ]
            aggregator_scored.sort(key=_stable_score_key)
            from ibreeze.routing.ensemble import select_proposer_candidates

            max_proposers = min(4, policy.ensemble.max_proposers, len(proposer_scored))
            proposer_lineup = select_proposer_candidates(
                proposer_scored,
                max_proposers=max_proposers,
                required_tier=effective_tier.required_tier,
            )
            proposers = [
                PlannedDeployment(
                    c,
                    next(score for score, item in proposer_scored if item is c),
                    RouteRole.PROPOSER,
                )
                for c, _role in proposer_lineup
            ]
            aggregators = [PlannedDeployment(c, s, RouteRole.AGGREGATOR) for s, c in aggregator_scored]
            from ibreeze.routing.ensemble import should_ensemble

            ensemble_enabled = should_ensemble(
                context,
                confidence=tier.confidence,
                proposer_count=len(proposers),
                aggregator_available=bool(aggregators),
                estimated_input_tokens=context.estimated_input_tokens,
                aggregator_context_window=(
                    int(aggregators[0].candidate.get("context_window", 0))
                    - int(aggregators[0].candidate.get("max_output_tokens", 0))
                    if aggregators
                    else None
                ),
                max_proposers=max_proposers,
                proposer_provider_count=len({str(candidate.candidate.get("provider_release_id")) for candidate in proposers}),
                vision_proposer_count=sum(bool(candidate.candidate.get("supports_vision", False)) for candidate in proposers),
                aggregator_supports_vision=bool(aggregators and aggregators[0].candidate.get("supports_vision", False)),
                force_ensemble=context.operator_forced_mode == "force_ensemble",
                required_tier=effective_tier.required_tier,
            )
            if ensemble_enabled:
                selected = tuple(proposers)
                aggregator = aggregators[0]
                selected_kind = "ensemble"
        return RoutePlan(
            effective_mode,
            selected_kind,
            selected,
            fallback,
            aggregator,
            effective_tier.required_tier,
            Decimal(str(tier.confidence)),
            tier.policy_trail,
        )
