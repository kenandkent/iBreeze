"""JSON-RPC 2.0 Server，TCP 方式提供所有业务方法。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from ibreeze.local_db import LocalDB


def _now_iso() -> str:
    """返回当前 UTC 时间的 RFC 3339 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _uuid4() -> str:
    """生成 UUID v4 字符串。"""
    return str(uuid.uuid4())


def _sha256(content: str) -> str:
    """计算 SHA-256 哈希。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class RPCError(Exception):
    """JSON-RPC 业务错误。"""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.data = data


# ---- 字段校验工具 ----

_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_RE_PHONE = re.compile(r"^\+[1-9]\d{10,14}$")
_RE_UNIFIED_CREDIT_CODE = re.compile(r"^[A-Z0-9]{18}$", re.IGNORECASE)
_RE_ID_CARD = re.compile(r"^\d{17}[\dXx]$")


def _validate_email(value: str) -> None:
    if not _RE_EMAIL.match(value):
        raise RPCError(-32602, "邮箱格式无效")


def _validate_phone(value: str) -> None:
    if not _RE_PHONE.match(value):
        raise RPCError(-32602, "手机号格式无效（需要 E.164 格式，+开头）")


def _validate_unified_credit_code(value: str) -> None:
    if not _RE_UNIFIED_CREDIT_CODE.match(value):
        raise RPCError(-32602, "统一社会信用代码必须为 18 位字母数字")


def _validate_id_card(value: str) -> None:
    if not _RE_ID_CARD.match(value):
        raise RPCError(-32602, "身份证号必须为 18 位（最后一位可为 X）")


def _validate_required(params: dict[str, Any], fields: list[str]) -> None:
    """校验必填字段。"""
    for field in fields:
        if field not in params or params[field] is None:
            raise RPCError(-32602, f"缺少必填字段: {field}")


class RPCServer:
    """JSON-RPC 2.0 TCP 服务器。"""

    def __init__(
        self, db: LocalDB, host: str = "127.0.0.1", port: int = 51890
    ) -> None:
        self.db = db
        self.host = host
        self.port = port
        self.methods: dict[str, Callable[..., Any]] = {}
        self._server: asyncio.Server | None = None
        self._register_methods()

    def _register_methods(self) -> None:
        """注册所有 RPC 方法。"""
        # 系统方法
        self.methods["ping"] = self._ping
        self.methods["health"] = self._health
        self.methods["version"] = self._version

        # Company 方法
        self.methods["company.create"] = self._company_create
        self.methods["company.list"] = self._company_list
        self.methods["company.get"] = self._company_get
        self.methods["company.update"] = self._company_update
        self.methods["company.delete"] = self._company_delete

        # Conversation 方法
        self.methods["conversation.create"] = self._conversation_create
        self.methods["conversation.list"] = self._conversation_list
        self.methods["conversation.get"] = self._conversation_get
        self.methods["conversation.update"] = self._conversation_update
        self.methods["conversation.delete"] = self._conversation_delete
        self.methods["conversation.archive"] = self._conversation_archive
        self.methods["conversation.message.add"] = self._conversation_message_add
        self.methods["conversation.message.list"] = self._conversation_message_list

        # Knowledge 方法
        self.methods["knowledge.create"] = self._knowledge_create
        self.methods["knowledge.list"] = self._knowledge_list
        self.methods["knowledge.get"] = self._knowledge_get
        self.methods["knowledge.update"] = self._knowledge_update
        self.methods["knowledge.archive"] = self._knowledge_archive
        self.methods["knowledge.search"] = self._knowledge_search

        # Workspace 方法
        self.methods["workspace.create"] = self._workspace_create
        self.methods["workspace.list"] = self._workspace_list
        self.methods["workspace.get"] = self._workspace_get
        self.methods["workspace.update"] = self._workspace_update
        self.methods["workspace.delete"] = self._workspace_delete
        self.methods["workspace.member.add"] = self._workspace_member_add
        self.methods["workspace.member.remove"] = self._workspace_member_remove
        self.methods["workspace.member.list"] = self._workspace_member_list

        # Orchestration 方法
        self.methods["orchestration.create"] = self._orchestration_create
        self.methods["orchestration.list"] = self._orchestration_list
        self.methods["orchestration.get"] = self._orchestration_get
        self.methods["orchestration.update"] = self._orchestration_update
        self.methods["orchestration.delete"] = self._orchestration_delete
        self.methods["orchestration.node.add"] = self._orchestration_node_add
        self.methods["orchestration.node.remove"] = self._orchestration_node_remove
        self.methods["orchestration.edge.add"] = self._orchestration_edge_add
        self.methods["orchestration.run"] = self._orchestration_run
        self.methods["orchestration.run.history"] = self._orchestration_run_history

        # Employee 方法
        self.methods["employee.create"] = self._employee_create
        self.methods["employee.list"] = self._employee_list
        self.methods["employee.get"] = self._employee_get
        self.methods["employee.update"] = self._employee_update
        self.methods["employee.delete"] = self._employee_delete
        self.methods["department.list"] = self._department_list
        self.methods["department.create"] = self._department_create

        # Agent 方法
        self.methods["agent.run"] = self._agent_run
        self.methods["agent.status"] = self._agent_status
        self.methods["agent.list"] = self._agent_list
        self.methods["agent.stop"] = self._agent_stop

        # Audit 方法
        self.methods["audit.log"] = self._audit_log
        self.methods["audit.query"] = self._audit_query
        self.methods["audit.export"] = self._audit_export

    # ---- 请求处理 ----

    async def _handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """处理单个 JSON-RPC 2.0 请求。"""
        req_id = request.get("id")
        if request.get("jsonrpc") != "2.0":
            return _error_response(req_id, -32600, "无效的 JSON-RPC 版本")

        method_name = request.get("method")
        params = request.get("params", {})
        if not isinstance(params, dict):
            return _error_response(req_id, -32602, "params 必须是对象")

        if method_name not in self.methods:
            return _error_response(req_id, -32601, f"方法未找到: {method_name}")

        try:
            handler = self.methods[method_name]
            result = await handler(params)
            return {"jsonrpc": "2.0", "result": result, "id": req_id}
        except RPCError as e:
            return _error_response(req_id, e.code, e.message, e.data)
        except Exception:
            tb = traceback.format_exc()
            return _error_response(req_id, -32603, "内部错误", {"trace": tb})

    # ---- TCP 服务器 ----

    async def start(self) -> None:
        """启动 TCP 服务器。"""
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """处理单个 TCP 连接，每行一个 JSON 对象。"""
        addr = writer.get_extra_info("peername")
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    request = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    resp = _error_response(None, -32700, f"解析错误: {exc}")
                else:
                    resp = await self._handle_request(request)
                writer.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
                await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    # ---- 系统方法 ----

    async def _ping(self, _params: dict[str, Any]) -> dict[str, str]:
        return {"pong": "pong"}

    async def _health(self, _params: dict[str, Any]) -> dict[str, str]:
        return {"status": "healthy", "database_status": "ready"}

    async def _version(self, _params: dict[str, Any]) -> dict[str, str]:
        return {"version": "0.1.0", "protocol_version": "1"}

    # ---- Company 方法 ----

    async def _company_create(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["name"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "name": params["name"],
            "email": params.get("email"),
            "phone": params.get("phone"),
            "unified_credit_code": params.get("unified_credit_code"),
            "business_license_url": params.get("business_license_url"),
            "legal_rep_id_card": params.get("legal_rep_id_card"),
            "industry": params.get("industry"),
            "address": params.get("address"),
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        if data["email"]:
            _validate_email(data["email"])
        if data["phone"]:
            _validate_phone(data["phone"])
        if data["unified_credit_code"]:
            _validate_unified_credit_code(data["unified_credit_code"])
        if data["legal_rep_id_card"]:
            _validate_id_card(data["legal_rep_id_card"])
        return await self.db.insert("companies", data)

    async def _company_list(self, params: dict[str, Any]) -> dict[str, Any]:
        filters = {}
        if "status" in params:
            filters["status"] = params["status"]
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        items = await self.db.list_all("companies", filters, limit, offset)
        total = await self.db.count("companies", filters)
        return {"items": items, "total": total}

    async def _company_get(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        result = await self.db.get_by_id("companies", params["id"])
        if result is None:
            raise RPCError(-32602, "公司不存在")
        return result

    async def _company_update(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        now = _now_iso()
        update_data: dict[str, Any] = {"updated_at": now}
        allowed = [
            "name", "email", "phone", "unified_credit_code",
            "business_license_url", "legal_rep_id_card", "industry",
            "address", "status",
        ]
        for field in allowed:
            if field in params:
                update_data[field] = params[field]
        if "email" in update_data and update_data["email"]:
            _validate_email(update_data["email"])
        if "phone" in update_data and update_data["phone"]:
            _validate_phone(update_data["phone"])
        if "unified_credit_code" in update_data and update_data["unified_credit_code"]:
            _validate_unified_credit_code(update_data["unified_credit_code"])
        if "legal_rep_id_card" in update_data and update_data["legal_rep_id_card"]:
            _validate_id_card(update_data["legal_rep_id_card"])
        result = await self.db.update_by_id("companies", params["id"], update_data)
        if result is None:
            raise RPCError(-32602, "公司不存在")
        return result

    async def _company_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        deleted = await self.db.delete_by_id("companies", params["id"])
        if not deleted:
            raise RPCError(-32602, "公司不存在")
        return {"deleted": True}

    # ---- Conversation 方法 ----

    async def _conversation_create(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["user_id"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "user_id": params["user_id"],
            "title": params.get("title"),
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        return await self.db.insert("conversations", data)

    async def _conversation_list(self, params: dict[str, Any]) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if "status" in params:
            filters["status"] = params["status"]
        if "user_id" in params:
            filters["user_id"] = params["user_id"]
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        items = await self.db.list_all("conversations", filters, limit, offset)
        total = await self.db.count("conversations", filters)
        return {"items": items, "total": total}

    async def _conversation_get(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        result = await self.db.get_by_id("conversations", params["id"])
        if result is None:
            raise RPCError(-32602, "会话不存在")
        return result

    async def _conversation_update(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        now = _now_iso()
        update_data: dict[str, Any] = {"updated_at": now}
        for field in ("title", "status"):
            if field in params:
                update_data[field] = params[field]
        result = await self.db.update_by_id("conversations", params["id"], update_data)
        if result is None:
            raise RPCError(-32602, "会话不存在")
        return result

    async def _conversation_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        deleted = await self.db.delete_by_id("conversations", params["id"])
        if not deleted:
            raise RPCError(-32602, "会话不存在")
        return {"deleted": True}

    async def _conversation_archive(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        now = _now_iso()
        result = await self.db.update_by_id(
            "conversations", params["id"], {"status": "archived", "updated_at": now}
        )
        if result is None:
            raise RPCError(-32602, "会话不存在")
        return result

    async def _conversation_message_add(self, params: dict[str, Any]) -> dict[str, Any]:
        """添加消息（软删除：messages 表不支持物理删除，只追加）。"""
        _validate_required(params, ["conversation_id", "role", "content"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "conversation_id": params["conversation_id"],
            "role": params["role"],
            "content": params["content"],
            "metadata": json.dumps(params.get("metadata")) if params.get("metadata") else None,
            "deleted_at": None,
            "created_at": now,
        }
        return await self.db.insert("messages", data)

    async def _conversation_message_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """列出消息，排除软删除的消息。"""
        _validate_required(params, ["conversation_id"])
        assert self.db._db is not None, "数据库未初始化"
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        cursor = await self.db._db.execute(
            "SELECT * FROM messages WHERE conversation_id = ? AND deleted_at IS NULL "
            "ORDER BY created_at ASC LIMIT ? OFFSET ?",
            (params["conversation_id"], limit, offset),
        )
        rows = await cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        items = [dict(zip(columns, row)) for row in rows]
        count_cursor = await self.db._db.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND deleted_at IS NULL",
            (params["conversation_id"],),
        )
        count_row = await count_cursor.fetchone()
        total = count_row[0] if count_row else 0
        return {"items": items, "total": total}

    # ---- Knowledge 方法 ----

    async def _knowledge_create(self, params: dict[str, Any]) -> dict[str, Any]:
        """创建知识条目，去重：相同 SHA256 的 active 条目不重复创建。"""
        _validate_required(params, ["title", "content", "type"])
        content_hash = _sha256(params["content"])
        # 检查是否已存在相同 hash 的 active 条目
        assert self.db._db is not None, "数据库未初始化"
        cursor = await self.db._db.execute(
            "SELECT * FROM knowledge_entries WHERE content_hash = ? AND status = 'active' LIMIT 1",
            (content_hash,),
        )
        existing_row = await cursor.fetchone()
        if existing_row is not None:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, existing_row))

        now = _now_iso()
        data = {
            "id": _uuid4(),
            "title": params["title"],
            "content": params["content"],
            "type": params["type"],
            "content_hash": content_hash,
            "tags": json.dumps(params.get("tags")) if params.get("tags") else None,
            "status": "active",
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        return await self.db.insert("knowledge_entries", data)

    async def _knowledge_list(self, params: dict[str, Any]) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if "status" in params:
            filters["status"] = params["status"]
        if "type" in params:
            filters["type"] = params["type"]
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        items = await self.db.list_all("knowledge_entries", filters, limit, offset)
        total = await self.db.count("knowledge_entries", filters)
        return {"items": items, "total": total}

    async def _knowledge_get(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        result = await self.db.get_by_id("knowledge_entries", params["id"])
        if result is None:
            raise RPCError(-32602, "知识条目不存在")
        return result

    async def _knowledge_update(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        now = _now_iso()
        update_data: dict[str, Any] = {"updated_at": now}
        for field in ("title", "content", "type", "tags"):
            if field in params:
                if field == "tags" and params[field] is not None:
                    update_data[field] = json.dumps(params[field])
                else:
                    update_data[field] = params[field]
        # 如果内容更新了，重新计算 hash
        if "content" in update_data:
            update_data["content_hash"] = _sha256(update_data["content"])
        result = await self.db.update_by_id("knowledge_entries", params["id"], update_data)
        if result is None:
            raise RPCError(-32602, "知识条目不存在")
        return result

    async def _knowledge_archive(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        now = _now_iso()
        result = await self.db.update_by_id(
            "knowledge_entries", params["id"],
            {"status": "archived", "updated_at": now},
        )
        if result is None:
            raise RPCError(-32602, "知识条目不存在")
        return result

    async def _knowledge_search(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["query"])
        query = params["query"]
        fields = params.get("fields") or ["title", "content"]
        results = await self.db.search("knowledge_entries", query, fields)
        return {"items": results, "total": len(results)}

    # ---- Workspace 方法 ----

    async def _workspace_create(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["name", "owner_id"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "name": params["name"],
            "description": params.get("description"),
            "owner_id": params["owner_id"],
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        return await self.db.insert("workspaces", data)

    async def _workspace_list(self, params: dict[str, Any]) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if "owner_id" in params:
            filters["owner_id"] = params["owner_id"]
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        items = await self.db.list_all("workspaces", filters, limit, offset)
        total = await self.db.count("workspaces", filters)
        return {"items": items, "total": total}

    async def _workspace_get(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        result = await self.db.get_by_id("workspaces", params["id"])
        if result is None:
            raise RPCError(-32602, "工作区不存在")
        return result

    async def _workspace_update(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        now = _now_iso()
        update_data: dict[str, Any] = {"updated_at": now}
        for field in ("name", "description", "status"):
            if field in params:
                update_data[field] = params[field]
        result = await self.db.update_by_id("workspaces", params["id"], update_data)
        if result is None:
            raise RPCError(-32602, "工作区不存在")
        return result

    async def _workspace_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        deleted = await self.db.delete_by_id("workspaces", params["id"])
        if not deleted:
            raise RPCError(-32602, "工作区不存在")
        return {"deleted": True}

    async def _workspace_member_add(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["workspace_id", "user_id"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "workspace_id": params["workspace_id"],
            "user_id": params["user_id"],
            "role": params.get("role", "member"),
            "created_at": now,
        }
        return await self.db.insert("workspace_members", data)

    async def _workspace_member_remove(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        deleted = await self.db.delete_by_id("workspace_members", params["id"])
        if not deleted:
            raise RPCError(-32602, "成员不存在")
        return {"deleted": True}

    async def _workspace_member_list(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["workspace_id"])
        filters = {"workspace_id": params["workspace_id"]}
        items = await self.db.list_all("workspace_members", filters)
        return {"items": items, "total": len(items)}

    # ---- Orchestration 方法 ----

    async def _orchestration_create(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["name"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "name": params["name"],
            "description": params.get("description"),
            "version": 1,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }
        return await self.db.insert("orchestrations", data)

    async def _orchestration_list(self, params: dict[str, Any]) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if "status" in params:
            filters["status"] = params["status"]
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        items = await self.db.list_all("orchestrations", filters, limit, offset)
        total = await self.db.count("orchestrations", filters)
        return {"items": items, "total": total}

    async def _orchestration_get(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        result = await self.db.get_by_id("orchestrations", params["id"])
        if result is None:
            raise RPCError(-32602, "编排不存在")
        return result

    async def _orchestration_update(self, params: dict[str, Any]) -> dict[str, Any]:
        """更新编排，自动 version += 1。"""
        _validate_required(params, ["id"])
        now = _now_iso()
        # 获取当前编排以递增版本
        current = await self.db.get_by_id("orchestrations", params["id"])
        if current is None:
            raise RPCError(-32602, "编排不存在")
        new_version = current["version"] + 1
        update_data: dict[str, Any] = {"updated_at": now, "version": new_version}
        for field in ("name", "description", "status"):
            if field in params:
                update_data[field] = params[field]
        result = await self.db.update_by_id("orchestrations", params["id"], update_data)
        return result

    async def _orchestration_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        deleted = await self.db.delete_by_id("orchestrations", params["id"])
        if not deleted:
            raise RPCError(-32602, "编排不存在")
        return {"deleted": True}

    async def _orchestration_node_add(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["orchestration_id", "type", "name"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "orchestration_id": params["orchestration_id"],
            "type": params["type"],
            "name": params["name"],
            "config": json.dumps(params.get("config")) if params.get("config") else None,
            "position_x": params.get("position_x", 0.0),
            "position_y": params.get("position_y", 0.0),
            "created_at": now,
        }
        return await self.db.insert("orchestration_nodes", data)

    async def _orchestration_node_remove(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        deleted = await self.db.delete_by_id("orchestration_nodes", params["id"])
        if not deleted:
            raise RPCError(-32602, "节点不存在")
        return {"deleted": True}

    async def _orchestration_edge_add(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["orchestration_id", "source_node_id", "target_node_id"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "orchestration_id": params["orchestration_id"],
            "source_node_id": params["source_node_id"],
            "target_node_id": params["target_node_id"],
            "source_port": params.get("source_port"),
            "target_port": params.get("target_port"),
            "created_at": now,
        }
        return await self.db.insert("orchestration_edges", data)

    async def _orchestration_run(self, params: dict[str, Any]) -> dict[str, Any]:
        """创建并启动一个编排运行。"""
        _validate_required(params, ["orchestration_id"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "orchestration_id": params["orchestration_id"],
            "status": "running",
            "started_at": now,
            "finished_at": None,
            "error_message": None,
            "result": None,
            "created_at": now,
        }
        return await self.db.insert("orchestration_runs", data)

    async def _orchestration_run_history(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["orchestration_id"])
        filters = {"orchestration_id": params["orchestration_id"]}
        items = await self.db.list_all("orchestration_runs", filters)
        return {"items": items, "total": len(items)}

    # ---- Employee 方法 ----

    async def _employee_create(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["name"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "name": params["name"],
            "department_id": params.get("department_id"),
            "role": params.get("role"),
            "email": params.get("email"),
            "phone": params.get("phone"),
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        if data["email"]:
            _validate_email(data["email"])
        if data["phone"]:
            _validate_phone(data["phone"])
        return await self.db.insert("employees", data)

    async def _employee_list(self, params: dict[str, Any]) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if "department_id" in params:
            filters["department_id"] = params["department_id"]
        if "status" in params:
            filters["status"] = params["status"]
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        items = await self.db.list_all("employees", filters, limit, offset)
        total = await self.db.count("employees", filters)
        return {"items": items, "total": total}

    async def _employee_get(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        result = await self.db.get_by_id("employees", params["id"])
        if result is None:
            raise RPCError(-32602, "职员不存在")
        return result

    async def _employee_update(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        now = _now_iso()
        update_data: dict[str, Any] = {"updated_at": now}
        for field in ("name", "department_id", "role", "email", "phone", "status"):
            if field in params:
                update_data[field] = params[field]
        if "email" in update_data and update_data["email"]:
            _validate_email(update_data["email"])
        if "phone" in update_data and update_data["phone"]:
            _validate_phone(update_data["phone"])
        result = await self.db.update_by_id("employees", params["id"], update_data)
        if result is None:
            raise RPCError(-32602, "职员不存在")
        return result

    async def _employee_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        deleted = await self.db.delete_by_id("employees", params["id"])
        if not deleted:
            raise RPCError(-32602, "职员不存在")
        return {"deleted": True}

    # ---- Department 方法 ----

    async def _department_create(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["name"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "name": params["name"],
            "parent_id": params.get("parent_id"),
            "created_at": now,
            "updated_at": now,
        }
        return await self.db.insert("departments", data)

    async def _department_list(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        items = await self.db.list_all("departments", limit=limit, offset=offset)
        total = await self.db.count("departments")
        return {"items": items, "total": total}

    # ---- Agent 方法 ----

    async def _agent_run(self, params: dict[str, Any]) -> dict[str, Any]:
        """启动一个 Agent 运行（占位实现）。"""
        _validate_required(params, ["agent_id"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "agent_id": params["agent_id"],
            "user_id": params.get("user_id", ""),
            "status": "running",
            "config": json.dumps(params.get("config")) if params.get("config") else None,
            "last_heartbeat": now,
            "created_at": now,
            "updated_at": now,
        }
        return await self.db.insert("agent_states", data)

    async def _agent_status(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        result = await self.db.get_by_id("agent_states", params["id"])
        if result is None:
            raise RPCError(-32602, "Agent 状态不存在")
        return result

    async def _agent_list(self, params: dict[str, Any]) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if "status" in params:
            filters["status"] = params["status"]
        if "user_id" in params:
            filters["user_id"] = params["user_id"]
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        items = await self.db.list_all("agent_states", filters, limit, offset)
        total = await self.db.count("agent_states", filters)
        return {"items": items, "total": total}

    async def _agent_stop(self, params: dict[str, Any]) -> dict[str, Any]:
        _validate_required(params, ["id"])
        now = _now_iso()
        result = await self.db.update_by_id(
            "agent_states", params["id"],
            {"status": "stopped", "updated_at": now},
        )
        if result is None:
            raise RPCError(-32602, "Agent 状态不存在")
        return result

    # ---- Audit 方法 ----

    async def _audit_log(self, params: dict[str, Any]) -> dict[str, Any]:
        """写入审计日志。"""
        _validate_required(params, ["event_type", "actor_id", "resource_type", "resource_id"])
        now = _now_iso()
        data = {
            "id": _uuid4(),
            "event_type": params["event_type"],
            "actor_id": params["actor_id"],
            "resource_type": params["resource_type"],
            "resource_id": params["resource_id"],
            "detail": json.dumps(params.get("detail")) if params.get("detail") else None,
            "created_at": now,
        }
        return await self.db.insert("audit_log", data)

    async def _audit_query(self, params: dict[str, Any]) -> dict[str, Any]:
        """查询审计日志。"""
        filters: dict[str, Any] = {}
        for field in ("event_type", "actor_id", "resource_type", "resource_id"):
            if field in params:
                filters[field] = params[field]
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        items = await self.db.list_all("audit_log", filters, limit, offset)
        total = await self.db.count("audit_log", filters)
        return {"items": items, "total": total}

    async def _audit_export(self, params: dict[str, Any]) -> dict[str, Any]:
        """导出审计日志为 JSON 列表。"""
        filters: dict[str, Any] = {}
        for field in ("event_type", "actor_id", "resource_type"):
            if field in params:
                filters[field] = params[field]
        items = await self.db.list_all("audit_log", filters, limit=10000)
        return {"items": items, "total": len(items)}


def _error_response(
    req_id: Any, code: int, message: str, data: Any = None
) -> dict[str, Any]:
    """构造 JSON-RPC 2.0 错误响应。"""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "error": error, "id": req_id}
