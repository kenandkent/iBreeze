"""RPC 幂等键管理器与 trace_id 测试。"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from acos.rpc.idempotency import IdempotencyManager
from acos.rpc.server import RPCServer
from acos.rpc.errors import SYS_IDEMPOTENCY_CONFLICT, SYS_INTERNAL

# ── fixtures ──────────────────────────────────────────────────────────────

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS rpc_idempotency_records (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    method TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing' CHECK (status IN ('processing', 'succeeded', 'failed')),
    response_ref TEXT,
    error_ref TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_idempotency_unique ON rpc_idempotency_records(company_id, actor_type, actor_id, method, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON rpc_idempotency_records(expires_at);
"""


@pytest.fixture
async def db() -> aiosqlite.Connection:
    conn = await aiosqlite.connect(":memory:")
    await conn.executescript(MIGRATION_SQL)
    yield conn
    await conn.close()


@pytest.fixture
def manager() -> IdempotencyManager:
    return IdempotencyManager(retention_hours=24)


# ── 幂等键管理器测试 ─────────────────────────────────────────────────────


async def test_same_key_returns_same_result(db: aiosqlite.Connection, manager: IdempotencyManager) -> None:
    """同一 key 第二次调用应返回首次的结果。"""
    h = manager.compute_request_hash("create_order", {"item": "A"})

    # 第一次 — 预约
    result = await manager.check_and_reserve(db, "c1", "user", "u1", "create_order", "key-1", h)
    assert result is None

    # 完成
    await manager.complete(db, "c1", "user", "u1", "create_order", "key-1", "succeeded", result={"id": 1})

    # 第二次 — 返回缓存
    cached = await manager.check_and_reserve(db, "c1", "user", "u1", "create_order", "key-1", h)
    assert cached is not None
    assert cached["status"] == "succeeded"
    assert cached["response_ref"] == json.dumps({"id": 1})


async def test_different_keys_execute_independently(db: aiosqlite.Connection, manager: IdempotencyManager) -> None:
    """不同 key 应各自独立执行。"""
    h = manager.compute_request_hash("create_order", {"item": "A"})

    r1 = await manager.check_and_reserve(db, "c1", "user", "u1", "create_order", "key-a", h)
    assert r1 is None

    r2 = await manager.check_and_reserve(db, "c1", "user", "u1", "create_order", "key-b", h)
    assert r2 is None


async def test_different_company_no_share(db: aiosqlite.Connection, manager: IdempotencyManager) -> None:
    """不同公司的同一 key 不共享。"""
    h = manager.compute_request_hash("create_order", {"item": "A"})

    r1 = await manager.check_and_reserve(db, "c1", "user", "u1", "create_order", "k", h)
    assert r1 is None

    r2 = await manager.check_and_reserve(db, "c2", "user", "u1", "create_order", "k", h)
    assert r2 is None


async def test_conflicting_hash_rejected(db: aiosqlite.Connection, manager: IdempotencyManager) -> None:
    """相同 key 不同 request_hash 应抛 SYS-IDEMPOTENCY-CONFLICT。"""
    h1 = manager.compute_request_hash("create_order", {"item": "A"})
    h2 = manager.compute_request_hash("create_order", {"item": "B"})

    await manager.check_and_reserve(db, "c1", "user", "u1", "create_order", "k", h1)

    from acos.rpc.errors import AcosError
    with pytest.raises(AcosError) as exc_info:
        await manager.check_and_reserve(db, "c1", "user", "u1", "create_order", "k", h2)
    assert exc_info.value.code == SYS_IDEMPOTENCY_CONFLICT


async def test_expired_record_allows_reexecution(db: aiosqlite.Connection) -> None:
    """过期记录应允许重新执行。"""
    mgr = IdempotencyManager(retention_hours=-1)  # 已过期
    h = mgr.compute_request_hash("create_order", {"item": "A"})

    r1 = await mgr.check_and_reserve(db, "c1", "user", "u1", "create_order", "k", h)
    assert r1 is None

    # 用正常 manager（24h）检查 — 记录存在但未完成
    mgr2 = IdempotencyManager(retention_hours=24)
    r2 = await mgr2.check_and_reserve(db, "c1", "user", "u1", "create_order", "k", h)
    assert r2 is not None  # processing 状态返回已有记录

    # 清理过期记录
    deleted = await mgr.cleanup_expired(db)
    assert deleted >= 1

    # 清理后可重新执行
    r3 = await mgr2.check_and_reserve(db, "c1", "user", "u1", "create_order", "k", h)
    assert r3 is None


# ── trace_id 测试 ─────────────────────────────────────────────────────────

@pytest.fixture
def socket_path() -> str:
    path = f"/tmp/acos_rpc_idem_{os.getpid()}_{id(object())}.sock"
    yield path
    if os.path.exists(path):
        os.unlink(path)


async def _send_and_recv(socket_path: str, request: dict) -> dict:
    reader, writer = await asyncio.open_unix_connection(socket_path)
    try:
        writer.write((json.dumps(request) + "\n").encode())
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        return json.loads(line.decode())
    finally:
        writer.close()
        await writer.wait_closed()


async def test_trace_id_auto_generated(socket_path: str) -> None:
    """未提供 trace_id 时自动生成。"""
    server = RPCServer(socket_path=socket_path)
    await server.start()
    try:
        resp = await _send_and_recv(socket_path, {
            "type": "request",
            "id": "t1",
            "method": "sys.health",
            "params": {},
        })
        assert resp["trace_id"]
        assert len(resp["trace_id"]) == 32  # uuid4 hex
    finally:
        await server.stop()


async def test_trace_id_preserved(socket_path: str) -> None:
    """客户端提供的 trace_id 被保留在响应中。"""
    server = RPCServer(socket_path=socket_path)
    await server.start()
    try:
        resp = await _send_and_recv(socket_path, {
            "type": "request",
            "id": "t2",
            "method": "sys.health",
            "params": {},
            "trace_id": "my-custom-trace",
        })
        assert resp["trace_id"] == "my-custom-trace"
    finally:
        await server.stop()
