from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from ibreeze.routing.types import ProviderFailureKind, RouteRole, RoutingMode


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class RoutingRepository:
    """SQLite repository whose methods must run inside WriteQueue transactions."""

    async def create_decision(
        self,
        db: aiosqlite.Connection,
        *,
        decision_id: str,
        company_id: str,
        run_id: str,
        turn_index: int,
        execution_snapshot_id: str,
        routing_mode: RoutingMode,
        classifier_version: str,
        input_fingerprint: str,
        required_tier: str,
        confidence: float,
        selected_kind: str,
        selected_bindings: list[dict[str, Any]],
        policy_trail: list[dict[str, Any]],
        aggregator_candidate_id: str | None = None,
    ) -> dict[str, Any]:
        if not 0 <= confidence <= 1 or len(input_fingerprint) != 64:
            raise ValueError("ROUTE_DECISION_INVALID")
        if required_tier not in {"C0", "C1", "C2", "C3"}:
            raise ValueError("ROUTE_DECISION_TIER_INVALID")
        if selected_kind not in {"single", "ensemble"} or not selected_bindings:
            raise ValueError("ROUTE_SELECTION_INVALID")
        if not all(item.get("candidate_id") and item.get("role") for item in selected_bindings):
            raise ValueError("ROUTE_SELECTION_INVALID")
        now = _now()
        try:
            await db.execute(
                """INSERT INTO route_decisions
                   (id, company_id, run_id, turn_index, execution_snapshot_id,
                    routing_mode, classifier_version, input_fingerprint, required_tier,
                    confidence, selected_kind, selected_bindings_json,
                    aggregator_candidate_id, policy_trail_json, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'planned', ?)""",
                (
                    decision_id,
                    company_id,
                    run_id,
                    turn_index,
                    execution_snapshot_id,
                    str(routing_mode),
                    classifier_version,
                    input_fingerprint,
                    required_tier,
                    confidence,
                    selected_kind,
                    _json(selected_bindings),
                    aggregator_candidate_id,
                    _json(policy_trail),
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("ROUTE_DECISION_EXISTS") from exc
        return {
            "id": decision_id,
            "company_id": company_id,
            "run_id": run_id,
            "turn_index": turn_index,
            "routing_mode": str(routing_mode),
            "status": "planned",
            "created_at": now,
        }

    async def transition_decision(
        self,
        db: aiosqlite.Connection,
        decision_id: str,
        expected_status: str,
        target_status: str,
    ) -> bool:
        allowed_targets = {
            "planned": {"executing", "failed", "cancelled"},
            "executing": {"succeeded", "failed", "cancelled"},
            "succeeded": set(),
            "failed": set(),
            "cancelled": set(),
        }
        if expected_status not in allowed_targets:
            raise ValueError("ROUTE_DECISION_STATUS_INVALID")
        if target_status not in allowed_targets[expected_status]:
            raise ValueError("ROUTE_DECISION_TRANSITION_INVALID")
        cursor = await db.execute(
            """UPDATE route_decisions
               SET status=?, completed_at=CASE WHEN ? IN ('succeeded','failed','cancelled') THEN ? ELSE completed_at END
               WHERE id=? AND status=?""",
            (target_status, target_status, _now(), decision_id, expected_status),
        )
        return cursor.rowcount == 1

    async def create_attempt(
        self,
        db: aiosqlite.Connection,
        *,
        attempt_id: str,
        route_decision_id: str,
        company_id: str,
        run_id: str,
        execution_snapshot_id: str,
        attempt_sequence: int,
        role: RouteRole,
        candidate_id: str,
        provider_release_id: str,
        model_binding_id: str,
        credential_ref_sha256: str,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        if attempt_sequence < 1 or len(credential_ref_sha256) != 64:
            raise ValueError("ROUTE_ATTEMPT_INVALID")
        now = _now()
        try:
            await db.execute(
                """INSERT INTO route_attempts
                   (id, route_decision_id, company_id, run_id, execution_snapshot_id,
                    attempt_sequence, role, candidate_id, provider_release_id,
                    model_binding_id, credential_ref_sha256, request_id, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'created', ?)""",
                (
                    attempt_id,
                    route_decision_id,
                    company_id,
                    run_id,
                    execution_snapshot_id,
                    attempt_sequence,
                    str(role),
                    candidate_id,
                    provider_release_id,
                    model_binding_id,
                    credential_ref_sha256,
                    request_id,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            message = str(exc)
            if "request_id" in message:
                raise ValueError("ROUTE_ATTEMPT_REQUEST_EXISTS") from exc
            if "attempt_sequence" in message:
                raise ValueError("ROUTE_ATTEMPT_SEQUENCE_EXISTS") from exc
            raise ValueError("ROUTE_ATTEMPT_INVALID") from exc
        return {"id": attempt_id, "status": "created", "created_at": now}

    async def transition_attempt(
        self,
        db: aiosqlite.Connection,
        attempt_id: str,
        expected_status: str,
        target_status: str,
        *,
        failure_kind: ProviderFailureKind | None = None,
        http_status: int | None = None,
        latency_ms: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        candidate_truncated: bool | None = None,
    ) -> bool:
        allowed_targets = {
            "created": {"accepted", "failed", "cancelled", "timed_out"},
            "accepted": {"streaming", "succeeded", "failed", "cancelled", "timed_out"},
            "streaming": {"succeeded", "failed", "cancelled", "timed_out"},
            "succeeded": set(),
            "failed": set(),
            "cancelled": set(),
            "timed_out": set(),
        }
        if expected_status not in allowed_targets:
            raise ValueError("ROUTE_ATTEMPT_STATUS_INVALID")
        if target_status not in allowed_targets[expected_status]:
            raise ValueError("ROUTE_ATTEMPT_TRANSITION_INVALID")
        if failure_kind is not None and not isinstance(failure_kind, ProviderFailureKind):
            failure_kind = ProviderFailureKind(str(failure_kind))
        for value in (latency_ms, input_tokens, output_tokens, total_tokens):
            if value is not None and value < 0:
                raise ValueError("ROUTE_ATTEMPT_USAGE_INVALID")
        cursor = await db.execute(
            """UPDATE route_attempts
               SET status=?, failure_kind=?, http_status=?,
                   accepted_at=CASE WHEN ?='accepted' THEN COALESCE(accepted_at, ?) ELSE accepted_at END,
                   started_at=CASE WHEN ?='streaming' THEN COALESCE(started_at, ?) ELSE started_at END,
                   completed_at=CASE WHEN ? IN ('succeeded','failed','cancelled','timed_out') THEN ? ELSE completed_at END
                   ,latency_ms=COALESCE(?, latency_ms), input_tokens=COALESCE(?, input_tokens),
                   output_tokens=COALESCE(?, output_tokens), total_tokens=COALESCE(?, total_tokens),
                   candidate_truncated=COALESCE(?, candidate_truncated)
               WHERE id=? AND status=?""",
            (
                target_status,
                failure_kind.value if failure_kind else None,
                http_status,
                target_status,
                _now(),
                target_status,
                _now(),
                target_status,
                _now(),
                latency_ms,
                input_tokens,
                output_tokens,
                total_tokens,
                int(candidate_truncated) if candidate_truncated is not None else None,
                attempt_id,
                expected_status,
            ),
        )
        return cursor.rowcount == 1

    async def bind_attempt_request(
        self,
        db: aiosqlite.Connection,
        *,
        attempt_id: str,
        request_id: str,
    ) -> bool:
        """Bind the Rust physical request id exactly once after acceptance."""
        if not request_id:
            raise ValueError("ROUTE_ATTEMPT_REQUEST_INVALID")
        try:
            cursor = await db.execute(
                """UPDATE route_attempts
                   SET request_id=?
                   WHERE id=? AND request_id IS NULL""",
                (request_id, attempt_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("ROUTE_ATTEMPT_REQUEST_EXISTS") from exc
        return cursor.rowcount == 1

    async def record_outcome(
        self,
        db: aiosqlite.Connection,
        outcome_id: str,
        route_decision_id: str,
        company_id: str,
        outcome_type: str,
        source_id: str,
        score: float,
        label: str,
    ) -> bool:
        if not 0 <= score <= 1:
            raise ValueError("ROUTE_OUTCOME_SCORE_INVALID")
        cursor = await db.execute(
            """INSERT OR IGNORE INTO route_outcomes
               (id, route_decision_id, company_id, outcome_type, source_id, score, label, occurred_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (outcome_id, route_decision_id, company_id, outcome_type, source_id, score, label, _now()),
        )
        return cursor.rowcount == 1

    async def upsert_health(
        self,
        db: aiosqlite.Connection,
        *,
        company_id: str,
        provider_release_id: str,
        model_binding_id: str,
        credential_ref_sha256: str,
        availability_state: str,
        consecutive_strikes: int,
        benched_until: str | None,
        last_failure_kind: ProviderFailureKind | None,
        last_failure_at: str | None,
        last_success_at: str | None,
    ) -> None:
        if availability_state not in {"ready", "credential_invalid"} or consecutive_strikes < 0:
            raise ValueError("DEPLOYMENT_HEALTH_INVALID")
        await db.execute(
            """INSERT INTO deployment_health
               (company_id, provider_release_id, model_binding_id, credential_ref_sha256,
                availability_state, consecutive_strikes, benched_until, last_failure_kind,
                last_failure_at, last_success_at, version, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,1,?)
               ON CONFLICT(company_id, provider_release_id, model_binding_id, credential_ref_sha256)
               DO UPDATE SET availability_state=excluded.availability_state,
                 consecutive_strikes=excluded.consecutive_strikes,
                 benched_until=excluded.benched_until,
                 last_failure_kind=excluded.last_failure_kind,
                 last_failure_at=excluded.last_failure_at,
                 last_success_at=excluded.last_success_at,
                 version=deployment_health.version+1,
                 updated_at=excluded.updated_at""",
            (
                company_id,
                provider_release_id,
                model_binding_id,
                credential_ref_sha256,
                availability_state,
                consecutive_strikes,
                benched_until,
                last_failure_kind.value if last_failure_kind else None,
                last_failure_at,
                last_success_at,
                _now(),
            ),
        )

    async def set_override(self, db: aiosqlite.Connection, company_id: str, run_id: str, override_mode: str | None) -> None:
        if override_mode not in {None, "force_fixed", "force_single", "force_ensemble"}:
            raise ValueError("ROUTING_OVERRIDE_INVALID")
        await db.execute(
            """INSERT INTO routing_run_controls(company_id, run_id, override_mode, version, updated_at)
               VALUES (?,?,?,1,?)
               ON CONFLICT(company_id, run_id) DO UPDATE SET override_mode=excluded.override_mode,
                 version=routing_run_controls.version+1, updated_at=excluded.updated_at""",
            (company_id, run_id, override_mode, _now()),
        )
