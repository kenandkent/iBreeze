from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from ibreeze.workers.outbox import OutboxWorker


class TestOutboxWorkerInit:
    def test_name(self):
        w = OutboxWorker()
        assert w.name == "OutboxWorker"

    def test_health_initial(self):
        w = OutboxWorker()
        h = w.health()
        assert h.name == "OutboxWorker"
        assert h.state == "stopped"

    def test_has_outbox_writer(self):
        w = OutboxWorker()
        assert w._outbox is not None


class TestOutboxWorkerWorkNoWriteQueue:
    async def test_sleeps_when_no_wq(self):
        w = OutboxWorker()
        start = datetime.now(UTC)
        await w.work()
        elapsed = (datetime.now(UTC) - start).total_seconds()
        assert elapsed >= 0.9


class TestOutboxWorkerWorkSuccess:
    @patch("ibreeze.workers.outbox.logger")
    async def test_submits_deliver_task(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock(return_value=0)
        w = OutboxWorker(write_queue=wq)
        await w.work()
        wq.submit.assert_awaited_once()
        args, _ = wq.submit.await_args
        assert args[0] == "outbox.deliver"
        assert isinstance(args[1], UUID)
        assert args[1].int == 0

    @patch("ibreeze.workers.outbox.logger")
    async def test_logs_when_delivered_count_positive(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock(return_value=5)
        w = OutboxWorker(write_queue=wq)
        await w.work()
        mock_logger.info.assert_called_once_with(
            "OutboxWorker delivered %d events", 5
        )

    @patch("ibreeze.workers.outbox.logger")
    async def test_does_not_log_when_delivered_count_zero(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock(return_value=0)
        w = OutboxWorker(write_queue=wq)
        await w.work()
        mock_logger.info.assert_not_called()

    @patch("ibreeze.workers.outbox.logger")
    async def test_inner_deliver_empty_result(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[])
        conn.execute = AsyncMock(return_value=cursor)

        async def submit_side_effect(*args, **_kwargs):
            _, _, _, fn = args
            return await fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = OutboxWorker(write_queue=wq)
        await w.work()
        mock_logger.info.assert_not_called()

    @patch("ibreeze.workers.outbox.logger")
    async def test_inner_deliver_with_rows(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        row_1 = {
            "id": "evt-1",
            "topic": "company_task.status_changed",
            "payload_json": "{}",
            "domain_event_id": "domain-1",
            "attempts": 0,
        }
        row_2 = {
            "id": "evt-2",
            "topic": "company_task.status_changed",
            "payload_json": "{}",
            "domain_event_id": "domain-2",
            "attempts": 0,
        }
        cursor.fetchall = AsyncMock(return_value=[row_1, row_2])
        conn.execute = AsyncMock(return_value=cursor)
        conn.commit = AsyncMock()

        async def submit_side_effect(*args, **_kwargs):
            _, _, _, fn = args
            return await fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = OutboxWorker(write_queue=wq)
        await w.work()

        # Should update outbox for each row
        update_calls = [
            c for c in conn.execute.await_args_list
            if "UPDATE outbox" in str(c.args)
        ]
        assert len(update_calls) == 2

        # WriteQueue owns the transaction boundary; the worker never commits
        # the connection directly.
        conn.commit.assert_not_awaited()

        mock_logger.info.assert_called_once_with(
            "OutboxWorker delivered %d events", 2
        )

    @patch("ibreeze.workers.outbox.logger")
    async def test_inner_deliver_selects_pending_before_now(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(return_value=[])
        conn.execute = AsyncMock(return_value=cursor)

        captured_sql = None
        captured_params = None

        async def capture_execute(sql, params=None):
            nonlocal captured_sql, captured_params
            captured_sql = sql
            captured_params = params
            return cursor

        conn.execute = AsyncMock(side_effect=capture_execute)

        async def submit_side_effect(*args, **_kwargs):
            _, _, _, fn = args
            return await fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = OutboxWorker(write_queue=wq)
        await w.work()

        assert captured_sql is not None
        assert "status = 'pending'" in str(captured_sql)
        assert "next_attempt_at <= ?" in str(captured_sql)
        assert "LIMIT ?" in str(captured_sql)


class TestOutboxWorkerMalformedRows:
    """Cover the malformed / filtered / dispatch branches of the deliver loop."""

    @patch("ibreeze.workers.outbox.logger")
    async def test_marks_non_string_topic_row(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        row = {"id": "evt-x", "topic": 123, "payload_json": "{}", "attempts": 0}
        cursor.fetchall = AsyncMock(return_value=[row])
        conn.execute = AsyncMock(return_value=cursor)

        async def submit_side_effect(*args, **_kwargs):
            _, _, _, fn = args
            return await fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = OutboxWorker(write_queue=wq)
        await w.work()

        updates = [str(c.args) for c in conn.execute.await_args_list if "UPDATE outbox" in str(c.args)]
        assert any("MALFORMED_OUTBOX_ROW" in u for u in updates)
        mock_logger.info.assert_not_called()

    @patch("ibreeze.workers.outbox.logger")
    async def test_fails_unknown_topic(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        row = {"id": "evt-y", "topic": "foo.bar", "payload_json": "{}", "attempts": 0}
        cursor.fetchall = AsyncMock(return_value=[row])
        conn.execute = AsyncMock(return_value=cursor)

        async def submit_side_effect(*args, **_kwargs):
            _, _, _, fn = args
            return await fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = OutboxWorker(write_queue=wq)
        await w.work()

        updates = [str(c.args) for c in conn.execute.await_args_list if "UPDATE outbox" in str(c.args)]
        assert any("UNKNOWN_OUTBOX_TOPIC:foo.bar" in u for u in updates)

    @patch("ibreeze.workers.outbox.logger")
    async def test_fails_malformed_payload(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        row = {"id": "evt-z", "topic": "run.completed", "payload_json": "{bad", "attempts": 0}
        cursor.fetchall = AsyncMock(return_value=[row])
        conn.execute = AsyncMock(return_value=cursor)

        async def submit_side_effect(*args, **_kwargs):
            _, _, _, fn = args
            return await fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = OutboxWorker(write_queue=wq)
        await w.work()

        updates = [str(c.args) for c in conn.execute.await_args_list if "UPDATE outbox" in str(c.args)]
        assert any("MALFORMED_OUTBOX_PAYLOAD" in u for u in updates)

    @patch("ibreeze.workers.outbox.logger")
    async def test_skips_when_state_outside_trigger(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        row = {
            "id": "evt-a",
            "topic": "employee_task.status_changed",
            "payload_json": '{"to_state":"submitted"}',
            "attempts": 0,
        }
        cursor.fetchall = AsyncMock(return_value=[row])
        conn.execute = AsyncMock(return_value=cursor)

        async def submit_side_effect(*args, **_kwargs):
            _, _, _, fn = args
            return await fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = OutboxWorker(write_queue=wq)
        await w.work()

        updates = [str(c.args) for c in conn.execute.await_args_list if "UPDATE outbox" in str(c.args)]
        assert any("delivered" in u for u in updates)
        mock_logger.info.assert_called_once_with("OutboxWorker delivered %d events", 1)

    @patch("ibreeze.workers.outbox.logger")
    async def test_dispatches_internal_command(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        row = {
            "id": "evt-b",
            "topic": "employee_task.status_changed",
            "payload_json": '{"to_state":"accepted","company_id":"c1","aggregate_id":"t1","expected_version":1}',
            "attempts": 0,
        }
        cursor.fetchall = AsyncMock(return_value=[row])
        conn.execute = AsyncMock(return_value=cursor)
        bus = AsyncMock()

        async def submit_side_effect(*args, **_kwargs):
            _, _, _, fn = args
            return await fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = OutboxWorker(write_queue=wq, command_bus=bus)
        await w.work()

        bus.dispatch.assert_awaited_once()
        args, kwargs = bus.dispatch.await_args
        assert args[0] == "EvaluateDepartmentReadiness"
        assert kwargs["connection"] is conn
        updates = [str(c.args) for c in conn.execute.await_args_list if "UPDATE outbox" in str(c.args)]
        assert any("delivered" in u for u in updates)

    @patch("ibreeze.workers.outbox.logger")
    async def test_raises_when_bus_missing(self, mock_logger):
        conn = AsyncMock()
        cursor = AsyncMock()
        row = {
            "id": "evt-c",
            "topic": "employee_task.status_changed",
            "payload_json": '{"to_state":"accepted","company_id":"c1","aggregate_id":"t1","expected_version":1}',
            "attempts": 0,
        }
        cursor.fetchall = AsyncMock(return_value=[row])
        conn.execute = AsyncMock(return_value=cursor)

        async def submit_side_effect(*args, **_kwargs):
            _, _, _, fn = args
            return await fn(conn)

        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=submit_side_effect)
        w = OutboxWorker(write_queue=wq)
        await w.work()

        mock_logger.exception.assert_called_once_with("OutboxWorker deliver failed")


class TestOutboxWorkerWorkException:
    @patch("ibreeze.workers.outbox.logger")
    async def test_logs_exception_on_failure(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=RuntimeError("db down"))
        w = OutboxWorker(write_queue=wq)
        await w.work()
        mock_logger.exception.assert_called_once_with(
            "OutboxWorker deliver failed"
        )

    @patch("ibreeze.workers.outbox.logger")
    async def test_does_not_re_raise(self, mock_logger):
        wq = AsyncMock()
        wq.submit = AsyncMock(side_effect=RuntimeError("db down"))
        w = OutboxWorker(write_queue=wq)
        try:
            await w.work()
        except Exception:
            pytest.fail("work() should not re-raise exceptions")
