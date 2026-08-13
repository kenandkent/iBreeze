"""Deployment health state and deterministic strike/bench policy."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from ibreeze.routing.types import ProviderFailureKind


@dataclass(frozen=True, slots=True)
class HealthState:
    availability_state: str = "ready"
    consecutive_strikes: int = 0
    benched_until: datetime | None = None
    last_failure_kind: ProviderFailureKind | None = None
    last_failure_at: datetime | None = None
    last_success_at: datetime | None = None
    version: int = 1

    def is_eligible(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        return self.availability_state == "ready" and (self.benched_until is None or self.benched_until <= now)


def _parse_timestamp(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def load_health_ledger(
    read_pool: Any | None,
    company_id: str,
    candidates: Sequence[Mapping[str, object]],
) -> dict[str, HealthState]:
    """Load persisted Deployment Health into candidate-id keyed runtime state.

    The database keys health by the hashed credential reference, while the
    immutable Snapshot identifies a candidate by UUID.  The mapping is done
    only against the current company and Snapshot candidate set, so a health
    row from another company or another credential cannot influence routing.
    """
    if not candidates or not company_id:
        return {}
    query_all = getattr(read_pool, "query_all", None)
    if not callable(query_all):
        raise RuntimeError("ROUTING_HEALTH_UNAVAILABLE")
    candidate_ids_by_key: dict[tuple[str, str, str], list[str]] = {}
    for candidate in candidates:
        credential_ref = str(candidate.get("credential_ref", ""))
        key = (
            str(candidate.get("provider_release_id", "")),
            str(candidate.get("model_binding_id", "")),
            hashlib.sha256(credential_ref.encode("utf-8")).hexdigest(),
        )
        candidate_ids_by_key.setdefault(key, []).append(str(candidate.get("candidate_id", "")))
    rows = await query_all(
        """SELECT provider_release_id,model_binding_id,credential_ref_sha256,
                  availability_state,consecutive_strikes,benched_until,
                  last_failure_kind,last_failure_at,last_success_at,version
             FROM deployment_health WHERE company_id=?""",
        (company_id,),
    )
    result: dict[str, HealthState] = {}
    for row in rows:
        key = (
            str(row.get("provider_release_id", "")),
            str(row.get("model_binding_id", "")),
            str(row.get("credential_ref_sha256", "")),
        )
        candidate_ids = candidate_ids_by_key.get(key, ())
        if not candidate_ids:
            continue
        state_value = str(row.get("availability_state", "credential_invalid"))
        if state_value not in {"ready", "credential_invalid"}:
            # A corrupted health state must fail closed rather than silently
            # bypassing a possible bench.
            state_value = "credential_invalid"
        try:
            strikes = max(0, int(row.get("consecutive_strikes", 0) or 0))
        except (TypeError, ValueError):
            strikes = 0
        try:
            version = max(1, int(row.get("version", 1) or 1))
        except (TypeError, ValueError):
            version = 1
        failure_kind: ProviderFailureKind | None = None
        raw_failure = row.get("last_failure_kind")
        if raw_failure:
            try:
                failure_kind = ProviderFailureKind(str(raw_failure))
            except ValueError:
                failure_kind = None
        state = HealthState(
            availability_state=state_value,
            consecutive_strikes=strikes,
            benched_until=_parse_timestamp(row.get("benched_until")),
            last_failure_kind=failure_kind,
            last_failure_at=_parse_timestamp(row.get("last_failure_at")),
            last_success_at=_parse_timestamp(row.get("last_success_at")),
            version=version,
        )
        for candidate_id in candidate_ids:
            if candidate_id:
                result[candidate_id] = state
    return result


_NO_STRIKE = {ProviderFailureKind.CONTEXT_OVERFLOW, ProviderFailureKind.BAD_REQUEST, ProviderFailureKind.POLICY_REFUSAL}
_CREDENTIAL_FAILURES = {ProviderFailureKind.AUTH_INVALID}
_IMMEDIATE_BENCH = {
    ProviderFailureKind.RATE_LIMITED,
    ProviderFailureKind.MODEL_NOT_FOUND,
    ProviderFailureKind.UNSUPPORTED_CAPABILITY,
    ProviderFailureKind.INSUFFICIENT_CREDITS,
}


def apply_failure(
    state: HealthState,
    kind: ProviderFailureKind,
    *,
    now: datetime | None = None,
    retry_after_seconds: int | None = None,
) -> HealthState:
    now = now or datetime.now(UTC)
    if kind in _CREDENTIAL_FAILURES:
        return replace(
            state, availability_state="credential_invalid", last_failure_kind=kind, last_failure_at=now, version=state.version + 1
        )
    if kind in _NO_STRIKE:
        return replace(state, last_failure_kind=kind, last_failure_at=now, version=state.version + 1)
    strikes = state.consecutive_strikes + 1
    if kind == ProviderFailureKind.RATE_LIMITED:
        # RATE_LIMITED is the one failure kind whose bench window is dictated
        # by the provider.  A missing Retry-After has the contract default of
        # 30 seconds; do not widen a shorter provider window to 30 seconds.
        duration = min(900, max(1, retry_after_seconds if retry_after_seconds is not None else 30))
    else:
        duration = 30
    benched: datetime | None = state.benched_until
    if kind in _IMMEDIATE_BENCH or strikes >= 3:
        benched = now + timedelta(seconds=duration)
    return replace(
        state, consecutive_strikes=strikes, benched_until=benched, last_failure_kind=kind, last_failure_at=now, version=state.version + 1
    )


def apply_success(state: HealthState, *, now: datetime | None = None) -> HealthState:
    return replace(
        state,
        availability_state="ready",
        consecutive_strikes=0,
        benched_until=None,
        last_success_at=now or datetime.now(UTC),
        version=state.version + 1,
    )


def cleanup_expired(state: HealthState, *, now: datetime | None = None) -> HealthState:
    now = now or datetime.now(UTC)
    if state.benched_until is not None and state.benched_until <= now and state.availability_state == "ready":
        return replace(state, benched_until=None, version=state.version + 1)
    return state
