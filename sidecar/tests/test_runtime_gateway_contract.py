"""Integration checks for the single snapshot-bound Runtime Gateway entry."""

from __future__ import annotations

import json
import uuid

import pytest

from ibreeze.runtime.gateway import RunValidationError, start


async def _execution_fixture(db, published_profile):
    company = await (await db.execute("SELECT * FROM companies LIMIT 1")).fetchone()
    department = await (
        await db.execute(
            "SELECT * FROM departments WHERE company_id=? LIMIT 1",
            (company["id"],),
        )
    ).fetchone()
    employee = await (
        await db.execute(
            "SELECT * FROM employees WHERE company_id=? LIMIT 1",
            (company["id"],),
        )
    ).fetchone()
    profile = await (
        await db.execute(
            "SELECT * FROM employee_base_profile_versions WHERE id=?",
            (published_profile,),
        )
    ).fetchone()
    now = "2026-08-01T00:00:00.000000Z"
    company_task_id = str(uuid.uuid4())
    department_task_id = str(uuid.uuid4())
    employee_task_id = str(uuid.uuid4())
    message_event_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO domain_events
           (event_id, company_id, aggregate_type, aggregate_id,
            aggregate_version, event_type, payload_json, trace_id, occurred_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            message_event_id,
            company["id"],
            "company_task",
            company_task_id,
            1,
            "conversation.user_message",
            json.dumps({"company_id": company["id"]}),
            str(uuid.uuid4()),
            now,
        ),
    )
    await db.execute(
        """INSERT INTO company_tasks
           (id, company_id, company_conversation_id, user_message_event_id,
            title, status, created_at, updated_at, version)
           VALUES (?,?,?,?,?,'executing',?,?,1)""",
        (
            company_task_id,
            company["id"],
            company["company_conversation_id"],
            message_event_id,
            "Gateway contract task",
            now,
            now,
        ),
    )
    await db.execute(
        """INSERT INTO department_tasks
           (id, company_id, company_task_id, department_id, stage_key,
            objective, deliverables_json, acceptance_criteria_json,
            status, created_at, updated_at, version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""",
        (
            department_task_id,
            company["id"],
            company_task_id,
            department["id"],
            "implementation",
            "Implement the contract test",
            "[]",
            "[]",
            "ready",
            now,
            now,
        ),
    )
    await db.execute(
        """INSERT INTO employee_tasks
           (id, company_id, department_task_id, employee_id, task_kind,
            objective, acceptance_criteria_json, status, created_at,
            updated_at, version)
           VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
        (
            employee_task_id,
            company["id"],
            department_task_id,
            employee["id"],
            "standard",
            "Implement the contract test",
            "[]",
            "assigned",
            now,
            now,
        ),
    )
    availability_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())
    content_sha = "a" * 64
    await db.execute(
        """INSERT INTO employee_availability_snapshots
           (id, company_id, company_task_id, department_task_id,
            work_item_type, work_item_id, employee_id, base_profile_version_id,
            prospective_execution_sha256, catalog_release_id, checks_json,
            overall_status, checked_at, expires_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            availability_id,
            company["id"],
            company_task_id,
            department_task_id,
            "task_execution",
            employee_task_id,
            employee["id"],
            published_profile,
            content_sha,
            profile["catalog_release_id"],
            json.dumps({"checks": []}),
            "available",
            now,
            "2099-01-01T00:00:00.000000Z",
        ),
    )
    await db.execute(
        """INSERT INTO execution_snapshots
           (id, company_id, company_task_id, department_id,
            department_task_id, employee_task_id, employee_id,
            snapshot_purpose, work_item_id, company_revision_id,
            department_revision_id, base_profile_version_id, catalog_release_id,
            runtime_binding_json, skill_lock_json, tool_policy_json,
            workspace_policy_json, verification_commands_json, content_sha256,
            created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            execution_id,
            company["id"],
            company_task_id,
            department["id"],
            department_task_id,
            employee_task_id,
            employee["id"],
            "task_execution",
            employee_task_id,
            company["current_revision_id"],
            department["current_revision_id"],
            published_profile,
            profile["catalog_release_id"],
            json.dumps({"agent_cli": "codex_cli"}),
            "{}",
            "{}",
            "{}",
            "[]",
            content_sha,
            now,
        ),
    )
    await db.commit()
    return {
        "company_id": company["id"],
        "company_task_id": company_task_id,
        "employee_id": employee["id"],
        "conversation_id": company["company_conversation_id"],
        "availability_snapshot_id": availability_id,
        "execution_snapshot_id": execution_id,
        "department_task_id": department_task_id,
        "employee_task_id": employee_task_id,
    }


@pytest.mark.asyncio
async def test_gateway_creates_snapshot_bound_task_execution(db, published_profile):
    values = await _execution_fixture(db, published_profile)
    result = await start(
        db,
        **values,
        model_id="codex_cli",
        prompt="run",
        run_purpose="task_execution",
        adapter_type="codex_cli",
        work_item_id=values["employee_task_id"],
    )
    run = await (await db.execute("SELECT * FROM agent_runs WHERE id=?", (result["run_id"],))).fetchone()
    queue = await (await db.execute("SELECT * FROM runtime_queue WHERE run_id=?", (result["run_id"],))).fetchone()
    assert result["status"] == "queued"
    assert run["run_purpose"] == "task_execution"
    assert queue["work_item_type"] == "employee_task"
    assert queue["priority"] == 10
    assert (await (await db.execute("SELECT COUNT(*) AS count FROM outbox_events WHERE topic='run.queued'")).fetchone())["count"] == 1


@pytest.mark.asyncio
async def test_gateway_rejects_removed_employee_task_purpose(db, published_profile):
    values = await _execution_fixture(db, published_profile)
    with pytest.raises(RunValidationError, match="RUN_PURPOSE_INVALID"):
        await start(
            db,
            **values,
            model_id="codex_cli",
            prompt="run",
            run_purpose="employee_task",
            adapter_type="codex_cli",
        )
