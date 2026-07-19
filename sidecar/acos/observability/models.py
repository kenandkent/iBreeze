"""可观测性领域模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TaskReadModel:
    task_id: str = ""
    company_id: str = ""
    title: str = ""
    status: str = ""
    priority: int = 5
    assigned_employee_id: Optional[str] = None
    assigned_backend_id: Optional[str] = None
    progress_pct: float = 0.0


@dataclass
class DashboardMetric:
    metric_id: str = ""
    company_id: str = ""
    metric_type: str = ""
    metric_name: str = ""
    metric_value: float = 0.0
    period_start: str = ""
    period_end: str = ""
