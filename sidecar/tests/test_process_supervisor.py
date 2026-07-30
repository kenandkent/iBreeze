"""Tests for ibreeze.runtime.process_supervisor module."""

from __future__ import annotations

import asyncio
import signal
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ibreeze.runtime.process_supervisor import (
    ProcessSupervisor,
    _now,
    get_supervisor,
)


class TestNow:
    def test_returns_utc_iso_format(self):
        result = _now()
        assert isinstance(result, str)
        assert "T" in result
        assert result.endswith("Z")


class TestProcessSupervisor:
    @pytest.fixture
    def supervisor(self) -> ProcessSupervisor:
        return ProcessSupervisor()

    async def test_start_process(self, supervisor: ProcessSupervisor):
        with patch("ibreeze.runtime.process_supervisor.asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.pid = 12345
            mock_create.return_value = mock_proc

            with patch("ibreeze.runtime.process_supervisor.os.getpgid", return_value=12300):
                result = await supervisor.start(
                    "run-1",
                    ["echo", "hello"],
                    cwd="/tmp",
                    env={"TEST": "val"},
                    timeout=30,
                )

            assert result["run_id"] == "run-1"
            assert result["pid"] == 12345
            assert result["pgid"] == 12300
            assert "started_at" in result

    async def test_start_process_stores_metadata(self, supervisor: ProcessSupervisor):
        with patch("ibreeze.runtime.process_supervisor.asyncio.create_subprocess_exec") as mock_create:
            mock_proc = AsyncMock()
            mock_proc.pid = 11111
            mock_create.return_value = mock_proc

            with patch("ibreeze.runtime.process_supervisor.os.getpgid", return_value=11100):
                await supervisor.start("run-2", ["test"])

            assert supervisor.get_pid("run-2") == 11111
            assert supervisor.get_start_time("run-2") is not None

    async def test_wait_process_not_found(self, supervisor: ProcessSupervisor):
        result = await supervisor.wait("nonexistent")
        assert result["error"] == "Process not found"

    async def test_wait_process_completes(self, supervisor: ProcessSupervisor):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"stdout", b"stderr"))
        mock_proc.returncode = 0
        supervisor._processes["run-3"] = mock_proc
        supervisor._pids["run-3"] = 99999
        supervisor._start_times["run-3"] = "2026-01-01T00:00:00Z"

        result = await supervisor.wait("run-3", timeout=10)

        assert result["exit_code"] == 0
        assert result["stdout_preview"] == "stdout"
        assert result["stderr_preview"] == "stderr"
        assert "stdout_sha256" in result
        assert "stderr_sha256" in result
        assert result["run_id"] == "run-3"
        # Process should be cleaned up
        assert supervisor.get_pid("run-3") is None

    async def test_wait_timeout_kills_process(self, supervisor: ProcessSupervisor):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_proc.pid = 22222
        mock_proc.returncode = None
        supervisor._processes["run-4"] = mock_proc
        supervisor._pids["run-4"] = 22222

        with patch.object(supervisor, "kill") as mock_kill:
            result = await supervisor.wait("run-4", timeout=1)
            mock_kill.assert_awaited_once_with("run-4")

        assert result["error"] == "timeout"
        assert result["exit_code"] == -1

    async def test_kill_process_not_found(self, supervisor: ProcessSupervisor):
        # Should not raise
        await supervisor.kill("nonexistent")

    async def test_kill_already_exited(self, supervisor: ProcessSupervisor):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        supervisor._processes["run-5"] = mock_proc

        await supervisor.kill("run-5")
        assert supervisor.get_pid("run-5") is None

    async def test_kill_sends_sigterm_then_sigkill(self, supervisor: ProcessSupervisor):
        mock_proc = AsyncMock()
        mock_proc.pid = 33333
        mock_proc.returncode = None
        supervisor._processes["run-6"] = mock_proc

        with patch("ibreeze.runtime.process_supervisor.os.getpgid", return_value=33300):
            with patch("ibreeze.runtime.process_supervisor.os.killpg") as mock_killpg:
                with patch("ibreeze.runtime.process_supervisor.asyncio.sleep", new_callable=AsyncMock):
                    await supervisor.kill("run-6")

                # Should have sent SIGTERM first
                mock_killpg.assert_any_call(33300, signal.SIGTERM)

    async def test_kill_handles_process_lookup_error(self, supervisor: ProcessSupervisor):
        mock_proc = AsyncMock()
        mock_proc.pid = 44444
        mock_proc.returncode = None
        supervisor._processes["run-7"] = mock_proc

        with patch("ibreeze.runtime.process_supervisor.os.getpgid", side_effect=ProcessLookupError):
            # Should not raise
            await supervisor.kill("run-7")

    async def test_heartbeat_check_process_alive(self, supervisor: ProcessSupervisor):
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        supervisor._processes["run-8"] = mock_proc

        assert await supervisor.heartbeat_check("run-8") is True

    async def test_heartbeat_check_process_exited(self, supervisor: ProcessSupervisor):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        supervisor._processes["run-9"] = mock_proc

        assert await supervisor.heartbeat_check("run-9") is False

    async def test_heartbeat_check_not_found(self, supervisor: ProcessSupervisor):
        assert await supervisor.heartbeat_check("nonexistent") is False

    async def test_get_pid_returns_none_for_unknown(self, supervisor: ProcessSupervisor):
        assert supervisor.get_pid("unknown") is None

    async def test_get_start_time_returns_none_for_unknown(self, supervisor: ProcessSupervisor):
        assert supervisor.get_start_time("unknown") is None

    def test_cleanup_removes_all_metadata(self, supervisor: ProcessSupervisor):
        supervisor._processes["x"] = MagicMock()
        supervisor._pids["x"] = 123
        supervisor._start_times["x"] = "now"
        supervisor._cleanup("x")
        assert "x" not in supervisor._processes
        assert "x" not in supervisor._pids
        assert "x" not in supervisor._start_times

    def test_wrap_with_seatbelt(self, supervisor: ProcessSupervisor):
        result = supervisor._wrap_with_seatbelt(["echo", "hello"])
        assert result[0] == "sandbox-exec"
        assert result[1] == "-p"
        assert "echo" in result
        assert "hello" in result


class TestGetSupervisor:
    def test_returns_singleton(self):
        s1 = get_supervisor()
        s2 = get_supervisor()
        assert s1 is s2
