from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import aiosqlite


@dataclass
class WriteSession:
    connection: aiosqlite.Connection
    company_id: UUID | None = None

    async def execute(self, sql: str, parameters: tuple[object, ...] = ()) -> Any:
        """Expose the single writer connection to domain repositories.

        Domain handlers receive ``WriteSession`` rather than the raw
        connection.  Keeping this tiny forwarding method makes repository
        code transaction-aware while preserving the WriteQueue-owned
        BEGIN/COMMIT boundary.
        """
        return await self.connection.execute(sql, parameters)


@dataclass
class DomainEventRecord:
    event_id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    aggregate_version: int
    company_id: UUID | None
    payload_json: str
    trace_id: str

    def __getitem__(self, key: str) -> object:
        """Read-only mapping compatibility for diagnostics and fixtures."""
        if key in {"from_state", "to_state", "issue_id", "severity", "assignee_employee_id", "evidence_refs"}:
            import json

            payload = json.loads(self.payload_json)
            return payload[key]
        # Event records are persisted as text UUIDs and the generated event
        # contract exposes those values as JSON strings.  Keep the typed UUID
        # attributes for the persistence writer, but make the mapping view
        # contract-compatible for query/diagnostic consumers.
        if key in {"event_id", "aggregate_id", "company_id"}:
            value = getattr(self, key)
            return str(value) if value is not None else None
        try:
            return getattr(self, key)
        except AttributeError as exc:
            try:
                import json

                payload = json.loads(self.payload_json)
            except (TypeError, ValueError, json.JSONDecodeError) as decode_error:
                raise KeyError(key) from decode_error
            if key in payload:
                return payload[key]
            raise KeyError(key) from exc


@dataclass
class OutboxRecord:
    topic: str
    payload_json: str
    domain_event_id: UUID | None = None

    def __getitem__(self, key: str) -> object:
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc
