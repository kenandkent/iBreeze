"""JSON-RPC 2.0 over Unix Domain Socket 服务端实现。"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
import uuid
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from acos.rpc.errors import AcosError, SYS_INTERNAL
from acos.rpc.idempotency import IdempotencyManager

logger = logging.getLogger(__name__)

# Type alias for RPC method handlers
RPCHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]

# 写方法前缀 — 匹配的方法自动检查幂等键
_WRITE_PREFIXES = ("create", "update", "delete", "set", "add", "remove", "submit", "approve", "reject")


class RPCServer:
    """NDJSON-framed JSON-RPC 2.0 服务端。

    消息格式:
        {"type": "request", "id": str, "method": str, "params": dict}
        {"type": "response", "id": str, "result": dict | null, "error": str | null}

    标准请求字段:
        trace_id: 可选，客户端提供的追踪 ID，缺失时自动生成
        idempotency_key: 可选，幂等键，写方法必须提供
    """

    def __init__(
        self,
        socket_path: str = "/tmp/acos.sock",
        db_conn_factory: Callable[[], Coroutine[Any, Any, Any]] | None = None,
    ) -> None:
        self._socket_path = socket_path
        self._db_conn_factory = db_conn_factory
        self._handlers: dict[str, RPCHandler] = {}
        self._server: asyncio.AbstractServer | None = None
        self._client_connected = False
        self._shutdown_event: asyncio.Event | None = None
        self._idempotency = IdempotencyManager()

        self._register_builtin_methods()

    def _register_builtin_methods(self) -> None:
        self._handlers["sys.health"] = self._handle_sys_health
        self._handlers["sys.shutdown"] = self._handle_sys_shutdown

    def register_method(self, name: str, handler: RPCHandler) -> None:
        self._handlers[name] = handler

    async def complete_idempotency(
        self,
        conn: Any,
        company_id: str,
        actor_type: str,
        actor_id: str,
        method: str,
        idempotency_key: str,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        """完成幂等记录（供 handler 调用）。"""
        await self._idempotency.complete(
            conn, company_id, actor_type, actor_id, method,
            idempotency_key, status, result, error,
        )

    @property
    def shutdown_event(self) -> asyncio.Event:
        if self._shutdown_event is None:
            self._shutdown_event = asyncio.Event()
        return self._shutdown_event

    async def _handle_sys_health(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "healthy", "components": {"rpc": "up"}}

    async def _handle_sys_shutdown(self, _params: dict[str, Any]) -> dict[str, Any]:
        self.shutdown_event.set()
        return {"status": "shutting_down"}

    async def start(self) -> None:
        path = Path(self._socket_path)
        if path.exists():
            path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            str(path),
        )

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        path = Path(self._socket_path)
        if path.exists():
            path.unlink()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._client_connected = True
        logger.info("Client connected to RPC server")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                except json.JSONDecodeError as exc:
                    response = {
                        "type": "response",
                        "id": None,
                        "result": None,
                        "error": f"Invalid JSON: {exc}",
                    }
                    writer.write((json.dumps(response) + "\n").encode())
                    await writer.drain()
                    continue

                response = await self._dispatch(request)
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()
        finally:
            self._client_connected = False
            writer.close()
            await writer.wait_closed()

    def _is_write_method(self, method: str) -> bool:
        """判断方法是否为写方法（需要幂等键检查）。"""
        return any(method.startswith(p) for p in _WRITE_PREFIXES)

    async def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        # trace_id: 客户端提供或自动生成
        trace_id = request.get("trace_id") or uuid.uuid4().hex

        if not method:
            return {
                "type": "response",
                "id": req_id,
                "result": None,
                "error": "Missing method field",
            }

        handler = self._handlers.get(method)
        if not handler:
            return {
                "type": "response",
                "id": req_id,
                "result": None,
                "error": f"Method not found: {method}",
            }

        # 写方法 + 提供了 idempotency_key → 先预约幂等记录
        idempotency_key = request.get("idempotency_key")
        ide_reserved = False
        if self._is_write_method(method) and idempotency_key:
            if self._db_conn_factory is None:
                return {
                    "type": "response",
                    "id": req_id,
                    "trace_id": trace_id,
                    "result": None,
                    "error": {
                        "code": SYS_INTERNAL,
                        "message": "幂等检查需要数据库连接",
                        "cause": "",
                        "suggestion": "",
                        "trace_id": trace_id,
                    },
                }
            conn = await self._db_conn_factory()
            try:
                request_hash = self._idempotency.compute_request_hash(method, params)
                cached = await self._idempotency.check_and_reserve(
                    conn,
                    company_id=params.get("_company_id", ""),
                    actor_type=params.get("_actor_type", ""),
                    actor_id=params.get("_actor_id", ""),
                    method=method,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                )
                if cached is not None:
                    # 命中已有幂等记录，直接返回缓存结果，不重跑 handler
                    return {
                        "type": "response",
                        "id": req_id,
                        "trace_id": trace_id,
                        "result": {
                            "cached": True,
                            "status": cached["status"],
                            "response_ref": cached["response_ref"],
                        },
                        "error": None,
                    }
                ide_reserved = True
            finally:
                await conn.close()

        try:
            result = await handler(params)
        except AcosError as exc:
            exc.trace_id = exc.trace_id or trace_id
            response = {
                "type": "response",
                "id": req_id,
                "trace_id": trace_id,
                "result": None,
                "error": exc.to_dict(),
            }
            await self._complete_idempotency(
                ide_reserved, idempotency_key, method, params, trace_id,
                status="failed", error_code=exc.code,
            )
            return response
        except Exception as exc:
            logger.exception("Unhandled exception in RPC handler %s", method)
            response = {
                "type": "response",
                "id": req_id,
                "trace_id": trace_id,
                "result": None,
                "error": {
                    "code": SYS_INTERNAL,
                    "message": "系统内部错误",
                    "cause": "",
                    "suggestion": "请联系管理员",
                    "trace_id": trace_id,
                },
            }
            await self._complete_idempotency(
                ide_reserved, idempotency_key, method, params, trace_id,
                status="failed", error_code=SYS_INTERNAL,
            )
            return response

        # handler 成功：回填幂等结果
        await self._complete_idempotency(
            ide_reserved, idempotency_key, method, params, trace_id,
            status="succeeded", result=result,
        )
        return {
            "type": "response",
            "id": req_id,
            "trace_id": trace_id,
            "result": result,
            "error": None,
        }

    async def _complete_idempotency(
        self,
        reserved: bool,
        idempotency_key: str | None,
        method: str,
        params: dict[str, Any],
        trace_id: str,
        status: str,
        result: dict | None = None,
        error_code: str | None = None,
    ) -> None:
        """若本请求预约了幂等记录，统一回填结果/失败状态（E2E-99 步骤1）。"""
        if not reserved or not idempotency_key or self._db_conn_factory is None:
            return
        try:
            conn = await self._db_conn_factory()
            try:
                await self._idempotency.complete(
                    conn,
                    company_id=params.get("_company_id", ""),
                    actor_type=params.get("_actor_type", ""),
                    actor_id=params.get("_actor_id", ""),
                    method=method,
                    idempotency_key=idempotency_key,
                    status=status,
                    result=result,
                    error=error_code,
                )
            finally:
                await conn.close()
        except Exception:  # 幂等回填失败不应影响主响应
            logger.exception("幂等记录回填失败 method=%s key=%s", method, idempotency_key)
