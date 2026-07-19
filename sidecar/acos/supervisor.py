"""Sidecar 进程生命周期管理 (Supervisor)。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def log_event(event: str, **kwargs: object) -> None:
    """输出结构化 JSON 日志。"""
    import json as _json
    from datetime import datetime as _dt, timezone as _tz

    record = {
        "ts": _dt.now(_tz.utc).isoformat(),
        "level": "info",
        "event": event,
        **kwargs,
    }
    print(_json.dumps(record), flush=True)


@dataclass
class RestartRecord:
    """重启记录。"""

    timestamp: str
    reason: str
    restart_count: int
    backoff_delay: float


class SidecarProcess:
    """管理单个 sidecar 进程的生命周期。"""

    def __init__(
        self,
        command: list[str],
        socket_path: str,
        *,
        health_check_interval: float = 5.0,
        max_backoff: float = 60.0,
        shutdown_timeout: float = 10.0,
    ) -> None:
        self._command = command
        self._socket_path = socket_path
        self._process: asyncio.subprocess.Process | None = None
        self._restart_count = 0
        self._consecutive_failures = 0
        self._max_backoff = max_backoff
        self._health_check_interval = health_check_interval
        self._shutdown_timeout = shutdown_timeout
        self._restart_history: list[RestartRecord] = []
        self._shutdown_event: asyncio.Event | None = None

    async def start(self) -> None:
        """启动子进程。"""
        if self._process is not None and self._process.returncode is None:
            return

        self._process = await asyncio.create_subprocess_exec(
            *self._command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        log_event(
            "sidecar.process.started",
            pid=self._process.pid,
            command=self._command,
        )

        await self._wait_for_socket(timeout=30.0)

    async def stop(self) -> None:
        """优雅关闭: sys.shutdown → SIGTERM → SIGKILL。"""
        if self._process is None or self._process.returncode is not None:
            return

        pid = self._process.pid
        try:
            await self._rpc_call("sys.shutdown", {}, timeout=5.0)
            log_event("sidecar.shutdown.requested", pid=pid)

            try:
                await asyncio.wait_for(
                    self._process.wait(), timeout=self._shutdown_timeout
                )
                log_event("sidecar.process.stopped", pid=pid, method="graceful")
                return
            except asyncio.TimeoutError:
                pass
        except (ConnectionError, OSError, asyncio.TimeoutError):
            pass

        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            log_event("sidecar.process.sigterm", pid=pid)
            await asyncio.wait_for(
                self._process.wait(), timeout=self._shutdown_timeout
            )
            log_event("sidecar.process.stopped", pid=pid, method="sigterm")
            return
        except (ProcessLookupError, asyncio.TimeoutError, OSError):
            pass

        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
            log_event("sidecar.process.sigkill", pid=pid)
        except (ProcessLookupError, OSError):
            pass

        try:
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except (asyncio.TimeoutError, ProcessLookupError):
            pass

        log_event("sidecar.process.stopped", pid=pid, method="force")

    async def health_check(self) -> bool:
        """通过 UDS 调用 sys.health 检查健康状态。"""
        try:
            result = await self._rpc_call("sys.health", {}, timeout=5.0)
            healthy = result.get("status") == "healthy"
            if healthy:
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
            return healthy
        except (ConnectionError, OSError, asyncio.TimeoutError):
            self._consecutive_failures += 1
            return False

    async def restart(self, reason: str) -> None:
        """重启进程（指数退避）。"""
        self._restart_count += 1
        delay = self._calculate_backoff()

        record = RestartRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=reason,
            restart_count=self._restart_count,
            backoff_delay=delay,
        )
        self._restart_history.append(record)
        log_event(
            "sidecar.process.restarting",
            reason=reason,
            restart_count=self._restart_count,
            backoff_delay=delay,
        )

        await self.stop()
        await asyncio.sleep(delay)
        await self.start()

    def _calculate_backoff(self) -> float:
        """计算指数退避时间: 2, 4, 8, …, max 60s。连续成功后重置。"""
        delay = min(2 ** self._consecutive_failures, self._max_backoff)
        return float(delay)

    @property
    def is_running(self) -> bool:
        """进程是否正在运行。"""
        return self._process is not None and self._process.returncode is None

    @property
    def restart_count(self) -> int:
        return self._restart_count

    @property
    def restart_history(self) -> list[RestartRecord]:
        return list(self._restart_history)

    async def _rpc_call(
        self, method: str, params: dict, *, timeout: float = 5.0
    ) -> dict:
        """通过 UDS 发送 JSON-RPC 请求并返回 result。"""
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(self._socket_path),
            timeout=timeout,
        )
        try:
            request = {
                "type": "request",
                "id": f"supervisor-{method}",
                "method": method,
                "params": params,
            }
            writer.write((json.dumps(request) + "\n").encode())
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=timeout)
            if not line:
                raise ConnectionError("Server closed connection")

            response = json.loads(line.decode())
            if response.get("error"):
                raise ConnectionError(f"RPC error: {response['error']}")
            return response.get("result", {})
        finally:
            writer.close()
            await writer.wait_closed()

    async def _wait_for_socket(self, *, timeout: float = 30.0) -> None:
        """等待 UDS socket 文件出现。"""
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            if Path(self._socket_path).exists():
                return
            await asyncio.sleep(0.1)
        raise TimeoutError(
            f"Socket {self._socket_path} not available after {timeout}s"
        )


class Supervisor:
    """管理多个 SidecarProcess 实例。"""

    def __init__(self) -> None:
        self._processes: dict[str, SidecarProcess] = {}
        self._running = False
        self._stop_event = asyncio.Event()

    async def register(self, name: str, process: SidecarProcess) -> None:
        """注册一个进程。"""
        self._processes[name] = process

    async def start_all(self) -> None:
        """启动所有注册的进程。"""
        for name, process in self._processes.items():
            log_event("supervisor.starting_process", name=name)
            await process.start()

    async def stop_all(self) -> None:
        """停止所有进程。"""
        self._running = False
        self._stop_event.set()

        for name, process in self._processes.items():
            log_event("supervisor.stopping_process", name=name)
            try:
                await asyncio.wait_for(process.stop(), timeout=30.0)
            except asyncio.TimeoutError:
                log_event("supervisor.force_stop_timeout", name=name)

    async def run_forever(self) -> None:
        """主循环: 定期健康检查 + 自动重启。"""
        self._running = True
        self._stop_event.clear()

        while self._running:
            for name, process in self._processes.items():
                if not self._running:
                    break

                if not process.is_running:
                    log_event("supervisor.process_dead", name=name)
                    await process.restart(reason="process exited unexpectedly")
                    continue

                healthy = await process.health_check()
                if not healthy:
                    log_event("supervisor.health_check_failed", name=name)
                    await process.restart(reason="health check failed")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._processes[
                        next(iter(self._processes))
                    ]._health_check_interval
                    if self._processes
                    else 5.0,
                )
                break
            except asyncio.TimeoutError:
                pass
