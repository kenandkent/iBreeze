from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from uuid import uuid4

from ibreeze.persistence.types import DomainEventRecord, OutboxRecord, WriteSession

EVENT_COMMAND_MAP: MappingProxyType[str, str] = MappingProxyType(
    {
        "review.submitted": "EvaluateEmployeeAcceptance",
        "review.issue_changed": "EvaluateAffectedTask",
        "employee_task.status_changed": "EvaluateDepartmentReadiness",
        "department_task.status_changed": "EvaluateCompanyReadiness",
    }
)

EVENT_TO_STATE_TRIGGER: MappingProxyType[str, frozenset[str]] = MappingProxyType(
    {
        "review.issue_changed": frozenset({"closed"}),
        "employee_task.status_changed": frozenset({"accepted"}),
        "department_task.status_changed": frozenset({"completed"}),
    }
)


class OutboxWriter:
    async def enqueue_all(
        self,
        session: WriteSession,
        records: tuple[OutboxRecord, ...],
    ) -> None:
        for record in records:
            await session.connection.execute(
                """INSERT INTO outbox
                   (id, domain_event_id, topic, payload_json, status, attempts,
                    next_attempt_at, created_at)
                   VALUES (?, ?, ?, ?, 'pending', 0, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))""",
                (
                    str(uuid4()),
                    "",
                    record.topic,
                    record.payload_json,
                    datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ),
            )

    async def enqueue_from_events(
        self,
        session: WriteSession,
        events: tuple[DomainEventRecord, ...],
        topic: str,
    ) -> None:
        for event in events:
            await session.connection.execute(
                """INSERT INTO outbox
                   (id, domain_event_id, topic, payload_json, status, attempts,
                    next_attempt_at, created_at)
                   VALUES (?, ?, ?, ?, 'pending', 0, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))""",
                (
                    str(uuid4()),
                    str(event.event_id),
                    topic,
                    event.payload_json,
                    datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                ),
            )
