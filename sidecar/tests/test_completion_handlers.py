"""Cover the five completion-gate command handlers in isolation.

Each handler runs inside a mocked UnitOfWork whose ``execute`` invokes the
handler's command closure with a scripted session, so the success, gate-blocked,
optimistic-lock-conflict and resource-not-found branches are all exercised.
The gate objects are mocked so this file stays focused on handler mechanics;
the real SQL gates are covered by ``test_completion_gate.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from ibreeze.application.completion_handlers import (
    AcceptEmployeeTaskHandler,
    CompleteCompanyTaskHandler,
    CompleteDepartmentTaskHandler,
    StartEmployeeTaskHandler,
    SubmitEmployeeTaskHandler,
)
from ibreeze.domain.tasks.commands import (
    AcceptEmployeeTask,
    CompleteCompanyTask,
    CompleteDepartmentTask,
    StartEmployeeTask,
    SubmitEmployeeTask,
)

COMPANY_ID = UUID("00000000-0000-0000-0000-0000000000c1")
TASK_ID = UUID("00000000-0000-0000-0000-0000000000c2")


def _context() -> Mock:
    return Mock()


def _session(lock_row: dict | None = None, update_rowcount: int = 1) -> AsyncMock:
    """Scripted session: SELECT returns lock_row, UPDATE returns rowcount."""
    session = AsyncMock()

    async def execute(sql, *_params):
        cursor = AsyncMock()
        text = str(sql)
        if text.lstrip().startswith("SELECT"):
            cursor.fetchone = AsyncMock(return_value=lock_row)
            cursor.rowcount = None
        else:
            cursor.fetchone = AsyncMock(return_value=None)
            cursor.rowcount = update_rowcount
        return cursor

    session.execute = AsyncMock(side_effect=execute)
    return session


def _uow(session: AsyncMock) -> AsyncMock:
    uow = AsyncMock()

    async def execute(_context, _sha, command):
        return await command(session)

    uow.execute = AsyncMock(side_effect=execute)
    return uow


def _gate(blockers: tuple[str, ...] = ()) -> AsyncMock:
    gate = AsyncMock()
    gate.blockers = AsyncMock(return_value=blockers)
    return gate


@pytest.mark.asyncio
class TestAcceptEmployeeTaskHandler:
    async def test_success_emits_status_and_graph_advance_outbox(self) -> None:
        handler = AcceptEmployeeTaskHandler(
            _gate(()),
            _uow(_session(lock_row={"id": str(TASK_ID), "status": "running", "version": 1})),
        )
        result = await handler.handle(_context(), AcceptEmployeeTask(COMPANY_ID, TASK_ID, 1))
        assert result.response == {"id": str(TASK_ID), "status": "accepted"}
        topics = {record.topic for record in result.outbox}
        assert topics == {"employee_task.status_changed", "employee_task.graph_advance"}

    async def test_blocked_raises_gate_error(self) -> None:
        handler = AcceptEmployeeTaskHandler(
            _gate(("blocking_issue_open",)),
            _uow(_session(lock_row={"id": str(TASK_ID), "status": "running", "version": 1})),
        )
        with pytest.raises(ValueError, match="COMPLETION_GATE_BLOCKED:blocking_issue_open"):
            await handler.handle(_context(), AcceptEmployeeTask(COMPANY_ID, TASK_ID, 1))

    async def test_lock_conflict_raises(self) -> None:
        handler = AcceptEmployeeTaskHandler(
            _gate(()),
            _uow(_session(lock_row={"id": str(TASK_ID), "status": "running", "version": 1}, update_rowcount=0)),
        )
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await handler.handle(_context(), AcceptEmployeeTask(COMPANY_ID, TASK_ID, 1))

    async def test_task_not_found_raises(self) -> None:
        handler = AcceptEmployeeTaskHandler(_gate(()), _uow(_session(lock_row=None)))
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await handler.handle(_context(), AcceptEmployeeTask(COMPANY_ID, TASK_ID, 1))


@pytest.mark.asyncio
class TestStartEmployeeTaskHandler:
    async def test_success_assigned_to_running(self) -> None:
        handler = StartEmployeeTaskHandler(_uow(_session(lock_row={"id": str(TASK_ID), "status": "assigned", "version": 1})))
        result = await handler.handle(_context(), StartEmployeeTask(COMPANY_ID, TASK_ID, 1))
        assert result.response == {"id": str(TASK_ID), "status": "running"}

    async def test_already_running_is_idempotent(self) -> None:
        handler = StartEmployeeTaskHandler(_uow(_session(lock_row={"id": str(TASK_ID), "status": "running", "version": 1})))
        result = await handler.handle(_context(), StartEmployeeTask(COMPANY_ID, TASK_ID, 1))
        assert result.response == {"id": str(TASK_ID), "status": "running"}

    async def test_wrong_state_raises(self) -> None:
        handler = StartEmployeeTaskHandler(_uow(_session(lock_row={"id": str(TASK_ID), "status": "accepted", "version": 1})))
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await handler.handle(_context(), StartEmployeeTask(COMPANY_ID, TASK_ID, 1))

    async def test_version_mismatch_raises(self) -> None:
        handler = StartEmployeeTaskHandler(_uow(_session(lock_row={"id": str(TASK_ID), "status": "assigned", "version": 2})))
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await handler.handle(_context(), StartEmployeeTask(COMPANY_ID, TASK_ID, 1))

    async def test_update_conflict_raises(self) -> None:
        handler = StartEmployeeTaskHandler(
            _uow(_session(lock_row={"id": str(TASK_ID), "status": "assigned", "version": 1}, update_rowcount=0))
        )
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await handler.handle(_context(), StartEmployeeTask(COMPANY_ID, TASK_ID, 1))

    async def test_task_not_found_raises(self) -> None:
        handler = StartEmployeeTaskHandler(_uow(_session(lock_row=None)))
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await handler.handle(_context(), StartEmployeeTask(COMPANY_ID, TASK_ID, 1))


@pytest.mark.asyncio
class TestSubmitEmployeeTaskHandler:
    async def test_success_running_to_submitted(self) -> None:
        handler = SubmitEmployeeTaskHandler(_uow(_session(lock_row={"id": str(TASK_ID), "status": "running", "version": 1})))
        result = await handler.handle(_context(), SubmitEmployeeTask(COMPANY_ID, TASK_ID, uuid4(), 1))
        assert result.response == {"id": str(TASK_ID), "status": "submitted"}

    @pytest.mark.parametrize("state", ["submitted", "peer_reviewing", "accepted"])
    async def test_already_final_state_is_idempotent(self, state: str) -> None:
        handler = SubmitEmployeeTaskHandler(_uow(_session(lock_row={"id": str(TASK_ID), "status": state, "version": 1})))
        result = await handler.handle(_context(), SubmitEmployeeTask(COMPANY_ID, TASK_ID, uuid4(), 1))
        assert result.response == {"id": str(TASK_ID), "status": state}
        assert result.events == ()

    async def test_wrong_state_raises(self) -> None:
        handler = SubmitEmployeeTaskHandler(_uow(_session(lock_row={"id": str(TASK_ID), "status": "assigned", "version": 1})))
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await handler.handle(_context(), SubmitEmployeeTask(COMPANY_ID, TASK_ID, uuid4(), 1))

    async def test_version_mismatch_raises(self) -> None:
        handler = SubmitEmployeeTaskHandler(_uow(_session(lock_row={"id": str(TASK_ID), "status": "running", "version": 2})))
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await handler.handle(_context(), SubmitEmployeeTask(COMPANY_ID, TASK_ID, uuid4(), 1))

    async def test_update_conflict_raises(self) -> None:
        handler = SubmitEmployeeTaskHandler(
            _uow(_session(lock_row={"id": str(TASK_ID), "status": "running", "version": 1}, update_rowcount=0))
        )
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await handler.handle(_context(), SubmitEmployeeTask(COMPANY_ID, TASK_ID, uuid4(), 1))

    async def test_task_not_found_raises(self) -> None:
        handler = SubmitEmployeeTaskHandler(_uow(_session(lock_row=None)))
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await handler.handle(_context(), SubmitEmployeeTask(COMPANY_ID, TASK_ID, uuid4(), 1))


@pytest.mark.asyncio
class TestCompleteDepartmentTaskHandler:
    async def test_success(self) -> None:
        handler = CompleteDepartmentTaskHandler(
            _gate(()),
            _uow(_session(lock_row={"id": str(TASK_ID), "status": "executing", "version": 1, "company_task_id": str(uuid4())})),
        )
        result = await handler.handle(_context(), CompleteDepartmentTask(COMPANY_ID, TASK_ID, 1))
        assert result.response == {"id": str(TASK_ID), "status": "completed"}

    async def test_blocked_raises_gate_error(self) -> None:
        handler = CompleteDepartmentTaskHandler(
            _gate(("required_employee_tasks_not_accepted",)),
            _uow(_session(lock_row={"id": str(TASK_ID), "status": "executing", "version": 1, "company_task_id": str(uuid4())})),
        )
        with pytest.raises(ValueError, match="COMPLETION_GATE_BLOCKED"):
            await handler.handle(_context(), CompleteDepartmentTask(COMPANY_ID, TASK_ID, 1))

    async def test_lock_conflict_raises(self) -> None:
        handler = CompleteDepartmentTaskHandler(
            _gate(()),
            _uow(
                _session(
                    lock_row={"id": str(TASK_ID), "status": "executing", "version": 1, "company_task_id": str(uuid4())}, update_rowcount=0
                )
            ),
        )
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await handler.handle(_context(), CompleteDepartmentTask(COMPANY_ID, TASK_ID, 1))

    async def test_task_not_found_raises(self) -> None:
        handler = CompleteDepartmentTaskHandler(_gate(()), _uow(_session(lock_row=None)))
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await handler.handle(_context(), CompleteDepartmentTask(COMPANY_ID, TASK_ID, 1))


@pytest.mark.asyncio
class TestCompleteCompanyTaskHandler:
    async def test_success(self) -> None:
        handler = CompleteCompanyTaskHandler(
            _gate(()),
            _uow(_session(lock_row={"id": str(TASK_ID), "status": "executing", "version": 1})),
        )
        result = await handler.handle(_context(), CompleteCompanyTask(COMPANY_ID, TASK_ID, 1))
        assert result.response == {"id": str(TASK_ID), "status": "completed"}

    async def test_blocked_raises_gate_error(self) -> None:
        handler = CompleteCompanyTaskHandler(
            _gate(("final_report_missing",)),
            _uow(_session(lock_row={"id": str(TASK_ID), "status": "executing", "version": 1})),
        )
        with pytest.raises(ValueError, match="COMPLETION_GATE_BLOCKED:final_report_missing"):
            await handler.handle(_context(), CompleteCompanyTask(COMPANY_ID, TASK_ID, 1))

    async def test_lock_conflict_raises(self) -> None:
        handler = CompleteCompanyTaskHandler(
            _gate(()),
            _uow(_session(lock_row={"id": str(TASK_ID), "status": "executing", "version": 1}, update_rowcount=0)),
        )
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await handler.handle(_context(), CompleteCompanyTask(COMPANY_ID, TASK_ID, 1))

    async def test_task_not_found_raises(self) -> None:
        handler = CompleteCompanyTaskHandler(_gate(()), _uow(_session(lock_row=None)))
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await handler.handle(_context(), CompleteCompanyTask(COMPANY_ID, TASK_ID, 1))
