"""Sidecar 集成测试 - 验证完整启动/健康检查/关闭流程。"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

from acos.supervisor import SidecarProcess


@pytest.fixture
def socket_path() -> str:
    path = f"/tmp/acos_integration_test_{os.getpid()}_{id(object())}.sock"
    yield path
    if os.path.exists(path):
        os.unlink(path)


def _helper_command(sock: str) -> list[str]:
    return [sys.executable, "-m", "tests._sidecar_helper", sock]


async def test_health_check_over_uds(socket_path: str) -> None:
    """启动 sidecar，通过 UDS 调用 sys.health 验证服务可用。"""
    proc = SidecarProcess(command=_helper_command(socket_path), socket_path=socket_path)
    await proc.start()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(socket_path), timeout=5.0
        )
        try:
            request = {
                "type": "request",
                "id": "integ-health-1",
                "method": "sys.health",
                "params": {},
            }
            writer.write((json.dumps(request) + "\n").encode())
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            response = json.loads(line.decode())

            assert response["id"] == "integ-health-1"
            assert response["error"] is None
            assert response["result"]["status"] == "healthy"
            assert response["result"]["components"]["rpc"] == "up"
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await proc.stop()


async def test_graceful_shutdown_over_uds(socket_path: str) -> None:
    """启动 sidecar，调用 sys.shutdown，验证优雅关闭。"""
    proc = SidecarProcess(command=_helper_command(socket_path), socket_path=socket_path)
    await proc.start()
    assert proc.is_running

    reader, writer = await asyncio.wait_for(
        asyncio.open_unix_connection(socket_path), timeout=5.0
    )
    try:
        request = {
            "type": "request",
            "id": "integ-shutdown-1",
            "method": "sys.shutdown",
            "params": {},
        }
        writer.write((json.dumps(request) + "\n").encode())
        await writer.drain()

        line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        response = json.loads(line.decode())

        assert response["id"] == "integ-shutdown-1"
        assert response["error"] is None
        assert response["result"]["status"] == "shutting_down"
    finally:
        writer.close()
        await writer.wait_closed()

    try:
        await asyncio.wait_for(proc._process.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        pytest.fail("Sidecar did not exit within timeout after sys.shutdown")

    assert not proc.is_running
    assert not os.path.exists(socket_path)
