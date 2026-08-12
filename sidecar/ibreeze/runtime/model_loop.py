"""Built-in Agent Loop used when an employee base is an API Model."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class ToolPermission(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True, slots=True)
class ModelTurn:
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentLoopResult:
    content: str
    turns: int
    tool_executions: int
    checkpoints: list[Checkpoint] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Checkpoint:
    turn_number: int
    tool_call_id: str
    tool_name: str
    arguments: dict[str, object]
    result: Any
    approved: bool


class ModelTransport(Protocol):
    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn: ...


Tool = Callable[[dict[str, object]], Awaitable[object]]
PermissionChecker = Callable[[str, dict[str, object]], Awaitable[ToolPermission]]
Verifier = Callable[[str, Any], Awaitable[bool]]


class ModelRuntime:
    """Run model/tool turns until a final response or a strict step limit."""

    def __init__(
        self,
        transport: ModelTransport,
        tools: dict[str, Tool],
        *,
        max_turns: int = 50,
        permission_checker: PermissionChecker | None = None,
        verifier: Verifier | None = None,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be positive")
        self._transport = transport
        self._tools = dict(tools)
        self._max_turns = max_turns
        self._permission_checker = permission_checker
        self._verifier = verifier

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
        checkpoints: list[Checkpoint] = []

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
                    checkpoints=checkpoints,
                )

            seen_ids: set[str] = set()
            for call in turn.tool_calls:
                if call.id in seen_ids:
                    raise ValueError("MODEL_TOOL_CALL_ID_DUPLICATE")
                seen_ids.add(call.id)

                approved = await self._check_permission(call.name, call.arguments)
                if approved == ToolPermission.DENY:
                    result: object = {
                        "error": "TOOL_PERMISSION_DENIED",
                        "tool_name": call.name,
                    }
                    checkpoints.append(
                        Checkpoint(
                            turn_number=turn_number,
                            tool_call_id=call.id,
                            tool_name=call.name,
                            arguments=call.arguments,
                            result=result,
                            approved=False,
                        )
                    )
                else:
                    tool = self._tools.get(call.name)
                    if tool is None:
                        result = {
                            "error": "TOOL_NOT_ALLOWED",
                            "tool_name": call.name,
                        }
                    else:
                        result = await tool(call.arguments)
                        executions += 1

                        if self._verifier is not None:
                            verified = await self._verifier(call.name, result)
                            if not verified:
                                result = {
                                    "error": "VERIFICATION_FAILED",
                                    "tool_name": call.name,
                                    "original_result": result,
                                }

                    checkpoints.append(
                        Checkpoint(
                            turn_number=turn_number,
                            tool_call_id=call.id,
                            tool_name=call.name,
                            arguments=call.arguments,
                            result=result,
                            approved=True,
                        )
                    )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result
                        if isinstance(result, str)
                        else json.dumps(result, ensure_ascii=False, sort_keys=True),
                    }
                )

        raise ValueError("AGENT_MAX_TURNS_EXCEEDED")

    async def _check_permission(
        self,
        tool_name: str,
        arguments: dict[str, object],
    ) -> ToolPermission:
        if self._permission_checker is None:
            return ToolPermission.ALLOW
        return await self._permission_checker(tool_name, arguments)
