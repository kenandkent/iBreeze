"""Company-scoped public RPC implementations for routing observability."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

from ibreeze.routing.policy import validate_routing_policy


def _cursor(value: str | None) -> tuple[int, str] | None:
    if not value:
        return None
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii") + b"===").decode("utf-8")
        turn, decision_id = decoded.split(":", 1)
        return int(turn), decision_id
    except (ValueError, UnicodeError, TypeError):
        raise ValueError("VALIDATION_FAILED") from None


def _encode_cursor(turn: int, decision_id: str) -> str:
    return base64.urlsafe_b64encode(f"{turn}:{decision_id}".encode()).decode("ascii").rstrip("=")


def _health_cursor(value: str | None) -> tuple[str, str, str] | None:
    if not value:
        return None
    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii") + b"===").decode("utf-8")
        provider, binding, credential = decoded.split(":", 2)
    except (ValueError, UnicodeError, TypeError):
        raise ValueError("VALIDATION_FAILED") from None
    if not provider or not binding or not credential:
        raise ValueError("VALIDATION_FAILED")
    return provider, binding, credential


def _encode_health_cursor(provider: str, binding: str, credential: str) -> str:
    return base64.urlsafe_b64encode(f"{provider}:{binding}:{credential}".encode()).decode("ascii").rstrip("=")


async def validate_policy(db: Any, params: dict[str, Any]) -> dict[str, Any]:
    if not (params.get("profile_version_id") or params.get("catalog_release_id")) or bool(params.get("profile_version_id")) == bool(
        params.get("catalog_release_id")
    ):
        raise ValueError("VALIDATION_FAILED")
    profile_type = str(params.get("profile_type", ""))
    policy = params.get("policy")
    if not isinstance(policy, dict):
        return {
            "valid": False,
            "canonical_json": None,
            "canonical_sha256": None,
            "issues": [{"code": "ROUTING_POLICY_INVALID", "json_pointer": "/policy", "message": "policy must be an object"}],
        }
    release_id = params.get("catalog_release_id")
    if params.get("profile_version_id"):
        cursor = await db.execute(
            """SELECT v.catalog_release_id, v.profile_type
               FROM employee_base_profile_versions v
               JOIN employee_base_profiles p ON p.id=v.profile_id
               WHERE v.id=? AND p.company_id=?""",
            (params["profile_version_id"], params["company_id"]),
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError("RESOURCE_NOT_FOUND")
        release_id = row[0]
        if profile_type != row[1]:
            return {
                "valid": False,
                "canonical_json": None,
                "canonical_sha256": None,
                "issues": [
                    {
                        "code": "ROUTING_POLICY_INVALID",
                        "json_pointer": "/profile_type",
                        "message": "profile type does not match pinned profile",
                    }
                ],
            }
    catalog_view: dict[str, dict[str, object]] = {}
    if release_id:
        cur = await db.execute(
            "SELECT resource_type,resource_id,content_json FROM catalog_cache_resources WHERE release_id=?",
            (release_id,),
        )
        rows = await cur.fetchall()
        models = {str(row[1]): json.loads(row[2]) for row in rows if row[0] == "model"}
        providers = {str(row[1]): json.loads(row[2]) for row in rows if row[0] == "provider"}
        for candidate in policy.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            provider = providers.get(str(candidate.get("provider_release_id")))
            binding = next(
                (
                    item
                    for item in (provider or {}).get("model_bindings", [])
                    if isinstance(item, dict) and str(item.get("binding_id")) == str(candidate.get("model_binding_id"))
                ),
                None,
            )
            binding_model_id = str((binding or {}).get("model_id", ""))
            if provider is None or binding is None or binding_model_id not in models:
                # Leave the candidate out of the view; the policy validator
                # emits the stable OUTSIDE_RELEASE issue below.
                continue
            catalog_view[str(candidate.get("candidate_id", ""))] = {
                "provider_release_id": str(candidate.get("provider_release_id")),
                "model_binding_id": str(candidate.get("model_binding_id")),
            }
    try:
        validated = validate_routing_policy(policy, profile_type=profile_type, catalog_release=catalog_view or None)
    except ValueError as exc:
        code = str(exc)
        return {
            "valid": False,
            "canonical_json": None,
            "canonical_sha256": None,
            "issues": [{"code": code, "json_pointer": "/policy", "message": code}],
        }
    return {"valid": True, "canonical_json": validated.canonical_json, "canonical_sha256": validated.sha256, "issues": []}


async def get_run_summary(db: Any, params: dict[str, Any], rollout_stage: str = "observe") -> dict[str, Any]:
    company_id, run_id = str(params["company_id"]), str(params["run_id"])
    run_cur = await db.execute("SELECT status FROM agent_runs WHERE id=? AND company_id=?", (run_id, company_id))
    run_row = await run_cur.fetchone()
    if run_row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    cur = await db.execute(
        "SELECT routing_mode FROM route_decisions WHERE company_id=? AND run_id=? ORDER BY turn_index LIMIT 1", (company_id, run_id)
    )
    mode_row = await cur.fetchone()
    cur = await db.execute(
        "SELECT status, COUNT(*) AS count FROM route_decisions WHERE company_id=? AND run_id=? GROUP BY status", (company_id, run_id)
    )
    decision_count = 0
    for row in await cur.fetchall():
        decision_count += int(row[1])
    cur = await db.execute(
        "SELECT selected_kind, COUNT(*) AS count FROM route_decisions WHERE company_id=? AND run_id=? GROUP BY selected_kind",
        (company_id, run_id),
    )
    counts = {str(row[0]): int(row[1]) for row in await cur.fetchall()}
    cur = await db.execute(
        "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(total_tokens),0), AVG(latency_ms) FROM route_attempts WHERE company_id=? AND run_id=?",
        (company_id, run_id),
    )
    usage = await cur.fetchone()
    cur = await db.execute(
        "SELECT latency_ms FROM route_attempts WHERE company_id=? AND run_id=? AND latency_ms IS NOT NULL ORDER BY latency_ms",
        (company_id, run_id),
    )
    latency_rows = await cur.fetchall()
    latencies = sorted(float(row[0]) for row in latency_rows if row[0] is not None)

    def percentile(values: list[float], fraction: float) -> float | None:
        if not values:
            return None
        index = min(len(values) - 1, max(0, int((len(values) - 1) * fraction)))
        return values[index]

    cur = await db.execute(
        "SELECT COUNT(*) FROM route_attempts WHERE company_id=? AND run_id=? AND role='fallback'",
        (company_id, run_id),
    )
    fallback_row = await cur.fetchone()
    cur = await db.execute(
        "SELECT candidate_id, provider_release_id, model_binding_id, COUNT(*), SUM(CASE WHEN status='succeeded' THEN 1 ELSE 0 END) FROM route_attempts WHERE company_id=? AND run_id=? GROUP BY candidate_id, provider_release_id, model_binding_id ORDER BY candidate_id",
        (company_id, run_id),
    )
    models = [
        {
            "candidate_id": row[0],
            "provider_release_id": row[1],
            "model_binding_id": row[2],
            "attempt_count": int(row[3]),
            "success_count": int(row[4]),
        }
        for row in await cur.fetchall()
    ]
    return {
        "run_id": run_id,
        "run_status": run_row[0],
        "routing_mode": mode_row[0] if mode_row else None,
        "rollout_stage": rollout_stage,
        "decision_count": decision_count,
        "single_count": counts.get("single", 0),
        "ensemble_count": counts.get("ensemble", 0),
        "fallback_hops": int(fallback_row[0] or 0) if fallback_row else 0,
        "total_prompt_tokens": int(usage[0] or 0),
        "total_completion_tokens": int(usage[1] or 0),
        "total_tokens": int(usage[2] or 0),
        "p50_latency_ms": percentile(latencies, 0.50),
        "p95_latency_ms": percentile(latencies, 0.95),
        "actual_models": models,
        "control": await get_override(db, company_id, run_id),
    }


async def list_decisions(db: Any, params: dict[str, Any]) -> dict[str, Any]:
    company_id, run_id = str(params["company_id"]), str(params["run_id"])
    limit = min(100, max(1, int(params.get("limit", 50))))
    cursor = _cursor(params.get("cursor"))
    where = "company_id=? AND run_id=?"
    args: list[Any] = [company_id, run_id]
    if cursor:
        where += " AND (turn_index > ? OR (turn_index=? AND id>?))"
        args.extend([cursor[0], cursor[0], cursor[1]])
    cur = await db.execute(
        f"SELECT id,turn_index,routing_mode,required_tier,confidence,selected_kind,status,created_at,completed_at,selected_bindings_json FROM route_decisions WHERE {where} ORDER BY turn_index,id LIMIT ?",
        (*args, limit + 1),
    )
    rows = await cur.fetchall()
    items = []
    for row in rows[:limit]:
        bindings = json.loads(row[9]) if row[9] else []
        items.append(
            {
                "decision_id": row[0],
                "turn_index": row[1],
                "routing_mode": row[2],
                "required_tier": row[3],
                "confidence": row[4],
                "selected_kind": row[5],
                "status": row[6],
                "created_at": row[7],
                "completed_at": row[8],
                "actual_candidate_ids": [item.get("candidate_id") for item in bindings if isinstance(item, dict)],
            }
        )
    next_cursor = _encode_cursor(int(rows[limit - 1][1]), str(rows[limit - 1][0])) if len(rows) > limit else None
    return {"items": items, "next_cursor": next_cursor}


async def get_decision(db: Any, params: dict[str, Any]) -> dict[str, Any]:
    cur = await db.execute(
        "SELECT id,company_id,run_id,turn_index,execution_snapshot_id,routing_mode,classifier_version,required_tier,confidence,selected_kind,selected_bindings_json,aggregator_candidate_id,policy_trail_json,status,created_at,completed_at FROM route_decisions WHERE id=? AND company_id=?",
        (params["decision_id"], params["company_id"]),
    )
    row = await cur.fetchone()
    if row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    decision = {
        "decision_id": row[0],
        "company_id": row[1],
        "run_id": row[2],
        "turn_index": row[3],
        "execution_snapshot_id": row[4],
        "routing_mode": row[5],
        "classifier_version": row[6],
        "required_tier": row[7],
        "confidence": row[8],
        "selected_kind": row[9],
        "selected_bindings": json.loads(row[10]),
        "aggregator_candidate_id": row[11],
        "policy_trail": json.loads(row[12]),
        "status": row[13],
        "created_at": row[14],
        "completed_at": row[15],
    }
    cur = await db.execute(
        "SELECT attempt_sequence,role,candidate_id,provider_release_id,model_binding_id,status,failure_kind,http_status,created_at,accepted_at,started_at,completed_at,latency_ms,input_tokens,output_tokens,total_tokens,candidate_truncated FROM route_attempts WHERE route_decision_id=? AND company_id=? ORDER BY attempt_sequence",
        (params["decision_id"], params["company_id"]),
    )
    attempts = [
        {
            "attempt_sequence": row[0],
            "role": row[1],
            "candidate_id": row[2],
            "provider_release_id": row[3],
            "model_binding_id": row[4],
            "status": row[5],
            "failure_kind": row[6],
            "http_status": row[7],
            "created_at": row[8],
            "accepted_at": row[9],
            "started_at": row[10],
            "completed_at": row[11],
            "latency_ms": row[12],
            "input_tokens": row[13],
            "output_tokens": row[14],
            "total_tokens": row[15],
            "candidate_truncated": bool(row[16]),
        }
        for row in await cur.fetchall()
    ]
    cur = await db.execute(
        "SELECT outcome_type,source_id,score,label,occurred_at FROM route_outcomes WHERE route_decision_id=? AND company_id=? ORDER BY occurred_at",
        (params["decision_id"], params["company_id"]),
    )
    outcomes = [
        {"outcome_type": row[0], "source_id": row[1], "score": row[2], "label": row[3], "occurred_at": row[4]}
        for row in await cur.fetchall()
    ]
    return {"decision": decision, "attempts": attempts, "outcomes": outcomes}


async def list_health(db: Any, params: dict[str, Any]) -> dict[str, Any]:
    company_id = str(params["company_id"])
    limit = min(100, max(1, int(params.get("limit", 50))))
    active_only = bool(params.get("active_only", False))
    condition = "AND (benched_until IS NOT NULL OR availability_state <> 'ready')" if active_only else ""
    cursor = _health_cursor(params.get("cursor"))
    args: list[Any] = [company_id]
    if cursor:
        condition += " AND (provider_release_id > ? OR (provider_release_id=? AND (model_binding_id > ? OR (model_binding_id=? AND credential_ref_sha256>?))))"
        args.extend([cursor[0], cursor[0], cursor[1], cursor[1], cursor[2]])
    args.append(limit + 1)
    cur = await db.execute(
        f"SELECT provider_release_id,model_binding_id,credential_ref_sha256,availability_state,consecutive_strikes,benched_until,last_failure_kind,last_failure_at,last_success_at,version FROM deployment_health WHERE company_id=? {condition} ORDER BY provider_release_id,model_binding_id,credential_ref_sha256 LIMIT ?",
        tuple(args),
    )
    rows = await cur.fetchall()
    items = [
        {
            "provider_release_id": row[0],
            "model_binding_id": row[1],
            "credential_slot": str(row[2])[:12],
            "availability_state": row[3],
            "consecutive_strikes": row[4],
            "benched_until": row[5],
            "last_failure_kind": row[6],
            "last_failure_at": row[7],
            "last_success_at": row[8],
            "version": row[9],
        }
        for row in rows[:limit]
    ]
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_health_cursor(str(last[0]), str(last[1]), str(last[2]))
    return {"items": items, "next_cursor": next_cursor}


async def get_override(db: Any, company_id: str, run_id: str) -> dict[str, Any]:
    cur = await db.execute("SELECT override_mode,version FROM routing_run_controls WHERE company_id=? AND run_id=?", (company_id, run_id))
    row = await cur.fetchone()
    return {"override_mode": row[0] if row else None, "version": int(row[1]) if row else 0}


async def set_override(db: Any, params: dict[str, Any]) -> dict[str, Any]:
    company_id, run_id = str(params["company_id"]), str(params["run_id"])
    override = params.get("override")
    expected = int(params.get("expected_version", -1))
    mode = None if override == "clear" else str(override)
    if mode not in {None, "force_fixed", "force_single", "force_ensemble"}:
        raise ValueError("VALIDATION_FAILED")
    cur = await db.execute("SELECT status FROM agent_runs WHERE id=? AND company_id=?", (run_id, company_id))
    run = await cur.fetchone()
    if run is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    if run[0] in {"succeeded", "failed", "cancelled", "timed_out", "lost"}:
        raise ValueError("ROUTING_OVERRIDE_NOT_AVAILABLE")
    if mode == "force_ensemble":
        from ibreeze.routing.config import startup_config

        if startup_config().stage not in {"selective_ensemble", "learning_candidate"}:
            raise ValueError("ROUTING_OVERRIDE_NOT_AVAILABLE")
        policy_cursor = await db.execute(
            """SELECT es.routing_policy_json
               FROM agent_runs ar
               JOIN execution_snapshots es ON es.id=ar.execution_snapshot_id AND es.company_id=ar.company_id
               WHERE ar.id=? AND ar.company_id=?""",
            (run_id, company_id),
        )
        policy_row = await policy_cursor.fetchone()
        if policy_row is None or not policy_allows_ensemble(policy_row[0]):
            raise ValueError("ROUTING_OVERRIDE_NOT_AVAILABLE")
    current = await get_override(db, company_id, run_id)
    if current["version"] != expected:
        raise ValueError("ROUTE_DECISION_CONFLICT")
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if expected == 0:
        await db.execute(
            "INSERT INTO routing_run_controls(company_id,run_id,override_mode,version,updated_at) VALUES(?,?,?,?,?)",
            (company_id, run_id, mode, 1, now),
        )
        version = 1
    else:
        updated = await db.execute(
            "UPDATE routing_run_controls SET override_mode=?,version=version+1,updated_at=? WHERE company_id=? AND run_id=? AND version=?",
            (mode, now, company_id, run_id, expected),
        )
        if updated.rowcount != 1:
            raise ValueError("ROUTE_DECISION_CONFLICT")
        version = expected + 1
    return {"run_id": run_id, "override_mode": mode, "version": version, "updated_at": now}


def policy_allows_ensemble(routing_policy_json: object) -> bool:
    try:
        policy = json.loads(str(routing_policy_json or "{}"))
    except (TypeError, ValueError):
        return False
    return isinstance(policy, dict) and policy.get("mode") == "selective_ensemble"


async def clear_expired_health(db: Any, params: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    cur = await db.execute(
        "DELETE FROM deployment_health WHERE company_id=? AND availability_state='ready' AND benched_until IS NOT NULL AND benched_until <= ?",
        (params["company_id"], now),
    )
    return {"deleted_count": cur.rowcount, "completed_at": now}
