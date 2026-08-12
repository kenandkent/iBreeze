"""Cover the module-level command-builders and remaining lifecycle branches.

``_build_command`` / ``_handler`` / ``_submit_handler`` / ``_internal_review_handler``
are the pieces that adapt public and internal commands to their handlers; the
``register_public_handlers`` tests stub them away, so they get direct coverage
here.  Also covers property returns, heartbeat-loop handling and the internal
command edge branches that the decision-tree suite does not reach.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest

from ibreeze.application.lifecycle import (
    ApplicationLifecycle,
    _build_command,
    _dict_to_uuid,
    _handler,
    _internal_review_handler,
    _submit_handler,
)
from ibreeze.domain.review.commands import ReviewIssueInput, SubmitReview
from ibreeze.domain.tasks.commands import AcceptEmployeeTask

C1 = "00000000-0000-0000-0000-000000000001"
T1 = "00000000-0000-0000-0000-000000000002"


class TestDictToUuid:
    def test_string_converts(self) -> None:
        assert _dict_to_uuid(C1) == UUID(C1)

    def test_uuid_passes_through(self) -> None:
        value = UUID(C1)
        assert _dict_to_uuid(value) is value


class TestBuildCommand:
    def test_uuid_fields_converted(self) -> None:
        command = _build_command(
            AcceptEmployeeTask,
            {"company_id": C1, "task_id": T1, "expected_version": 3},
        )
        assert isinstance(command, AcceptEmployeeTask)
        assert command.company_id == UUID(C1)
        assert command.task_id == UUID(T1)
        assert command.expected_version == 3

    def test_none_values_skipped(self) -> None:
        from dataclasses import dataclass, field

        @dataclass
        class _OptionalTask:
            company_id: UUID
            note: str = field(default_factory=str)

        command = _build_command(_OptionalTask, {"company_id": C1, "note": None})
        assert command.company_id == UUID(C1)
        assert command.note == ""  # None was skipped, default applied

    def test_review_issue_tuple_built(self) -> None:
        params = {
            "company_id": C1,
            "assignment_id": T1,
            "reviewer_run_id": T1,
            "reviewed_artifact_id": T1,
            "reviewed_sha256": "a" * 64,
            "report_artifact_id": T1,
            "verdict": "pass",
            "expected_assignment_version": 1,
            "issues": [
                {
                    "client_issue_id": T1,
                    "severity": "high",
                    "category": "functional",
                    "description": "d",
                    "expected": "e",
                    "actual": "a",
                    "evidence_refs": [T1, T1],
                    "suggested_fix": "fix",
                }
            ],
        }
        command = _build_command(SubmitReview, params)
        assert len(command.issues) == 1
        issue = command.issues[0]
        assert isinstance(issue, ReviewIssueInput)
        assert issue.client_issue_id == UUID(T1)
        assert issue.evidence_refs == (UUID(T1), UUID(T1))
        assert issue.assignee_employee_id is None

    def test_review_issue_with_assignee(self) -> None:
        params = {
            "company_id": C1,
            "assignment_id": T1,
            "reviewer_run_id": T1,
            "reviewed_artifact_id": T1,
            "reviewed_sha256": "a" * 64,
            "report_artifact_id": T1,
            "verdict": "needs_changes",
            "expected_assignment_version": 1,
            "issues": [
                {
                    "client_issue_id": T1,
                    "severity": "low",
                    "category": "documentation",
                    "description": "d",
                    "expected": "e",
                    "actual": "a",
                    "evidence_refs": [],
                    "suggested_fix": "fix",
                    "assignee_employee_id": C1,
                }
            ],
        }
        command = _build_command(SubmitReview, params)
        assert command.issues[0].assignee_employee_id == UUID(C1)


_SUBMIT_PARAMS = {
    "company_id": C1,
    "assignment_id": T1,
    "reviewer_run_id": T1,
    "reviewed_artifact_id": T1,
    "reviewed_sha256": "a" * 64,
    "report_artifact_id": T1,
    "verdict": "pass",
    "expected_assignment_version": 1,
    "issues": [],
}


class TestHandlerAdapter:
    @pytest.mark.asyncio
    async def test_handler_without_write_queue_calls_directly(self) -> None:
        handler = AsyncMock()
        handler.handle = AsyncMock(return_value={"ok": True})
        wrapped = _handler(handler, AcceptEmployeeTask)
        result = await wrapped({"company_id": C1, "task_id": T1, "expected_version": 1}, "session")
        handler.handle.assert_awaited_once()
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_handler_with_write_queue_submits(self) -> None:
        handler = AsyncMock()
        wq = AsyncMock()
        wq.submit = AsyncMock(return_value={"queued": True})
        wrapped = _handler(handler, AcceptEmployeeTask, write_queue=wq)
        result = await wrapped({"company_id": C1, "task_id": T1, "expected_version": 1}, Mock(trace_id=uuid4(), deadline_at=None))
        wq.submit.assert_awaited_once()
        assert result == {"queued": True}

    @pytest.mark.asyncio
    async def test_submit_handler_direct(self) -> None:
        handler = AsyncMock()
        handler.handle = AsyncMock(return_value={"ok": True})
        wrapped = _submit_handler(handler)
        result = await wrapped(dict(_SUBMIT_PARAMS), "session")
        handler.handle.assert_awaited_once()
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_submit_handler_with_write_queue(self) -> None:
        handler = AsyncMock()
        wq = AsyncMock()
        wq.submit = AsyncMock(return_value={"queued": True})
        wrapped = _submit_handler(handler, write_queue=wq)
        result = await wrapped(dict(_SUBMIT_PARAMS), Mock(trace_id=uuid4(), deadline_at=None))
        wq.submit.assert_awaited_once()
        assert result == {"queued": True}


class TestInternalReviewHandler:
    @pytest.mark.asyncio
    async def test_raises_without_connection(self) -> None:
        handler = AsyncMock()
        wrapped = _internal_review_handler(handler, SubmitReview)
        with pytest.raises(RuntimeError, match="INTERNAL_WRITE_CONNECTION_REQUIRED"):
            await wrapped({}, None)

    @pytest.mark.asyncio
    async def test_dispatches_with_connection(self) -> None:
        handler = AsyncMock()
        handler.handle = AsyncMock(return_value={"ok": True})
        wrapped = _internal_review_handler(handler, SubmitReview)
        result = await wrapped(dict(_SUBMIT_PARAMS), AsyncMock())
        handler.handle.assert_awaited_once()
        assert result == {"ok": True}


class TestLifecycleRemainingBranches:
    @pytest.mark.asyncio
    async def test_properties_return_when_initialized(self) -> None:
        lc = ApplicationLifecycle(Path("/tmp/irrelevant.db"))
        lc._read_pool = Mock()
        lc._write_queue = Mock()
        lc._unit_of_work = Mock()
        lc._workers = Mock()
        assert lc.read_pool is lc._read_pool
        assert lc.write_queue is lc._write_queue
        assert lc.unit_of_work is lc._unit_of_work
        assert lc.workers is lc._workers

    @pytest.mark.asyncio
    async def test_stop_cancels_heartbeat(self) -> None:
        lc = ApplicationLifecycle(Path("/tmp/irrelevant.db"))
        heartbeat = asyncio.create_task(asyncio.sleep(30))
        lc._heartbeat_task = heartbeat
        lc._workers = AsyncMock()
        lc._write_queue = AsyncMock()
        lc._writer = AsyncMock()
        lc._read_pool = AsyncMock()
        lc._prepared = AsyncMock()
        await lc.stop()
        assert heartbeat.cancelled()

    @pytest.mark.asyncio
    async def test_handle_review_list_issues(self) -> None:
        lc = ApplicationLifecycle(Path("/tmp/irrelevant.db"))
        lc._read_pool = AsyncMock()
        lc._read_pool.query_all = AsyncMock(return_value=[{"issue_id": "i1", "severity": "high"}])
        result = await lc._handle_review_list_issues({"company_id": C1, "review_id": T1}, None)
        assert result == {"issues": [{"issue_id": "i1", "severity": "high"}]}

    @pytest.mark.asyncio
    async def test_handle_review_list_issues_validation(self) -> None:
        lc = ApplicationLifecycle(Path("/tmp/irrelevant.db"))
        with pytest.raises(ValueError, match="VALIDATION_FAILED"):
            await lc._handle_review_list_issues({"company_id": C1}, None)

    @pytest.mark.asyncio
    async def test_heartbeat_loop_breaks_on_cancel(self) -> None:
        lc = ApplicationLifecycle(Path("/tmp/irrelevant.db"))
        with patch(
            "ibreeze.application.lifecycle.asyncio.sleep",
            side_effect=[None, asyncio.CancelledError()],
        ):
            await lc._heartbeat_loop()

    @pytest.mark.asyncio
    async def test_heartbeat_loop_logs_other_errors(self) -> None:
        lc = ApplicationLifecycle(Path("/tmp/irrelevant.db"))
        with (
            patch(
                "ibreeze.application.lifecycle.asyncio.sleep",
                side_effect=[RuntimeError("boom"), asyncio.CancelledError()],
            ),
            patch("ibreeze.application.lifecycle.logger") as mock_logger,
        ):
            await lc._heartbeat_loop()
        mock_logger.exception.assert_called_once_with("heartbeat loop error")
