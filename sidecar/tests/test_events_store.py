from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ibreeze.events.store import DomainEventStore
from ibreeze.persistence.types import DomainEventRecord


@pytest.mark.asyncio
class TestDomainEventStore:
    async def test_append_all_empty(self):
        store = DomainEventStore()
        session = AsyncMock()
        session.connection = AsyncMock()
        await store.append_all(session, ())
        session.connection.execute.assert_not_called()

    async def test_append_all_single(self):
        store = DomainEventStore()
        session = AsyncMock()
        session.connection = AsyncMock()
        event = DomainEventRecord(
            event_id="00000000-0000-0000-0000-000000000001",
            event_type="employee.created",
            aggregate_type="employee",
            aggregate_id="00000000-0000-0000-0000-000000000002",
            aggregate_version=1,
            company_id="00000000-0000-0000-0000-000000000003",
            payload_json='{"name": "test"}',
            trace_id="trace-1",
        )
        await store.append_all(session, (event,))
        assert session.connection.execute.call_count == 1

    async def test_append_all_multiple(self):
        store = DomainEventStore()
        session = AsyncMock()
        session.connection = AsyncMock()
        events = (
            DomainEventRecord(
                event_id="00000000-0000-0000-0000-000000000001",
                event_type="e1",
                aggregate_type="employee",
                aggregate_id="00000000-0000-0000-0000-000000000002",
                aggregate_version=1,
                company_id="00000000-0000-0000-0000-000000000003",
                payload_json="{}",
                trace_id="t1",
            ),
            DomainEventRecord(
                event_id="00000000-0000-0000-0000-000000000004",
                event_type="e2",
                aggregate_type="department",
                aggregate_id="00000000-0000-0000-0000-000000000005",
                aggregate_version=1,
                company_id="00000000-0000-0000-0000-000000000003",
                payload_json="{}",
                trace_id="t2",
            ),
        )
        await store.append_all(session, events)
        assert session.connection.execute.call_count == 2

    async def test_append_all_without_company_id(self):
        store = DomainEventStore()
        session = AsyncMock()
        session.connection = AsyncMock()
        event = DomainEventRecord(
            event_id="00000000-0000-0000-0000-000000000001",
            event_type="test",
            aggregate_type="system",
            aggregate_id="00000000-0000-0000-0000-000000000002",
            aggregate_version=1,
            company_id=None,
            payload_json="{}",
            trace_id="trace-1",
        )
        await store.append_all(session, (event,))
        assert session.connection.execute.call_count == 1
        call_kwargs = session.connection.execute.call_args_list[0]
        assert call_kwargs[0][1][1] is None
