"""审计与人工干预查询 RPC 方法。"""

from __future__ import annotations

import aiosqlite
from typing import Any

from acos.rpc.errors import (
    AUDIT_VALIDATION,
    INTERVENTION_NOT_FOUND,
    create_error,
)
from acos.rpc.server import RPCServer

# audit.query 路由表：audit_type -> (表名, 默认时间列)
_AUDIT_TABLES: dict[str, str] = {
    "acl": "acl_audit_log",
    "org": "org_change_audit",
    "governance": "governance_audit",
}


class AuditMethods:
    """审计日志 / 人工干预中心查询 RPC 方法（只读）。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def register_to(self, server: RPCServer) -> None:
        server.register_method("intervention.list", self._intervention_list)
        server.register_method("audit.query", self._audit_query)

    # ── 人工干预中心 ──────────────────────────────────────────────

    async def _intervention_list(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise create_error(
                AUDIT_VALIDATION,
                "company_id 为必填参数",
                cause="missing company_id",
            )

        status = params.get("status")  # open / resolved / None(全部)
        # pending 与 open 语义一致（DB 存的是 open），前端用 pending 表示待处理
        if status == "pending":
            status = "open"
        if status is not None and status not in ("open", "resolved"):
            raise create_error(
                AUDIT_VALIDATION,
                f"status 取值非法: {status}",
                cause="status must be 'open' / 'resolved' / 省略",
            )

        page = max(int(params.get("page", 1)), 1)
        limit = max(int(params.get("limit", 20)), 1)

        conds = ["company_id = ?"]
        vals: list[Any] = [company_id]
        if status is not None:
            conds.append("status = ?")
            vals.append(status)

        where = " AND ".join(conds)
        offset = (page - 1) * limit

        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cur = await conn.execute(
                f"SELECT COUNT(*) AS c FROM human_interventions WHERE {where}", vals
            )
            total = (await cur.fetchone())["c"]

            cur = await conn.execute(
                f"SELECT * FROM human_interventions WHERE {where} "
                f"ORDER BY created_at DESC LIMIT ? OFFSET ?",
                vals + [limit, offset],
            )
            items = [dict(r) for r in await cur.fetchall()]
        finally:
            await conn.close()

        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
        }

    # ── 审计日志查询（跨表路由）──────────────────────────────────

    async def _audit_query(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        if not company_id:
            raise create_error(
                AUDIT_VALIDATION,
                "company_id 为必填参数",
                cause="missing company_id",
            )

        # 兼容文档/前端的 type 与 audit_type 两种字段名
        audit_type = params.get("audit_type") or params.get("type")
        if audit_type not in _AUDIT_TABLES:
            raise create_error(
                AUDIT_VALIDATION,
                f"audit_type 取值非法: {audit_type}",
                cause="audit_type must be 'acl' / 'org' / 'governance'",
            )
        table = _AUDIT_TABLES[audit_type]

        start_at = params.get("start_at")
        end_at = params.get("end_at")
        if start_at and end_at and start_at > end_at:
            raise create_error(
                AUDIT_VALIDATION,
                "start_at 不能晚于 end_at",
                cause="time range inverted",
            )

        page = max(int(params.get("page", 1)), 1)
        limit = max(int(params.get("limit", 20)), 1)

        conds = ["company_id = ?"]
        vals: list[Any] = [company_id]
        if start_at:
            conds.append("timestamp >= ?")
            vals.append(start_at)
        if end_at:
            conds.append("timestamp <= ?")
            vals.append(end_at)

        where = " AND ".join(conds)
        offset = (page - 1) * limit

        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        try:
            cur = await conn.execute(
                f"SELECT COUNT(*) AS c FROM {table} WHERE {where}", vals
            )
            total = (await cur.fetchone())["c"]

            cur = await conn.execute(
                f"SELECT * FROM {table} WHERE {where} "
                f"ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                vals + [limit, offset],
            )
            items = [dict(r) for r in await cur.fetchall()]
        finally:
            await conn.close()

        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
            "audit_type": audit_type,
        }
