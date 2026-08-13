"""Loopback-only fake Provider used by routing acceptance tests.

The fake never accepts credentials and deliberately exposes only bounded
scenario names.  It is an in-process stand-in for the TLS loopback service;
the Rust HTTP broker contract tests remain responsible for wire-level checks.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ibreeze.runtime.model_loop import ModelTurn, ToolCall
from ibreeze.runtime.transport import ProviderRequestError


@dataclass
class FakeProvider:
    scenario: str = "ok_single"
    calls: int = 0
    received_tool_names: list[tuple[str, ...]] = field(default_factory=list)

    async def complete(self, *, tool_names: tuple[str, ...] = ()) -> ModelTurn:
        self.calls += 1
        self.received_tool_names.append(tool_names)
        if self.scenario == "rate_limited_then_ok" and self.calls == 1:
            raise ProviderRequestError(kind="RATE_LIMITED", retry_after_ms=0, safe_message="rate limited")
        if self.scenario == "overloaded":
            raise ProviderRequestError(kind="PROVIDER_OVERLOADED", safe_message="overloaded")
        if self.scenario == "timeout":
            await asyncio.sleep(3600)
        if self.scenario == "invalid_json":
            raise ProviderRequestError(kind="INVALID_RESPONSE", safe_message="invalid provider response")
        if self.scenario == "context_overflow":
            raise ProviderRequestError(kind="CONTEXT_OVERFLOW", safe_message="context overflow")
        if self.scenario == "auth_invalid":
            raise ProviderRequestError(kind="AUTH_INVALID", safe_message="credential rejected")
        if self.scenario == "stream_then_fail":
            raise ProviderRequestError(kind="TRANSPORT_TRANSIENT", safe_message="stream interrupted", visible_content=True)
        if self.scenario == "ok_tool_call":
            return ModelTurn(content="", tool_calls=(ToolCall(id="call-1", name="workspace.read", arguments={}),))
        return ModelTurn(content=f"fake-provider:{self.scenario}")
