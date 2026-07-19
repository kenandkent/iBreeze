"""ProviderAdapter 抽象测试。"""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from acos.providers.base import (
    AvailabilityStatus,
    ProviderAdapter,
    ProviderCapabilities,
    RuntimeEvent,
)


class DummyProvider(ProviderAdapter):
    def __init__(self, available: bool = True) -> None:
        self._available = available

    async def check_availability(self) -> AvailabilityStatus:
        return AvailabilityStatus(available=self._available, reason="ok" if self._available else "down")

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            models=["gpt-4", "gpt-3.5-turbo"],
            features=["chat", "completion"],
        )

    async def send(
        self, session: Any, message: str, stream: bool = False
    ) -> AsyncIterator[RuntimeEvent] | dict:
        yield RuntimeEvent(
            event_type="message",
            payload={"content": "response"},
        )

    async def cancel(self, run_id: str) -> bool:
        return True

    async def health_check(self) -> dict:
        return {"status": "ok"}


def test_runtime_event_defaults() -> None:
    event = RuntimeEvent()
    assert event.company_id == ""
    assert event.event_type == ""
    assert event.payload == {}


def test_availability_status() -> None:
    status = AvailabilityStatus(available=True, reason="healthy", healthy=True)
    assert status.available is True
    assert status.healthy is True


def test_provider_capabilities() -> None:
    caps = ProviderCapabilities(models=["m1"], features=["f1"])
    assert caps.models == ["m1"]
    assert caps.features == ["f1"]


@pytest.mark.asyncio
async def test_dummy_provider_check_availability() -> None:
    provider = DummyProvider(available=True)
    status = await provider.check_availability()
    assert status.available is True


@pytest.mark.asyncio
async def test_dummy_provider_unavailable() -> None:
    provider = DummyProvider(available=False)
    status = await provider.check_availability()
    assert status.available is False
    assert status.reason == "down"


@pytest.mark.asyncio
async def test_dummy_provider_capabilities() -> None:
    provider = DummyProvider()
    caps = await provider.capabilities()
    assert "gpt-4" in caps.models
    assert "chat" in caps.features


@pytest.mark.asyncio
async def test_dummy_provider_send() -> None:
    provider = DummyProvider()
    events = []
    async for event in provider.send(None, "hello"):
        events.append(event)
    assert len(events) == 1
    assert events[0].event_type == "message"
    assert events[0].payload["content"] == "response"


@pytest.mark.asyncio
async def test_dummy_provider_cancel() -> None:
    provider = DummyProvider()
    result = await provider.cancel("run-1")
    assert result is True


@pytest.mark.asyncio
async def test_dummy_provider_health_check() -> None:
    provider = DummyProvider()
    health = await provider.health_check()
    assert health["status"] == "ok"


def test_abstract_methods_raise() -> None:
    with pytest.raises(TypeError):
        ProviderAdapter()  # type: ignore[abstract]
