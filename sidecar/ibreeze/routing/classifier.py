"""The versioned deterministic Rules v1 classifier."""

from __future__ import annotations

from dataclasses import dataclass

from ibreeze.routing.context import RoutingContext


@dataclass(frozen=True, slots=True)
class TierDecision:
    required_tier: str
    confidence: float
    rules: tuple[str, ...]
    policy_trail: tuple[dict[str, object], ...]


class RulesV1Classifier:
    version = "rules-v1"

    def classify(self, context: RoutingContext) -> TierDecision:
        tier = 0
        rules: list[str] = []

        def raise_to(level: int, rule: str) -> None:
            nonlocal tier
            if level > tier:
                tier = level
            rules.append(rule)

        if context.message_char_count >= 4000 or context.estimated_input_tokens >= 8000:
            raise_to(1, "message_size")
        if context.contains_code and context.contains_review_signal:
            raise_to(2, "code_review_or_verification")
        if context.contains_structured_schema:
            raise_to(2, "structured_schema")
        if context.run_purpose in {"company_plan", "review", "verification", "summary"}:
            raise_to(2, "workflow_review")
        if context.run_purpose in {"repair", "merge"}:
            raise_to(3, "repair_or_merge")
        if context.context_pressure >= 0.75:
            raise_to(2, "context_pressure")
        if context.context_pressure >= 0.90:
            raise_to(3, "context_pressure_critical")
        if context.prior_tool_failures >= 1 or context.provider_failures >= 2:
            old = tier
            tier = min(3, tier + 1)
            rules.append("failure_history")
            if tier == old:
                rules.append("failure_history_capped")
        if context.verification_failures >= 1:
            raise_to(3, "verification_failure")
        if context.open_blocker_high_count >= 1:
            raise_to(3, "open_blocker_high")

        confidence = 0.60 if not rules else 0.70 if len(rules) == 1 else 0.85
        if context.operator_forced_mode and context.operator_forced_mode not in {"force_fixed", "force_single", "force_ensemble"}:
            confidence = 0.40
            rules.append("operator_conflict")
        trail = tuple({"rule": rule, "tier_after": tier} for rule in rules)
        return TierDecision(f"C{tier}", confidence, tuple(rules), trail)


def classify(context: RoutingContext) -> TierDecision:
    return RulesV1Classifier().classify(context)
