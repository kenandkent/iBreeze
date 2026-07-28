from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import aiosqlite


@dataclass
class WriteSession:
    connection: aiosqlite.Connection
    company_id: UUID | None = None


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


@dataclass
class OutboxRecord:
    topic: str
    payload_json: str
