"""Coverage tests for ibreeze/runtime/cli.py (uncovered branches)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ibreeze.runtime.cli import (
    AgentProbe,
    ClaudeCodeAdapter,
    CliAdapter,
    CodexCliAdapter,
    OpenCodeAdapter,
    ProcessResult,
    _minimal_environment,
    probe_agent,
)
from ibreeze.runtime.process_supervisor import ProcessSupervisor


def _make_executable(tmp_path: Path) -> Path:
    exe = tmp_path / "fake-agent"
    exe.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    exe.chmod(0o755)
    return exe


def _fake_supervisor(*, stdout: str = "out", stderr: str = "err", exit_code: int = 0, status: str = "completed"):
    supervisor = AsyncMock(spec=ProcessSupervisor)
    supervisor.start = AsyncMock()
    supervisor.wait = AsyncMock(
        return_value={"stdout": stdout, "stderr": stderr, "exit_code": exit_code, "status": status}
    )
    supervisor.kill = AsyncMock()
    return supervisor


class TestProbeAgentBranches:
    @pytest.mark.asyncio
    async def test_probe_codex_discovered(self) -> None:
        with patch("ibreeze.runtime.cli.shutil.which", return_value="/usr/bin/codex"):
            result = await probe_agent("codex_cli")
        assert isinstance(result, AgentProbe)
        assert result.available is True
        assert result.failure_code is None

    @pytest.mark.asyncio
    async def test_probe_claude_discovered(self) -> None:
        with patch("ibreeze.runtime.cli.shutil.which", return_value="/usr/bin/claude"):
            result = await probe_agent("claude_code")
        assert result.available is True

    @pytest.mark.asyncio
    async def test_probe_opencode_discovered(self) -> None:
        with patch("ibreeze.runtime.cli.shutil.which", return_value="/usr/bin/opencode"):
            result = await probe_agent("opencode")
        assert result.available is True


class TestCliAdapterRun:
    @pytest.mark.asyncio
    async def test_run_rejects_non_directory_workspace(self, tmp_path) -> None:
        adapter = CliAdapter(_make_executable(tmp_path))
        # A path that resolves but is not a directory must be rejected.
        (tmp_path / "not-a-dir").write_text("x", encoding="utf-8")
        with pytest.raises(ValueError, match="WORKSPACE_ACCESS_DENIED"):
            await adapter.run([], workspace=tmp_path / "not-a-dir", timeout_seconds=5)

    @pytest.mark.asyncio
    async def test_run_happy_path(self, tmp_path) -> None:
        adapter = CliAdapter(_make_executable(tmp_path))
        supervisor = _fake_supervisor(stdout="hello", stderr="warn", exit_code=0, status="completed")
        with patch("ibreeze.runtime.cli.get_supervisor", return_value=supervisor):
            result = await adapter.run(["--flag"], workspace=tmp_path, timeout_seconds=5, stdin=b"input")
        assert isinstance(result, ProcessResult)
        assert result.exit_code == 0
        assert result.stdout == b"hello"
        assert result.stderr == b"warn"
        assert result.timed_out is False
        supervisor.start.assert_awaited_once()
        supervisor.wait.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_output_limit_exceeded(self, tmp_path) -> None:
        adapter = CliAdapter(_make_executable(tmp_path), max_output_bytes=10)
        supervisor = _fake_supervisor(stdout="x" * 100, stderr="", exit_code=0, status="completed")
        with patch("ibreeze.runtime.cli.get_supervisor", return_value=supervisor):
            with pytest.raises(ValueError, match="AGENT_OUTPUT_LIMIT_EXCEEDED"):
                await adapter.run([], workspace=tmp_path, timeout_seconds=5)

    @pytest.mark.asyncio
    async def test_run_timed_out(self, tmp_path) -> None:
        adapter = CliAdapter(_make_executable(tmp_path))
        supervisor = _fake_supervisor(stdout="", stderr="", exit_code=-1, status="timed_out")
        with patch("ibreeze.runtime.cli.get_supervisor", return_value=supervisor):
            result = await adapter.run([], workspace=tmp_path, timeout_seconds=5)
        assert result.timed_out is True

    @pytest.mark.asyncio
    async def test_run_error_field_timeout(self, tmp_path) -> None:
        adapter = CliAdapter(_make_executable(tmp_path))
        supervisor = AsyncMock(spec=ProcessSupervisor)
        supervisor.start = AsyncMock()
        supervisor.wait = AsyncMock(return_value={"stdout": "", "stderr": "", "exit_code": -1, "error": "timeout"})
        with patch("ibreeze.runtime.cli.get_supervisor", return_value=supervisor):
            result = await adapter.run([], workspace=tmp_path, timeout_seconds=5)
        assert result.timed_out is True


def test_minimal_environment_filters_to_allowed_keys() -> None:
    env = _minimal_environment()
    allowed = {"PATH", "LANG", "LC_ALL", "TERM", "TMPDIR", "USER", "SHELL"}
    assert isinstance(env, dict)
    assert set(env.keys()) <= allowed


class TestAdapterConstructors:
    def test_codex_requires_executable(self) -> None:
        with patch("ibreeze.runtime.cli.shutil.which", return_value=None):
            with pytest.raises(ValueError, match="CODEX_EXECUTABLE_NOT_FOUND"):
                CodexCliAdapter()

    def test_claude_requires_executable(self) -> None:
        with patch("ibreeze.runtime.cli.shutil.which", return_value=None):
            with pytest.raises(ValueError, match="CLAUDE_EXECUTABLE_NOT_FOUND"):
                ClaudeCodeAdapter()

    def test_opencode_requires_executable(self) -> None:
        with patch("ibreeze.runtime.cli.shutil.which", return_value=None):
            with pytest.raises(ValueError, match="OPENCODE_EXECUTABLE_NOT_FOUND"):
                OpenCodeAdapter()


class TestCodexAdapterMethods:
    @pytest.mark.asyncio
    async def test_probe(self, tmp_path) -> None:
        adapter = CodexCliAdapter(executable=_make_executable(tmp_path))
        with patch("ibreeze.runtime.cli.shutil.which", return_value="/usr/bin/codex"):
            result = await adapter.probe()
        assert result.available is True

    @pytest.mark.asyncio
    async def test_run_builds_argv(self, tmp_path) -> None:
        adapter = CodexCliAdapter(executable=_make_executable(tmp_path))
        inner = AsyncMock()
        inner.run = AsyncMock(return_value=ProcessResult(0, b"", b"", False))
        adapter._adapter = inner
        await adapter.run(
            "hello",
            workspace=tmp_path,
            model="codex-mini-latest",
            approval_mode="suggest",
            timeout_seconds=5,
            run_id="rid",
        )
        inner.run.assert_awaited_once_with(
            ["--model", "codex-mini-latest", "--approval-mode", "suggest", "--quiet", "hello"],
            workspace=tmp_path,
            timeout_seconds=5,
            run_id="rid",
        )

    @pytest.mark.asyncio
    async def test_cancel(self, tmp_path) -> None:
        adapter = CodexCliAdapter(executable=_make_executable(tmp_path))
        supervisor = _fake_supervisor()
        with patch("ibreeze.runtime.cli.get_supervisor", return_value=supervisor):
            await adapter.cancel("run-1")
        supervisor.kill.assert_awaited_once_with("run-1")


class TestClaudeAdapterMethods:
    @pytest.mark.asyncio
    async def test_probe(self, tmp_path) -> None:
        adapter = ClaudeCodeAdapter(executable=_make_executable(tmp_path))
        with patch("ibreeze.runtime.cli.shutil.which", return_value="/usr/bin/claude"):
            result = await adapter.probe()
        assert result.available is True

    @pytest.mark.asyncio
    async def test_run_builds_argv(self, tmp_path) -> None:
        adapter = ClaudeCodeAdapter(executable=_make_executable(tmp_path))
        inner = AsyncMock()
        inner.run = AsyncMock(return_value=ProcessResult(0, b"", b"", False))
        adapter._adapter = inner
        await adapter.run(
            "hello",
            workspace=tmp_path,
            model="claude-sonnet-4-20250514",
            permission_mode="acceptEdits",
            timeout_seconds=5,
            run_id="rid",
        )
        inner.run.assert_awaited_once_with(
            ["--model", "claude-sonnet-4-20250514", "--permission-mode", "acceptEdits", "--print", "hello"],
            workspace=tmp_path,
            timeout_seconds=5,
            run_id="rid",
        )

    @pytest.mark.asyncio
    async def test_cancel(self, tmp_path) -> None:
        adapter = ClaudeCodeAdapter(executable=_make_executable(tmp_path))
        supervisor = _fake_supervisor()
        with patch("ibreeze.runtime.cli.get_supervisor", return_value=supervisor):
            await adapter.cancel("run-2")
        supervisor.kill.assert_awaited_once_with("run-2")


class TestOpenCodeAdapterMethods:
    @pytest.mark.asyncio
    async def test_probe(self, tmp_path) -> None:
        adapter = OpenCodeAdapter(executable=_make_executable(tmp_path))
        with patch("ibreeze.runtime.cli.shutil.which", return_value="/usr/bin/opencode"):
            result = await adapter.probe()
        assert result.available is True

    @pytest.mark.asyncio
    async def test_run_builds_argv(self, tmp_path) -> None:
        adapter = OpenCodeAdapter(executable=_make_executable(tmp_path))
        inner = AsyncMock()
        inner.run = AsyncMock(return_value=ProcessResult(0, b"", b"", False))
        adapter._adapter = inner
        await adapter.run(
            "hello",
            workspace=tmp_path,
            model="anthropic/claude-sonnet-4-20250514",
            timeout_seconds=5,
            run_id="rid",
        )
        inner.run.assert_awaited_once_with(
            ["--model", "anthropic/claude-sonnet-4-20250514", "--non-interactive", "hello"],
            workspace=tmp_path,
            timeout_seconds=5,
            run_id="rid",
        )

    @pytest.mark.asyncio
    async def test_cancel(self, tmp_path) -> None:
        adapter = OpenCodeAdapter(executable=_make_executable(tmp_path))
        supervisor = _fake_supervisor()
        with patch("ibreeze.runtime.cli.get_supervisor", return_value=supervisor):
            await adapter.cancel("run-3")
        supervisor.kill.assert_awaited_once_with("run-3")
