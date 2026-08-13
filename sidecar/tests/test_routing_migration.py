from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_routing_migration_creates_tables_and_columns(local_db) -> None:
    tables = {row[0] async for row in await local_db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"route_decisions", "route_attempts", "deployment_health", "route_outcomes", "routing_run_controls"} <= tables
    cursor = await local_db.execute("PRAGMA table_info(employee_base_profile_versions)")
    assert "routing_policy_json" in {row[1] async for row in cursor}
    cursor = await local_db.execute("PRAGMA table_info(execution_snapshots)")
    assert {
        "routing_policy_json",
        "routing_policy_sha256",
        "routing_classifier_version",
        "candidate_bindings_json",
        "candidate_bindings_sha256",
    } <= {row[1] async for row in cursor}
    cursor = await local_db.execute("PRAGMA table_info(employee_task_dispatch_specs)")
    assert "required_capability_tags_json" in {row[1] async for row in cursor}


@pytest.mark.asyncio
async def test_routing_attempt_parent_guard_rejects_unselected_candidate(local_db) -> None:
    await local_db.execute("PRAGMA foreign_keys = OFF")
    await local_db.execute(
        "INSERT INTO route_decisions (id, company_id, run_id, turn_index, execution_snapshot_id, routing_mode, classifier_version, input_fingerprint, required_tier, confidence, selected_kind, selected_bindings_json, policy_trail_json, status, created_at) VALUES ('d','c','r',1,'s','fixed','v','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','C0',1.0,'single', '[{\"candidate_id\":\"allowed\",\"role\":\"single\"}]', '[]', 'planned', 'now')"
    )
    with pytest.raises(Exception):
        await local_db.execute(
            "INSERT INTO route_attempts (id,route_decision_id,company_id,run_id,execution_snapshot_id,attempt_sequence,role,candidate_id,provider_release_id,model_binding_id,credential_ref_sha256,status,created_at) VALUES ('a','d','c','r','s',1,'single','denied','p','m','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','created','now')"
        )
