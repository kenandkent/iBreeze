"""RPC Server 冒烟测试 - 验证 sys.health 及 echo 方法返回正确响应。"""

import asyncio
import json
import os

import pytest

from acos.rpc.methods import EchoMethods
from acos.rpc.server import RPCServer


@pytest.fixture
def socket_path() -> str:
    path = f"/tmp/acos_test_{os.getpid()}_{id(object())}.sock"
    yield path
    if os.path.exists(path):
        os.unlink(path)


def _make_server(socket_path: str) -> RPCServer:
    server = RPCServer(socket_path=socket_path)
    EchoMethods().register_to(server)
    return server


async def _send_and_recv(
    socket_path: str,
    method: str,
    params: dict,
    req_id: str = "test-1",
) -> dict:
    reader, writer = await asyncio.open_unix_connection(socket_path)
    try:
        request = {
            "type": "request",
            "id": req_id,
            "method": method,
            "params": params,
        }
        writer.write((json.dumps(request) + "\n").encode())
        await writer.drain()

        line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        return json.loads(line.decode())
    finally:
        writer.close()
        await writer.wait_closed()


async def test_sys_health(socket_path: str) -> None:
    server = _make_server(socket_path)
    await server.start()
    try:
        resp = await _send_and_recv(socket_path, "sys.health", {}, "test-1")
        assert resp["id"] == "test-1"
        assert resp["error"] is None
        assert resp["result"]["status"] == "healthy"
        assert resp["result"]["components"]["rpc"] == "up"
    finally:
        await server.stop()


async def test_method_not_found(socket_path: str) -> None:
    server = RPCServer(socket_path=socket_path)
    await server.start()
    try:
        resp = await _send_and_recv(
            socket_path, "unknown.method", {}, "test-2"
        )
        assert resp["id"] == "test-2"
        assert "Method not found" in resp["error"]
    finally:
        await server.stop()


async def test_echo_string(socket_path: str) -> None:
    server = _make_server(socket_path)
    await server.start()
    try:
        resp = await _send_and_recv(
            socket_path, "echo.string", {"value": "hello"}, "e1"
        )
        assert resp["error"] is None
        assert resp["result"]["value"] == "hello"
    finally:
        await server.stop()


async def test_echo_int(socket_path: str) -> None:
    server = _make_server(socket_path)
    await server.start()
    try:
        resp = await _send_and_recv(
            socket_path, "echo.int", {"value": 42}, "e2"
        )
        assert resp["error"] is None
        assert resp["result"]["value"] == 42
    finally:
        await server.stop()


async def test_echo_float(socket_path: str) -> None:
    server = _make_server(socket_path)
    await server.start()
    try:
        resp = await _send_and_recv(
            socket_path, "echo.float", {"value": 3.14}, "e3"
        )
        assert resp["error"] is None
        assert resp["result"]["value"] == pytest.approx(3.14)
    finally:
        await server.stop()


async def test_echo_bool(socket_path: str) -> None:
    server = _make_server(socket_path)
    await server.start()
    try:
        resp_true = await _send_and_recv(
            socket_path, "echo.bool", {"value": True}, "e4a"
        )
        assert resp_true["error"] is None
        assert resp_true["result"]["value"] is True

        resp_false = await _send_and_recv(
            socket_path, "echo.bool", {"value": False}, "e4b"
        )
        assert resp_false["error"] is None
        assert resp_false["result"]["value"] is False
    finally:
        await server.stop()


async def test_echo_array(socket_path: str) -> None:
    server = _make_server(socket_path)
    await server.start()
    try:
        arr = [1, "two", 3.0, None]
        resp = await _send_and_recv(
            socket_path, "echo.array", {"value": arr}, "e5"
        )
        assert resp["error"] is None
        assert resp["result"]["value"] == arr
    finally:
        await server.stop()


async def test_echo_object(socket_path: str) -> None:
    server = _make_server(socket_path)
    await server.start()
    try:
        obj = {"a": 1, "b": "two", "c": None}
        resp = await _send_and_recv(
            socket_path, "echo.object", {"value": obj}, "e6"
        )
        assert resp["error"] is None
        assert resp["result"]["value"] == obj
    finally:
        await server.stop()


async def test_echo_null(socket_path: str) -> None:
    server = _make_server(socket_path)
    await server.start()
    try:
        resp = await _send_and_recv(
            socket_path, "echo.null", {}, "e7"
        )
        assert resp["error"] is None
        assert resp["result"]["value"] is None
    finally:
        await server.stop()


async def test_echo_mirror(socket_path: str) -> None:
    server = _make_server(socket_path)
    await server.start()
    try:
        resp = await _send_and_recv(
            socket_path, "echo.mirror", {}, "e8"
        )
        assert resp["error"] is None
        assert resp["result"]["echo"] is True
    finally:
        await server.stop()
