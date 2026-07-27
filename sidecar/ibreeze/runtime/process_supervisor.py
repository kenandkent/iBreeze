"""Subprocess supervision with PID tracking and cleanup.

I.7 子进程监管：
- 每个 Run 创建独立进程组
- PID/PGID/start time 写入 agent_runs 并通知 Rust
- 超时或取消：SIGTERM 等 5s → SIGKILL 整个进程组
- 退出时记录 exit code、signal、stdout/stderr SHA-256

macOS Seatbelt (spec §I.8):
- 在 macOS 上通过 sandbox-exec 对子进程施加最小权限沙箱
- 非 macOS 平台跳过沙箱步骤，仅使用 minimal_env 隔离
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import signal
import sys
from datetime import UTC, datetime
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


class ProcessSupervisor:
    """Supervises CLI subprocess execution with PID tracking and cleanup."""

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._pids: dict[str, int] = {}
        self._start_times: dict[str, str] = {}

    async def start(
        self,
        run_id: str,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int = 600,
    ) -> dict[str, Any]:
        """Start a supervised subprocess in its own process group."""
        from ibreeze.security.process_security import minimal_env

        merged_env: dict[str, str] = {**minimal_env(), **(env or {})}

        actual_cmd = cmd
        if sys.platform == "darwin":
            actual_cmd = self._wrap_with_seatbelt(cmd)

        proc = await asyncio.create_subprocess_exec(
            *actual_cmd,
            cwd=cwd,
            env=merged_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        self._processes[run_id] = proc
        self._pids[run_id] = proc.pid
        self._start_times[run_id] = _now()

        pgid = None
        try:
            pgid = os.getpgid(proc.pid) if proc.pid else None
        except (ProcessLookupError, PermissionError):
            pass

        return {
            "run_id": run_id,
            "pid": proc.pid,
            "pgid": pgid,
            "started_at": self._start_times[run_id],
        }

    async def wait(self, run_id: str, timeout: int = 600) -> dict[str, Any]:
        """Wait for process completion with timeout."""
        proc = self._processes.get(run_id)
        if not proc:
            return {"error": "Process not found"}

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            exit_code = proc.returncode
            stdout_text = stdout.decode(errors="replace") if stdout else ""
            stderr_text = stderr.decode(errors="replace") if stderr else ""
            stdout_sha256 = hashlib.sha256(stdout_text.encode()).hexdigest()
            stderr_sha256 = hashlib.sha256(stderr_text.encode()).hexdigest()

            self._cleanup(run_id)

            return {
                "run_id": run_id,
                "exit_code": exit_code,
                "stdout_preview": stdout_text[:65536],
                "stderr_preview": stderr_text[:65536],
                "stdout_sha256": stdout_sha256,
                "stderr_sha256": stderr_sha256,
                "completed_at": _now(),
            }
        except TimeoutError:
            await self.kill(run_id)
            return {
                "run_id": run_id,
                "exit_code": -1,
                "error": "timeout",
                "completed_at": _now(),
            }

    async def kill(self, run_id: str) -> None:
        """Kill process group: SIGTERM → 5s → SIGKILL."""
        proc = self._processes.get(run_id)
        if not proc or proc.returncode is not None:
            self._cleanup(run_id)
            return

        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
            await asyncio.sleep(5)
            if proc.returncode is None:
                os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

        self._cleanup(run_id)

    def _wrap_with_seatbelt(self, cmd: list[str]) -> list[str]:
        """Wrap command with macOS sandbox-exec for least-privilege isolation.

        Uses a restrictive profile that denies network, file write outside workspace,
        and process injection while allowing stdin/stdout/stderr.
        """
        profile = (
            "(version 1)"
            "(deny default)"
            "(allow process-exec)"
            "(allow process-fork)"
            "(allow sysctl-read)"
            "(allow mach-lookup)"
            "(allow ipc-posix-shm-read-data ipc-posix-shm-write-data)"
            "(allow file-read* (subpath \"/usr\") (subpath \"/System\") (subpath \"/Library\"))"
            "(allow file-read* (subpath \"/private/tmp\"))"
            "(allow file-write* (subpath \"/private/tmp\") (subpath \"/private/var/folders\"))"
            "(allow network* (remote-ip \"127.0.0.1\"))"
            "(deny network*)"
        )
        return ["sandbox-exec", "-p", profile, *cmd]

    def _cleanup(self, run_id: str) -> None:
        self._processes.pop(run_id, None)
        self._pids.pop(run_id, None)
        self._start_times.pop(run_id, None)

    async def heartbeat_check(self, run_id: str) -> bool:
        """Check if process is still alive."""
        proc = self._processes.get(run_id)
        if not proc:
            return False
        return proc.returncode is None

    def get_pid(self, run_id: str) -> int | None:
        return self._pids.get(run_id)

    def get_start_time(self, run_id: str) -> str | None:
        return self._start_times.get(run_id)


_supervisor: ProcessSupervisor | None = None


def get_supervisor() -> ProcessSupervisor:
    global _supervisor
    if _supervisor is None:
        _supervisor = ProcessSupervisor()
    return _supervisor
