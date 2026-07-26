"""Standard event system for Agent Runtime Gateway."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    TOOL_REQUESTED = "tool.requested"
    TOOL_APPROVED = "tool.approved"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    TOOL_DENIED = "tool.denied"
    MODEL_THINKING = "model.thinking"
    MODEL_OUTPUT = "model.output"
    MODEL_OUTPUT_DELTA = "model.output.delta"
    MODEL_OUTPUT_COMPACTED = "model.output.compacted"
    CHECKPOINT_CREATED = "checkpoint.created"
    VERIFICATION_PASSED = "verification.passed"
    VERIFICATION_FAILED = "verification.failed"
    PERMISSION_GRANTED = "permission.granted"
    PERMISSION_DENIED = "permission.denied"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    WORKSPACE_CHANGED = "workspace.changed"


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: str
    event_type: EventType
    sequence: int
    timestamp: str
    run_id: str
    company_id: str
    employee_id: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


class EventPublisher:
    """Publish events with sequence tracking and optional DB persistence."""

    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._sequences: dict[str, int] = {}
        self._subscribers: dict[EventType, list[Any]] = {}

    def publish(
        self,
        event_type: EventType,
        *,
        run_id: str,
        company_id: str,
        employee_id: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> EventEnvelope:
        key = f"{run_id}:{company_id}"
        seq = self._sequences.get(key, 0) + 1
        self._sequences[key] = seq

        envelope = EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            sequence=seq,
            timestamp=datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
            run_id=run_id,
            company_id=company_id,
            employee_id=employee_id,
            payload=payload,
            metadata=metadata or {},
        )

        for subscriber in self._subscribers.get(event_type, []):
            subscriber(envelope)

        return envelope

    async def persist(self, envelope: EventEnvelope) -> None:
        """Persist an event to the DB (agent_run_events table)."""
        if self._db is None:
            return
        await self._db.execute(
            """INSERT INTO agent_run_events
               (event_id, run_id, event_type, payload_json, sequence, trace_id, occurred_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                envelope.event_id,
                envelope.run_id,
                envelope.event_type,
                serialize_event(envelope),
                envelope.sequence,
                str(uuid.uuid4()),
                envelope.timestamp,
            ),
        )

    def subscribe(
        self,
        event_type: EventType,
        callback: Any,
    ) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def unsubscribe(
        self,
        event_type: EventType,
        callback: Any,
    ) -> None:
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                cb for cb in self._subscribers[event_type] if cb != callback
            ]

    def get_sequence(self, run_id: str, company_id: str) -> int:
        key = f"{run_id}:{company_id}"
        return self._sequences.get(key, 0)

    def replay(
        self,
        run_id: str,
        company_id: str,
        from_sequence: int = 0,
    ) -> list[EventEnvelope]:
        return []

    async def replay_from_db(
        self,
        run_id: str,
        company_id: str,
        from_sequence: int = 0,
    ) -> list[EventEnvelope]:
        if self._db is None:
            return []
        cursor = await self._db.execute(
            """SELECT event_id, event_type, payload_json, sequence, occurred_at
               FROM agent_run_events
               WHERE run_id=? AND sequence>?
               ORDER BY sequence ASC""",
            (run_id, from_sequence),
        )
        rows = await cursor.fetchall()
        result: list[EventEnvelope] = []
        for row in rows:
            payload_data = json.loads(row["payload_json"])
            envelope = EventEnvelope(
                event_id=row["event_id"],
                event_type=EventType(row["event_type"]),
                sequence=row["sequence"],
                timestamp=row["occurred_at"],
                run_id=run_id,
                company_id=company_id,
                employee_id="",
                payload=payload_data if isinstance(payload_data, dict) else {},
                metadata={},
            )
            result.append(envelope)
        return result


def serialize_event(envelope: EventEnvelope) -> str:
    """Serialize an event envelope to JSON."""
    return json.dumps(
        {
            "event_id": envelope.event_id,
            "event_type": envelope.event_type,
            "sequence": envelope.sequence,
            "timestamp": envelope.timestamp,
            "run_id": envelope.run_id,
            "company_id": envelope.company_id,
            "employee_id": envelope.employee_id,
            "payload": envelope.payload,
            "metadata": envelope.metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def deserialize_event(data: str) -> EventEnvelope:
    """Deserialize a JSON string to an event envelope."""
    obj = json.loads(data)
    return EventEnvelope(
        event_id=obj["event_id"],
        event_type=EventType(obj["event_type"]),
        sequence=obj["sequence"],
        timestamp=obj["timestamp"],
        run_id=obj["run_id"],
        company_id=obj["company_id"],
        employee_id=obj["employee_id"],
        payload=obj["payload"],
        metadata=obj.get("metadata", {}),
    )
