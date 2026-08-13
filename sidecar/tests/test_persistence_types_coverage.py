"""Coverage-focused tests for ``ibreeze.persistence.types``.

Exercises ``WriteSession.execute`` forwarding, the ``DomainEventRecord``
mapping fallback (payload lookup and error branches), and ``OutboxRecord``
mapping compatibility.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from ibreeze.persistence.types import DomainEventRecord, OutboxRecord, WriteSession


def _event(payload_json: str) -> DomainEventRecord:
    return DomainEventRecord(
        event_id=UUID(int=1),
        event_type="employee.updated",
        aggregate_type="employee",
        aggregate_id=UUID(int=2),
        aggregate_version=3,
        company_id=UUID(int=4),
        payload_json=payload_json,
        trace_id="trace-1",
    )


@pytest.mark.asyncio
class TestWriteSession:
    async def test_execute_forwards_to_connection(self) -> None:
        conn = AsyncMock()
        session = WriteSession(connection=conn)
        await session.execute("SELECT 1", (1,))
        conn.execute.assert_awaited_once_with("SELECT 1", (1,))

    async def test_execute_forwards_default_params(self) -> None:
        conn = AsyncMock()
        session = WriteSession(connection=conn)
        await session.execute("SELECT 1")
        conn.execute.assert_awaited_once_with("SELECT 1", ())


class TestDomainEventRecordMapping:
    def test_unknown_key_looks_up_payload(self) -> None:
        event = _event('{"custom": 42}')
        assert event["custom"] == 42

    def test_unknown_key_absent_from_payload_raises_keyerror(self) -> None:
        event = _event('{"custom": 42}')
        with pytest.raises(KeyError, match="missing_key"):
            event["missing_key"]

    def test_invalid_payload_raises_keyerror(self) -> None:
        event = _event("{not valid json")
        with pytest.raises(KeyError):
            event["missing_key"]

    def test_nullable_id_maps_to_none(self) -> None:
        event = _event("{}")
        event.company_id = None
        assert event["company_id"] is None


class TestOutboxRecordMapping:
    def test_getitem_returns_attributes(self) -> None:
        record = OutboxRecord(topic="t", payload_json="{}", domain_event_id=None)
        assert record["topic"] == "t"
        assert record["payload_json"] == "{}"

    def test_getitem_missing_attribute_raises_keyerror(self) -> None:
        record = OutboxRecord(topic="t", payload_json="{}")
        with pytest.raises(KeyError, match="missing_key"):
            record["missing_key"]
