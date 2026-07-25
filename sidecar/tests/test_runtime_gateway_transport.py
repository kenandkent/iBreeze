"""Tests for runtime/gateway.py, runtime/transport.py, runtime/event_normalizer.py gaps."""

from __future__ import annotations

import json
import uuid

import aiosqlite
import pytest

from ibreeze.runtime.gateway import (
    RunNotFoundError,
    RunValidationError,
    cancel,
    get_status,
    resume,
    start,
)
from ibreeze.runtime.transport import (
    AnthropicTransport,
    OpenAITransport,
    UsageStats,
    _parse_json,
    create_transport,
)
from ibreeze.runtime.event_normalizer import (
    EVENT_TYPES,
    create_approval_event,
    create_checkpoint,
    create_compacted_event,
    create_model_delta,
    create_model_done,
    create_run_cancelled,
    create_run_completed,
    create_run_failed,
    create_run_started,
    create_tool_approved_event,
    create_tool_event,
    create_tool_rejected_event,
    create_verification_completed_event,
    create_verification_started_event,
    create_workspace_changed_event,
    normalize_event,
    store_event,
)


def _sha256(data: str) -> str:
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()


async def _setup_gateway_env(db: aiosqlite.Connection, company_id: str) -> None:
    now = "2026-01-01T00:00:00Z"
    rev_id = str(uuid.uuid4())
    dept_rev_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    dept_conv_id = str(uuid.uuid4())
    dept_id = str(uuid.uuid4())
    employee_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    profile_id = str(uuid.uuid4())
    release_id = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT INTO company_revisions (id, company_id, revision_number, name, introduction, content_sha256, created_by_type, created_at)
               VALUES (?, ?, 1, 'Co', 'Intro', ?, 'system', ?)""",
            (rev_id, company_id, _sha256("co"), now),
        )
        await db.execute(
            """INSERT INTO conversations (id, company_id, conversation_type, status, created_at)
               VALUES (?, ?, 'department', 'active', ?)""",
            (dept_conv_id, company_id, now),
        )
        await db.execute(
            """INSERT INTO department_revisions (id, department_id, company_id, revision_number, name, function_description, content_sha256, created_at)
               VALUES (?, ?, ?, 1, 'Root', 'Root', ?, ?)""",
            (dept_rev_id, dept_id, company_id, _sha256("root"), now),
        )
        await db.execute(
            """INSERT INTO employees (id, company_id, department_id, display_name, normalized_display_name,
                base_profile_version_id, workflow_role, status, created_at, updated_at, version)
               VALUES (?, ?, ?, 'GM', 'gm', ?, 'general_manager', 'active', ?, ?, 1)""",
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


async def _create_task(db: aiosqlite.Connection, company_id: str, task_id: str) -> None:
    now = "2026-01-01T00:00:00Z"
    conv_id = str(uuid.uuid4())
    msg_event = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT OR IGNORE INTO company_tasks
               (id, company_id, supersedes_task_id, company_conversation_id, user_message_event_id,
                title, status, created_at, updated_at, version)
               VALUES (?, ?, NULL, ?, ?, 'Task', 'draft', ?, ?, 1)""",
            (task_id, company_id, conv_id, msg_event, now, now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


async def _create_run(
    db: aiosqlite.Connection, company_id: str, run_id: str, task_id: str,
    employee_id: str, conv_id: str, status: str = "queued",
    resume_state: str | None = None,
) -> None:
    now = "2026-01-01T00:00:00Z"
    sha = _sha256("spec")
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute(
            """INSERT INTO agent_runs
               (id, company_id, company_task_id, work_item_id, employee_id,
                conversation_id, availability_snapshot_id, execution_snapshot_id,
                run_purpose, adapter_type, run_spec_json, run_spec_sha256,
                status, resume_state, attempt, created_at, updated_at, version)
               VALUES (?, ?, ?, ?, ?, ?, 'avail', 'exec', 'review', 'codex_cli', '{}', ?,
                       ?, ?, 1, ?, ?, 1)""",
            (run_id, company_id, task_id, task_id, employee_id, conv_id,
             sha, status, resume_state, now, now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


@pytest.fixture
async def gw_env(db: aiosqlite.Connection):
    company_id = str(uuid.uuid4())
    await _setup_gateway_env(db, company_id)
    emp_row = await (await db.execute(
        "SELECT id FROM employees WHERE company_id=?", (company_id,)
    )).fetchone()
    conv_row = await (await db.execute(
        "SELECT id FROM conversations WHERE company_id=? AND conversation_type='company'", (company_id,)
    )).fetchone()
    return {
        "company_id": company_id,
        "employee_id": emp_row["id"],
        "conv_id": conv_row["id"],
    }


# ── gateway ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestGatewayStart:
    async def test_start_success(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        result = await start(
            db,
            company_id=company_id,
            company_task_id=task_id,
            employee_id=gw_env["employee_id"],
            model_id="gpt-4o",
            prompt="Build something",
            run_purpose="company_plan",
            adapter_type="codex_cli",
            conversation_id=gw_env["conv_id"],
            availability_snapshot_id="avail-1",
            execution_snapshot_id="exec-1",
        )
        assert result["status"] == "queued"
        assert result["run_id"]

    async def test_start_nonexistent_task(self, db, gw_env):
        with pytest.raises(RunNotFoundError):
            await start(
                db,
                company_id=gw_env["company_id"],
                company_task_id="nonexistent",
                employee_id=gw_env["employee_id"],
                model_id="gpt-4o", prompt="test",
                run_purpose="company_plan", adapter_type="codex_cli",
                conversation_id=gw_env["conv_id"],
                availability_snapshot_id="a", execution_snapshot_id="e",
            )

    async def test_start_nonexistent_employee(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        with pytest.raises(RunNotFoundError):
            await start(
                db, company_id=company_id, company_task_id=task_id,
                employee_id="nonexistent", model_id="gpt-4o", prompt="test",
                run_purpose="company_plan", adapter_type="codex_cli",
                conversation_id=gw_env["conv_id"],
                availability_snapshot_id="a", execution_snapshot_id="e",
            )


@pytest.mark.asyncio
class TestGatewayCancel:
    async def test_cancel_success(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        await _create_run(db, company_id, run_id, task_id, gw_env["employee_id"], gw_env["conv_id"], "running")
        result = await cancel(db, company_id, run_id, reason="test cancel")
        assert result["status"] == "cancelled"

    async def test_cancel_terminal(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        await _create_run(db, company_id, run_id, task_id, gw_env["employee_id"], gw_env["conv_id"], "succeeded")
        result = await cancel(db, company_id, run_id)
        assert result["status"] == "succeeded"

    async def test_cancel_nonexistent(self, db, gw_env):
        with pytest.raises(RunNotFoundError):
            await cancel(db, gw_env["company_id"], "nonexistent")


@pytest.mark.asyncio
class TestGatewayResume:
    async def test_resume_waiting_approval(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        await _create_run(db, company_id, run_id, task_id, gw_env["employee_id"], gw_env["conv_id"],
                          "waiting_approval", resume_state="running")
        result = await resume(db, company_id, run_id)
        assert result["status"] == "running"

    async def test_resume_non_waiting(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        await _create_run(db, company_id, run_id, task_id, gw_env["employee_id"], gw_env["conv_id"], "running")
        with pytest.raises(RunValidationError, match="STATE_TRANSITION_INVALID"):
            await resume(db, company_id, run_id)

    async def test_resume_nonexistent(self, db, gw_env):
        with pytest.raises(RunNotFoundError):
            await resume(db, gw_env["company_id"], "nonexistent")


@pytest.mark.asyncio
class TestGatewayGetStatus:
    async def test_get_status(self, db, gw_env):
        company_id = gw_env["company_id"]
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        await _create_task(db, company_id, task_id)
        await _create_run(db, company_id, run_id, task_id, gw_env["employee_id"], gw_env["conv_id"])
        status = await get_status(db, company_id, run_id)
        assert status["id"] == run_id

    async def test_get_status_nonexistent(self, db, gw_env):
        with pytest.raises(RunNotFoundError):
            await get_status(db, gw_env["company_id"], "nonexistent")


# ── transport ────────────────────────────────────────────────────────
class TestTransport:
    def test_parse_json_valid(self):
        assert _parse_json('{"key": "value"}') == {"key": "value"}

    def test_parse_json_invalid(self):
        assert _parse_json("not json") == {}

    def test_parse_json_non_dict(self):
        assert _parse_json('"string"') == {}

    def test_openai_transport_init(self):
        t = OpenAITransport(api_key="test-key", model="gpt-4o")
        assert t._api_key == "test-key"
        assert t._model == "gpt-4o"

    def test_anthropic_transport_init(self):
        t = AnthropicTransport(api_key="test-key")
        assert t._api_key == "test-key"

    def test_openai_normalize_usage(self):
        t = OpenAITransport(api_key="k")
        stats = t.normalize_usage({"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30})
        assert isinstance(stats, UsageStats)
        assert stats.prompt_tokens == 10
        assert stats.total_tokens == 30

    def test_anthropic_normalize_usage(self):
        t = AnthropicTransport(api_key="k")
        stats = t.normalize_usage({"input_tokens": 10, "output_tokens": 20})
        assert stats.prompt_tokens == 10
        assert stats.total_tokens == 30

    def test_create_transport_openai(self):
        t = create_transport("openai", api_key="k")
        assert isinstance(t, OpenAITransport)

    def test_create_transport_anthropic(self):
        t = create_transport("anthropic", api_key="k")
        assert isinstance(t, AnthropicTransport)

    def test_create_transport_unsupported(self):
        with pytest.raises(ValueError, match="Unsupported provider"):
            create_transport("unknown", api_key="k")


# ── event_normalizer ─────────────────────────────────────────────────
class TestEventNormalizer:
    def test_normalize_event(self):
        ev = normalize_event({"type": "run.started", "data": {"k": "v"}}, "run-1", 1, trace_id="t1")
        assert ev["run_id"] == "run-1"
        assert ev["sequence"] == 1
        assert ev["event_type"] == "run.started"
        assert json.loads(ev["payload_json"]) == {"k": "v"}

    def test_create_run_started(self):
        ev = create_run_started("r1", 1, employee_id="e1", model_id="m1")
        assert ev["event_type"] == "run.started"

    def test_create_run_completed(self):
        ev = create_run_completed("r1", 2, summary="done")
        assert ev["event_type"] == "run.completed"

    def test_create_run_failed(self):
        ev = create_run_failed("r1", 3, error="boom")
        assert ev["event_type"] == "run.failed"

    def test_create_run_cancelled(self):
        ev = create_run_cancelled("r1", 4, reason="timeout")
        assert ev["event_type"] == "run.cancelled"

    def test_create_model_delta(self):
        ev = create_model_delta("r1", 5, delta="hello")
        assert ev["event_type"] == "model.output.delta"

    def test_create_model_done(self):
        ev = create_model_done("r1", 6, output="final")
        assert ev["event_type"] == "model.output.done"

    def test_create_tool_event_valid(self):
        for status in ("requested", "started", "completed", "failed"):
            ev = create_tool_event("r1", 7, tool_name="bash", status=status)
            assert ev["event_type"] == f"tool.{status}"

    def test_create_tool_event_invalid(self):
        with pytest.raises(ValueError, match="Invalid tool status"):
            create_tool_event("r1", 7, tool_name="bash", status="invalid")

    def test_create_checkpoint_created(self):
        ev = create_checkpoint("r1", 8, checkpoint_id="cp-1")
        assert ev["event_type"] == "checkpoint.created"

    def test_create_checkpoint_restored(self):
        ev = create_checkpoint("r1", 9, checkpoint_id="cp-1", restored=True)
        assert ev["event_type"] == "checkpoint.restored"

    def test_create_approval_event(self):
        ev = create_approval_event("r1", 10, tool_name="bash", status="requested")
        assert ev["event_type"] == "approval.requested"

    def test_create_approval_event_invalid(self):
        with pytest.raises(ValueError, match="Invalid approval status"):
            create_approval_event("r1", 10, tool_name="bash", status="invalid")

    def test_create_compacted_event(self):
        ev = create_compacted_event("r1", 1, original_events=[{"x": 1}], compacted_data={"summary": "ok"})
        assert ev["event_type"] == "model.output.compacted"
        assert json.loads(ev["payload_json"])["original_count"] == 1

    def test_create_tool_approved_event(self):
        ev = create_tool_approved_event("r1", 1, tool_name="bash", tool_args={"cmd": "ls"})
        assert ev["event_type"] == "tool.approved"

    def test_create_tool_rejected_event(self):
        ev = create_tool_rejected_event("r1", 1, tool_name="rm", reason="unsafe")
        assert ev["event_type"] == "tool.rejected"

    def test_create_workspace_changed_event(self):
        ev = create_workspace_changed_event("r1", 1, changes=[{"file": "a.py"}])
        assert ev["event_type"] == "workspace.changed"

    def test_create_verification_started_event(self):
        ev = create_verification_started_event("r1", 1, target_run_id="target-1")
        assert ev["event_type"] == "verification.started"

    def test_create_verification_completed_event(self):
        ev = create_verification_completed_event("r1", 1, verdict="passed", issues=[])
        assert ev["event_type"] == "verification.completed"

    def test_all_event_types_present(self):
        assert len(EVENT_TYPES) == 14

    @pytest.mark.asyncio
    async def test_store_event(self, db):
        company_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        await _setup_gateway_env(db, company_id)
        await _create_task(db, company_id, task_id)
        emp_row = await (await db.execute("SELECT id FROM employees WHERE company_id=?", (company_id,))).fetchone()
        conv_row = await (await db.execute("SELECT id FROM conversations WHERE company_id=? AND conversation_type='company'", (company_id,))).fetchone()
        await _create_run(db, company_id, run_id, task_id, emp_row["id"], conv_row["id"])
        ev = create_run_started(run_id, 1, employee_id=emp_row["id"], model_id="gpt-4o")
        eid = await store_event(db, ev)
        assert eid == ev["event_id"]
        cursor = await db.execute("SELECT event_type FROM agent_run_events WHERE run_id=?", (run_id,))
        row = await cursor.fetchone()
        assert row["event_type"] == "run.started"
