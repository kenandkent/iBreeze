"""ProviderAdapter 抽象基类与统一运行时契约。

对照设计方案 §11.1/§11.2：Agent Runtime 与 ProviderAdapter 是本方案自研契约。
任何 Provider 实现的 send() 都必须把底层原始输出翻译成统一 RuntimeEvent，
不允许把 provider 专有格式泄露给上层。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class RuntimeEvent:
    """统一运行时事件。"""
    company_id: str = ""
    department_id: str = ""
    employee_id: str = ""
    task_id: str = ""
    conversation_id: str = ""
    run_id: str = ""
    trace_id: str = ""
    event_type: str = ""
    payload: dict = field(default_factory=dict)


@dataclass
class AvailabilityStatus:
    available: bool
    reason: str = ""
    healthy: bool = True


@dataclass
class ProviderCapabilities:
    models: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)


@dataclass
class ProviderSession:
    """Provider 原生会话载体。"""
    session_id: str = ""
    native_session_id: str = ""
    company_id: str = ""
    provider_id: str = ""
    model: str = ""
    config: dict = field(default_factory=dict)


@dataclass
class UsageRecord:
    """一次 run 的用量结算事实（token 计数，供计价）。"""
    run_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    tool_call_count: int = 0


@dataclass
class HealthStatus:
    healthy: bool = True
    detail: dict = field(default_factory=dict)


class ProviderAdapter(ABC):
    """所有 Provider Driver 的统一契约。

    抽象方法（必须由 Driver 实现）：check_availability/capabilities/send/cancel/health_check。
    带默认实现的方法（Driver 可覆盖）：create_session/resume/collect_usage。
    """

    @abstractmethod
    async def check_availability(self) -> AvailabilityStatus: ...

    @abstractmethod
    async def capabilities(self) -> ProviderCapabilities: ...

    @abstractmethod
    async def send(
        self, session: Any, message: str, stream: bool = False
    ) -> AsyncIterator[RuntimeEvent] | dict: ...

    @abstractmethod
    async def cancel(self, run_id: str) -> bool: ...

    @abstractmethod
    async def health_check(self) -> dict: ...

    async def create_session(self, config: dict[str, Any]) -> ProviderSession:
        """为该 Provider 生成/绑定原生 session id 的载体。"""
        return ProviderSession(
            company_id=str(config.get("company_id", "")),
            provider_id=str(config.get("provider_id", "")),
            model=str(config.get("model", "")),
            config=dict(config),
        )

    async def resume(self, checkpoint: dict[str, Any]) -> ProviderSession:
        """从 checkpoint 恢复会话。"""
        return ProviderSession(
            session_id=str(checkpoint.get("session_id", "")),
            native_session_id=str(checkpoint.get("native_session_id", "")),
            company_id=str(checkpoint.get("company_id", "")),
            provider_id=str(checkpoint.get("provider_id", "")),
            model=str(checkpoint.get("model", "")),
        )

    async def collect_usage(self, run_id: str) -> UsageRecord:
        """收集一次 run 的用量（token 计数）。"""
        return UsageRecord(run_id=run_id)
