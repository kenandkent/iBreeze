from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from ibreeze.routing.canonical_json import canonical_json
from ibreeze.routing.policy import validate_routing_policy


async def resolve_candidate_bindings(
    db: Any,
    *,
    company_id: str,
    employee_id: str,
    catalog_release_id: str,
    profile_type: str,
    runtime_binding: dict[str, Any],
    routing_policy_json: str | None,
) -> tuple[str, str, str]:
    """Expand an immutable profile policy into canonical snapshot bindings.

    The resolver runs during plan confirmation. It only reads the pinned
    Catalog release and never falls back to the global directory.
    """
    if profile_type == "agent_cli":
        return "{}", "", "fixed"
    try:
        policy = json.loads(routing_policy_json or "{}")
    except (TypeError, ValueError) as exc:
        raise ValueError("ROUTING_POLICY_INVALID") from exc
    if not isinstance(policy, dict):
        raise ValueError("ROUTING_POLICY_INVALID")
    model_rows = await db.execute(
        "SELECT resource_id, content_json FROM catalog_cache_resources WHERE release_id=? AND resource_type='model'",
        (catalog_release_id,),
    )
    resources = {str(row[0]): json.loads(row[1]) for row in await model_rows.fetchall()}
    provider_rows = await db.execute(
        "SELECT content_json FROM catalog_cache_resources WHERE release_id=? AND resource_type='provider'",
        (catalog_release_id,),
    )
    providers: list[dict[str, Any]] = [json.loads(row[0]) for row in await provider_rows.fetchall()]
    provider_by_binding: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for provider in providers:
        for binding in provider.get("model_bindings", []):
            if isinstance(binding, dict) and binding.get("binding_id"):
                model = resources.get(str(binding.get("model_id")), {})
                provider_by_binding[str(binding["binding_id"])] = (provider, model)
    raw_policy_candidates = policy.get("candidates", [])
    if not isinstance(raw_policy_candidates, list):
        raise ValueError("ROUTING_POLICY_INVALID")
    catalog_view: dict[str, dict[str, object]] = {
        str(item.get("candidate_id")): {} for item in raw_policy_candidates if isinstance(item, dict)
    }
    validated = validate_routing_policy(policy, profile_type=profile_type, catalog_release=catalog_view)
    expanded: list[dict[str, Any]] = []
    for candidate in validated.candidates:
        provider, model = provider_by_binding.get(candidate.model_binding_id, ({}, {}))
        if not provider or not model:
            raise ValueError("ROUTING_CANDIDATE_OUTSIDE_RELEASE")
        if str(provider.get("id")) != candidate.provider_release_id:
            raise ValueError("ROUTING_CANDIDATE_OUTSIDE_RELEASE")
        expanded.append(
            {
                "candidate_id": candidate.candidate_id,
                "provider_release_id": candidate.provider_release_id,
                "provider_key": provider.get("key", ""),
                "provider_protocol": provider.get("protocol", ""),
                "model_binding_id": candidate.model_binding_id,
                "model_id": model.get("id", ""),
                "provider_model_name": next(
                    (
                        item.get("provider_model_name", "")
                        for item in provider.get("model_bindings", [])
                        if item.get("binding_id") == candidate.model_binding_id
                    ),
                    "",
                ),
                "credential_ref": candidate.credential_ref,
                "credential_secret_version": int(
                    candidate.credential_secret_version or runtime_binding.get("credential_secret_version", 1)
                ),
                "context_window": int(model.get("context_window", 0)),
                "max_output_tokens": int(model.get("max_output_tokens", 0)),
                "supports_tools": bool(model.get("supports_tools", False)),
                "supports_streaming": bool(model.get("supports_streaming", False)),
                "supports_vision": bool(model.get("supports_vision", False)),
                "routing_tier": int(model.get("routing_tier", 0)),
                "quality_prior": str(Decimal(str(model.get("quality_prior", "0.5000"))).quantize(Decimal("0.0001"))),
                "tool_reliability_prior": str(Decimal(str(model.get("tool_reliability_prior", "0.5000"))).quantize(Decimal("0.0001"))),
                "latency_prior_ms": int(model.get("latency_prior_ms", 3000)),
                "model_family": model.get("model_family", "unknown"),
                "model_vendor": model.get("model_vendor", "unknown"),
                "architecture_class": model.get("architecture_class", "unknown"),
                "supports_reasoning": bool(model.get("supports_reasoning", False)),
                "reasoning_levels": list(model.get("reasoning_levels", [])),
                "input_price_microusd_per_million": int(model.get("input_price_microusd_per_million", 0)),
                "output_price_microusd_per_million": int(model.get("output_price_microusd_per_million", 0)),
                "routing_enabled": bool(model.get("routing_enabled", False)),
                "eligible_roles": list(candidate.eligible_roles),
                "request_defaults_sha256": hashlib.sha256(
                    canonical_json(
                        next(
                            (
                                item.get("request_defaults", {})
                                for item in provider.get("model_bindings", [])
                                if item.get("binding_id") == candidate.model_binding_id
                            ),
                            {},
                        )
                    ).encode()
                ).hexdigest(),
            }
        )
    expanded.sort(key=lambda item: (str(item["model_binding_id"]), str(item["candidate_id"])))
    canonical = canonical_json(expanded)
    return canonical, hashlib.sha256(canonical.encode()).hexdigest(), validated.mode.value
