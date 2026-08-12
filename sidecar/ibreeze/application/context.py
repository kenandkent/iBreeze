from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CommandContext:
    trace_id: UUID
    ipc_session_id: UUID
    window_session_id: UUID | None
    idempotency_key: str | None
    deadline_at: datetime | None = None
    company_scope: UUID | None = None
