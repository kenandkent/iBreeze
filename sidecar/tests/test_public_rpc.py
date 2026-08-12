"""Cover the sidecar public RPC handler layer (``public_rpc.py``).

These tests drive the module-level ``_xxx(db, params)`` adapters directly
against a real migrated database, and run ``register_public_handlers`` against
a fake lifecycle so the full 112-method registry gate is exercised.  The domain
services underneath are real; only the transport (ReadPool / WriteQueue /
UnitOfWork) is faked to route onto the test connection.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio

from ibreeze.application import public_rpc as rpc
from ibreeze.application.context import CommandContext
from ibreeze.rpc.dispatcher import Dispatcher


def _ctx() -> CommandContext:
    return CommandContext(
        trace_id=uuid4(),
        ipc_session_id=uuid4(),
        window_session_id=None,
        idempotency_key=str(uuid4()),
        deadline_at=datetime.now(UTC) + timedelta(seconds=30),
    )


class _FakeReadPool:
    def __init__(self, db):
        self._db = db

    async def read_transaction(self, fn):
        return await fn(self._db)


class _FakeWriteQueue:
    def __init__(self, db):
        self._db = db

    async def barrier(self) -> None:
        return None

    async def submit(self, *, command_name, trace_id, deadline_at, execute):
        return await execute(self._db)


class _FakeUnitOfWork:
    def __init__(self, db):
        self._db = db

    async def execute(self, idempotency_key, request_sha256, command):
        result = await command(SimpleNamespace(connection=self._db))
        return result.response


class _FakeLifecycle:
    def __init__(self, profile_path: Path, db) -> None:
        self._profile_path = profile_path
        self.dispatcher = Dispatcher()
        self.read_pool = _FakeReadPool(db)
        self.write_queue = _FakeWriteQueue(db)
        self.unit_of_work = _FakeUnitOfWork(db)


@pytest_asyncio.fixture
async def env(db, published_profile, tmp_path):
    """Full company + published profile + registered fake lifecycle."""
    cur = await db.execute("SELECT id FROM companies LIMIT 1")
    company_id = str((await cur.fetchone())["id"])
    cur = await db.execute("SELECT id FROM employees LIMIT 1")
    employee_id = str((await cur.fetchone())["id"])
    cur = await db.execute("SELECT id FROM departments LIMIT 1")
    dept_id = str((await cur.fetchone())["id"])
    cur = await db.execute("SELECT id FROM conversations WHERE conversation_type='company' LIMIT 1")
    conv_id = str((await cur.fetchone())["id"])
    cur = await db.execute("SELECT id FROM employee_base_profiles LIMIT 1")
    profile_id = str((await cur.fetchone())["id"])

    lifecycle = _FakeLifecycle(tmp_path / "profile.db", db)
    registered = rpc.register_public_handlers(lifecycle)
    return SimpleNamespace(
        db=db,
        company_id=company_id,
        employee_id=employee_id,
        dept_id=dept_id,
        conversation_id=conv_id,
        profile_id=profile_id,
        profile_version_id=published_profile,
        lifecycle=lifecycle,
        registered=registered,
        tmp_path=tmp_path,
    )


async def _insert_domain_event(db, company_id: str) -> str:
    event_id = str(uuid4())
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    await db.execute(
        """INSERT INTO domain_events
           (event_id, company_id, aggregate_type, aggregate_id, aggregate_version,
            event_type, payload_json, trace_id, occurred_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (event_id, company_id, "company_task", str(uuid4()), 1, "test.event", "{}", str(uuid4()), now),
    )
    return event_id


async def _insert_company_task(db, env, *, status: str = "draft") -> str:
    event_id = await _insert_domain_event(db, env.company_id)
    task_id = str(uuid4())
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    await db.execute(
        """INSERT INTO company_tasks
           (id, company_id, company_conversation_id, user_message_event_id,
            title, status, created_at, updated_at, version)
           VALUES (?,?,?,?,?,?,?,?,1)""",
        (task_id, env.company_id, env.conversation_id, event_id, "T", status, now, now),
    )
    return task_id


class TestPrimitives:
    def test_serialize_handles_all_types(self) -> None:
        assert rpc._serialize({"x": uuid4()})["x"]
        assert rpc._serialize(datetime.now(UTC)).endswith("Z")

    def test_required_missing(self) -> None:
        with pytest.raises(ValueError, match="VALIDATION_FAILED"):
            rpc._required({"a": 1}, "a", "b")

    def test_context_rejects_non_command_context(self) -> None:
        with pytest.raises(ValueError, match="IPC_SESSION_INVALID"):
            rpc._context(object())

    @pytest.mark.asyncio
    async def test_direct_query(self, db) -> None:
        rows = await rpc._direct_query(db, "SELECT 1 AS x")
        assert rows == [{"x": 1}]


class TestFirstPublishedProfile:
    @pytest.mark.asyncio
    async def test_raises_without_published_profile(self, db) -> None:
        with pytest.raises(ValueError, match="PROFILE_VERSION_INVALID"):
            await rpc._company_create(db, {"name": "NoProfile"})


class TestCompanyHandlers:
    @pytest.mark.asyncio
    async def test_get(self, env) -> None:
        result = await rpc._company_get(env.db, {"company_id": env.company_id})
        assert result["company_id"] == env.company_id
        assert result["name"]

    @pytest.mark.asyncio
    async def test_list(self, env) -> None:
        result = await rpc._company_list(env.db, {})
        assert result["items"]
        assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_create_and_update(self, env) -> None:
        created = await rpc._company_create(
            env.db, {"name": "Acme", "introduction": "Intro", "base_profile_version_id": env.profile_version_id}
        )
        assert created["company_id"]
        updated = rpc._serialize(
            await rpc._company_update(
                env.db,
                {"company_id": created["company_id"], "name": "Acme2", "expected_version": created["version"]},
            )
        )
        assert updated["version"] > created["version"]


class TestDepartmentHandlers:
    @pytest.mark.asyncio
    async def test_create_get_list(self, env) -> None:
        created = await rpc._department_create(
            env.db, {"company_id": env.company_id, "name": "Eng", "function_description": "Engineering", "base_profile_version_id": env.profile_version_id}
        )
        assert created["department_id"]
        got = await rpc._department_get(env.db, {"company_id": env.company_id, "department_id": created["department_id"]})
        assert got["id"] == created["department_id"]
        listed = await rpc._department_list(env.db, {"company_id": env.company_id})
        assert any(item["id"] == created["department_id"] for item in listed["items"])

    @pytest.mark.asyncio
    async def test_update_and_set_leader(self, env) -> None:
        dept_id = (
            await rpc._department_create(
                env.db, {"company_id": env.company_id, "name": "Prod", "function_description": "Ops", "base_profile_version_id": env.profile_version_id}
            )
        )["department_id"]
        member_id = (
            await rpc._employee_create(env.db, {"company_id": env.company_id, "department_id": dept_id, "display_name": "Lead"})
        )["employee_id"]
        await rpc._department_update(
            env.db, {"company_id": env.company_id, "department_id": dept_id, "name": "Renamed", "expected_version": 1}
        )
        result = await rpc._department_set_leader(
            env.db, {"company_id": env.company_id, "department_id": dept_id, "employee_id": member_id, "expected_version": 2}
        )
        assert result["version"] == 3

    @pytest.mark.asyncio
    async def test_responsibility_crud(self, env) -> None:
        created = await rpc._responsibility_create(
            env.db, {"company_id": env.company_id, "department_id": env.dept_id, "responsibility_key": "dev"}
        )
        assert created["version"] == 1
        await rpc._responsibility_update(env.db, {"company_id": env.company_id, "department_id": env.dept_id, "name": "X", "expected_version": 1})
        deleted = await rpc._responsibility_delete(env.db, {"company_id": env.company_id, "department_id": env.dept_id})
        assert deleted["status"] == "deleted"


class TestEmployeeHandlers:
    @pytest.mark.asyncio
    async def test_create_get_list(self, env) -> None:
        created = await rpc._employee_create(
            env.db, {"company_id": env.company_id, "department_id": env.dept_id, "display_name": "Bob"}
        )
        got = await rpc._employee_get(env.db, {"company_id": env.company_id, "employee_id": created["employee_id"]})
        assert got["employee_id"] == created["employee_id"]
        listed = await rpc._employee_list(env.db, {"company_id": env.company_id})
        assert any(item["id"] == created["employee_id"] for item in listed["items"])

    @pytest.mark.asyncio
    async def test_update_display_and_status(self, env) -> None:
        member_id = (
            await rpc._employee_create(env.db, {"company_id": env.company_id, "department_id": env.dept_id, "display_name": "Member"})
        )["employee_id"]
        display = await rpc._employee_update_display(
            env.db, {"company_id": env.company_id, "employee_id": member_id, "display_name": "Member2"}
        )
        assert display["success"] is True
        status = await rpc._employee_update_status(
            env.db, {"company_id": env.company_id, "employee_id": member_id, "status": "draining", "expected_version": 2}
        )
        assert status["version"] == 3

    @pytest.mark.asyncio
    async def test_base_profile_and_work_role(self, env) -> None:
        base = await rpc._employee_base_profile(
            env.db, {"company_id": env.company_id, "employee_id": env.employee_id, "base_profile_version_id": env.profile_version_id}
        )
        assert base["success"] is True
        role = await rpc._employee_work_role(env.db, {"company_id": env.company_id, "employee_id": env.employee_id, "work_role": "member"})
        assert role["success"] is True

    @pytest.mark.asyncio
    async def test_archive_row_success_and_already(self, env) -> None:
        # departments.status permits 'archived'; employees.status does not.
        result = await rpc._archive_row(env.db, "departments", env.dept_id, env.company_id, "archived")
        assert result["status"] == "archived"
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND_OR_ALREADY_ARCHIVED"):
            await rpc._archive_row(env.db, "departments", env.dept_id, env.company_id, "archived")


class TestConversationHandlers:
    @pytest.mark.asyncio
    async def test_create_list_messages(self, env) -> None:
        created = await rpc._conversation_create(env.db, {"company_id": env.company_id, "title": "C"})
        listed = await rpc._conversation_list(env.db, {"company_id": env.company_id})
        assert any(item["id"] == created["conversation_id"] for item in listed["items"])
        messages = await rpc._conversation_messages(
            env.db, {"company_id": env.company_id, "conversation_id": created["conversation_id"]}
        )
        assert messages["items"] == []

    @pytest.mark.asyncio
    async def test_submit_user_message(self, env) -> None:
        result = await rpc._conversation_submit(
            env.db, {"company_id": env.company_id, "conversation_id": env.conversation_id, "content": "请做一件事"}
        )
        assert result["message_id"]
        assert result["task_status"] in {"draft", "revision_requested"}


class TestTaskAndReviewHandlers:
    @pytest.mark.asyncio
    async def test_task_row_raises_when_missing(self, env) -> None:
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await rpc._task_row(env.db, "employee_tasks", str(uuid4()), env.company_id)

    @pytest.mark.asyncio
    async def test_task_rows_empty(self, env) -> None:
        result = await rpc._task_rows(env.db, "employee_tasks", {"company_id": env.company_id})
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_workspace_list_and_approval_list(self, env) -> None:
        workspaces = await rpc._workspace_list(env.db, {"company_id": env.company_id})
        assert workspaces["items"] == []
        approvals = await rpc._approval_list(env.db, {"company_id": env.company_id})
        assert approvals["approvals"] == []

    @pytest.mark.asyncio
    async def test_review_get_not_found_and_list_empty(self, env) -> None:
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await rpc._review_get(env.db, {"company_id": env.company_id, "review_id": str(uuid4())})
        listed = await rpc._review_list(env.db, {"company_id": env.company_id})
        assert listed["items"] == []

    @pytest.mark.asyncio
    async def test_task_supersede(self, env) -> None:
        task_id = await _insert_company_task(env.db, env)
        result = await rpc._task_supersede(env.db, {"company_id": env.company_id, "task_id": task_id, "reason": "改需求"})
        assert result["new_task_id"]
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await rpc._task_supersede(env.db, {"company_id": env.company_id, "task_id": str(uuid4())})


class TestArtifactAndKnowledge:
    @pytest.mark.asyncio
    async def test_artifact_create(self, env) -> None:
        task_id = await _insert_company_task(env.db, env)
        result = await rpc._artifact_create(
            env.db,
            {
                "company_id": env.company_id,
                "company_task_id": task_id,
                "artifact_type": "document",
                "content": "content",
                "filename": "plan.md",
                "created_by_employee_id": env.employee_id,
            },
        )
        assert result["artifact_id"]

    @pytest.mark.asyncio
    async def test_knowledge_import(self, env) -> None:
        event_id = await _insert_domain_event(env.db, env.company_id)
        result = await rpc._knowledge_import(
            env.db, {"company_id": env.company_id, "title": "K", "content": "data", "visibility": "company", "source_message_event_id": event_id}
        )
        assert result["status"] == "imported"


class TestSettingsAndEvents:
    @pytest.mark.asyncio
    async def test_settings_get(self, env) -> None:
        result = await rpc._settings_get(env.db, {})
        assert "settings" in result

    @pytest.mark.asyncio
    async def test_settings_update_allowed_and_ignored(self, env) -> None:
        v1 = await rpc._settings_update(env.db, {"updates": {"cli_global_concurrency": 3}})
        assert v1["version"] >= 2
        v2 = await rpc._settings_update(env.db, {"updates": {"bogus_key": 1}})
        assert v2["version"] == v1["version"]

    @pytest.mark.asyncio
    async def test_event_replay_and_subscribe(self, env) -> None:
        result = await rpc._event_replay(env.db, {"company_id": env.company_id})
        assert result["replayed_event_ids"] == []
        sub = rpc._event_subscribe({"scope": "company"})
        assert sub["scope"] == "company"


_MANIFEST = {
    "release_id": "rel-2026-01",
    "release_sequence": 7,
    "created_at": "2026-01-01T00:00:00Z",
    "signature": "sig",
    "signing_key_id": "key-1",
    "resources": [
        {"type": "agent", "id": "agent-1", "key": "a1", "display_name": "Agent One", "version": "1.0.0"},
        {"type": "provider", "id": "prov-1", "key": "openai", "protocol": "chat",
         "model_bindings": [{"binding_id": "b1", "provider_model_name": "gpt-4o", "model_id": "model-1"}]},
        {"type": "model", "id": "model-1", "key": "openai/gpt-4o", "display_name": "GPT-4o", "version": "1"},
        {"type": "skill", "id": "skill-1", "skill_version_id": "sv-1", "display_name": "Skill One",
         "version": "1.0.0", "description": "d", "content_sha256": "abc" + "0" * 61},
    ],
}


class TestCatalog:
    @pytest.mark.asyncio
    async def test_manifest_missing_raises_not_ready(self, tmp_path) -> None:
        lc = _FakeLifecycle(tmp_path / "p.db", None)
        with pytest.raises(ValueError, match="CATALOG_NOT_READY"):
            rpc._catalog_manifest(lc)

    @pytest.mark.asyncio
    async def test_manifest_invalid(self, tmp_path) -> None:
        (tmp_path / "catalog-manifest.v1.json").write_text("{}", encoding="utf-8")
        lc = _FakeLifecycle(tmp_path / "p.db", None)
        with pytest.raises(ValueError, match="CATALOG_INVALID"):
            rpc._catalog_manifest(lc)

    @pytest.mark.asyncio
    async def test_manifest_invalid_json(self, tmp_path) -> None:
        (tmp_path / "catalog-manifest.v1.json").write_text("{bad", encoding="utf-8")
        lc = _FakeLifecycle(tmp_path / "p.db", None)
        with pytest.raises(ValueError, match="CATALOG_NOT_READY"):
            rpc._catalog_manifest(lc)

    @pytest.mark.asyncio
    async def test_list_resources(self, tmp_path) -> None:
        (tmp_path / "catalog-manifest.v1.json").write_text(json.dumps(_MANIFEST), encoding="utf-8")
        lc = _FakeLifecycle(tmp_path / "p.db", None)
        agents = await rpc._catalog_list_resources(lc, "agent")
        assert agents["agents"][0]["agent_id"] == "agent-1"
        models = await rpc._catalog_list_resources(lc, "model")
        assert models["models"][0]["model_id"] == "model-1"
        assert models["models"][0]["provider"] == "openai"
        skills = await rpc._catalog_list_resources(lc, "skill")
        assert skills["skills"][0]["skill_id"] == "skill-1"

    @pytest.mark.asyncio
    async def test_list_catalogs_get_active(self, tmp_path) -> None:
        (tmp_path / "catalog-manifest.v1.json").write_text(json.dumps(_MANIFEST), encoding="utf-8")
        lc = _FakeLifecycle(tmp_path / "p.db", None)
        catalogs = await rpc._catalog_list_catalogs(lc)
        assert catalogs["catalogs"][0]["catalog_id"] == "rel-2026-01"
        got = await rpc._catalog_get(lc, {"catalog_id": "rel-2026-01"})
        assert got["catalog_id"] == "rel-2026-01"
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await rpc._catalog_get(lc, {"catalog_id": "nope"})
        active = await rpc._catalog_active(lc)
        assert active["status"] == "active"

    @pytest.mark.asyncio
    async def test_sync_and_verify(self, db, tmp_path) -> None:
        (tmp_path / "catalog-manifest.v1.json").write_text(json.dumps(_MANIFEST), encoding="utf-8")
        lc = _FakeLifecycle(tmp_path / "p.db", db)
        before = await rpc._catalog_verify(lc, db)
        assert before["valid"] is False
        synced = await rpc._catalog_sync(lc, db)
        assert synced["status"] == "synced"
        after = await rpc._catalog_verify(lc, db)
        assert after["valid"] is True

    @pytest.mark.asyncio
    async def test_verify_without_manifest(self, tmp_path) -> None:
        lc = _FakeLifecycle(tmp_path / "p.db", None)
        assert await rpc._catalog_verify(lc, None) == {"valid": False, "release_count": 0}

    @pytest.mark.asyncio
    async def test_install_and_remove(self, db, tmp_path) -> None:
        (tmp_path / "catalog-manifest.v1.json").write_text(json.dumps(_MANIFEST), encoding="utf-8")
        lc = _FakeLifecycle(tmp_path / "p.db", db)
        await rpc._catalog_sync(lc, db)
        result = await rpc._catalog_install(
            lc,
            db,
            {
                "skill_id": "skill-1",
                "skill_version_id": "sv-1",
                "skill_version": "1.0.0",
                "package_sha256": "abc" + "0" * 61,
                "package_path": "/tmp/skill.zip",
            },
        )
        assert result["installed"] is True
        with pytest.raises(ValueError, match="CATALOG_SKILL_INVALID"):
            await rpc._catalog_install(lc, db, {"skill_id": "missing", "skill_version_id": "x", "skill_version": "1"})
        removed = await rpc._catalog_remove(db, {"skill_id": "skill-1"})
        assert removed["removed"] is True


class TestBackup:
    @pytest.mark.asyncio
    async def test_create_list_get(self, env) -> None:
        created = await rpc._backup_create(env.lifecycle, env.db, {})
        assert created["backup_id"]
        listed = await rpc._backup_list(env.lifecycle, {})
        assert any(str(item.get("id", item.get("backup_id", ""))) == created["backup_id"] for item in listed["items"])
        got = await rpc._backup_get(env.lifecycle, {"backup_id": created["backup_id"]})
        assert str(got.get("id", got.get("backup_id", ""))) == created["backup_id"]

    @pytest.mark.asyncio
    async def test_get_not_found(self, env) -> None:
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await rpc._backup_get(env.lifecycle, {"backup_id": "missing"})


class TestRuntime:
    @pytest.mark.asyncio
    async def test_run_validation(self, env) -> None:
        with pytest.raises(ValueError, match="VALIDATION_FAILED"):
            await rpc._runtime_run(env.db, {"company_id": env.company_id})

    @pytest.mark.asyncio
    async def test_stop_empty(self, env) -> None:
        result = await rpc._runtime_stop(env.db, {"company_id": env.company_id, "agent_id": env.employee_id})
        assert result == {"stopped": True, "count": 0}


class TestVerifyRegistry:
    def test_raises_when_review_handlers_missing(self, env) -> None:
        # register_public_handlers alone covers 108 methods; the four review.*
        # handlers are registered by the lifecycle afterwards.
        with pytest.raises(RuntimeError, match="SIDECAR_RPC_HANDLER_MISSING:review.listIssues"):
            rpc.verify_sidecar_registry(env.lifecycle.dispatcher)

    @pytest.mark.asyncio
    async def test_passes_when_all_handlers_registered(self, env) -> None:
        async def _dummy(params, session):
            return {}

        dispatcher = env.lifecycle.dispatcher
        for method in ("review.listIssues", "review.rerun", "review.resolveIssue", "review.submit"):
            dispatcher.register(method, _dummy)
        assert rpc.verify_sidecar_registry(dispatcher) == 112


class TestRegisterAndDispatch:
    def test_registers_all_public_sidecar_methods(self, env) -> None:
        # 112 sidecar methods total; the four review.* live in the lifecycle.
        assert env.registered == 108

    @pytest.mark.asyncio
    async def test_dispatch_company_get(self, env) -> None:
        result = await env.lifecycle.dispatcher.dispatch("company.get", {"company_id": env.company_id}, _ctx())
        assert result["company_id"] == env.company_id

    @pytest.mark.asyncio
    async def test_dispatch_company_create_write(self, env) -> None:
        result = await env.lifecycle.dispatcher.dispatch(
            "company.create", {"name": "DispatchCo", "introduction": "Intro", "base_profile_version_id": env.profile_version_id}, _ctx()
        )
        assert result["company_id"]

    @pytest.mark.asyncio
    async def test_dispatch_settings_and_event(self, env) -> None:
        settings = await env.lifecycle.dispatcher.dispatch("settings.get", {}, _ctx())
        assert "settings" in settings
        sub = await env.lifecycle.dispatcher.dispatch("event.subscribe", {"scope": "global"}, _ctx())
        assert sub["scope"] == "global"

    @pytest.mark.asyncio
    async def test_dispatch_sql_reads(self, env) -> None:
        tasks = await env.lifecycle.dispatcher.dispatch("employeeTask.list", {"company_id": env.company_id}, _ctx())
        assert tasks["items"] == []
        reviews = await env.lifecycle.dispatcher.dispatch("review.list", {"company_id": env.company_id}, _ctx())
        assert reviews["items"] == []
        approvals = await env.lifecycle.dispatcher.dispatch("approval.listPending", {"company_id": env.company_id}, _ctx())
        assert approvals["approvals"] == []

    @pytest.mark.asyncio
    async def test_dispatch_profile_read(self, env) -> None:
        profile = await env.lifecycle.dispatcher.dispatch(
            "profile.get", {"company_id": env.company_id, "profile_id": env.profile_id}, _ctx()
        )
        assert profile["id"] == env.profile_id

    @pytest.mark.asyncio
    async def test_dispatch_task_read_missing_returns_none(self, env) -> None:
        result = await env.lifecycle.dispatcher.dispatch("task.get", {"company_id": env.company_id, "task_id": str(uuid4())}, _ctx())
        assert result is None

    @pytest.mark.asyncio
    async def test_dispatch_catalog_list_agents(self, env) -> None:
        (env.tmp_path / "catalog-manifest.v1.json").write_text(json.dumps(_MANIFEST), encoding="utf-8")
        agents = await env.lifecycle.dispatcher.dispatch("catalog.listAgents", {}, _ctx())
        assert agents["agents"][0]["agent_id"] == "agent-1"

    @pytest.mark.asyncio
    async def test_dispatch_conversation_get_company(self, env) -> None:
        conv = await env.lifecycle.dispatcher.dispatch(
            "conversation.getCompany", {"company_id": env.company_id, "conversation_id": env.conversation_id}, _ctx()
        )
        assert conv["id"] == env.conversation_id

    @pytest.mark.asyncio
    async def test_dispatch_backup_list(self, env) -> None:
        result = await env.lifecycle.dispatcher.dispatch("backup.list", {}, _ctx())
        assert "items" in result

    @pytest.mark.asyncio
    async def test_dispatch_runtime_get_status(self, env) -> None:
        from unittest.mock import AsyncMock, patch

        with patch.object(rpc.runtime_service, "get_runtime_status", new=AsyncMock(return_value={"status": "ready"})) as m:
            result = await env.lifecycle.dispatcher.dispatch(
                "runtime.getStatus", {"company_id": env.company_id}, _ctx()
            )
        assert result["status"] == "ready"
        m.assert_awaited_once()
