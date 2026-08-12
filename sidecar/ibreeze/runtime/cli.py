"""Shell-free CLI adapters backed by the Rust ProcessSupervisor."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

from ibreeze.runtime.process_supervisor import get_supervisor

AdapterName = Literal["codex_cli", "claude_code", "opencode"]

_EXECUTABLES: dict[AdapterName, str] = {
    "codex_cli": "codex",
    "claude_code": "claude",
    "opencode": "opencode",
}


@dataclass(frozen=True, slots=True)
class AgentProbe:
    adapter_type: AdapterName
    available: bool
    executable_path: str | None
    version: str | None
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class ProcessResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    timed_out: bool


async def probe_agent(
    adapter_type: AdapterName,
    *,
    timeout_seconds: float = 5,
) -> AgentProbe:
    executable = shutil.which(_EXECUTABLES[adapter_type])
    if executable is None:
        return AgentProbe(
            adapter_type=adapter_type,
            available=False,
            executable_path=None,
            version=None,
            failure_code="AGENT_EXECUTABLE_NOT_FOUND",
        )
    # Probing must not launch an unbound process.  The Rust supervisor performs
    # the authoritative snapshot/catalog checks at real run start; this
    # preflight only reports whether the allow-listed binary is discoverable.
    return AgentProbe(
        adapter_type=adapter_type,
        available=True,
        executable_path=executable,
        version=None,
        failure_code=None,
    )


class CliAdapter:
    """Build and execute an approved argv through Rust."""

    def __init__(
        self,
        executable: str | Path,
        *,
        max_output_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        resolved = Path(executable).resolve(strict=True)
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise ValueError("AGENT_EXECUTABLE_NOT_FOUND")
        self._executable = str(resolved)
        self._max_output_bytes = max_output_bytes

    async def run(
        self,
        arguments: list[str],
        *,
        workspace: str | Path,
        timeout_seconds: float,
        stdin: bytes = b"",
        run_id: str | None = None,
    ) -> ProcessResult:
        root = Path(workspace).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("WORKSPACE_ACCESS_DENIED")
        supervisor = get_supervisor()
        actual_run_id = run_id or str(uuid4())
        await supervisor.start(
            actual_run_id,
            [self._executable, *arguments],
            cwd=str(root),
            timeout=max(1, int(timeout_seconds)),
            stdin=stdin,
        )
        result = await supervisor.wait(actual_run_id, timeout=max(1, int(timeout_seconds)))
        stdout = str(result.get("stdout", "")).encode("utf-8", errors="replace")
        stderr = str(result.get("stderr", "")).encode("utf-8", errors="replace")
        if len(stdout) + len(stderr) > self._max_output_bytes:
            raise ValueError("AGENT_OUTPUT_LIMIT_EXCEEDED")
        return ProcessResult(
            exit_code=int(result.get("exit_code", -1)),
            stdout=stdout,
            stderr=stderr,
            timed_out=result.get("status") == "timed_out" or result.get("error") == "timeout",
        )


def _minimal_environment() -> dict[str, str]:
    allowed = {"PATH", "LANG", "LC_ALL", "TERM", "TMPDIR", "USER", "SHELL"}
    return {key: value for key, value in os.environ.items() if key in allowed}


class CodexCliAdapter:
    def __init__(self, executable: str | Path | None = None) -> None:
        path = executable or shutil.which("codex")
        if path is None:
            raise ValueError("CODEX_EXECUTABLE_NOT_FOUND")
        self._adapter = CliAdapter(path)

    async def probe(self, *, timeout_seconds: float = 5) -> AgentProbe:
        return await probe_agent("codex_cli", timeout_seconds=timeout_seconds)

    async def run(
        self,
        prompt: str,
        *,
        workspace: str | Path,
        model: str = "codex-mini-latest",
        approval_mode: str = "suggest",
        timeout_seconds: float = 300,
        run_id: str | None = None,
    ) -> ProcessResult:
        return await self._adapter.run(
            ["--model", model, "--approval-mode", approval_mode, "--quiet", prompt],
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            run_id=run_id,
        )

    async def cancel(self, run_id: str) -> None:
        await get_supervisor().kill(run_id)


class ClaudeCodeAdapter:
    def __init__(self, executable: str | Path | None = None) -> None:
        path = executable or shutil.which("claude")
        if path is None:
            raise ValueError("CLAUDE_EXECUTABLE_NOT_FOUND")
        self._adapter = CliAdapter(path)

    async def probe(self, *, timeout_seconds: float = 5) -> AgentProbe:
        return await probe_agent("claude_code", timeout_seconds=timeout_seconds)

    async def run(
        self,
        prompt: str,
        *,
        workspace: str | Path,
        model: str = "claude-sonnet-4-20250514",
        permission_mode: str = "acceptEdits",
        timeout_seconds: float = 300,
        run_id: str | None = None,
    ) -> ProcessResult:
        return await self._adapter.run(
            ["--model", model, "--permission-mode", permission_mode, "--print", prompt],
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            run_id=run_id,
        )

    async def cancel(self, run_id: str) -> None:
        await get_supervisor().kill(run_id)


class OpenCodeAdapter:
    def __init__(self, executable: str | Path | None = None) -> None:
        path = executable or shutil.which("opencode")
        if path is None:
            raise ValueError("OPENCODE_EXECUTABLE_NOT_FOUND")
        self._adapter = CliAdapter(path)

    async def probe(self, *, timeout_seconds: float = 5) -> AgentProbe:
        return await probe_agent("opencode", timeout_seconds=timeout_seconds)

    async def run(
        self,
        prompt: str,
        *,
        workspace: str | Path,
        model: str = "anthropic/claude-sonnet-4-20250514",
        timeout_seconds: float = 300,
        run_id: str | None = None,
    ) -> ProcessResult:
        return await self._adapter.run(
            ["--model", model, "--non-interactive", prompt],
            workspace=workspace,
            timeout_seconds=timeout_seconds,
            run_id=run_id,
        )

    async def cancel(self, run_id: str) -> None:
        await get_supervisor().kill(run_id)


def create_adapter(
    adapter_type: AdapterName,
    executable: str | Path | None = None,
) -> CodexCliAdapter | ClaudeCodeAdapter | OpenCodeAdapter:
    adapters = {"codex_cli": CodexCliAdapter, "claude_code": ClaudeCodeAdapter, "opencode": OpenCodeAdapter}
    return adapters[adapter_type](executable)  # type: ignore[return-value]
