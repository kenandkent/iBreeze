from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from ibreeze.workers.analysis import AnalysisWorker, _now


class TestNowUtility:
    def test_now_returns_z_terminated_iso_format(self):
        result = _now()
        assert result.endswith("Z")
        assert "T" in result
        # Should be parseable back
        parsed = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None

    def test_now_no_plus_offset(self):
        result = _now()
        assert "+" not in result.rstrip("Z")


class TestAnalysisWorkerInit:
    def test_name(self):
        w = AnalysisWorker()
        assert w.name == "AnalysisWorker"

    def test_health_initial(self):
        w = AnalysisWorker()
        h = w.health()
        assert h.name == "AnalysisWorker"
        assert h.state == "stopped"

    def test_health_after_construction(self):
        w = AnalysisWorker()
        assert w._write_queue is None


class TestAnalysisWorkerWorkNoWriteQueue:
    async def test_sleeps_when_no_wq(self):
        w = AnalysisWorker()
        start = datetime.now(UTC)
        await w.work()
        elapsed = (datetime.now(UTC) - start).total_seconds()
        assert elapsed >= 0.9


class TestAnalysisWorkerWorkSuccess:
    @patch("ibreeze.workers.analysis.logger")
    async def test_submits_cleanup_task(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock(return_value=0)
        w = AnalysisWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()
        args, _ = wq.submit.await_args
        assert args[0] == "analysis.cleanup_leases"
        assert isinstance(args[1], UUID)
        assert args[1].int == 0

    @patch("ibreeze.workers.analysis.logger")
    async def test_logs_when_cleanup_count_positive(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock(return_value=3)
        w = AnalysisWorker(write_queue=wq)
        await w.work()
        mock_logger.info.assert_called_once_with("Cleaned up %d expired runtime leases", 3)

    @patch("ibreeze.workers.analysis.logger")
    async def test_does_not_log_when_cleanup_count_zero(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock(return_value=0)
        w = AnalysisWorker(write_queue=wq)
        await w.work()
        mock_logger.info.assert_not_called()

    @patch("ibreeze.workers.analysis.logger")
    async def test_inner_cleanup_empty_result(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[])
        conn.execute = AsyncMock(return_value=cursor)

        call_args = None

        async def submit_side_effect(*args, **_kwargs):
            nonlocal call_args
            call_args = args
            _, _, _, fn = args
            return await fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = AnalysisWorker(write_queue=wq)
        await w.work()
        assert call_args is not None
        assert call_args[0] == "analysis.cleanup_leases"
        mock_logger.info.assert_not_called()

    @patch("ibreeze.workers.analysis.logger")
    async def test_inner_cleanup_expired_rows(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(
            return_value=[
                {
                    "id": "lease-1",
                    "queue_id": "queue-1",
                    "job_id": "job-1",
                    "run_id": None,
                    "company_id": "c1",
                },
                {
                    "id": "lease-2",
                    "queue_id": "queue-2",
                    "job_id": "job-2",
                    "run_id": None,
                    "company_id": "c2",
                },
            ]
        )
        conn.execute = AsyncMock(return_value=cursor)

        async def submit_side_effect(*args, **_kwargs):
            _, _, _, fn = args
            return await fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = AnalysisWorker(write_queue=wq)
        await w.work()

        # Should update runtime_queue for each expired lease
        update_calls = [c for c in conn.execute.await_args_list if "UPDATE runtime_queue" in str(c.args)]
        assert len(update_calls) == 2

        delete_calls = [c for c in conn.execute.await_args_list if "DELETE FROM runtime_leases" in str(c.args)]
        assert len(delete_calls) == 2

        mock_logger.info.assert_called_once_with("Cleaned up %d expired runtime leases", 2)

    @patch("ibreeze.workers.analysis.logger")
    async def test_inner_cleanup_with_run_id_updates_agent_runs(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(
            return_value=[
                {
                    "id": "lease-1",
                    "queue_id": "queue-1",
                    "job_id": None,
                    "run_id": "run-1",
                    "company_id": "c1",
                }
            ]
        )
        conn.execute = AsyncMock(return_value=cursor)

        async def submit_side_effect(*args, **_kwargs):
            _, _, _, fn = args
            return await fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = AnalysisWorker(write_queue=wq)
        await w.work()

        agent_run_calls = [c for c in conn.execute.await_args_list if "UPDATE agent_runs" in str(c.args)]
        assert len(agent_run_calls) == 1
        sql, params = agent_run_calls[0].args
        assert "status='lost'" in str(sql)
        assert params[1] == "run-1"
        assert params[2] == "c1"


class TestAnalysisWorkerWorkException:
    @patch("ibreeze.workers.analysis.logger")
    async def test_logs_exception_on_failure(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=RuntimeError("db down"))
        w = AnalysisWorker(write_queue=wq)
        await w.work()
        mock_logger.exception.assert_called_once_with("AnalysisWorker cleanup failed")

    @patch("ibreeze.workers.analysis.logger")
    async def test_does_not_re_raise(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=RuntimeError("db down"))
        w = AnalysisWorker(write_queue=wq)
        try:
            await w.work()
        except Exception:
            pytest.fail("work() should not re-raise exceptions")
