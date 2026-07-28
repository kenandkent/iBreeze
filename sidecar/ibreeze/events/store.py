from __future__ import annotations

from ibreeze.persistence.types import DomainEventRecord, WriteSession


class DomainEventStore:
    async def append_all(
        self,
        session: WriteSession,
        events: tuple[DomainEventRecord, ...],
    ) -> None:
        for event in events:
            company_id = str(event.company_id) if event.company_id else None
            await session.connection.execute(
                """INSERT INTO domain_event_store
                   (id, company_id, aggregate_type, aggregate_id, aggregate_version,
                    event_type, payload_json, trace_id, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))""",
                (
                    str(event.event_id),
                    company_id,
                    event.aggregate_type,
                    str(event.aggregate_id),
                    event.aggregate_version,
                    event.event_type,
                    event.payload_json,
                    event.trace_id,
                ),
            )
            await session.connection.execute(
                """INSERT INTO domain_events
                   (event_id, company_id, aggregate_type, aggregate_id, aggregate_version,
                    event_type, payload_json, trace_id, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))""",
                (
                    str(event.event_id),
                    company_id,
                    event.aggregate_type,
                    str(event.aggregate_id),
                    event.aggregate_version,
                    event.event_type,
                    event.payload_json,
                    event.trace_id,
                ),
            )
