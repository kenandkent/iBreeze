"""Tests for runtime/service.py — runtime monitoring and control (target: 100%)."""

from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.runtime.run_executor import _resource_wait_failure_code
from ibreeze.runtime.service import (
    cancel_run,
    get_agent_run,
    get_runtime_status,
    list_agent_runs,
    list_available_models,
    list_run_events,
    probe_agent,
    probe_provider,
    resume_run,
)


def _sha256(data: str) -> str:
    import hashlib

    return hashlib.sha256(data.encode()).hexdigest()


def test_resource_wait_failure_code_is_explicit_and_failures_are_not_retriable() -> None:
    assert _resource_wait_failure_code(ValueError("MODEL_CAPABILITY_UNAVAILABLE")) == "MODEL_CAPABILITY_UNAVAILABLE"
    assert _resource_wait_failure_code(RuntimeError("CREDENTIAL_NOT_READY")) == "CREDENTIAL_NOT_READY"
    assert _resource_wait_failure_code(RuntimeError("EXECUTION_ERROR")) is None


async def _setup_runtime_env(
    db: aiosqlite.Connection,
    company_id: str,
    version_id: str,
    profile_id: str,
    employee_id: str,
    dept_id: str,
):
    now = "2026-01-01T00:00:00Z"
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        rev_id = str(uuid.uuid4())
        dept_rev_id = str(uuid.uuid4())
        conv_id = str(uuid.uuid4())
        dept_conv_id = str(uuid.uuid4())
        release_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO company_revisions
               (id, company_id, revision_number, name, introduction, content_sha256, created_by_type, created_at)
               VALUES (?, ?, 1, 'Co', 'Intro', ?, 'system', ?)""",
            (rev_id, company_id, _sha256("co"), now),
        )
        await db.execute(
            """INSERT INTO conversations (id, company_id, conversation_type, status, created_at)
               VALUES (?, ?, 'department', 'active', ?)""",
            (dept_conv_id, company_id, now),
        )
        await db.execute(
            """INSERT INTO department_revisions
               (id, department_id, company_id, revision_number, name, function_description, content_sha256, created_at)
               VALUES (?, ?, ?, 1, 'Root', 'Root', ?, ?)""",
            (dept_rev_id, dept_id, company_id, _sha256("root"), now),
        )
        await db.execute(
            """INSERT INTO employees (id, company_id, department_id, display_name, normalized_display_name,
                base_profile_version_id, workflow_role, status, created_at, updated_at, version)
               VALUES (?, ?, ?, 'Agent', 'agent', ?, 'general_manager', 'active', ?, ?, 1)""",
            (employee_id, company_id, dept_id, version_id, now, now),
        )
        await db.execute(
            """INSERT INTO departments (id, company_id, department_type, normalized_name, current_revision_id,
                leader_employee_id, department_conversation_id, status, created_at, updated_at, version)
               VALUES (?, ?, 'general_manager_office', 'root', ?, ?, ?, 'active', ?, ?, 1)""",
            (dept_id, company_id, dept_rev_id, employee_id, dept_conv_id, now, now),
        )
        await db.execute(
            """INSERT INTO conversations (id, company_id, conversation_type, status, created_at)
               VALUES (?, ?, 'company', 'active', ?)""",
            (conv_id, company_id, now),
        )
        await db.execute(
            """INSERT INTO companies (id, normalized_name, current_revision_id, general_manager_office_id,
                general_manager_employee_id, company_conversation_id, status, created_at, updated_at, version)
               VALUES (?, 't', ?, ?, ?, ?, 'active', ?, ?, 1)""",
            (company_id, rev_id, dept_id, employee_id, conv_id, now, now),
        )
        await db.execute(
            """INSERT INTO catalog_cache_releases (release_id, release_sequence, manifest_json, manifest_sha256,
                signature, signing_key_id, status, downloaded_at, activated_at)
               VALUES (?, 1, '{}', ?, 'sig', 'key', 'active', ?, ?)""",
            (release_id, _sha256("{}"), now, now),
        )
        await db.execute(
            """INSERT INTO employee_base_profiles (id, company_id, name, normalized_name, description,
                current_version_id, status, created_at, updated_at, version)
               VALUES (?, ?, 'Default', 'default', 'Default', ?, 'active', ?, ?, 1)""",
            (profile_id, company_id, version_id, now, now),
        )
        await db.execute(
            """INSERT INTO employee_base_profile_versions
               (id, profile_id, version_number, name, description, profile_type,
                runtime_binding_json, system_prompt, capability_tags_json,
                tool_policy_json, timeout_seconds, max_retries, workspace_policy,
                catalog_release_id, content_sha256, status, created_at, published_at)
               VALUES (?, ?, 1, 'Default v1', 'Default', 'agent_cli', '{"adapter_type":"codex_cli"}',
                       'Act.', '[]', '{}', 300, 2, 'workspace_rw_external_ro', ?, ?,
                       'published', ?, ?)""",
            (version_id, profile_id, release_id, _sha256("v1"), now, now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


async def _create_agent_run(
    db: aiosqlite.Connection,
    company_id: str,
    run_id: str,
    *,
    company_task_id: str | None = None,
    status: str = "queued",
    adapter_type: str = "codex_cli",
    resume_state: str | None = None,
) -> None:
    now = "2026-01-01T00:00:00Z"
    sha = _sha256("spec")
    company_task_id = company_task_id or str(uuid.uuid4())
    # Ensure company_task exists
    conv_id = str(uuid.uuid4())
    msg_event = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT OR IGNORE INTO company_tasks
               (id, company_id, supersedes_task_id, company_conversation_id, user_message_event_id,
                title, status, created_at, updated_at, version)
               VALUES (?, ?, NULL, ?, ?, 'Task', 'draft', ?, ?, 1)""",
            (company_task_id, company_id, conv_id, msg_event, now, now),
        )
        await db.execute(
            """INSERT INTO agent_runs
               (id, company_id, company_task_id, work_item_id, employee_id,
                conversation_id, availability_snapshot_id, execution_snapshot_id,
                run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                status, resume_state, attempt, created_at, updated_at, version)
               VALUES (?, ?, ?, ?, ?, ?, 'avail', 'exec', 'review', ?, '{}', ?,
                       ?, ?, 1, ?, ?, 1)""",
            (
                run_id,
                company_id,
                company_task_id,
                company_task_id,
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                adapter_type,
                sha,
                status,
                resume_state,
                now,
                now,
            ),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


async def _setup_runtime_env_full(db, company_id, version_id, profile_id, employee_id, dept_id):
    """Create full runtime env including a task and run."""
    await _setup_runtime_env(db, company_id, version_id, profile_id, employee_id, dept_id)


@pytest.fixture
async def runtime_env(db: aiosqlite.Connection):
    company_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    profile_id = str(uuid.uuid4())
    employee_id = str(uuid.uuid4())
    dept_id = str(uuid.uuid4())
    await _setup_runtime_env(db, company_id, version_id, profile_id, employee_id, dept_id)
    return {
        "company_id": company_id,
        "version_id": version_id,
        "profile_id": profile_id,
        "employee_id": employee_id,
        "dept_id": dept_id,
    }


@pytest.mark.asyncio
class TestProbeAgent:
    async def test_probe_active_agent(self, db, runtime_env):
        result = await probe_agent(db, runtime_env["company_id"], runtime_env["employee_id"])
        assert result["available"] is True
        assert result["name"] == "Agent"

    async def test_probe_inactive_agent(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        emp_id = str(uuid.uuid4())
        dept_id = runtime_env["dept_id"]
        ver_id = runtime_env["version_id"]
        now = "2026-01-01T00:00:00Z"
        await db.execute("PRAGMA foreign_keys = OFF")
        try:
            await db.execute(
                """INSERT INTO employees (id, company_id, department_id, display_name, normalized_display_name,
                    base_profile_version_id, workflow_role, status, created_at, updated_at, version)
                   VALUES (?, ?, ?, 'Inactive', 'inactive', ?, 'member', 'inactive', ?, ?, 1)""",
                (emp_id, company_id, dept_id, ver_id, now, now),
            )
        finally:
            await db.execute("PRAGMA foreign_keys = ON")
        await db.commit()
        result = await probe_agent(db, company_id, emp_id)
        assert result["available"] is False

    async def test_probe_nonexistent_agent(self, db, runtime_env):
        with pytest.raises(ValueError, match="AGENT_NOT_FOUND"):
            await probe_agent(db, runtime_env["company_id"], "no-such-agent")


@pytest.mark.asyncio
class TestProbeProvider:
    async def test_probe_active_provider(self, db, runtime_env):
        result = await probe_provider(db, runtime_env["company_id"], runtime_env["profile_id"])
        assert result["available"] is True

    async def test_probe_nonexistent_provider(self, db, runtime_env):
        result = await probe_provider(db, runtime_env["company_id"], "nonexistent")
        assert result["available"] is False


@pytest.mark.asyncio
class TestListAvailableModels:
    async def test_list_models(self, db, runtime_env):
        models = await list_available_models(db, runtime_env["company_id"])
        assert len(models) >= 1
        assert models[0]["profile_id"] == runtime_env["profile_id"]

    async def test_list_models_empty_company(self, db):
        models = await list_available_models(db, "nonexistent-company")
        assert models == []


@pytest.mark.asyncio
class TestGetRuntimeStatus:
    async def test_status_healthy(self, db, runtime_env):
        status = await get_runtime_status(db, runtime_env["company_id"])
        assert status["status"] == "healthy"
        assert "queue_depth" in status
        assert "active_runs" in status


@pytest.mark.asyncio
class TestListAgentRuns:
    async def test_list_runs(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="queued")
        runs = await list_agent_runs(db, company_id)
        assert len(runs) == 1
        assert runs[0]["id"] == run_id

    async def test_list_runs_by_status(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        await _create_agent_run(db, company_id, str(uuid.uuid4()), status="running")
        await _create_agent_run(db, company_id, str(uuid.uuid4()), status="queued")
        running = await list_agent_runs(db, company_id, status="running")
        assert len(running) == 1
        assert running[0]["status"] == "running"

    async def test_list_runs_empty(self, db, runtime_env):
        runs = await list_agent_runs(db, runtime_env["company_id"])
        assert runs == []


@pytest.mark.asyncio
class TestGetAgentRun:
    async def test_get_existing_run(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id)
        run = await get_agent_run(db, company_id, run_id)
        assert run is not None
        assert run["id"] == run_id

    async def test_get_nonexistent_run(self, db, runtime_env):
        run = await get_agent_run(db, runtime_env["company_id"], "no-id")
        assert run is None


@pytest.mark.asyncio
class TestListRunEvents:
    async def test_list_events_empty(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id)
        events = await list_run_events(db, company_id, run_id)
        assert events == []

    async def test_list_events_nonexistent_run(self, db, runtime_env):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await list_run_events(db, runtime_env["company_id"], "no-run")


@pytest.mark.asyncio
class TestCancelRun:
    async def test_cancel_running(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="running")
        result = await cancel_run(db, company_id, run_id)
        assert result["status"] == "cancelled"

    async def test_cancel_nonexistent_run(self, db, runtime_env):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await cancel_run(db, runtime_env["company_id"], "no-run")

    async def test_cancel_terminal_run(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="succeeded")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await cancel_run(db, company_id, run_id)

    async def test_cancel_queue_status_updates(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="running")
        # Enqueue
        now = "2026-01-01T00:00:00Z"
        queue_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO runtime_queue
               (id, company_id, work_item_type, work_item_id, job_id, run_id,
                priority, status, queued_at)
               VALUES (?, ?, 'review', ?, ?, ?, 0, 'leased', ?)""",
            (queue_id, company_id, str(uuid.uuid4()), str(uuid.uuid4()), run_id, now),
        )
        await db.commit()
        await cancel_run(db, company_id, run_id)
        row = await (await db.execute("SELECT status FROM runtime_queue WHERE id=?", (queue_id,))).fetchone()
        assert row["status"] == "cancelled"


@pytest.mark.asyncio
class TestResumeRun:
    async def test_resume_waiting_approval(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="waiting_approval", resume_state="running")
        result = await resume_run(db, company_id, run_id)
        assert result["status"] == "running"

    async def test_resume_waiting_resource(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="waiting_resource", resume_state="running")
        result = await resume_run(db, company_id, run_id)
        assert result["status"] == "running"

    async def test_resume_nonexistent_run(self, db, runtime_env):
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await resume_run(db, runtime_env["company_id"], "no-run")

    async def test_resume_running_run_raises(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="running")
        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await resume_run(db, company_id, run_id)

    async def test_resume_with_no_resume_state_defaults_to_running(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="waiting_approval", resume_state="running")
        result = await resume_run(db, company_id, run_id)
        assert result["status"] == "running"
