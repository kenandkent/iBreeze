"""Cover events branches the main suite does not reach.

Targets the second-subscribe append path (``114->116``) and the full
``replay_from_db`` decision tree including the non-dict payload fallback.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

from ibreeze.events import EventPublisher, EventType


class TestSubscribe:
    def test_subscribe_second_callback_appends(self) -> None:
        publisher = EventPublisher()
        first = Mock()
        second = Mock()
        publisher.subscribe(EventType.RUN_STARTED, first)
        publisher.subscribe(EventType.RUN_STARTED, second)
        assert publisher._subscribers[EventType.RUN_STARTED] == [first, second]


class TestReplayFromDb:
    async def test_returns_empty_when_no_db(self) -> None:
        publisher = EventPublisher()
        assert await publisher.replay_from_db("r1", "c1", from_sequence=0) == []

    async def test_replays_dict_and_non_dict_payloads(self) -> None:
        db = AsyncMock()
        cursor = AsyncMock()
        cursor.fetchall = AsyncMock(
            return_value=[
                {
                    "event_id": "e1",
                    "event_type": "run.started",
                    "payload_json": '{"x": 1}',
                    "sequence": 1,
                    "occurred_at": "2026-01-01T00:00:00Z",
                },
                {
                    "event_id": "e2",
                    "event_type": "run.completed",
                    "payload_json": '"just-a-string"',
                    "sequence": 2,
                    "occurred_at": "2026-01-01T00:00:01Z",
                },
            ]
        )
        db.execute = AsyncMock(return_value=cursor)
        publisher = EventPublisher(db=db)
        result = await publisher.replay_from_db("r1", "c1", from_sequence=0)
        assert len(result) == 2
        assert result[0].event_id == "e1"
        assert result[0].event_type == EventType.RUN_STARTED
        assert result[0].sequence == 1
        assert result[0].run_id == "r1"
        assert result[0].company_id == "c1"
        assert result[0].employee_id == ""
        assert result[0].payload == {"x": 1}
        assert result[0].metadata == {}
        assert result[1].payload == {}
