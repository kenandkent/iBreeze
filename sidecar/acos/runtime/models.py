"""Runtime 数据模型。

RuntimeEvent 统一结构在 acos.providers.base 中定义（作为 Provider 契约的一部分），
此处 re-export 供 runtime 层统一引用，避免重复定义。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from acos.providers.base import RuntimeEvent  # noqa: F401  re-export

__all__ = ["RuntimeEvent", "RuntimeSession", "RuntimeRun"]


@dataclass
class RuntimeSession:
    session_id: str
    company_id: str
    provider_id: str
    model: str
    department_id: str = ""
    employee_id: str = ""
    native_session_id: str = ""
    status: str = "active"
    version: int = 1


@dataclass
class RuntimeRun:
    run_id: str
    session_id: str
    company_id: str
    task_id: str = ""
    conversation_id: str = ""
    trace_id: str = ""
    status: str = "running"
    pricing_version_id: str | None = None
    version: int = 1
    events: list = field(default_factory=list)
