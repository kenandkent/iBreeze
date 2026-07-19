"""领域事件与 Outbox 投递的数据模型。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class DomainEvent:
    """不可变领域事件信封。"""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    event_type: str = ""
    aggregate_type: str = ""
    aggregate_id: str = ""
    aggregate_version: int = 0
    task_id: Optional[str] = None
    employee_id: Optional[str] = None
    run_id: Optional[str] = None
    occurred_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    trace_id: str = ""
    actor_type: str = ""  # local_owner | assignment | system
    actor_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboxDelivery:
    """Outbox 投递状态。"""

    delivery_id: str
    event_id: str
    consumer_name: str
    status: str = "pending"
    attempt_count: int = 0
    next_retry_at: Optional[str] = None
    last_error: Optional[str] = None
