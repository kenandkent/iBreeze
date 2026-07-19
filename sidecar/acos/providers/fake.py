"""FakeProviderAdapter：可测桩，不调真实 CLI/API。

用于驱动 Runtime 骨架的契约测试与 provider.runtime.* RPC 的默认 driver。
真实 CLI/API Driver 在 P6-T3 之后按 ProviderAdapter 契约单独实现。
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from acos.providers.base import (
    AvailabilityStatus,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderSession,
    RuntimeEvent,
    UsageRecord,
)


class FakeProviderAdapter(ProviderAdapter):
    """行为确定、可断言的 Provider 测试替身。"""

    def __init__(
        self,
        provider_id: str = "fake",
        available: bool = True,
        models: list[str] | None = None,
    ) -> None:
        self.provider_id = provider_id
        self._available = available
        self._models = models or ["fake-model-1"]
        self.cancelled: list[str] = []

    async def check_availability(self) -> AvailabilityStatus:
        return AvailabilityStatus(
            available=self._available,
            reason="ok" if self._available else "unavailable",
            healthy=self._available,
        )

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(models=list(self._models), features=["chat", "streaming"])

    async def create_session(self, config: dict[str, Any]) -> ProviderSession:
        return ProviderSession(
            native_session_id=f"native-{config.get('model', 'fake-model-1')}",
            company_id=str(config.get("company_id", "")),
            provider_id=self.provider_id,
            model=str(config.get("model", "fake-model-1")),
            config=dict(config),
        )

    async def send(
        self, session: Any, message: str, stream: bool = False
    ) -> AsyncIterator[RuntimeEvent] | dict:
        async def _gen() -> AsyncIterator[RuntimeEvent]:
            yield RuntimeEvent(event_type="token", payload={"text": message[:1]})
            yield RuntimeEvent(event_type="message", payload={"content": f"echo:{message}"})
            yield RuntimeEvent(
                event_type="usage",
                payload={"input_tokens": len(message), "output_tokens": 8, "tool_call_count": 0},
            )

        return _gen()

    async def cancel(self, run_id: str) -> bool:
        self.cancelled.append(run_id)
        return True

    async def health_check(self) -> dict:
        return {"status": "ok" if self._available else "down"}

    async def collect_usage(self, run_id: str) -> UsageRecord:
        return UsageRecord(run_id=run_id, input_tokens=10, output_tokens=8, tool_call_count=0)
