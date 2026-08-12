"""Model transport adapters using credential/egress broker via reverse RPC.

All provider network calls go through the Rust Credential/Egress Broker
via reverse RPC. The Sidecar must NOT do direct outbound HTTP to providers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from ibreeze.runtime.model_loop import ModelTurn, ToolCall

logger = logging.getLogger(__name__)

MAX_FRAME_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class UsageStats:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ModelRunCancelledError(RuntimeError):
    """Raised when Rust terminates an in-flight provider request for a run."""


@dataclass(slots=True)
class _ActiveModelRequest:
    rpc: ReverseRpcClient
    request_id: str | None = None
    cancel_requested: bool = False
    cancel_sent: bool = False


_active_model_requests: dict[str, _ActiveModelRequest] = {}
_active_model_lock: asyncio.Lock | None = None


async def _get_active_model_lock() -> asyncio.Lock:
    """Create the registry lock in the running event loop.

    Tests and embedded callers may create more than one event loop during the
    process lifetime, so the lock is deliberately lazy instead of being
    constructed at module import time.
    """
    global _active_model_lock
    if _active_model_lock is None:
        _active_model_lock = asyncio.Lock()
    return _active_model_lock


async def _register_active_model_request(run_id: str, rpc: ReverseRpcClient) -> None:
    lock = await _get_active_model_lock()
    async with lock:
        _active_model_requests[run_id] = _ActiveModelRequest(rpc=rpc)


async def _set_active_model_request_id(run_id: str, request_id: str) -> bool:
    lock = await _get_active_model_lock()
    async with lock:
        active = _active_model_requests.get(run_id)
        if active is None:
            return False
        active.request_id = request_id
        return active.cancel_requested


async def _unregister_active_model_request(run_id: str) -> None:
    lock = await _get_active_model_lock()
    async with lock:
        _active_model_requests.pop(run_id, None)


async def cancel_model_run(run_id: str, reason: str = "cancelled by user") -> bool:
    """Cancel the active API Model request owned by ``run_id``.

    The database cancellation is performed by :mod:`runtime.service`; this
    function only controls the provider request.  Marking the request before
    awaiting reverse RPC closes the race where cancellation arrives while the
    ``credential.http.start`` response is still in flight.
    """
    lock = await _get_active_model_lock()
    async with lock:
        active = _active_model_requests.get(run_id)
        if active is None:
            return False
        active.cancel_requested = True
        request_id = active.request_id
        if request_id is None or active.cancel_sent:
            return True
        active.cancel_sent = True
        rpc = active.rpc
    await rpc.call(
        "credential.http.cancel",
        {"run_id": run_id, "request_id": request_id, "reason": reason[:500] or "cancelled"},
    )
    return True


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


_reverse_rpc_session: Any | None = None


def set_reverse_rpc_session(session: Any | None) -> None:
    """Bind the authenticated Rust↔Sidecar stream for reverse calls."""
    global _reverse_rpc_session
    _reverse_rpc_session = session


def get_reverse_rpc_session() -> Any | None:
    return _reverse_rpc_session


_broker_event_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}


def register_broker_stream(request_id: str) -> asyncio.Queue[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
    _broker_event_queues[request_id] = queue
    return queue


def publish_broker_event(payload: dict[str, Any]) -> None:
    request_id = str(payload.get("request_id", ""))
    queue = _broker_event_queues.get(request_id)
    if queue is None:
        queue = _broker_event_queues.get(str(payload.get("run_id", "")))
    if queue is None:
        return
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull as exc:
        raise RuntimeError("BROKER_EVENT_BACKPRESSURE") from exc


def unregister_broker_stream(request_id: str) -> None:
    _broker_event_queues.pop(request_id, None)


async def collect_broker_stream(
    request_id: str,
    queue: asyncio.Queue[dict[str, Any]],
    timeout_seconds: float,
    *,
    aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("BROKER_EVENT_TIMEOUT")
            event = await asyncio.wait_for(queue.get(), timeout=remaining)
            kind = event.get("event")
            payload = event.get("payload")
            if kind == "failed":
                raise RuntimeError(str(payload))
            if kind == "completed":
                if isinstance(payload, dict) and set(payload) - {"status"}:
                    return payload
                return {"events": events}
            if isinstance(payload, dict):
                events.append(payload)
            if len(events) > 4096:
                raise RuntimeError("BROKER_EVENT_LIMIT_EXCEEDED")
    finally:
        unregister_broker_stream(request_id)
        for alias in aliases:
            unregister_broker_stream(alias)


class ReverseRpcClient:
    """Client for the authenticated Rust reverse-RPC session.

    Production code receives the already-authenticated :class:`IpcSession`
    through the lifecycle binding and never opens a second connection to the
    Sidecar UDS.
    """

    def __init__(self, session: Any | None = None) -> None:
        self._session = session
        self.last_method: str | None = None
        self.last_params: dict[str, Any] | None = None

    async def _ensure_connected(self) -> None:
        if self._session is not None:
            return
        if _reverse_rpc_session is not None:
            self._session = _reverse_rpc_session
            return

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.last_method = method
        self.last_params = params

        await self._ensure_connected()
        if self._session is not None:
            result = await self._session.call(method, params)
            return result if isinstance(result, dict) else {}

        logger.warning("ReverseRpcClient has no authenticated Rust session for method=%s", method)
        raise RuntimeError(
            "RUST_REVERSE_SESSION_UNAVAILABLE: bind the authenticated IPC session before executing reverse RPC; "
            "Credential Broker is not configured for this Sidecar instance"
        )


class ReverseRpcTransport(ModelTransport):
    """Transport that goes through the Credential/Egress Broker via reverse RPC.

    Never holds an api_key directly - only a credential_ref that the Rust
    side resolves into actual credentials for the provider.

    Uses :class:`ReverseRpcClient` over the authenticated IPC session.
    """

    def __init__(
        self,
        credential_ref: str,
        model: str,
        run_id: str = "",
        provider_release_id: str = "",
        model_binding_id: str = "",
        provider_protocol: str = "openai_chat_completions",
        session: Any | None = None,
    ) -> None:
        self._credential_ref = credential_ref
        self._model = model
        self._run_id = run_id
        self._provider_release_id = provider_release_id
        self._model_binding_id = model_binding_id
        if provider_protocol not in {
            "openai_responses",
            "anthropic_messages",
            "openai_chat_completions",
        }:
            raise ValueError("PROVIDER_PROTOCOL_INVALID")
        self._provider_protocol = provider_protocol
        self._rpc = ReverseRpcClient(session=session)

    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn:
        from datetime import UTC, datetime, timedelta

        deadline_at = (datetime.now(UTC) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        queue = register_broker_stream(self._run_id)
        request_id: str | None = None
        await _register_active_model_request(self._run_id, self._rpc)
        try:
            accepted = await self._rpc.call(
                "credential.http.start",
                {
                    "run_id": self._run_id,
                    "credential_ref": self._credential_ref,
                    "provider_release_id": self._provider_release_id,
                    "model_binding_id": self._model_binding_id,
                    "protocol": self._provider_protocol,
                    "operation": "model_turn",
                    "relative_path": _protocol_path(self._provider_protocol),
                    "request": _build_provider_request(self._provider_protocol, messages, tool_names),
                    "deadline_at": deadline_at,
                },
            )
            if accepted.get("accepted") is not True or accepted.get("stream") is not True:
                raise RuntimeError("BROKER_REQUEST_NOT_ACCEPTED")
            request_id = accepted.get("request_id")
            if not isinstance(request_id, str) or not request_id:
                raise RuntimeError("BROKER_REQUEST_ID_MISSING")
            cancel_requested = await _set_active_model_request_id(self._run_id, request_id)
            _broker_event_queues[request_id] = queue
            if cancel_requested:
                await cancel_model_run(self._run_id, "cancelled before provider request was ready")
            result = await collect_broker_stream(self._run_id, queue, 300.0, aliases=(request_id,))
            if result.get("state") == "cancelled":
                raise ModelRunCancelledError("MODEL_RUN_CANCELLED")
        except Exception:
            unregister_broker_stream(self._run_id)
            if request_id is not None:
                unregister_broker_stream(request_id)
            raise
        finally:
            await _unregister_active_model_request(self._run_id)
        normalized = _normalize_model_response(result)
        return ModelTurn(
            content=normalized.get("content", ""),
            tool_calls=tuple(
                ToolCall(
                    id=tc["id"],
                    name=tc["name"],
                    arguments=tc.get("arguments", {}),
                )
                for tc in normalized.get("tool_calls", [])
            ),
            usage=normalized.get("usage", {}),
        )

    async def probe(self) -> bool:
        if not self._provider_release_id or not self._model_binding_id:
            return False
        result = await self._rpc.call(
            "credential.probe",
            {
                "credential_ref": self._credential_ref,
                "provider_release_id": self._provider_release_id,
                "model_binding_id": self._model_binding_id,
            },
        )
        return result.get("available", result.get("status") == "ok") is True

    def normalize_usage(self, raw_usage: dict[str, Any]) -> UsageStats:
        return UsageStats(
            prompt_tokens=raw_usage.get("prompt_tokens", 0),
            completion_tokens=raw_usage.get("completion_tokens", 0),
            total_tokens=raw_usage.get("total_tokens", 0),
        )


def _normalize_model_response(result: dict[str, Any]) -> dict[str, Any]:
    """Normalize OpenAI/Anthropic-compatible broker output to ModelTurn."""
    if isinstance(result.get("content"), str) or isinstance(result.get("tool_calls"), list):
        return result
    choices = result.get("choices")
    if isinstance(choices, list) and choices:
        first: dict[str, Any] = choices[0] if isinstance(choices[0], dict) else {}
        raw_message = first.get("message")
        message: dict[str, Any] = cast(dict[str, Any], raw_message) if isinstance(raw_message, dict) else {}
        return {
            "content": message.get("content", first.get("text", "")) or "",
            "tool_calls": message.get("tool_calls", first.get("tool_calls", [])) or [],
            "usage": result.get("usage", {}) or {},
        }
    anthropic_content = result.get("content")
    if isinstance(anthropic_content, list):
        content_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in anthropic_content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type == "text" and isinstance(block.get("text"), str):
                content_parts.append(block["text"])
            elif block_type == "tool_use":
                arguments = block.get("input", {})
                tool_calls.append(
                    {
                        "id": str(block.get("id", uuid4())),
                        "name": str(block.get("name", "unknown")),
                        "arguments": arguments if isinstance(arguments, dict) else {},
                    }
                )
        return {"content": "".join(content_parts), "tool_calls": tool_calls, "usage": result.get("usage", {}) or {}}
    responses_output = result.get("output")
    if isinstance(responses_output, list):
        content_parts = []
        tool_calls = []
        for item in responses_output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "function_call":
                arguments = item.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {"raw": arguments}
                tool_calls.append(
                    {
                        "id": str(item.get("call_id", item.get("id", uuid4()))),
                        "name": str(item.get("name", "unknown")),
                        "arguments": arguments if isinstance(arguments, dict) else {},
                    }
                )
            for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    content_parts.append(content["text"])
        return {"content": "".join(content_parts), "tool_calls": tool_calls, "usage": result.get("usage", {}) or {}}
    events = result.get("events")
    if isinstance(events, list):
        event_content_parts: list[str] = []
        event_tool_calls: list[dict[str, Any]] = []
        usage: dict[str, Any] = {}
        for event in events:
            if not isinstance(event, dict):
                continue
            raw_delta = event.get("delta")
            delta: dict[str, Any] = cast(dict[str, Any], raw_delta) if isinstance(raw_delta, dict) else event
            text = delta.get("content", delta.get("text", ""))
            if isinstance(text, str):
                event_content_parts.append(text)
            calls = delta.get("tool_calls")
            if isinstance(calls, list):
                for item in calls:
                    if not isinstance(item, dict):
                        continue
                    raw_function = item.get("function")
                    function: dict[str, Any] = cast(dict[str, Any], raw_function) if isinstance(raw_function, dict) else {}
                    arguments = function.get("arguments", item.get("arguments", {}))
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {"raw": arguments}
                    event_tool_calls.append({
                        "id": str(item.get("id", uuid4())),
                        "name": function.get("name", item.get("name", "unknown")),
                        "arguments": arguments if isinstance(arguments, dict) else {},
                    })
            if isinstance(event.get("usage"), dict):
                usage = event["usage"]
        return {"content": "".join(event_content_parts), "tool_calls": event_tool_calls, "usage": usage}
    return {"content": "", "tool_calls": [], "usage": result.get("usage", {}) or {}}


def create_transport(
    credential_ref: str,
    model: str,
    run_id: str = "",
    provider_release_id: str = "",
    model_binding_id: str = "",
    provider_protocol: str = "openai_chat_completions",
    session: Any | None = None,
) -> ReverseRpcTransport:
    """Factory function to create the appropriate model transport.

    All providers now go through the Credential/Egress Broker and the
    authenticated reverse session.
    """
    return ReverseRpcTransport(
        credential_ref=credential_ref,
        model=model,
        run_id=run_id,
        provider_release_id=provider_release_id,
        model_binding_id=model_binding_id,
        provider_protocol=provider_protocol,
        session=session,
    )


def _protocol_path(protocol: str) -> str:
    return {
        "openai_responses": "/v1/responses",
        "anthropic_messages": "/v1/messages",
        "openai_chat_completions": "/v1/chat/completions",
    }[protocol]


def _build_provider_request(
    protocol: str,
    messages: tuple[dict[str, object], ...],
    tool_names: tuple[str, ...],
) -> dict[str, object]:
    tool_parameters: dict[str, dict[str, object]] = {
        "read_file": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative file path"},
                "offset": {"type": "integer", "minimum": 0},
                "length": {"type": "integer", "minimum": 1, "maximum": 1048576},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "list_files": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "pattern": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
            },
            "additionalProperties": False,
        },
        "search_text": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 256},
                "path": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }
    tools = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": "Runtime tool",
                "parameters": tool_parameters.get(name, {"type": "object", "properties": {}}),
            },
        }
        for name in tool_names
    ]
    if protocol == "anthropic_messages":
        system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
        body: dict[str, object] = {
            "system": system,
            "messages": _anthropic_messages(messages),
            "max_tokens": 4096,
        }
        if tools:
            body["tools"] = [
                {
                    "name": name,
                    "description": "Read-only workspace inspection tool",
                    "input_schema": tool_parameters.get(name, {"type": "object", "properties": {}}),
                }
                for name in tool_names
            ]
        return body
    if protocol == "openai_responses":
        body = {"input": _responses_input(messages), "store": False}
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "name": name,
                    "description": "Read-only workspace inspection tool",
                    "parameters": tool_parameters.get(name, {"type": "object", "properties": {}}),
                }
                for name in tool_names
            ]
        return body
    body = {"messages": list(messages)}
    if tools:
        body["tools"] = tools
    return body


def _anthropic_messages(messages: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    converted: list[dict[str, object]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            continue
        if role == "tool":
            content = message.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": message.get("tool_call_id", ""),
                            "content": content,
                        }
                    ],
                }
            )
            continue
        if role == "assistant" and isinstance(message.get("tool_calls"), list):
            blocks: list[dict[str, object]] = []
            if isinstance(message.get("content"), str) and message["content"]:
                blocks.append({"type": "text", "text": message["content"]})
            for call in cast(list[object], message["tool_calls"]):
                if isinstance(call, dict):
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": call.get("id", ""),
                            "name": call.get("name", ""),
                            "input": call.get("arguments", {}),
                        }
                    )
            converted.append({"role": "assistant", "content": blocks})
            continue
        converted.append(dict(message))
    return converted


def _responses_input(messages: tuple[dict[str, object], ...]) -> list[dict[str, object] | str]:
    converted: list[dict[str, object] | str] = []
    for message in messages:
        role = message.get("role")
        if role == "tool":
            content = message.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            converted.append(
                {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id", ""),
                    "output": content,
                }
            )
            continue
        if role == "assistant" and isinstance(message.get("tool_calls"), list):
            if isinstance(message.get("content"), str) and message["content"]:
                converted.append({"role": "assistant", "content": message["content"]})
            for call in cast(list[object], message["tool_calls"]):
                if isinstance(call, dict):
                    converted.append(
                        {
                            "type": "function_call",
                            "call_id": call.get("id", ""),
                            "name": call.get("name", ""),
                            "arguments": json.dumps(call.get("arguments", {}), ensure_ascii=False),
                        }
                    )
            continue
        converted.append(dict(message))
    return converted
