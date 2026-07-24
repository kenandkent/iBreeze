"""Shell-free CLI adapters for Codex CLI, Claude Code and OpenCode."""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
    try:
        process = await asyncio.create_subprocess_exec(
            executable,
            "--version",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_minimal_environment(),
            start_new_session=True,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        return AgentProbe(
            adapter_type=adapter_type,
            available=False,
            executable_path=executable,
            version=None,
            failure_code="AGENT_PROBE_TIMED_OUT",
        )
    if process.returncode != 0:
        return AgentProbe(
            adapter_type=adapter_type,
            available=False,
            executable_path=executable,
            version=None,
            failure_code="AGENT_AUTH_UNAVAILABLE",
        )
    version = (stdout or stderr).decode("utf-8", errors="replace").strip()
    return AgentProbe(
        adapter_type=adapter_type,
        available=True,
        executable_path=executable,
        version=version[:500],
        failure_code=None,
    )


class CliAdapter:
    """Execute an approved argv in an already-authorized Run Workspace."""

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
    ) -> ProcessResult:
        root = Path(workspace).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("WORKSPACE_ACCESS_DENIED")
        process = await asyncio.create_subprocess_exec(
            self._executable,
            *arguments,
            cwd=root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_minimal_environment(),
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(stdin),
                timeout=timeout_seconds,
            )
            timed_out = False
        except TimeoutError:
            process.kill()
            stdout, stderr = await process.communicate()
            timed_out = True
        if len(stdout) + len(stderr) > self._max_output_bytes:
            raise ValueError("AGENT_OUTPUT_LIMIT_EXCEEDED")
        return ProcessResult(
            exit_code=process.returncode if process.returncode is not None else -1,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
        )


def _minimal_environment() -> dict[str, str]:
    allowed = {
        "PATH",
        "LANG",
        "LC_ALL",
        "TERM",
        "TMPDIR",
        "USER",
        "SHELL",
    }
    return {
        key: value
        for key, value in os.environ.items()
        if key in allowed
    }
