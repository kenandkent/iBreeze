"""会话模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SessionThread:
    thread_id: str = ""
    company_id: str = ""
    employee_id: str = ""
    security_context_key: str = ""
    status: str = "active"
    primary_thread_id: Optional[str] = None
    last_checkpoint_offset: int = 0
    transcript_path: Optional[str] = None
    version: int = 1
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SessionTurn:
    turn_id: str = ""
    thread_id: str = ""
    company_id: str = ""
    employee_id: str = ""
    role: str = "user"
    content: str = ""
    security_context_key: str = ""
    status: str = "pending"
    version: int = 1
    created_at: str = ""
