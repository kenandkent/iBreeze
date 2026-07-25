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
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    TOOL_DENIED = "tool.denied"
    MODEL_THINKING = "model.thinking"
    MODEL_OUTPUT = "model.output"
    CHECKPOINT_CREATED = "checkpoint.created"
    VERIFICATION_PASSED = "verification.passed"
    VERIFICATION_FAILED = "verification.failed"
    PERMISSION_GRANTED = "permission.granted"
    PERMISSION_DENIED = "permission.denied"


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
    """Publish events with sequence tracking."""

    def __init__(self) -> None:
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
