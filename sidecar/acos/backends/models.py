"""Backend 领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Backend:
    backend_id: str = ""
    company_id: str = ""
    name: str = ""
    backend_type: str = "local_process"
    status: str = "disabled"
    health_status: str = "unknown"
    capabilities: list[str] = field(default_factory=list)
    workspace_types: list[str] = field(default_factory=list)
    workspace_root: str = ""
    concurrency_limit: int = 1
    last_health_probe_at: Optional[str] = None
    version: int = 1


@dataclass
class BackendLease:
    lease_id: str = ""
    backend_id: str = ""
    company_id: str = ""
    run_id: Optional[str] = None
    session_turn_id: Optional[str] = None
    worker_pid: Optional[int] = None
    status: str = "active"
    version: int = 1


@dataclass
class BackendQueueEntry:
    entry_id: str = ""
    backend_id: str = ""
    company_id: str = ""
    run_id: Optional[str] = None
    session_turn_id: Optional[str] = None
    wait_reason: Optional[str] = None
    status: str = "waiting"
