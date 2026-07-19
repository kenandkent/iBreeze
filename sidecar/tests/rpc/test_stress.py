"""RPC Echo 压力测试 - 并发客户端场景。"""

import asyncio
import json
import os
import time

import pytest

from acos.rpc.methods import EchoMethods
from acos.rpc.server import RPCServer


@pytest.fixture
def socket_path() -> str:
    path = f"/tmp/acos_stress_{os.getpid()}_{id(object())}.sock"
    yield path
    if os.path.exists(path):
        os.unlink(path)


async def _client_worker(
    socket_path: str,
    client_id: int,
    count: int,
) -> list[tuple[int, int, str]]:
    """单个客户端：建立一次连接，发送 count 个 echo.string 请求。"""
    reader, writer = await asyncio.open_unix_connection(socket_path)
    results: list[tuple[int, int, str]] = []
    try:
        for seq in range(count):
            value = f"client-{client_id}-seq-{seq}"
            request = {
                "type": "request",
                "id": f"s-{client_id}-{seq}",
                "method": "echo.string",
                "params": {"value": value},
            }
            writer.write((json.dumps(request) + "\n").encode())
            await writer.drain()

            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            response = json.loads(line.decode())
            assert response["error"] is None, f"Client {client_id} seq {seq}: {response['error']}"
            assert response["result"]["value"] == value
            results.append((client_id, seq, value))
    finally:
        writer.close()
        await writer.wait_closed()
    return results


async def test_concurrent_echo_string(socket_path: str) -> None:
    """并发 10 个客户端，每个发送 100 个 echo.string 请求，10 秒内完成。"""
    server = RPCServer(socket_path=socket_path)
    EchoMethods().register_to(server)
    await server.start()

    try:
        start = time.monotonic()
        tasks = [
            _client_worker(socket_path, client_id, 100)
            for client_id in range(10)
        ]
        results = await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        flat = [item for sublist in results for item in sublist]
        assert len(flat) == 1000

        for client_id, seq, value in flat:
            assert value == f"client-{client_id}-seq-{seq}"

        assert elapsed < 10.0, f"Stress test took {elapsed:.2f}s, exceeded 10s limit"
    finally:
        await server.stop()
