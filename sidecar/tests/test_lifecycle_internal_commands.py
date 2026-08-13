"""Cover ``ApplicationLifecycle._evaluate_internal_command`` decision tree.

The Outbox worker routes every internal command through this one method; a
missing branch leaves a persisted event undelivered.  Each test drives one
command with a scripted connection so the resolution queries (agent_runs,
employee_tasks, review assignments) return exactly what the branch expects.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ibreeze.application.lifecycle import ApplicationLifecycle


class TestEvaluateInternalCommand:
    def _handlers(self) -> None:
        """Install AsyncMock completion handlers on a fresh lifecycle."""
        self.lc = ApplicationLifecycle(Path("/tmp/irrelevant.db"))
        self.lc._writer = AsyncMock()  # ``db = connection or self.writer``
        self.lc._employee_start_handler = AsyncMock()
        self.lc._employee_submit_handler = AsyncMock()
        self.lc._employee_accept_handler = AsyncMock()
        self.lc._department_complete_handler = AsyncMock()
        self.lc._company_complete_handler = AsyncMock()

    def _conn(self, *, run_row=None, task_row=None, dept_row=None, company_row=None, assignment_row=None, issue_row=None) -> AsyncMock:
        conn = AsyncMock()

        async def fake_execute(sql, _params=()):
            text = str(sql)
            if "FROM agent_runs" in text:
                return self._cursor(run_row)
            if "JOIN company_tasks" in text:
                return self._cursor(company_row)
            # The issue SQL also joins review_assignments, so check it first.
            if "FROM review_issues" in text:
                return self._cursor(issue_row)
            if "review_assignments" in text:
                return self._cursor(assignment_row)
            if "JOIN department_tasks" in text:
                return self._cursor(dept_row)
            return self._cursor(task_row)

        conn.execute = AsyncMock(side_effect=fake_execute)
        return conn

    @staticmethod
    def _cursor(row) -> AsyncMock:
        cursor = AsyncMock()
        cursor.fetchone = AsyncMock(return_value=row)
        return cursor

    @pytest.mark.asyncio
    async def test_raises_when_handlers_unavailable(self) -> None:
        self.lc = ApplicationLifecycle(Path("/tmp/irrelevant.db"))
        with pytest.raises(RuntimeError, match="INTERNAL_COMMAND_HANDLERS_UNAVAILABLE"):
            await self.lc._evaluate_internal_command("StartEmployeeTask", {"company_id": "00000000-0000-0000-0000-000000000001"})

    @pytest.mark.asyncio
    async def test_ignored_when_company_id_missing(self) -> None:
        self._handlers()
        result = await self.lc._evaluate_internal_command("Anything", {})
        assert result == {"status": "ignored", "reason": "company_id_missing"}

    @pytest.mark.asyncio
    async def test_start_employee_task_success(self) -> None:
        self._handlers()
        self.lc._employee_start_handler.handle = AsyncMock(return_value={"ok": True})
        result = await self.lc._evaluate_internal_command(
            "StartEmployeeTask",
            {
                "company_id": "00000000-0000-0000-0000-000000000001",
                "aggregate_id": "00000000-0000-0000-0000-000000000002",
                "expected_version": 2,
            },
        )
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_start_employee_task_ignored_missing_fields(self) -> None:
        self._handlers()
        result = await self.lc._evaluate_internal_command(
            "StartEmployeeTask",
            {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000002"},
        )
        assert result == {"status": "ignored", "reason": "task_id_or_version_missing"}

    @pytest.mark.asyncio
    async def test_evaluate_employee_submission_success(self) -> None:
        self._handlers()
        self.lc._employee_submit_handler.handle = AsyncMock(return_value={"ok": True})
        conn = self._conn(
            run_row={
                "employee_task_id": "00000000-0000-0000-0000-000000000003",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "status": "succeeded",
            },
            task_row={"version": 1},
        )
        result = await self.lc._evaluate_internal_command(
            "EvaluateEmployeeSubmission",
            {"company_id": "00000000-0000-0000-0000-000000000001", "run_id": "00000000-0000-0000-0000-000000000008"},
            connection=conn,
        )
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_evaluate_employee_submission_ignored_when_run_missing(self) -> None:
        self._handlers()
        conn = self._conn(run_row=None)
        result = await self.lc._evaluate_internal_command(
            "EvaluateEmployeeSubmission",
            {"company_id": "00000000-0000-0000-0000-000000000001", "run_id": "00000000-0000-0000-0000-000000000008"},
            connection=conn,
        )
        assert result == {"status": "ignored", "reason": "run_not_successful_or_not_employee_task"}

    @pytest.mark.asyncio
    async def test_evaluate_employee_submission_ignored_run_not_succeeded(self) -> None:
        self._handlers()
        conn = self._conn(
            run_row={
                "employee_task_id": "00000000-0000-0000-0000-000000000003",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "status": "failed",
            },
            task_row={"version": 1},
        )
        result = await self.lc._evaluate_internal_command(
            "EvaluateEmployeeSubmission",
            {"company_id": "00000000-0000-0000-0000-000000000001", "run_id": "00000000-0000-0000-0000-000000000008"},
            connection=conn,
        )
        assert result == {"status": "ignored", "reason": "run_not_successful_or_not_employee_task"}

    @pytest.mark.asyncio
    async def test_evaluate_employee_submission_ignored_on_lock_conflict(self) -> None:
        self._handlers()
        self.lc._employee_submit_handler.handle = AsyncMock(side_effect=ValueError("OPTIMISTIC_LOCK_CONFLICT"))
        conn = self._conn(
            run_row={
                "employee_task_id": "00000000-0000-0000-0000-000000000003",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "status": "succeeded",
            },
            task_row={"version": 1},
        )
        result = await self.lc._evaluate_internal_command(
            "EvaluateEmployeeSubmission",
            {"company_id": "00000000-0000-0000-0000-000000000001", "run_id": "00000000-0000-0000-0000-000000000008"},
            connection=conn,
        )
        assert result == {"status": "ignored", "reason": "OPTIMISTIC_LOCK_CONFLICT"}

    @pytest.mark.asyncio
    async def test_evaluate_employee_submission_run_id_missing(self) -> None:
        self._handlers()
        conn = self._conn(run_row=None)
        result = await self.lc._evaluate_internal_command(
            "EvaluateEmployeeSubmission", {"company_id": "00000000-0000-0000-0000-000000000001"}, connection=conn
        )
        assert result == {"status": "ignored", "reason": "run_id_missing"}

    @pytest.mark.asyncio
    async def test_evaluate_employee_submission_employee_task_missing(self) -> None:
        self._handlers()
        conn = self._conn(
            run_row={
                "employee_task_id": "00000000-0000-0000-0000-000000000003",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "status": "succeeded",
            },
            task_row=None,
        )
        result = await self.lc._evaluate_internal_command(
            "EvaluateEmployeeSubmission",
            {"company_id": "00000000-0000-0000-0000-000000000001", "run_id": "00000000-0000-0000-0000-000000000008"},
            connection=conn,
        )
        assert result == {"status": "ignored", "reason": "employee_task_missing"}

    @pytest.mark.asyncio
    async def test_evaluate_employee_submission_re_raises_unknown_valueerror(self) -> None:
        self._handlers()
        self.lc._employee_submit_handler.handle = AsyncMock(side_effect=ValueError("SOMETHING_ELSE"))
        conn = self._conn(
            run_row={
                "employee_task_id": "00000000-0000-0000-0000-000000000003",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "status": "succeeded",
            },
            task_row={"version": 1},
        )
        with pytest.raises(ValueError, match="SOMETHING_ELSE"):
            await self.lc._evaluate_internal_command(
                "EvaluateEmployeeSubmission",
                {"company_id": "00000000-0000-0000-0000-000000000001", "run_id": "00000000-0000-0000-0000-000000000008"},
                connection=conn,
            )

    @pytest.mark.asyncio
    async def test_evaluate_company_readiness_re_raises_unknown_valueerror(self) -> None:
        self._handlers()
        self.lc._company_complete_handler.handle = AsyncMock(side_effect=ValueError("SOMETHING_ELSE"))
        conn = self._conn(
            company_row={"id": "00000000-0000-0000-0000-000000000005", "company_id": "00000000-0000-0000-0000-000000000001", "version": 1}
        )
        with pytest.raises(ValueError, match="SOMETHING_ELSE"):
            await self.lc._evaluate_internal_command(
                "EvaluateCompanyReadiness",
                {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000004"},
                connection=conn,
            )

    @pytest.mark.asyncio
    async def test_evaluate_department_readiness_re_raises_unknown_valueerror(self) -> None:
        self._handlers()
        self.lc._department_complete_handler.handle = AsyncMock(side_effect=ValueError("SOMETHING_ELSE"))
        conn = self._conn(
            dept_row={"id": "00000000-0000-0000-0000-000000000004", "company_id": "00000000-0000-0000-0000-000000000001", "version": 1}
        )
        with pytest.raises(ValueError, match="SOMETHING_ELSE"):
            await self.lc._evaluate_internal_command(
                "EvaluateDepartmentReadiness",
                {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000003"},
                connection=conn,
            )

    @pytest.mark.asyncio
    async def test_accept_via_assignment_resolution(self) -> None:
        self._handlers()
        self.lc._employee_accept_handler.handle = AsyncMock(return_value={"ok": True})
        conn = self._conn(
            assignment_row={"task_id": "00000000-0000-0000-0000-000000000003", "version": 1},
            task_row={"id": "00000000-0000-0000-0000-000000000003", "company_id": "00000000-0000-0000-0000-000000000001", "version": 1},
        )
        result = await self.lc._evaluate_internal_command(
            "AcceptEmployeeTask",
            {"company_id": "00000000-0000-0000-0000-000000000001", "assignment_id": "00000000-0000-0000-0000-000000000006"},
            connection=conn,
        )
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_accept_via_issue_resolution(self) -> None:
        self._handlers()
        self.lc._employee_accept_handler.handle = AsyncMock(return_value={"ok": True})
        conn = self._conn(
            assignment_row=None,
            issue_row={"task_id": "00000000-0000-0000-0000-000000000003", "version": 1},
            task_row={"id": "00000000-0000-0000-0000-000000000003", "company_id": "00000000-0000-0000-0000-000000000001", "version": 1},
        )
        result = await self.lc._evaluate_internal_command(
            "AcceptEmployeeTask",
            {"company_id": "00000000-0000-0000-0000-000000000001", "issue_id": "00000000-0000-0000-0000-000000000007"},
            connection=conn,
        )
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_ignored_when_task_id_missing(self) -> None:
        self._handlers()
        conn = self._conn()
        result = await self.lc._evaluate_internal_command(
            "AcceptEmployeeTask", {"company_id": "00000000-0000-0000-0000-000000000001"}, connection=conn
        )
        assert result == {"status": "ignored", "reason": "task_id_missing"}

    @pytest.mark.asyncio
    async def test_evaluate_company_readiness_success(self) -> None:
        self._handlers()
        self.lc._company_complete_handler.handle = AsyncMock(return_value={"ok": True})
        conn = self._conn(
            company_row={"id": "00000000-0000-0000-0000-000000000005", "company_id": "00000000-0000-0000-0000-000000000001", "version": 1}
        )
        result = await self.lc._evaluate_internal_command(
            "EvaluateCompanyReadiness",
            {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000004"},
            connection=conn,
        )
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_evaluate_company_readiness_blocked(self) -> None:
        self._handlers()
        self.lc._company_complete_handler.handle = AsyncMock(side_effect=ValueError("COMPLETION_GATE_BLOCKED:review"))
        conn = self._conn(
            company_row={"id": "00000000-0000-0000-0000-000000000005", "company_id": "00000000-0000-0000-0000-000000000001", "version": 1}
        )
        result = await self.lc._evaluate_internal_command(
            "EvaluateCompanyReadiness",
            {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000004"},
            connection=conn,
        )
        assert result == {"status": "blocked", "reason": "COMPLETION_GATE_BLOCKED:review"}

    @pytest.mark.asyncio
    async def test_evaluate_company_readiness_missing_task(self) -> None:
        self._handlers()
        conn = self._conn(company_row=None)
        result = await self.lc._evaluate_internal_command(
            "EvaluateCompanyReadiness",
            {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000004"},
            connection=conn,
        )
        assert result == {"status": "ignored", "reason": "company_task_missing"}

    @pytest.mark.asyncio
    async def test_evaluate_department_readiness_success(self) -> None:
        self._handlers()
        self.lc._department_complete_handler.handle = AsyncMock(return_value={"ok": True})
        conn = self._conn(
            dept_row={"id": "00000000-0000-0000-0000-000000000004", "company_id": "00000000-0000-0000-0000-000000000001", "version": 1}
        )
        result = await self.lc._evaluate_internal_command(
            "EvaluateDepartmentReadiness",
            {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000003"},
            connection=conn,
        )
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_evaluate_department_readiness_blocked(self) -> None:
        self._handlers()
        self.lc._department_complete_handler.handle = AsyncMock(side_effect=ValueError("COMPLETION_GATE_BLOCKED:issues"))
        conn = self._conn(
            dept_row={"id": "00000000-0000-0000-0000-000000000004", "company_id": "00000000-0000-0000-0000-000000000001", "version": 1}
        )
        result = await self.lc._evaluate_internal_command(
            "EvaluateDepartmentReadiness",
            {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000003"},
            connection=conn,
        )
        assert result == {"status": "blocked", "reason": "COMPLETION_GATE_BLOCKED:issues"}

    @pytest.mark.asyncio
    async def test_evaluate_department_readiness_missing_task(self) -> None:
        self._handlers()
        conn = self._conn(dept_row=None)
        result = await self.lc._evaluate_internal_command(
            "EvaluateDepartmentReadiness",
            {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000003"},
            connection=conn,
        )
        assert result == {"status": "ignored", "reason": "department_task_missing"}

    @pytest.mark.asyncio
    async def test_advance_employee_task_graph(self) -> None:
        self._handlers()
        with patch(
            "ibreeze.application.lifecycle.advance_employee_task_graph",
            new=AsyncMock(return_value={"dispatched": 1}),
        ) as m_advance:
            result = await self.lc._evaluate_internal_command(
                "AdvanceEmployeeTaskGraph",
                {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000003"},
            )
        m_advance.assert_awaited_once()
        assert result == {"dispatched": 1}

    @pytest.mark.asyncio
    async def test_default_accept_success(self) -> None:
        self._handlers()
        self.lc._employee_accept_handler.handle = AsyncMock(return_value={"ok": True})
        conn = self._conn(
            task_row={"id": "00000000-0000-0000-0000-000000000003", "company_id": "00000000-0000-0000-0000-000000000001", "version": 1}
        )
        result = await self.lc._evaluate_internal_command(
            "AcceptEmployeeTask",
            {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000003"},
            connection=conn,
        )
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_default_accept_blocked(self) -> None:
        self._handlers()
        self.lc._employee_accept_handler.handle = AsyncMock(side_effect=ValueError("COMPLETION_GATE_BLOCKED:gate"))
        conn = self._conn(
            task_row={"id": "00000000-0000-0000-0000-000000000003", "company_id": "00000000-0000-0000-0000-000000000001", "version": 1}
        )
        result = await self.lc._evaluate_internal_command(
            "AcceptEmployeeTask",
            {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000003"},
            connection=conn,
        )
        assert result == {"status": "blocked", "reason": "COMPLETION_GATE_BLOCKED:gate"}

    @pytest.mark.asyncio
    async def test_default_accept_missing_task(self) -> None:
        self._handlers()
        conn = self._conn(task_row=None)
        result = await self.lc._evaluate_internal_command(
            "AcceptEmployeeTask",
            {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000003"},
            connection=conn,
        )
        assert result == {"status": "ignored", "reason": "employee_task_missing"}

    @pytest.mark.asyncio
    async def test_default_accept_re_raises_unknown_valueerror(self) -> None:
        self._handlers()
        self.lc._employee_accept_handler.handle = AsyncMock(side_effect=ValueError("SOMETHING_ELSE"))
        conn = self._conn(
            task_row={"id": "00000000-0000-0000-0000-000000000003", "company_id": "00000000-0000-0000-0000-000000000001", "version": 1}
        )
        with pytest.raises(ValueError, match="SOMETHING_ELSE"):
            await self.lc._evaluate_internal_command(
                "AcceptEmployeeTask",
                {"company_id": "00000000-0000-0000-0000-000000000001", "aggregate_id": "00000000-0000-0000-0000-000000000003"},
                connection=conn,
            )
