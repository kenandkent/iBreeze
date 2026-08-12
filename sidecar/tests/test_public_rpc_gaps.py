"""Cover the remaining public_rpc branches that the main suite does not reach.

These are mostly thin adapter branches (`_profile_call`/`_task_call`/
`_runtime_call` default handling), error paths, and the runtime/backup
SQL helpers.  Service modules are mocked so the tests assert argument
forwarding rather than re-running full domain flows.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from ibreeze.application import public_rpc as rpc
from ibreeze.rpc.dispatcher import Dispatcher

C1 = "00000000-0000-0000-0000-000000000001"
T1 = "00000000-0000-0000-0000-000000000002"


class _FakeLifecycle:
    def __init__(self, profile_path: Path) -> None:
        self._profile_path = profile_path
        self.dispatcher = Dispatcher()
        self.read_pool = SimpleNamespace(
            read_transaction=lambda fn: _noop_read(fn)
        )
        self.write_queue = SimpleNamespace()

    @property
    def method_count(self) -> int:
        return self.dispatcher.method_count


async def _noop_read(fn):
    return await fn(None)


@pytest.mark.asyncio
class TestProfileCall:
    async def test_create_draft_defaults(self) -> None:
        with patch.object(rpc.profile_service, "create_draft", new=AsyncMock(return_value={"id": "p1"})) as m:
            result = await rpc._profile_call(
                None,
                "create_draft",
                {"company_id": C1, "name": "Draft"},
            )
        assert result == {"id": "p1"}
        m.assert_awaited_once()
        _, company_id = m.await_args.args
        kwargs = m.await_args.kwargs
        assert company_id == C1
        assert kwargs["agent_cli"] == ""
        assert kwargs["api_model"] == ""
        assert kwargs["base_profile"] == {}
        assert kwargs["credential_ref"] == ""
        assert kwargs["provider_release_id"] == ""
        assert kwargs["model_binding_id"] == ""
        assert kwargs["provider_protocol"] == ""

    async def test_update_draft_defaults(self) -> None:
        with patch.object(rpc.profile_service, "update_draft", new=AsyncMock(return_value={"id": "p1"})) as m:
            await rpc._profile_call(None, "update_draft", {"company_id": C1})
        kwargs = m.await_args.kwargs
        assert kwargs["agent_cli"] == ""
        assert kwargs["api_model"] == ""


@pytest.mark.asyncio
class TestTaskCall:
    async def test_reason_defaults(self) -> None:
        for method in ("request_plan_revision", "reject_plan", "cancel_task"):
            with patch.object(rpc.task_service, method, new=AsyncMock(return_value={"ok": True})) as m:
                await rpc._task_call(None, method, {"company_id": C1, "task_id": T1})
            kwargs = m.await_args.kwargs
            assert kwargs["reason"] == ""

    async def test_replace_employee_renames(self) -> None:
        with patch.object(rpc.task_service, "replace_employee", new=AsyncMock(return_value={"ok": True})) as m:
            await rpc._task_call(
                None,
                "replace_employee",
                {"company_id": C1, "task_id": T1, "current_employee_id": "e1", "new_employee_id": "e2"},
            )
        kwargs = m.await_args.kwargs
        assert kwargs["old_employee_id"] == "e1"
        assert kwargs["new_employee_id"] == "e2"
        assert "current_employee_id" not in kwargs


@pytest.mark.asyncio
class TestRuntimeCall:
    async def test_probe_provider(self) -> None:
        with patch.object(rpc.runtime_service, "probe_provider", new=AsyncMock(return_value={"ok": True})) as m:
            result = await rpc._runtime_call(None, "probe_provider", {"company_id": C1, "provider_type": "openai"})
        assert result == {"ok": True}
        m.assert_awaited_once_with(None, C1, "openai")

    async def test_regular_method(self) -> None:
        with patch.object(rpc.runtime_service, "list_available_models", new=AsyncMock(return_value={"models": []})) as m:
            result = await rpc._runtime_call(None, "list_available_models", {"company_id": C1, "limit": 5})
        assert result == {"models": []}
        m.assert_awaited_once_with(None, C1, limit=5)


@pytest.mark.asyncio
class TestConfirmAndDispatch:
    async def test_builds_command_and_dispatches(self) -> None:
        params = {
            "company_id": C1,
            "company_task_id": T1,
            "plan_artifact_id": T1,
            "plan_sha256": "a" * 64,
            "expected_version": 3,
            "workspace_grant_ids": [T1],
        }
        with patch.object(rpc, "confirm_and_dispatch", new=AsyncMock(return_value={"status": "dispatched"})) as m:
            result = await rpc._confirm_plan_and_dispatch(None, params)
        assert result == {"status": "dispatched"}
        command = m.await_args.args[1]
        assert command.company_id == C1
        assert command.company_task_id == T1
        assert command.expected_version == 3
        assert command.workspace_grant_ids == (T1,)


@pytest.mark.asyncio
class TestRuntimeSql:
    async def test_runtime_stop_cancels_runs(self) -> None:
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[{"id": "r1"}, {"id": "r2"}])
        db = AsyncMock()
        db.execute = AsyncMock(return_value=cursor)
        with patch.object(rpc.runtime_service, "cancel_run", new=AsyncMock(return_value=None)) as m:
            result = await rpc._runtime_stop(db, {"company_id": C1, "agent_id": "e1"})
        assert result == {"stopped": True, "count": 2}
        assert m.await_count == 2

    async def test_runtime_run(self) -> None:
        params = {
            "company_id": C1,
            "agent_id": "e1",
            "company_task_id": T1,
            "conversation_id": T1,
            "availability_snapshot_id": T1,
            "execution_snapshot_id": T1,
            "model_id": "m1",
            "run_purpose": "execute",
            "adapter_type": "openai",
            "message": "go",
            "work_item_id": T1,
            "department_task_id": T1,
            "employee_task_id": T1,
        }
        with patch("ibreeze.runtime.gateway.start", new=AsyncMock(return_value={"run_id": "r1"})) as m:
            result = await rpc._runtime_run(None, params)
        assert result == {"run_id": "r1"}
        _, kwargs = m.await_args.args, m.await_args.kwargs
        assert kwargs["run_purpose"] == "execute"
        assert kwargs["adapter_type"] == "openai"


@pytest.mark.asyncio
class TestVerifyRegistryFallback:
    async def test_returns_count_without_registry_file(self) -> None:
        dispatcher = Dispatcher()
        with patch.object(Path, "exists", return_value=False):
            count = rpc.verify_sidecar_registry(dispatcher)
        assert count == dispatcher.method_count


@pytest.mark.asyncio
class TestCatalogErrors:
    def _manifest(self, tmp_path, resources, **extra) -> _FakeLifecycle:
        (tmp_path / "catalog-manifest.v1.json").write_text(
            json.dumps({"release_id": "rel-1", "release_sequence": 1, "resources": resources, **extra}),
            encoding="utf-8",
        )
        return _FakeLifecycle(tmp_path / "p.db")

    async def test_manifest_rejects_bad_release_fields(self, tmp_path) -> None:
        for payload in ({"resources": [], "release_id": 5}, {"resources": [], "release_id": "r", "release_sequence": "x"}):
            (tmp_path / "catalog-manifest.v1.json").write_text(json.dumps(payload), encoding="utf-8")
            lc = _FakeLifecycle(tmp_path / "p.db")
            with pytest.raises(ValueError, match="CATALOG_INVALID"):
                rpc._catalog_manifest(lc)

    async def test_sync_rejects_non_dict_resource(self, tmp_path) -> None:
        lc = self._manifest(tmp_path, [42])
        db = AsyncMock()
        with pytest.raises(ValueError, match="CATALOG_INVALID"):
            await rpc._catalog_sync(lc, db)


@pytest.mark.asyncio
class TestBackupGaps:
    async def test_restore(self, tmp_path) -> None:
        lc = _FakeLifecycle(tmp_path / "p.db")
        with patch.object(
            rpc.backup_service, "restore_backup", new=AsyncMock(return_value={"restored_at": "t"})
        ) as m:
            result = await rpc._backup_restore(lc, None, {"backup_id": "b1"})
        assert result["restored_at"] == "t"
        m.assert_awaited_once()

    async def test_restore_non_dict_result(self, tmp_path) -> None:
        lc = _FakeLifecycle(tmp_path / "p.db")
        with patch.object(rpc.backup_service, "restore_backup", new=AsyncMock(return_value=None)):
            result = await rpc._backup_restore(lc, None, {"backup_id": "b1"})
        assert result["restored_at"]

    async def test_get_found_and_missing(self, tmp_path) -> None:
        lc = _FakeLifecycle(tmp_path / "p.db")
        rows = [{"id": "b1", "created_at": "t"}]
        with patch.object(rpc.backup_service, "list_backups", new=AsyncMock(return_value=rows)):
            found = await rpc._backup_get(lc, {"backup_id": "b1"})
            assert found["id"] == "b1"
            with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
                await rpc._backup_get(lc, {"backup_id": "nope"})


@pytest.mark.asyncio
class TestSqlHelpers:
    async def test_task_row(self) -> None:
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value={"id": T1, "company_id": C1})
        db = AsyncMock()
        db.execute = AsyncMock(return_value=cursor)
        row = await rpc._task_row(db, "company_tasks", T1, C1)
        assert row["id"] == T1
        db.execute = AsyncMock(return_value=AsyncMock(fetchone=AsyncMock(return_value=None)))
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await rpc._task_row(db, "company_tasks", T1, C1)

    async def test_employee_base_profile_dict(self) -> None:
        db = AsyncMock()
        await rpc._employee_base_profile(
            db,
            {"company_id": C1, "employee_id": "e1", "base_profile": {"base_profile_version_id": "p1"}},
        )
        sql, args = db.execute.await_args.args
        assert "base_profile_version_id" in sql
        assert args[0] == "p1"
        db.execute = AsyncMock()
        with pytest.raises(ValueError, match="VALIDATION_FAILED"):
            await rpc._employee_base_profile(db, {"company_id": C1, "employee_id": "e1"})

    async def test_review_get_found_and_missing(self) -> None:
        row = {"review_id": "r1", "assignment_id": T1, "reviewer_employee_id": "e1", "status": "submitted"}
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[row])
        db = AsyncMock()
        db.execute = AsyncMock(return_value=cursor)
        assert await rpc._review_get(db, {"review_id": "r1", "company_id": C1}) == row
        db.execute = AsyncMock(return_value=AsyncMock(fetchall=AsyncMock(return_value=[])))
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await rpc._review_get(db, {"review_id": "r1", "company_id": C1})
