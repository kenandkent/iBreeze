"""Cover ApplicationLifecycle branches the main suite does not reach.

Targets: the ``verify_sidecar_registry`` call inside ``start()`` when public
handlers are registered, the non-callable-submit and awaitable-result paths of
``_reconcile_startup_state``, the ``_internal_command_handler`` wrapper body,
and the ``492->494`` fall-through when assignment resolution returns no row.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibreeze.application.lifecycle import ApplicationLifecycle

C1 = "00000000-0000-0000-0000-000000000001"
C2 = "00000000-0000-0000-0000-000000000002"
C3 = "00000000-0000-0000-0000-000000000003"


def _handlers() -> ApplicationLifecycle:
    """Install AsyncMock completion handlers on a fresh lifecycle."""
    lc = ApplicationLifecycle(Path("/tmp/irrelevant.db"))
    lc._writer = AsyncMock()  # ``db = connection or self.writer``
    lc._employee_start_handler = AsyncMock()
    lc._employee_submit_handler = AsyncMock()
    lc._employee_accept_handler = AsyncMock()
    lc._department_complete_handler = AsyncMock()
    lc._company_complete_handler = AsyncMock()
    return lc


def _conn(*, assignment_row=None) -> AsyncMock:
    conn = AsyncMock()

    async def fake_execute(sql, _params=()):
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=assignment_row)
        return cursor

    conn.execute = AsyncMock(side_effect=fake_execute)
    return conn


class TestStartRegistryVerification:
    async def test_start_verifies_sidecar_registry_when_handlers_registered(self, tmp_path) -> None:
        lc = ApplicationLifecycle(tmp_path / "profile.db")
        with (
            patch("ibreeze.application.lifecycle.startup_config", return_value=SimpleNamespace(stage="test")),
            patch("ibreeze.application.lifecycle.prepare", new=AsyncMock()),
            patch("ibreeze.application.lifecycle.open_writer", new=AsyncMock()),
            patch("ibreeze.application.lifecycle.ReadPool.open", new=AsyncMock()),
            patch("ibreeze.application.lifecycle.WriteQueue", new=MagicMock()),
            patch("ibreeze.application.lifecycle.UnitOfWork", new=MagicMock()),
            patch("ibreeze.application.lifecycle.register_public_handlers", return_value=2),
            patch("ibreeze.application.lifecycle.verify_sidecar_registry", return_value=2) as m_verify,
            patch("ibreeze.application.lifecycle.WorkerSupervisor") as m_worker,
            patch.object(lc, "_ensure_profile_identity", new=AsyncMock()),
            patch.object(lc, "_reconcile_startup_state", new=AsyncMock()),
            patch.object(lc, "_init_review_completion_handlers", new=AsyncMock()),
        ):
            m_worker.return_value.start = AsyncMock()
            await lc.start()
        m_verify.assert_called_once_with(lc.dispatcher)
        lc._heartbeat_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await lc._heartbeat_task


class TestReconcileStartupState:
    async def test_returns_when_submit_not_callable(self) -> None:
        lc = ApplicationLifecycle(Path("/tmp/irrelevant.db"))
        lc._write_queue = object()  # no ``submit`` attribute at all
        await lc._reconcile_startup_state()  # must return without raising

    async def test_awaits_result_when_submit_returns_awaitable(self) -> None:
        lc = ApplicationLifecycle(Path("/tmp/irrelevant.db"))
        lc._write_queue = MagicMock()
        lc._write_queue.submit = AsyncMock(return_value="recovery-ok")
        await lc._reconcile_startup_state()
        lc._write_queue.submit.assert_awaited_once()


class TestInternalCommandHandlerWrapper:
    async def test_wrapper_delegates_to_evaluate(self) -> None:
        lc = _handlers()
        handler = lc._internal_command_handler("StartEmployeeTask")
        result = await handler({"company_id": C1, "aggregate_id": C2})
        assert result == {"status": "ignored", "reason": "task_id_or_version_missing"}


class TestAssignmentResolutionFallThrough:
    async def test_row_none_falls_through_to_task_id_missing(self) -> None:
        lc = _handlers()
        conn = _conn(assignment_row=None)
        result = await lc._evaluate_internal_command(
            "AcceptEmployeeTask",
            {"company_id": C1, "assignment_id": C3},
            connection=conn,
        )
        assert result == {"status": "ignored", "reason": "task_id_missing"}
