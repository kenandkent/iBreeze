"""Coverage tests for ibreeze/runtime/service.py (uncovered branches)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest

from ibreeze.runtime.service import (
    cancel_run,
    list_agent_runs,
    resume_run,
)


def _sha256(data: str) -> str:
    import hashlib

    return hashlib.sha256(data.encode()).hexdigest()


async def _setup_runtime_env(
    db: aiosqlite.Connection,
    company_id: str,
    version_id: str,
    profile_id: str,
    employee_id: str,
    dept_id: str,
) -> None:
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


async def _create_agent_run(
    db: aiosqlite.Connection,
    company_id: str,
    run_id: str,
    *,
    company_task_id: str | None = None,
    status: str = "queued",
    adapter_type: str = "codex_cli",
    resume_state: str | None = None,
    run_purpose: str = "review",
    attempt: int = 1,
) -> None:
    now = "2026-01-01T00:00:00Z"
    sha = _sha256("spec")
    company_task_id = company_task_id or str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    msg_event = str(uuid.uuid4())
    # task_execution runs must satisfy the agent_runs CHECK constraint:
    # department_task_id/employee_task_id NOT NULL and work_item_id = employee_task_id.
    if run_purpose == "task_execution":
        employee_task_id = str(uuid.uuid4())
        department_task_id = str(uuid.uuid4())
        work_item_id = employee_task_id
    else:
        employee_task_id = None
        department_task_id = None
        work_item_id = company_task_id
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
               (id, company_id, company_task_id, department_task_id, employee_task_id,
                work_item_id, employee_id, conversation_id, availability_snapshot_id,
                execution_snapshot_id, run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                status, resume_state, attempt, created_at, updated_at, version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'avail',
                       'exec', ?, ?, '{}', ?,
                       ?, ?, ?, ?, ?, 1)""",
            (
                run_id,
                company_id,
                company_task_id,
                department_task_id,
                employee_task_id,
                work_item_id,
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                run_purpose,
                adapter_type,
                sha,
                status,
                resume_state,
                attempt,
                now,
                now,
            ),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


# ---------------------------------------------------------------------------
# list_agent_runs branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListAgentRunsBranches:
    async def test_limit_below_range(self, db, runtime_env):
        with pytest.raises(ValueError, match="LIMIT_INVALID"):
            await list_agent_runs(db, runtime_env["company_id"], limit=0)

    async def test_limit_above_range(self, db, runtime_env):
        with pytest.raises(ValueError, match="LIMIT_INVALID"):
            await list_agent_runs(db, runtime_env["company_id"], limit=101)

    async def test_filter_by_task_id(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        company_task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, company_task_id=company_task_id, status="running")
        # a second run for a different task must not match the filter
        await _create_agent_run(db, company_id, str(uuid.uuid4()), status="running")
        runs = await list_agent_runs(db, company_id, task_id=company_task_id)
        assert len(runs) == 1
        assert runs[0]["id"] == run_id

    async def test_filter_by_status_and_task(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        company_task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, company_task_id=company_task_id, status="queued")
        runs = await list_agent_runs(db, company_id, task_id=company_task_id, status="queued")
        assert [r["id"] for r in runs] == [run_id]


# ---------------------------------------------------------------------------
# cancel_run branches
# ---------------------------------------------------------------------------


class _Row(dict):
    pass


class _Cursor:
    def __init__(self, rows=None, rowcount: int = 1):
        self._rows = rows or []
        self.rowcount = rowcount

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows


class _FakeDb:
    """Deterministic fake db returning a scripted cursor per execute call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def execute(self, sql, parameters=()):
        self.calls.append((sql, parameters))
        if self._responses:
            return self._responses.pop(0)
        return _Cursor(rowcount=1)


@pytest.mark.asyncio
class TestCancelRunBranches:
    async def test_api_model_cancels_via_transport(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="running", adapter_type="api_model")
        with patch("ibreeze.runtime.service.cancel_model_run", new=AsyncMock(return_value=True)) as cmr:
            result = await cancel_run(db, company_id, run_id)
        cmr.assert_awaited_once_with(run_id, "cancelled by user")
        assert result["status"] == "cancelled"

    async def test_api_model_cancel_failure_raises(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="running", adapter_type="api_model")
        with patch(
            "ibreeze.runtime.service.cancel_model_run",
            new=AsyncMock(side_effect=RuntimeError("transport down")),
        ):
            with pytest.raises(ValueError, match="MODEL_CANCEL_FAILED"):
                await cancel_run(db, company_id, run_id)

    async def test_reverse_rpc_cancels_via_supervisor(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="running", adapter_type="codex_cli")
        supervisor = MagicMock()
        supervisor.kill = AsyncMock()
        with (
            patch("ibreeze.runtime.service.get_reverse_rpc_session", return_value=object()),
            patch("ibreeze.runtime.service.get_supervisor", return_value=supervisor),
        ):
            result = await cancel_run(db, company_id, run_id)
        supervisor.kill.assert_awaited_once_with(run_id, reason="cancelled by user")
        assert result["status"] == "cancelled"

    async def test_reverse_rpc_cancel_failure_raises(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="running", adapter_type="codex_cli")
        supervisor = MagicMock()
        supervisor.kill = AsyncMock(side_effect=RuntimeError("kill failed"))
        with (
            patch("ibreeze.runtime.service.get_reverse_rpc_session", return_value=object()),
            patch("ibreeze.runtime.service.get_supervisor", return_value=supervisor),
        ):
            with pytest.raises(ValueError, match="PROCESS_CANCEL_FAILED"):
                await cancel_run(db, company_id, run_id)

    async def test_reverse_rpc_cancel_resource_not_found_swallowed(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(db, company_id, run_id, status="running", adapter_type="codex_cli")
        supervisor = MagicMock()
        supervisor.kill = AsyncMock(side_effect=RuntimeError("RESOURCE_NOT_FOUND"))
        with (
            patch("ibreeze.runtime.service.get_reverse_rpc_session", return_value=object()),
            patch("ibreeze.runtime.service.get_supervisor", return_value=supervisor),
        ):
            result = await cancel_run(db, company_id, run_id)
        assert result["status"] == "cancelled"

    async def test_missing_adapter_type_uses_none(self):
        fake_db = _FakeDb([_Cursor([_Row(status="running", version=1)])])
        with patch("ibreeze.runtime.service.get_reverse_rpc_session", return_value=None):
            result = await cancel_run(fake_db, "company", "run")
        assert result["status"] == "cancelled"

    async def test_optimistic_lock_conflict(self):
        fake_db = _FakeDb(
            [
                _Cursor([_Row(status="running", adapter_type="codex_cli", version=1)]),
                _Cursor(rowcount=0),
            ]
        )
        with patch("ibreeze.runtime.service.get_reverse_rpc_session", return_value=None):
            with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
                await cancel_run(fake_db, "company", "run")


# ---------------------------------------------------------------------------
# resume_run branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestResumeRunBranches:
    async def test_attempt_limit_exceeded(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(
            db,
            company_id,
            run_id,
            status="waiting_approval",
            resume_state="running",
            run_purpose="review",
            attempt=6,
        )
        with pytest.raises(ValueError, match="RUN_ATTEMPT_LIMIT_EXCEEDED"):
            await resume_run(db, company_id, run_id)

    async def test_task_execution_purpose_maps_to_employee_task(self, db, runtime_env):
        company_id = runtime_env["company_id"]
        run_id = str(uuid.uuid4())
        await _create_agent_run(
            db,
            company_id,
            run_id,
            status="waiting_resource",
            resume_state="running",
            run_purpose="task_execution",
            attempt=1,
        )
        result = await resume_run(db, company_id, run_id)
        assert result["status"] == "running"
        queue = await (await db.execute("SELECT work_item_type FROM runtime_queue WHERE run_id=?", (run_id,))).fetchone()
        assert queue["work_item_type"] == "employee_task"

    async def test_unknown_purpose_falls_back_to_employee_task(self):
        # An unmapped run_purpose must fall back to "employee_task".  A real
        # DB would reject the purpose via CHECK, so drive the mapping with a
        # scripted fake db.
        fake_db = _FakeDb(
            [
                _Cursor(
                    [
                        _Row(
                            status="waiting_approval",
                            resume_state="running",
                            run_purpose="custom_purpose",
                            work_item_id="wi",
                            version=1,
                            attempt=1,
                        )
                    ]
                ),
                _Cursor(rowcount=1),  # UPDATE agent_runs
                _Cursor(rowcount=1),  # INSERT runtime_queue
                _Cursor(rowcount=1),  # INSERT agent_run_events
            ]
        )
        result = await resume_run(fake_db, "company", "run")
        assert result["status"] == "running"
        queue_params = fake_db.calls[2][1]
        assert queue_params[2] == "employee_task"

    async def test_optimistic_lock_conflict(self):
        fake_db = _FakeDb(
            [
                _Cursor(
                    [
                        _Row(
                            status="waiting_approval",
                            resume_state="running",
                            run_purpose="review",
                            work_item_id="wi",
                            version=1,
                            attempt=1,
                        )
                    ]
                ),
                _Cursor(rowcount=0),
            ]
        )
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await resume_run(fake_db, "company", "run")
