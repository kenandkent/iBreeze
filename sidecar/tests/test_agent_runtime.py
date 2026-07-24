"""Agent CLI and API Model runtime tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ibreeze.runtime import CliAdapter, ModelRuntime, ModelTurn, ToolCall


class ScriptedTransport:
    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = turns
        self.requests: list[tuple[dict[str, object], ...]] = []

    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn:
        assert tool_names == ("read_file",)
        self.requests.append(messages)
        return self.turns.pop(0)


@pytest.mark.asyncio
async def test_api_model_runs_a_complete_agent_loop() -> None:
    transport = ScriptedTransport(
        [
            ModelTurn(
                content="读取需求",
                tool_calls=(
                    ToolCall(
                        id="call-1",
                        name="read_file",
                        arguments={"path": "requirements.md"},
                    ),
                ),
            ),
            ModelTurn(content="已根据需求完成实现"),
        ]
    )
    observed: list[dict[str, object]] = []

    async def read_file(arguments: dict[str, object]) -> object:
        observed.append(arguments)
        return {"content": "需求正文"}

    result = await ModelRuntime(
        transport,
        {"read_file": read_file},
    ).run(
        system_prompt="你是开发工程师",
        user_message="完成需求",
    )
    assert result.content == "已根据需求完成实现"
    assert result.turns == 2
    assert result.tool_executions == 1
    assert observed == [{"path": "requirements.md"}]
    assert transport.requests[1][-1]["role"] == "tool"


@pytest.mark.asyncio
async def test_api_model_rejects_unbounded_loop() -> None:
    transport = ScriptedTransport(
        [
            ModelTurn(
                content="继续",
                tool_calls=(ToolCall(id="one", name="read_file", arguments={}),),
            )
        ]
    )

    async def read_file(_: dict[str, object]) -> object:
        return {}

    with pytest.raises(ValueError, match="AGENT_MAX_TURNS_EXCEEDED"):
        await ModelRuntime(
            transport,
            {"read_file": read_file},
            max_turns=1,
        ).run(system_prompt="system", user_message="task")


@pytest.mark.asyncio
async def test_cli_adapter_uses_argv_and_workspace(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "agent"
    executable.write_text(
        "#!/bin/sh\nprintf '%s|%s' \"$PWD\" \"$1\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = await CliAdapter(executable).run(
        ["argument with spaces"],
        workspace=workspace,
        timeout_seconds=2,
    )
    assert result.exit_code == 0
    assert result.stdout.decode() == f"{workspace}|argument with spaces"
    assert result.stderr == b""
    assert result.timed_out is False


def test_cli_adapter_rejects_non_executable(tmp_path: Path) -> None:
    executable = tmp_path / "agent"
    executable.write_text("not executable", encoding="utf-8")
    executable.chmod(0o600)
    assert not os.access(executable, os.X_OK)
    with pytest.raises(ValueError, match="AGENT_EXECUTABLE_NOT_FOUND"):
        CliAdapter(executable)
