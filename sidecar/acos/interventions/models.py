"""人工干预项数据模型。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HumanIntervention:
    """人工干预项。"""

    intervention_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str = ""
    task_id: Optional[str] = None
    node_id: Optional[str] = None
    run_id: Optional[str] = None
    subtype: str = ""
    target_ref: str = ""
    status: str = "open"
    allowed_actions: list[str] = field(default_factory=list)
    resolution_ref: Optional[str] = None
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    trace_id: str = ""
    version: int = 1
