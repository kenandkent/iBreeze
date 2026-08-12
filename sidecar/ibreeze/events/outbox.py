from __future__ import annotations

from datetime import UTC, datetime
from types import MappingProxyType
from uuid import uuid4

from ibreeze.persistence.types import DomainEventRecord, OutboxRecord, WriteSession

EVENT_COMMAND_MAP: MappingProxyType[str, str] = MappingProxyType(
    {
        "run.completed": "EvaluateEmployeeSubmission",
        "review.submitted": "EvaluateEmployeeAcceptance",
        "review.issue_changed": "EvaluateAffectedTask",
        "employee_task.status_changed": "EvaluateDepartmentReadiness",
        "employee_task.graph_advance": "AdvanceEmployeeTaskGraph",
        "department_task.status_changed": "EvaluateCompanyReadiness",
    }
)

EVENT_TO_STATE_TRIGGER: MappingProxyType[str, frozenset[str]] = MappingProxyType(
    {
        "run.completed": frozenset({"succeeded"}),
        "review.issue_changed": frozenset({"closed"}),
        "employee_task.status_changed": frozenset({"accepted"}),
        "employee_task.graph_advance": frozenset({"accepted"}),
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
            if record.domain_event_id is None:
                raise ValueError("OUTBOX_EVENT_REQUIRED")
            await session.connection.execute(
                """INSERT INTO outbox_events
                   (id, domain_event_id, topic, payload_json, status, attempts,
                    next_attempt_at, created_at)
                   VALUES (?, ?, ?, ?, 'pending', 0, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))""",
                (
                    str(uuid4()),
                    str(record.domain_event_id),
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
                """INSERT INTO outbox_events
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
