"""Authenticated UDS framing and JSON-RPC contract tests."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from ibreeze.local_db import LocalDB
from ibreeze.rpc_server import PROTOCOL_VERSION, RPCServer


def _uuid() -> str:
    return str(uuid.uuid4())


def _meta(
    *,
    ipc_session_id: str | None,
    idempotency_key: str | None,
) -> dict[str, str | None]:
    return {
        "trace_id": _uuid(),
        "ipc_session_id": ipc_session_id,
        "window_session_id": _uuid(),
        "idempotency_key": idempotency_key,
    }


def _request(
    method: str,
    params: dict[str, object],
    meta: dict[str, str | None],
) -> dict[str, object]:
    return {
        "jsonrpc": "2.0",
        "id": f"core:{_uuid()}",
        "method": method,
        "params": params,
        "meta": meta,
    }


async def _handshake(
    server: RPCServer,
    token: bytes,
    launch_id: str,
) -> str:
    nonce = base64.b64encode(b"n" * 32).decode()
    message = (
        b"1.0.0"
        + str(PROTOCOL_VERSION).encode()
        + launch_id.encode()
        + nonce.encode()
    )
    proof = base64.b64encode(
        hmac.new(token, message, hashlib.sha256).digest()
    ).decode()
    response = await server._handle_request(
        _request(
            "system.handshake",
            {
                "app_version": "1.0.0",
                "protocol_version": PROTOCOL_VERSION,
                "launch_id": launch_id,
                "nonce": nonce,
                "proof": proof,
            },
            _meta(ipc_session_id=None, idempotency_key=None),
        )
    )
    return str(response["result"]["ipc_session_id"])  # type: ignore[index]


@pytest.fixture
def server_factory(local_db: LocalDB, tmp_path: Path):
    servers: list[RPCServer] = []

    def factory() -> tuple[RPCServer, bytes, str]:
        token = b"s" * 32
        launch_id = _uuid()
        server = RPCServer(
            local_db,
            tmp_path / f"{launch_id}.sock",
            startup_token=token,
            launch_id=launch_id,
            app_version="1.0.0",
        )
        servers.append(server)
        return server, token, launch_id

    return factory


@pytest.mark.asyncio
async def test_handshake_health_and_method_partition(server_factory: Any) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    health = await server._handle_request(
        _request(
            "system.health",
            {},
            _meta(ipc_session_id=session, idempotency_key=None),
        )
    )
    assert health["result"]["status"] == "healthy"  # type: ignore[index]
    unknown = await server._handle_request(
        _request(
            "auth.login",
            {},
            _meta(ipc_session_id=session, idempotency_key=_uuid()),
        )
    )
    assert unknown["error"]["code"] == -32601  # type: ignore[index]


@pytest.mark.asyncio
async def test_write_requires_uuid_idempotency_key(
    server_factory: Any,
    published_profile: str,
) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    response = await server._handle_request(
        _request(
            "company.create",
            {
                "name": "无幂等键",
                "introduction": "应拒绝",
                "general_manager_name": "总经理",
                "base_profile_version_id": published_profile,
            },
            _meta(ipc_session_id=session, idempotency_key=None),
        )
    )
    assert response["error"]["data"]["code"] == "VALIDATION_FAILED"  # type: ignore[index]


@pytest.mark.asyncio
async def test_command_and_idempotency_result_are_replayed_atomically(
    server_factory: Any,
    published_profile: str,
) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    key = _uuid()
    params = {
        "name": "RPC 公司",
        "introduction": "验证同事务幂等",
        "general_manager_name": "总经理",
        "base_profile_version_id": published_profile,
    }
    first = await server._handle_request(
        _request(
            "company.create",
            params,
            _meta(ipc_session_id=session, idempotency_key=key),
        )
    )
    second = await server._handle_request(
        _request(
            "company.create",
            params,
            _meta(ipc_session_id=session, idempotency_key=key),
        )
    )
    assert first["result"] == second["result"]
    assert (
        await server.db.fetch_val(
            "SELECT COUNT(*) FROM companies WHERE normalized_name='rpc 公司'"
        )
    ) == 1
    conflict = await server._handle_request(
        _request(
            "company.create",
            {**params, "name": "不同请求"},
            _meta(ipc_session_id=session, idempotency_key=key),
        )
    )
    assert conflict["error"]["data"]["code"] == "IDEMPOTENCY_CONFLICT"  # type: ignore[index]


@pytest.mark.asyncio
async def test_result_persistence_failure_rolls_back_domain_write(
    server_factory: Any,
    published_profile: str,
) -> None:
    server, token, launch_id = server_factory()
    session = await _handshake(server, token, launch_id)
    await server.db.write_connection.execute(
        """CREATE TRIGGER reject_completed_idempotency
           BEFORE UPDATE OF status ON rpc_idempotency
           WHEN NEW.status='completed'
           BEGIN SELECT RAISE(ABORT, 'forced result failure'); END"""
    )
    await server.db.write_connection.commit()
    response = await server._handle_request(
        _request(
            "company.create",
            {
                "name": "必须回滚",
                "introduction": "结果无法落盘",
                "general_manager_name": "总经理",
                "base_profile_version_id": published_profile,
            },
            _meta(ipc_session_id=session, idempotency_key=_uuid()),
        )
    )
    assert response["error"]["data"]["code"] == "INTERNAL_ERROR"  # type: ignore[index]
    assert await server.db.fetch_val("SELECT COUNT(*) FROM companies") == 0


@pytest.mark.asyncio
async def test_uds_uses_four_byte_big_endian_frames(
    server_factory: Any,
) -> None:
    server, token, launch_id = server_factory()
    server.socket_path = Path.cwd() / f".rpc-{launch_id[:8]}.sock"
    await server.start()
    try:
        reader, writer = await asyncio.open_unix_connection(
            str(server.socket_path)
        )
        nonce = base64.b64encode(b"n" * 32).decode()
        message = (
            b"1.0.0"
            + str(PROTOCOL_VERSION).encode()
            + launch_id.encode()
            + nonce.encode()
        )
        request = _request(
            "system.handshake",
            {
                "app_version": "1.0.0",
                "protocol_version": PROTOCOL_VERSION,
                "launch_id": launch_id,
                "nonce": nonce,
                "proof": base64.b64encode(
                    hmac.new(token, message, hashlib.sha256).digest()
                ).decode(),
            },
            _meta(ipc_session_id=None, idempotency_key=None),
        )
        payload = json.dumps(request, separators=(",", ":")).encode()
        writer.write(len(payload).to_bytes(4, "big") + payload)
        await writer.drain()
        size = int.from_bytes(await reader.readexactly(4), "big")
        response = json.loads(await reader.readexactly(size))
        assert response["result"]["database_status"] == "ready"
        writer.close()
        await writer.wait_closed()
    finally:
        await server.close()
