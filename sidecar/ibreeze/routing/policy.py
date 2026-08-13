from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from ibreeze.routing.canonical_json import canonical_json
from ibreeze.routing.types import RoutingMode

_ROLES = {"single", "proposer", "aggregator", "fallback"}


@dataclass(frozen=True, slots=True)
class CandidatePolicy:
    candidate_id: str
    provider_release_id: str
    model_binding_id: str
    credential_ref: str
    enabled: bool
    eligible_roles: tuple[str, ...]
    routing_enabled: bool
    credential_secret_version: int = 1


@dataclass(frozen=True, slots=True)
class EnsemblePolicy:
    max_proposers: int
    min_successful_proposers: int
    proposer_timeout_seconds: int
    aggregator_timeout_seconds: int
    proposer_max_retries: int


@dataclass(frozen=True, slots=True)
class ValidatedRoutingPolicy:
    canonical_json: str
    sha256: str
    mode: RoutingMode
    anchor_candidate_id: str
    candidates: tuple[CandidatePolicy, ...]
    fallback_order: tuple[str, ...]
    ensemble: EnsemblePolicy


def _issue(code: str) -> ValueError:
    return ValueError(code)


def _require_uuid(value: object) -> str:
    text = str(value)
    try:
        UUID(text)
    except (ValueError, TypeError, AttributeError):
        raise _issue("ROUTING_POLICY_INVALID") from None
    return text


def validate_routing_policy(
    raw: Mapping[str, object] | None,
    *,
    profile_type: str,
    catalog_release: Mapping[str, Mapping[str, object]] | None = None,
) -> ValidatedRoutingPolicy:
    if profile_type == "agent_cli":
        if raw:
            raise _issue("ROUTING_POLICY_FORBIDDEN")
        raise _issue("ROUTING_POLICY_NOT_APPLICABLE")
    if profile_type != "api_model" or not raw:
        raise _issue("ROUTING_POLICY_REQUIRED")
    data = dict(raw)
    if data.get("schema_version") != 1:
        raise _issue("ROUTING_POLICY_INVALID")
    try:
        mode = RoutingMode(str(data["mode"]))
        anchor = _require_uuid(data["anchor_candidate_id"])
        raw_candidates: object = data["candidates"]
        raw_fallback_order: object = data["fallback_order"]
        if not isinstance(raw_fallback_order, list):
            raise _issue("ROUTING_POLICY_INVALID")
        try:
            fallback_order = tuple(_require_uuid(item) for item in raw_fallback_order)
        except ValueError as exc:
            raise _issue("ROUTING_FALLBACK_INVALID") from exc
        raw_ensemble: object = data["ensemble"]
        if not isinstance(raw_ensemble, Mapping):
            raise _issue("ROUTING_POLICY_INVALID")
        ensemble_raw = dict(raw_ensemble)
    except ValueError as exc:
        if str(exc) == "ROUTING_FALLBACK_INVALID":
            raise
        raise _issue("ROUTING_POLICY_INVALID") from exc
    except (KeyError, TypeError) as exc:
        raise _issue("ROUTING_POLICY_INVALID") from exc
    if not isinstance(raw_candidates, list) or not 1 <= len(raw_candidates) <= 12:
        raise _issue("ROUTING_POLICY_INVALID")
    candidates: list[CandidatePolicy] = []
    seen: set[str] = set()
    for item in raw_candidates:
        if not isinstance(item, Mapping):
            raise _issue("ROUTING_POLICY_INVALID")
        try:
            candidate_id = _require_uuid(item["candidate_id"])
            roles = tuple(str(role) for role in item["eligible_roles"])
            candidate = CandidatePolicy(
                candidate_id=candidate_id,
                provider_release_id=_require_uuid(item["provider_release_id"]),
                model_binding_id=_require_uuid(item["model_binding_id"]),
                credential_ref=_require_uuid(item["credential_ref"]),
                enabled=bool(item["enabled"]),
                eligible_roles=roles,
                routing_enabled=bool(item["routing_enabled"]),
                credential_secret_version=int(item.get("credential_secret_version", 1)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise _issue("ROUTING_POLICY_INVALID") from exc
        if not candidate_id or candidate_id in seen:
            raise _issue("ROUTING_CANDIDATE_DUPLICATE")
        if (
            not candidate.provider_release_id
            or not candidate.model_binding_id
            or not candidate.credential_ref
            or candidate.credential_secret_version < 1
        ):
            raise _issue("ROUTING_POLICY_INVALID")
        if not roles or not set(roles) <= _ROLES or len(set(roles)) != len(roles):
            raise _issue("ROUTING_ROLE_INSUFFICIENT")
        if not candidate.routing_enabled:
            raise _issue("ROUTING_CANDIDATE_DISABLED")
        if not candidate.enabled:
            raise _issue("ROUTING_CANDIDATE_DISABLED")
        if catalog_release is not None and candidate_id not in catalog_release:
            raise _issue("ROUTING_CANDIDATE_OUTSIDE_RELEASE")
        if catalog_release is not None and candidate_id in catalog_release:
            binding = catalog_release[candidate_id]
            expected_provider = binding.get("provider_release_id")
            expected_model = binding.get("model_binding_id")
            if expected_provider is not None and str(expected_provider) != candidate.provider_release_id:
                raise _issue("ROUTING_CANDIDATE_OUTSIDE_RELEASE")
            if expected_model is not None and str(expected_model) != candidate.model_binding_id:
                raise _issue("ROUTING_CANDIDATE_OUTSIDE_RELEASE")
        seen.add(candidate_id)
        candidates.append(candidate)
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    anchor_candidate = by_id.get(anchor)
    if anchor_candidate is None or not anchor_candidate.enabled:
        raise _issue("ROUTING_ANCHOR_MISSING")
    if not {"single", "fallback"} <= set(anchor_candidate.eligible_roles):
        raise _issue("ROUTING_ROLE_INSUFFICIENT")
    if len(set(fallback_order)) != len(fallback_order) or not fallback_order:
        raise _issue("ROUTING_FALLBACK_INVALID")
    if any(item not in by_id or "fallback" not in by_id[item].eligible_roles for item in fallback_order):
        raise _issue("ROUTING_FALLBACK_INVALID")
    if anchor not in fallback_order:
        raise _issue("ROUTING_FALLBACK_INVALID")
    if mode != RoutingMode.FIXED and len(candidates) < 2:
        raise _issue("ROUTING_CANDIDATE_COUNT_INVALID")
    proposer_count = sum("proposer" in item.eligible_roles for item in candidates if item.enabled)
    aggregator_count = sum("aggregator" in item.eligible_roles for item in candidates if item.enabled)
    if mode == RoutingMode.SELECTIVE_ENSEMBLE and (proposer_count < 2 or aggregator_count < 1):
        raise _issue("ROUTING_ROLE_INSUFFICIENT")
    try:
        ensemble = EnsemblePolicy(
            max_proposers=int(ensemble_raw["max_proposers"]),
            min_successful_proposers=int(ensemble_raw["min_successful_proposers"]),
            proposer_timeout_seconds=int(ensemble_raw["proposer_timeout_seconds"]),
            aggregator_timeout_seconds=int(ensemble_raw["aggregator_timeout_seconds"]),
            proposer_max_retries=int(ensemble_raw["proposer_max_retries"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise _issue("ROUTING_POLICY_INVALID") from exc
    if not 2 <= ensemble.max_proposers <= 4 or not 1 <= ensemble.min_successful_proposers <= ensemble.max_proposers:
        raise _issue("ROUTING_ENSEMBLE_INVALID")
    if not 10 <= ensemble.proposer_timeout_seconds <= 300:
        raise _issue("ROUTING_ENSEMBLE_INVALID")
    if not 10 <= ensemble.aggregator_timeout_seconds <= 480:
        raise _issue("ROUTING_ENSEMBLE_INVALID")
    if not 0 <= ensemble.proposer_max_retries <= 2:
        raise _issue("ROUTING_ENSEMBLE_INVALID")
    if mode == RoutingMode.SELECTIVE_ENSEMBLE:
        effective_proposers = min(proposer_count, ensemble.max_proposers)
        default_quorum = {2: 2, 3: 2, 4: 3}.get(effective_proposers, 2)
        if ensemble.min_successful_proposers < default_quorum:
            raise _issue("ROUTING_ENSEMBLE_INVALID")
    canonical = canonical_json(data)
    return ValidatedRoutingPolicy(
        canonical_json=canonical,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        mode=mode,
        anchor_candidate_id=anchor,
        candidates=tuple(candidates),
        fallback_order=fallback_order,
        ensemble=ensemble,
    )
