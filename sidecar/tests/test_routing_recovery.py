from __future__ import annotations

import uuid

import pytest

from ibreeze.runtime.recovery import cleanup_expired_health, reconcile_interrupted_routing, recover_stale_runs


async def _insert_decision_and_attempt(db, *, decision_status: str, attempt_status: str) -> tuple[str, str]:
    decision_id = str(uuid.uuid4())
    attempt_id = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    await db.execute(
        """INSERT INTO route_decisions
           (id, company_id, run_id, turn_index, execution_snapshot_id,
            routing_mode, classifier_version, input_fingerprint, required_tier,
            confidence, selected_kind, selected_bindings_json, policy_trail_json,
            status, created_at)
           VALUES (?, 'company', 'run', ?, 'snapshot', 'smart_single', 'rules-v1', ?,
                   'C1', 0.8, 'single', ?, '[]', ?, '2026-01-01T00:00:00Z')""",
        (
            decision_id,
            1 if decision_status == "planned" else 2,
            "a" * 64,
            '[{"candidate_id":"candidate","role":"single"}]',
            decision_status,
        ),
    )
    await db.execute(
        """INSERT INTO route_attempts
           (id, route_decision_id, company_id, run_id, execution_snapshot_id,
            attempt_sequence, role, candidate_id, provider_release_id,
            model_binding_id, credential_ref_sha256, status, created_at)
           VALUES (?, ?, 'company', 'run', 'snapshot', 1, 'single', 'candidate',
                   'provider', 'model', ?, ?, '2026-01-01T00:00:00Z')""",
        (attempt_id, decision_id, "b" * 64, attempt_status),
    )
    await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()
    return decision_id, attempt_id


@pytest.mark.asyncio
async def test_reconcile_interrupted_routing_fails_nonterminal_rows(db):
    planned_id, planned_attempt = await _insert_decision_and_attempt(db, decision_status="planned", attempt_status="created")
    executing_id, executing_attempt = await _insert_decision_and_attempt(db, decision_status="executing", attempt_status="streaming")

    result = await reconcile_interrupted_routing(db)

    assert result["failed_attempts"] == 2
    assert result["failed_planned_decisions"] == 1
    assert result["failed_executing_decisions"] == 1
    decision_rows = await db.execute("SELECT id, status FROM route_decisions WHERE id IN (?,?)", (planned_id, executing_id))
    assert {row["status"] async for row in decision_rows} == {"failed"}
    attempt_rows = await db.execute("SELECT id, status, failure_kind FROM route_attempts WHERE id IN (?,?)", (planned_attempt, executing_attempt))
    assert {(row["status"], row["failure_kind"]) async for row in attempt_rows} == {("failed", "TRANSPORT_TRANSIENT")}


@pytest.mark.asyncio
async def test_reconcile_preserves_verified_rust_attempt(db):
    decision_id, attempt_id = await _insert_decision_and_attempt(db, decision_status="executing", attempt_status="streaming")

    result = await reconcile_interrupted_routing(db, active_attempt_ids={attempt_id})

    assert result["preserved_attempts"] == 1
    assert result["failed_attempts"] == 0
    decision = await (await db.execute("SELECT status FROM route_decisions WHERE id=?", (decision_id,))).fetchone()
    attempt = await (await db.execute("SELECT status FROM route_attempts WHERE id=?", (attempt_id,))).fetchone()
    assert decision["status"] == "executing"
    assert attempt["status"] == "streaming"


@pytest.mark.asyncio
async def test_health_cleanup_only_removes_expired_ready_rows(db):
    await db.execute(
        """INSERT INTO deployment_health
           (company_id, provider_release_id, model_binding_id, credential_ref_sha256,
            availability_state, consecutive_strikes, benched_until, version, updated_at)
           VALUES ('company', 'provider', 'model', ?, 'ready', 1, '2025-01-01T00:00:00Z', 1, '2025-01-01T00:00:00Z')""",
        ("a" * 64,),
    )
    await db.execute(
        """INSERT INTO deployment_health
           (company_id, provider_release_id, model_binding_id, credential_ref_sha256,
            availability_state, consecutive_strikes, benched_until, version, updated_at)
           VALUES ('company', 'provider-2', 'model', ?, 'credential_invalid', 0, '2025-01-01T00:00:00Z', 1, '2025-01-01T00:00:00Z')""",
        ("b" * 64,),
    )
    await db.commit()

    assert await cleanup_expired_health(db, now="2026-01-01T00:00:00Z") == 1
    rows = await db.execute("SELECT availability_state FROM deployment_health")
    assert [row["availability_state"] async for row in rows] == ["credential_invalid"]


@pytest.mark.asyncio
async def test_recover_stale_runs_clears_queue_and_lease(db):
    company_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    # Reuse the runtime test fixture shape without requiring company/domain
    # event aggregates; the recovery helper remains useful for imported rows.
    now = "2026-01-01T00:00:00Z"
    await db.execute("PRAGMA foreign_keys = OFF")
    await db.execute(
        """INSERT INTO agent_runs
           (id, company_id, company_task_id, work_item_id, employee_id,
            conversation_id, availability_snapshot_id, execution_snapshot_id,
            run_purpose, adapter_type, run_spec_json, run_spec_sha256,
            status, attempt, created_at, updated_at, version)
           VALUES (?, ?, 'task', 'task', 'employee', 'conversation', 'availability',
                   'snapshot', 'review', 'codex_cli', '{}', ?, 'running', 1, ?, ?, 1)""",
        (run_id, company_id, "a" * 64, now, now),
    )
    await db.execute(
        """INSERT INTO runtime_queue
           (id, company_id, work_item_type, work_item_id, job_id, run_id,
            priority, status, queued_at)
           VALUES ('queue', ?, 'review', 'work', 'job', ?, 20, 'leased', ?)""",
        (company_id, run_id, now),
    )
    await db.execute(
        """INSERT INTO runtime_leases
           (id, queue_id, job_id, run_id, employee_id, company_id,
            conversation_id, acquired_at, heartbeat_at, expires_at)
           VALUES ('lease', 'queue', 'job', ?, 'employee', ?, 'conversation', ?, ?, ?)""",
        (run_id, company_id, now, now, now),
    )
    await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()

    result = await recover_stale_runs(db)

    assert result == {"recovered": 1, "checked": 1}
    run = await (await db.execute("SELECT status, failure_code, completed_at, process_pid FROM agent_runs WHERE id=?", (run_id,))).fetchone()
    queue = await (await db.execute("SELECT status FROM runtime_queue WHERE run_id=?", (run_id,))).fetchone()
    lease = await (await db.execute("SELECT id FROM runtime_leases WHERE run_id=?", (run_id,))).fetchone()
    assert run["status"] == "failed"
    assert run["failure_code"].startswith("Crash recovery:")
    assert run["completed_at"] is not None
    assert run["process_pid"] is None
    assert queue["status"] == "cancelled"
    assert lease is None
