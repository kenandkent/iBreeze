"""Model transport adapters using credential/egress broker via reverse RPC.

All provider network calls go through the Rust Credential/Egress Broker
via reverse RPC. The Sidecar must NOT do direct outbound HTTP to providers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ibreeze.runtime.model_loop import ModelTurn, ToolCall

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UsageStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelTransport:
    """Abstract base for model transport adapters."""

    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn:
        raise NotImplementedError

    async def probe(self) -> bool:
        raise NotImplementedError

    def normalize_usage(self, raw_usage: dict[str, Any]) -> UsageStats:
        raise NotImplementedError


class ReverseRpcClient:
    # Transitional: real UDS transport will replace stub mode.
    # When _use_stub is True (socket_path is None), returns canned responses.
    # Set socket_path in production to enable real UDS transport.

    def __init__(self, socket_path: str | None = None) -> None:
        self._socket_path = socket_path
        self._use_stub = socket_path is None
        self.last_method: str | None = None
        self.last_params: dict[str, Any] | None = None

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._use_stub:
            logger.warning("ReverseRpcClient using stub mode (no UDS socket configured)")
            self.last_method = method
            self.last_params = params
            return {
                "status": "ok",
                "content": "",
                "tool_calls": [],
                "usage": {},
            }
        raise NotImplementedError("UDS transport not yet implemented")


class ReverseRpcTransport(ModelTransport):
    """Transport that goes through the Credential/Egress Broker via reverse RPC.

    Never holds an api_key directly - only a credential_ref that the Rust
    side resolves into actual credentials for the provider.
    """

    def __init__(
        self,
        credential_ref: str,
        model: str,
    ) -> None:
        self._credential_ref = credential_ref
        self._model = model
        self._rpc = ReverseRpcClient()

    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn:
        result = await self._rpc.call("credential.http.start", {
            "credential_ref": self._credential_ref,
            "model": self._model,
            "messages": list(messages),
            "tool_names": list(tool_names),
        })
        return ModelTurn(
            content=result.get("content", ""),
            tool_calls=tuple(
                ToolCall(
                    id=tc["id"],
                    name=tc["name"],
                    arguments=tc.get("arguments", {}),
                )
                for tc in result.get("tool_calls", [])
            ),
            usage=result.get("usage", {}),
        )

    async def probe(self) -> bool:
        result = await self._rpc.call("credential.probe", {
            "credential_ref": self._credential_ref,
        })
        return result.get("status") == "ok"

    def normalize_usage(self, raw_usage: dict[str, Any]) -> UsageStats:
        return UsageStats(
            prompt_tokens=raw_usage.get("prompt_tokens", 0),
            completion_tokens=raw_usage.get("completion_tokens", 0),
            total_tokens=raw_usage.get("total_tokens", 0),
        )


def create_transport(
    credential_ref: str,
    model: str,
) -> ReverseRpcTransport:
    """Factory function to create the appropriate model transport.

    All providers now go through the Credential/Egress Broker,
    so there is a single transport type.
    """
    return ReverseRpcTransport(credential_ref=credential_ref, model=model)
