"""Model transport adapters for API-based model providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ibreeze.runtime.model_loop import ModelTurn, ToolCall


@dataclass(frozen=True, slots=True)
class UsageStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelTransport(ABC):
    """Abstract base for model transport adapters."""

    @abstractmethod
    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn: ...

    @abstractmethod
    async def probe(self) -> bool: ...

    @abstractmethod
    def normalize_usage(self, raw_usage: dict[str, Any]) -> UsageStats: ...


class OpenAITransport(ModelTransport):
    """Transport for OpenAI-compatible APIs."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn:
        import aiohttp

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": list(messages),
        }
        if tool_names:
            payload["tools"] = [
                {"type": "function", "function": {"name": name}}
                for name in tool_names
            ]

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            ) as resp:
                data = await resp.json()

        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content", "") or ""
        raw_tool_calls = message.get("tool_calls", [])

        tool_calls = tuple(
            ToolCall(
                id=tc["id"],
                name=tc["function"]["name"],
                arguments=_parse_json(tc["function"]["arguments"]),
            )
            for tc in raw_tool_calls
        )

        return ModelTurn(content=content, tool_calls=tool_calls)

    async def probe(self) -> bool:
        try:
            import aiohttp

            headers = {"Authorization": f"Bearer {self._api_key}"}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._base_url}/models",
                    headers=headers,
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    def normalize_usage(self, raw_usage: dict[str, Any]) -> UsageStats:
        return UsageStats(
            prompt_tokens=raw_usage.get("prompt_tokens", 0),
            completion_tokens=raw_usage.get("completion_tokens", 0),
            total_tokens=raw_usage.get("total_tokens", 0),
        )


class AnthropicTransport(ModelTransport):
    """Transport for Anthropic Claude API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        base_url: str = "https://api.anthropic.com",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")

    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn:
        import aiohttp

        system_content = ""
        user_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = str(msg.get("content", ""))
            else:
                user_messages.append(msg)

        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": user_messages,
        }
        if system_content:
            payload["system"] = system_content
        if tool_names:
            payload["tools"] = [
                {"name": name, "description": "", "input_schema": {"type": "object", "properties": {}}}
                for name in tool_names
            ]

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/v1/messages",
                json=payload,
                headers=headers,
            ) as resp:
                data = await resp.json()

        content_parts = []
        tool_calls = []
        for block in data.get("content", []):
            if block["type"] == "text":
                content_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block["id"],
                        name=block["name"],
                        arguments=block.get("input", {}),
                    )
                )

        return ModelTurn(
            content="\n".join(content_parts),
            tool_calls=tuple(tool_calls),
        )

    async def probe(self) -> bool:
        try:
            import aiohttp

            headers = {
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._base_url}/v1/models",
                    headers=headers,
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    def normalize_usage(self, raw_usage: dict[str, Any]) -> UsageStats:
        return UsageStats(
            prompt_tokens=raw_usage.get("input_tokens", 0),
            completion_tokens=raw_usage.get("output_tokens", 0),
            total_tokens=raw_usage.get("input_tokens", 0) + raw_usage.get("output_tokens", 0),
        )


def _parse_json(value: str) -> dict[str, Any]:
    import json

    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def create_transport(
    provider: str,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
) -> ModelTransport:
    """Factory function to create the appropriate model transport."""
    transports = {
        "openai": OpenAITransport,
        "anthropic": AnthropicTransport,
    }
    transport_cls = transports.get(provider)
    if transport_cls is None:
        raise ValueError(f"Unsupported provider: {provider}")
    kwargs: dict[str, Any] = {"api_key": api_key}
    if model is not None:
        kwargs["model"] = model
    if base_url is not None:
        kwargs["base_url"] = base_url
    return transport_cls(**kwargs)
