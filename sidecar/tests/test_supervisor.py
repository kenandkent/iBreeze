"""SidecarProcess / Supervisor 单元测试。"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys

import pytest

from acos.supervisor import SidecarProcess, Supervisor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def socket_path(tmp_path: object) -> str:
    path = f"/tmp/acos_supervisor_test_{os.getpid()}_{id(object())}.sock"
    yield path
    if os.path.exists(path):
        os.unlink(path)


def _helper_command(socket_path: str) -> list[str]:
    return [sys.executable, "-m", "tests._sidecar_helper", socket_path]


# ---------------------------------------------------------------------------
# SidecarProcess
# ---------------------------------------------------------------------------


async def test_sidecar_process_start_stop(socket_path: str) -> None:
    proc = SidecarProcess(command=_helper_command(socket_path), socket_path=socket_path)
    await proc.start()
    assert proc.is_running

    await proc.stop()
    assert not proc.is_running


async def test_health_check_success(socket_path: str) -> None:
    proc = SidecarProcess(command=_helper_command(socket_path), socket_path=socket_path)
    await proc.start()
    try:
        assert await proc.health_check() is True
    finally:
        await proc.stop()


async def test_health_check_failure(socket_path: str) -> None:
    proc = SidecarProcess(
        command=_helper_command(socket_path), socket_path="/tmp/nonexistent.sock"
    )
    assert await proc.health_check() is False


async def test_restart_backoff() -> None:
    proc = SidecarProcess(command=["echo"], socket_path="/tmp/x.sock")
    assert proc._calculate_backoff() == 1.0
    proc._consecutive_failures = 1
    assert proc._calculate_backoff() == 2.0
    proc._consecutive_failures = 2
    assert proc._calculate_backoff() == 4.0
    proc._consecutive_failures = 3
    assert proc._calculate_backoff() == 8.0
    proc._consecutive_failures = 10
    assert proc._calculate_backoff() == 60.0


async def test_restart_backoff_resets_on_health(socket_path: str) -> None:
    proc = SidecarProcess(command=_helper_command(socket_path), socket_path=socket_path)
    await proc.start()
    try:
        for _ in range(5):
            await proc.health_check()
        assert proc._consecutive_failures == 0
        assert proc._calculate_backoff() == 1.0
    finally:
        await proc.stop()


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------


async def test_supervisor_start_all(socket_path: str) -> None:
    sock_a = socket_path + ".a"
    sock_b = socket_path + ".b"
    for s in (sock_a, sock_b):
        if os.path.exists(s):
            os.unlink(s)

    sup = Supervisor()
    await sup.register("a", SidecarProcess(command=_helper_command(sock_a), socket_path=sock_a))
    await sup.register("b", SidecarProcess(command=_helper_command(sock_b), socket_path=sock_b))
    await sup.start_all()

    assert sup._processes["a"].is_running
    assert sup._processes["b"].is_running

    await sup.stop_all()
    for s in (sock_a, sock_b):
        if os.path.exists(s):
            os.unlink(s)


async def test_supervisor_stop_all(socket_path: str) -> None:
    sock_a = socket_path + ".a"
    sock_b = socket_path + ".b"
    for s in (sock_a, sock_b):
        if os.path.exists(s):
            os.unlink(s)

    sup = Supervisor()
    await sup.register("a", SidecarProcess(command=_helper_command(sock_a), socket_path=sock_a))
    await sup.register("b", SidecarProcess(command=_helper_command(sock_b), socket_path=sock_b))
    await sup.start_all()
    await sup.stop_all()

    assert not sup._processes["a"].is_running
    assert not sup._processes["b"].is_running

    for s in (sock_a, sock_b):
        if os.path.exists(s):
            os.unlink(s)


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------


async def test_graceful_shutdown(socket_path: str) -> None:
    proc = SidecarProcess(command=_helper_command(socket_path), socket_path=socket_path)
    await proc.start()
    assert proc.is_running

    await proc.stop()

    await asyncio.sleep(0.5)
    assert not proc.is_running


# ---------------------------------------------------------------------------
# Force kill on timeout
# ---------------------------------------------------------------------------


async def test_force_kill_on_timeout(socket_path: str) -> None:
    """Child ignores SIGTERM → supervisor escalates to SIGKILL."""

    helper = (
        "import asyncio, json, os, signal, sys"
        "\nfrom datetime import datetime, timezone"
        "\ndef log_event(e, **kw):"
        "\n    print(json.dumps({'ts': datetime.now(timezone.utc).isoformat(),"
        "\n        'level': 'info', 'event': e, **kw}), flush=True)"
        "\nasync def run(sp):"
        "\n    from acos.rpc.server import RPCServer"
        "\n    s = RPCServer(socket_path=sp)"
        "\n    await s.start()"
        "\n    log_event('helper.ignore_sigterm.started', socket=sp)"
        "\n    signal.signal(signal.SIGTERM, signal.SIG_IGN)"
        "\n    while True: await asyncio.sleep(60)"
        "\nif __name__ == '__main__': asyncio.run(run(sys.argv[1]))"
    )

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", helper, socket_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )

    deadline = asyncio.get_event_loop().time() + 30.0
    while asyncio.get_event_loop().time() < deadline:
        if os.path.exists(socket_path):
            break
        await asyncio.sleep(0.1)
    else:
        proc.kill()
        await proc.wait()
        pytest.skip("Helper socket did not appear in time")

    sp = SidecarProcess(command=["noop"], socket_path=socket_path)
    sp._process = proc

    await sp.stop()
    await asyncio.sleep(0.5)
    assert not sp.is_running

    if os.path.exists(socket_path):
        os.unlink(socket_path)
