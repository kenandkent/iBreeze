"""Built-in Agent Loop used when an employee base is an API Model."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True, slots=True)
class ModelTurn:
    content: str
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class AgentLoopResult:
    content: str
    turns: int
    tool_executions: int


class ModelTransport(Protocol):
    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn: ...


Tool = Callable[[dict[str, object]], Awaitable[object]]


class ModelRuntime:
    """Run model/tool turns until a final response or a strict step limit."""

    def __init__(
        self,
        transport: ModelTransport,
        tools: dict[str, Tool],
        *,
        max_turns: int = 32,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be positive")
        self._transport = transport
        self._tools = dict(tools)
        self._max_turns = max_turns

    async def run(
        self,
        *,
        system_prompt: str,
        user_message: str,
    ) -> AgentLoopResult:
        messages: list[dict[str, object]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        executions = 0
        for turn_number in range(1, self._max_turns + 1):
            turn = await self._transport.complete(
                tuple(messages),
                tuple(sorted(self._tools)),
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": turn.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "name": call.name,
                            "arguments": call.arguments,
                        }
                        for call in turn.tool_calls
                    ],
                }
            )
            if not turn.tool_calls:
                return AgentLoopResult(
                    content=turn.content,
                    turns=turn_number,
                    tool_executions=executions,
                )
            seen_ids: set[str] = set()
            for call in turn.tool_calls:
                if call.id in seen_ids:
                    raise ValueError("MODEL_TOOL_CALL_ID_DUPLICATE")
                seen_ids.add(call.id)
                tool = self._tools.get(call.name)
                if tool is None:
                    result: object = {
                        "error": "TOOL_NOT_ALLOWED",
                        "tool_name": call.name,
                    }
                else:
                    result = await tool(call.arguments)
                    executions += 1
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result,
                    }
                )
        raise ValueError("AGENT_MAX_TURNS_EXCEEDED")
