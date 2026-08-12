from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ibreeze.events.outbox import EVENT_COMMAND_MAP, EVENT_TO_STATE_TRIGGER, OutboxWriter
from ibreeze.persistence.types import DomainEventRecord, OutboxRecord


@pytest.mark.asyncio
class TestOutboxWriter:
    async def test_enqueue_all_empty(self):
        writer = OutboxWriter()
        session = AsyncMock()
        session.connection = AsyncMock()
        await writer.enqueue_all(session, ())
        session.connection.execute.assert_not_called()

    async def test_enqueue_all_single(self):
        writer = OutboxWriter()
        session = AsyncMock()
        session.connection = AsyncMock()
        record = OutboxRecord(topic="test.topic", payload_json='{"key": "value"}', domain_event_id=uuid4())
        await writer.enqueue_all(session, (record,))
        session.connection.execute.assert_called_once()

    async def test_enqueue_all_multiple(self):
        writer = OutboxWriter()
        session = AsyncMock()
        session.connection = AsyncMock()
        records = (
            OutboxRecord(topic="t1", payload_json="{}", domain_event_id=uuid4()),
            OutboxRecord(topic="t2", payload_json="{}", domain_event_id=uuid4()),
        )
        await writer.enqueue_all(session, records)
        assert session.connection.execute.call_count == 2

    async def test_enqueue_from_events_empty(self):
        writer = OutboxWriter()
        session = AsyncMock()
        session.connection = AsyncMock()
        await writer.enqueue_from_events(session, (), "test.topic")
        session.connection.execute.assert_not_called()

    async def test_enqueue_from_events_single(self):
        writer = OutboxWriter()
        session = AsyncMock()
        session.connection = AsyncMock()
        event = DomainEventRecord(
            event_id="00000000-0000-0000-0000-000000000001",
            event_type="test",
            aggregate_type="employee",
            aggregate_id="00000000-0000-0000-0000-000000000002",
            aggregate_version=1,
            company_id=None,
            payload_json="{}",
            trace_id="trace-1",
        )
        await writer.enqueue_from_events(session, (event,), "test.topic")
        session.connection.execute.assert_called_once()


class TestEventConstants:
    def test_event_command_map(self):
        assert "review.submitted" in EVENT_COMMAND_MAP
        assert EVENT_COMMAND_MAP["employee_task.status_changed"] == "EvaluateDepartmentReadiness"

    def test_event_to_state_trigger(self):
        assert "review.issue_changed" in EVENT_TO_STATE_TRIGGER
        assert "closed" in EVENT_TO_STATE_TRIGGER["review.issue_changed"]
