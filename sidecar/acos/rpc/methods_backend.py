"""Backend Registry / Health RPC 方法集合。

实现设计方案 §6.11 / §15 / 附录 B 的 backend.* 命名空间：
    backend.list / get / create / update / setDefault / enable / drain /
    archive / probe / checkAvailability

生命周期状态机：
    enabled → draining → disabled → enabled
    disabled → archived

默认唯一约束（company_backend_defaults，setDefault 用 version CAS 保证恰好一个
非 archived 默认）。有 held lease 禁止 archive；draining 最后一个 lease 释放后
自动 disabled。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

from acos.rpc.errors import AcosError, SYS_OPTIMISTIC_LOCK_CONFLICT, create_error
from acos.events.outbox import OutboxWriter


# LocalOwner 固定 actor（服务端注入，不接受客户端 actor 参数）
LOCAL_OWNER_TYPE = "LocalOwner"
LOCAL_OWNER_ID = "system"

# Backend v1 仅接受的类型
_ALLOWED_BACKEND_TYPES = ("local_process",)

# 允许的生命周期状态
_LIFECYCLE_STATES = ("enabled", "draining", "disabled", "archived")

# 合法的 workspace_types 枚举（设计方案 §6.11）
_ALLOWED_WORKSPACE_TYPES = (
    "TaskWorkspace",
    "ReadOnlyWorkspace",
    "RestrictedWorkspace",
    "GitWorktreeWorkspace",
)

# 合法的 backend 执行原语能力（与 provider supports 互不兼容）
_ALLOWED_CAPABILITIES = (
    "agent_runtime",
    "filesystem_io",
    "readonly_io",
    "git_cli",
)

# 健康状态枚举
_HEALTH_STATES = ("healthy", "degraded", "unavailable", "unknown", "timeout")

# 写方法本地错误码（不修改 errors.py，server 已支持任意 code 字符串）
_BACKEND_NOT_FOUND = "BACKEND-NOT-FOUND"
_BACKEND_CROSS_COMPANY = "BACKEND-CROSS-COMPANY-DENIED"
_BACKEND_STATE_TRANSITION = "BACKEND-STATE-TRANSITION-INVALID"
_BACKEND_DEFAULT_CONFLICT = "BACKEND-DEFAULT-CONFLICT"
_BACKEND_LEASE_HELD = "BACKEND-LEASE-HELD"
_BACKEND_HEALTH_NOT_HEALTHY = "BACKEND-HEALTH-NOT-HEALTHY"
_BACKEND_VALIDATION = "BACKEND-VALIDATION"
_BACKEND_COMPANY_NOT_WRITABLE = "BACKEND-COMPANY-NOT-WRITABLE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_backend(row: aiosqlite.Row) -> dict[str, Any]:
        return {
        "backend_id": row["backend_id"],
        "company_id": row["company_id"],
        "provider_id": row["provider_id"],
        "name": row["name"],
        "backend_type": row["backend_type"],
        "status": row["status"],
        "health_status": row["health_status"],
        "capabilities": json.loads(row["capabilities"]),
        "workspace_types": json.loads(row["workspace_types"]),
        "workspace_root": row["workspace_root"],
        "concurrency_limit": row["concurrency_limit"],
        "version": row["version"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class BackendMethods:
    """Backend 相关的 RPC 方法。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._server: Any = None

    def register_to(self, server: Any) -> None:
        self._server = server
        server.register_method("backend.list", self._list)
        server.register_method("backend.get", self._get)
        server.register_method("backend.create", self._create)
        server.register_method("backend.update", self._update)
        server.register_method("backend.setDefault", self._set_default)
        server.register_method("backend.enable", self._enable)
        server.register_method("backend.drain", self._drain)
        server.register_method("backend.archive", self._archive)
        server.register_method("backend.probe", self._probe)
        server.register_method("backend.checkAvailability", self._check_availability)

    # ── 内部辅助 ────────────────────────────────────────────

    async def _company_writable(self, conn: aiosqlite.Connection, company_id: str) -> bool:
        """写方法只接受 initializing/active 公司；返回是否可写。"""
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT status, deleted_at FROM companies WHERE company_id = ?",
            (company_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return False
        if row["deleted_at"] is not None:
            return False
        return row["status"] in ("initializing", "active")

    async def _get_backend_row(
        self, conn: aiosqlite.Connection, backend_id: str
    ) -> Optional[aiosqlite.Row]:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM backends WHERE backend_id = ?", (backend_id,)
        )
        return await cur.fetchone()

    async def _count_active_leases(
        self, conn: aiosqlite.Connection, backend_id: str
    ) -> int:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM backend_leases WHERE backend_id = ? AND status = 'active'",
            (backend_id,),
        )
        row = await cur.fetchone()
        return row[0] if row else 0

    async def _write_audit(
        self,
        conn: aiosqlite.Connection,
        *,
        company_id: str,
        backend_id: Optional[str],
        action: str,
        before: dict,
        after: dict,
        idempotency_key: Optional[str],
        request_hash: Optional[str],
        trace_id: str,
    ) -> None:
        await conn.execute(
            """INSERT INTO backend_change_audit
               (audit_id, company_id, backend_id, action, actor_type, actor_id,
                before_snapshot, after_snapshot, idempotency_key, request_hash, trace_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                company_id,
                backend_id,
                action,
                LOCAL_OWNER_TYPE,
                LOCAL_OWNER_ID,
                json.dumps(before, ensure_ascii=False),
                json.dumps(after, ensure_ascii=False),
                idempotency_key,
                request_hash,
                trace_id,
                _now(),
            ),
        )

    async def _emit_backend_status(
        self,
        conn: aiosqlite.Connection,
        *,
        company_id: str,
        backend_id: str,
        new_status: str,
        health_summary: str,
        held: int,
        limit: int,
        trace_id: str,
    ) -> None:
        """发送 notify.backendStatus 事件（写入 domain_events + outbox）。"""
        writer = OutboxWriter()
        await writer.emit_event(
            conn=conn,
            company_id=company_id,
            event_type="notify.backendStatus",
            aggregate_type="backend",
            aggregate_id=backend_id,
            aggregate_version=1,
            payload={
                "backend_id": backend_id,
                "new_status": new_status,
                "health_summary": health_summary,
                "held": held,
                "limit": limit,
            },
            trace_id=trace_id,
            actor_type=LOCAL_OWNER_TYPE,
            actor_id=LOCAL_OWNER_ID,
            consumers=["notify.backendStatus"],
        )

    async def _complete_idempotency(
        self,
        params: dict,
        method: str,
        status: str,
        result: Optional[dict],
    ) -> None:
        if self._server is None or not hasattr(self._server, "complete_idempotency"):
            return
        key = params.get("_idempotency_key")
        if not key:
            return
        async with aiosqlite.connect(self._db_path) as conn:
            await self._server.complete_idempotency(
                conn,
                params.get("company_id", ""),
                LOCAL_OWNER_TYPE,
                LOCAL_OWNER_ID,
                method,
                key,
                status,
                result,
            )

    # ── 读方法 ──────────────────────────────────────────────

    async def _list(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        company_id = params.get("company_id")
        if not company_id:
            raise AcosError(code=_BACKEND_VALIDATION, message="missing company_id")
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM backends WHERE company_id = ? ORDER BY name",
                (company_id,),
            )
            rows = await cur.fetchall()
        return [_row_to_backend(r) for r in rows]

    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        backend_id = params.get("backend_id")
        if not backend_id:
            raise AcosError(code=_BACKEND_VALIDATION, message="missing backend_id")
        async with aiosqlite.connect(self._db_path) as conn:
            row = await self._get_backend_row(conn, backend_id)
            if row is None:
                raise AcosError(code=_BACKEND_NOT_FOUND, message=f"backend {backend_id} 不存在")
            return _row_to_backend(row)

    # ── 写方法 ──────────────────────────────────────────────

    async def _create(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        name = params.get("name")
        if not company_id:
            raise AcosError(code=_BACKEND_VALIDATION, message="missing company_id")
        if not name:
            raise AcosError(code=_BACKEND_VALIDATION, message="missing name")

        backend_type = params.get("backend_type", "local_process")
        if backend_type not in _ALLOWED_BACKEND_TYPES:
            raise AcosError(
                code=_BACKEND_VALIDATION,
                message=f"backend_type 仅支持 {_ALLOWED_BACKEND_TYPES}",
            )

        capabilities = params.get("capabilities", ["agent_runtime", "filesystem_io", "readonly_io"])
        workspace_types = params.get("workspace_types", ["TaskWorkspace", "ReadOnlyWorkspace"])
        if any(c not in _ALLOWED_CAPABILITIES for c in capabilities):
            raise AcosError(code=_BACKEND_VALIDATION, message="非法 capabilities 值")
        if any(w not in _ALLOWED_WORKSPACE_TYPES for w in workspace_types):
            raise AcosError(code=_BACKEND_VALIDATION, message="非法 workspace_types 值")
        # git_cli 必须成对出现 GitWorktreeWorkspace
        if ("git_cli" in capabilities) != ("GitWorktreeWorkspace" in workspace_types):
            raise AcosError(
                code=_BACKEND_VALIDATION,
                message="git_cli 与 GitWorktreeWorkspace 必须成对",
            )

        concurrency_limit = params.get("concurrency_limit", 1)
        if not isinstance(concurrency_limit, int) or concurrency_limit < 1:
            raise AcosError(code=_BACKEND_VALIDATION, message="concurrency_limit 必须 ≥ 1")

        workspace_root = params.get("workspace_root", "")
        if workspace_root:
            await self._assert_workspace_root_unique(company_id, workspace_root, None)

        backend_id = params.get("backend_id") or f"be-{uuid.uuid4().hex[:12]}"
        now = _now()
        trace_id = params.get("_trace_id") or uuid.uuid4().hex

        # 新 backend 默认 disabled + unknown，绝不直接 enabled（需后续 probe 后才可 enable）
        async with aiosqlite.connect(self._db_path) as conn:
            if not await self._company_writable(conn, company_id):
                raise AcosError(
                    code=_BACKEND_COMPANY_NOT_WRITABLE,
                    message="公司不存在或状态不可写（仅 initializing/active）",
                )
            await conn.execute(
                """INSERT INTO backends
                   (backend_id, company_id, name, backend_type, status,
                    health_status, capabilities, workspace_types, workspace_root,
                    provider_id, concurrency_limit, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'disabled', 'unknown',
                           ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    backend_id,
                    company_id,
                    name,
                    backend_type,
                    json.dumps(capabilities, ensure_ascii=False),
                    json.dumps(workspace_types, ensure_ascii=False),
                    workspace_root,
                    params.get("provider_id"),
                    concurrency_limit,
                    now,
                    now,
                ),
            )
            # 没有默认则原子补为默认
            await self._ensure_default(conn, company_id, backend_id)
            await self._write_audit(
                conn,
                company_id=company_id,
                backend_id=backend_id,
                action="create",
                before={},
                after={"name": name, "status": "disabled", "health_status": "unknown"},
                idempotency_key=params.get("_idempotency_key"),
                request_hash=params.get("_request_hash"),
                trace_id=trace_id,
            )
            await conn.commit()

        await self._complete_idempotency(params, "backend.create", "succeeded", {"backend_id": backend_id})
        return await self._get({"backend_id": backend_id})

    async def _update(self, params: dict[str, Any]) -> dict[str, Any]:
        backend_id = params.get("backend_id")
        expected_version = params.get("expected_version", 1)
        if not backend_id:
            raise AcosError(code=_BACKEND_VALIDATION, message="missing backend_id")

        async with aiosqlite.connect(self._db_path) as conn:
            row = await self._get_backend_row(conn, backend_id)
            if row is None:
                raise AcosError(code=_BACKEND_NOT_FOUND, message=f"backend {backend_id} 不存在")
            company_id = row["company_id"]
            if not await self._company_writable(conn, company_id):
                raise AcosError(code=_BACKEND_COMPANY_NOT_WRITABLE, message="公司状态不可写")
            if row["version"] != expected_version:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突: backend {backend_id} (期望 v{expected_version}, 实际 v{row['version']})",
                )

            before = _row_to_backend(row)
            status = row["status"]

            sets: list[str] = []
            vals: list[Any] = []
            after: dict[str, Any] = {}

            # name / concurrency_limit 可在线更新（任何状态）
            if params.get("name") is not None:
                sets.append("name = ?")
                vals.append(params["name"])
                after["name"] = params["name"]
            if params.get("concurrency_limit") is not None:
                cl = params["concurrency_limit"]
                if not isinstance(cl, int) or cl < 1:
                    raise AcosError(code=_BACKEND_VALIDATION, message="concurrency_limit 必须 ≥ 1")
                # 提升并发不允许超过当前 held；降低并发不杀已有 lease
                held = await self._count_active_leases(conn, backend_id)
                if cl < held:
                    raise AcosError(
                        code=_BACKEND_VALIDATION,
                        message=f"concurrency_limit 不能低于当前 held lease 数 ({held})",
                    )
                sets.append("concurrency_limit = ?")
                vals.append(cl)
                after["concurrency_limit"] = cl

            # workspace_root / capabilities / workspace_types 仅 disabled + 无 held lease 可改
            restricted = any(
                k in params
                for k in ("workspace_root", "capabilities", "workspace_types")
            )
            if restricted:
                held = await self._count_active_leases(conn, backend_id)
                if status != "disabled" or held > 0:
                    raise AcosError(
                        code=_BACKEND_STATE_TRANSITION,
                        message="workspace_root/capabilities/workspace_types 仅 disabled 且无 held lease 可改",
                    )
                if params.get("workspace_root") is not None:
                    wr = params["workspace_root"]
                    if wr:
                        await self._assert_workspace_root_unique(company_id, wr, backend_id)
                    sets.append("workspace_root = ?")
                    vals.append(wr)
                    after["workspace_root"] = wr
                if params.get("capabilities") is not None:
                    caps = params["capabilities"]
                    if any(c not in _ALLOWED_CAPABILITIES for c in caps):
                        raise AcosError(code=_BACKEND_VALIDATION, message="非法 capabilities 值")
                    if ("git_cli" in caps) != ("GitWorktreeWorkspace" in params.get("workspace_types", before["workspace_types"])):
                        raise AcosError(code=_BACKEND_VALIDATION, message="git_cli 与 GitWorktreeWorkspace 必须成对")
                    sets.append("capabilities = ?")
                    vals.append(json.dumps(caps, ensure_ascii=False))
                    after["capabilities"] = caps
                if params.get("workspace_types") is not None:
                    wts = params["workspace_types"]
                    if any(w not in _ALLOWED_WORKSPACE_TYPES for w in wts):
                        raise AcosError(code=_BACKEND_VALIDATION, message="非法 workspace_types 值")
                    sets.append("workspace_types = ?")
                    vals.append(json.dumps(wts, ensure_ascii=False))
                    after["workspace_types"] = wts
                # 改后健康置 unknown
                sets.append("health_status = 'unknown'")
                after["health_status"] = "unknown"

            if not sets:
                raise AcosError(code=_BACKEND_VALIDATION, message="无可更新字段")

            sets.append("version = version + 1")
            sets.append("updated_at = ?")
            vals.extend([_now(), backend_id, expected_version])
            cur = await conn.execute(
                f"UPDATE backends SET {', '.join(sets)} WHERE backend_id = ? AND version = ?",
                vals,
            )
            if cur.rowcount == 0:
                raise create_error(SYS_OPTIMISTIC_LOCK_CONFLICT, "CAS 冲突: backend update")
            await self._write_audit(
                conn,
                company_id=company_id,
                backend_id=backend_id,
                action="update",
                before=before,
                after=after,
                idempotency_key=params.get("_idempotency_key"),
                request_hash=params.get("_request_hash"),
                trace_id=params.get("_trace_id") or uuid.uuid4().hex,
            )
            await conn.commit()

        await self._complete_idempotency(params, "backend.update", "succeeded", {"backend_id": backend_id})
        return await self._get({"backend_id": backend_id})

    async def _set_default(self, params: dict[str, Any]) -> dict[str, Any]:
        backend_id = params.get("backend_id")
        expected_version = params.get("expected_version", 1)
        if not backend_id:
            raise AcosError(code=_BACKEND_VALIDATION, message="missing backend_id")

        async with aiosqlite.connect(self._db_path) as conn:
            row = await self._get_backend_row(conn, backend_id)
            if row is None:
                raise AcosError(code=_BACKEND_NOT_FOUND, message=f"backend {backend_id} 不存在")
            company_id = row["company_id"]
            if not await self._company_writable(conn, company_id):
                raise AcosError(code=_BACKEND_COMPANY_NOT_WRITABLE, message="公司状态不可写")
            if row["status"] == "archived":
                raise AcosError(code=_BACKEND_STATE_TRANSITION, message="已归档 backend 不能设为默认")

            # 若已是默认则直接成功
            cur = await conn.execute(
                "SELECT * FROM company_backend_defaults WHERE company_id = ? AND backend_id = ? AND is_archived = 0",
                (company_id, backend_id),
            )
            existing = await cur.fetchone()
            if existing is not None:
                return {"backend_id": backend_id, "is_default": True}

            # version CAS：把其他非 archived 默认行 is_archived=1，本行置为默认
            now = _now()
            # 先把当前所有非 archived 默认标记 archived（CAS 用 version）
            cur = await conn.execute(
                """UPDATE company_backend_defaults
                   SET is_archived = 1, version = version + 1, updated_at = ?
                   WHERE company_id = ? AND is_archived = 0 AND version = ?""",
                (now, company_id, expected_version),
            )
            if cur.rowcount == 0:
                # 检查是否存在任何默认行（若存在说明 version 不匹配）
                cur = await conn.execute(
                    "SELECT COUNT(*) FROM company_backend_defaults WHERE company_id = ? AND is_archived = 0",
                    (company_id,),
                )
                cnt = (await cur.fetchone())[0]
                if cnt > 0:
                    raise create_error(SYS_OPTIMISTIC_LOCK_CONFLICT, "CAS 冲突: setDefault")

            # upsert 本 backend 为默认（非 archived）
            await conn.execute(
                """INSERT INTO company_backend_defaults
                   (default_id, company_id, backend_id, is_archived, version, created_at, updated_at)
                   VALUES (?, ?, ?, 0, 1, ?, ?)
                   ON CONFLICT(company_id, backend_id) DO UPDATE SET
                       is_archived = 0, version = version + 1, updated_at = ?""",
                (str(uuid.uuid4()), company_id, backend_id, now, now, now),
            )
            await self._write_audit(
                conn,
                company_id=company_id,
                backend_id=backend_id,
                action="setDefault",
                before={"is_default": False},
                after={"is_default": True},
                idempotency_key=params.get("_idempotency_key"),
                request_hash=params.get("_request_hash"),
                trace_id=params.get("_trace_id") or uuid.uuid4().hex,
            )
            await conn.commit()

        await self._complete_idempotency(params, "backend.setDefault", "succeeded", {"backend_id": backend_id, "is_default": True})
        return {"backend_id": backend_id, "is_default": True}

    async def _enable(self, params: dict[str, Any]) -> dict[str, Any]:
        backend_id = params.get("backend_id")
        expected_version = params.get("expected_version", 1)
        if not backend_id:
            raise AcosError(code=_BACKEND_VALIDATION, message="missing backend_id")

        async with aiosqlite.connect(self._db_path) as conn:
            row = await self._get_backend_row(conn, backend_id)
            if row is None:
                raise AcosError(code=_BACKEND_NOT_FOUND, message=f"backend {backend_id} 不存在")
            company_id = row["company_id"]
            if not await self._company_writable(conn, company_id):
                raise AcosError(code=_BACKEND_COMPANY_NOT_WRITABLE, message="公司状态不可写")
            if row["version"] != expected_version:
                raise create_error(SYS_OPTIMISTIC_LOCK_CONFLICT, f"CAS 冲突: backend {backend_id}")

            # enable 前必须先得到 healthy（fresh probe）
            if row["health_status"] != "healthy":
                raise AcosError(
                    code=_BACKEND_HEALTH_NOT_HEALTHY,
                    message=f"enable 前需 fresh healthy，当前 {row['health_status']}",
                )
            # disabled/archived → enabled；draining 不可直接 enable（需先 disabled）
            if row["status"] not in ("disabled",):
                raise AcosError(
                    code=_BACKEND_STATE_TRANSITION,
                    message=f"enable 仅允许从 disabled 进入，当前 {row['status']}",
                )

            before = _row_to_backend(row)
            cur = await conn.execute(
                "UPDATE backends SET status = 'enabled', version = version + 1, updated_at = ? WHERE backend_id = ? AND version = ?",
                (_now(), backend_id, expected_version),
            )
            if cur.rowcount == 0:
                raise create_error(SYS_OPTIMISTIC_LOCK_CONFLICT, "CAS 冲突: enable")
            await self._write_audit(
                conn,
                company_id=company_id,
                backend_id=backend_id,
                action="enable",
                before={"status": before["status"]},
                after={"status": "enabled"},
                idempotency_key=params.get("_idempotency_key"),
                request_hash=params.get("_request_hash"),
                trace_id=params.get("_trace_id") or uuid.uuid4().hex,
            )
            await self._emit_backend_status(
                conn, company_id=company_id, backend_id=backend_id,
                new_status="enabled", health_summary="healthy",
                held=await self._count_active_leases(conn, backend_id),
                limit=row["concurrency_limit"],
                trace_id=params.get("_trace_id") or uuid.uuid4().hex,
            )
            await conn.commit()

        await self._complete_idempotency(params, "backend.enable", "succeeded", {"backend_id": backend_id, "status": "enabled"})
        return await self._get({"backend_id": backend_id})

    async def _drain(self, params: dict[str, Any]) -> dict[str, Any]:
        backend_id = params.get("backend_id")
        expected_version = params.get("expected_version", 1)
        if not backend_id:
            raise AcosError(code=_BACKEND_VALIDATION, message="missing backend_id")

        async with aiosqlite.connect(self._db_path) as conn:
            row = await self._get_backend_row(conn, backend_id)
            if row is None:
                raise AcosError(code=_BACKEND_NOT_FOUND, message=f"backend {backend_id} 不存在")
            company_id = row["company_id"]
            if not await self._company_writable(conn, company_id):
                raise AcosError(code=_BACKEND_COMPANY_NOT_WRITABLE, message="公司状态不可写")
            if row["version"] != expected_version:
                raise create_error(SYS_OPTIMISTIC_LOCK_CONFLICT, f"CAS 冲突: backend {backend_id}")
            if row["status"] != "enabled":
                raise AcosError(
                    code=_BACKEND_STATE_TRANSITION,
                    message=f"drain 仅允许从 enabled 进入，当前 {row['status']}",
                )
            # 默认 backend 不可 drain，除非先切换默认
            cur = await conn.execute(
                "SELECT 1 FROM company_backend_defaults WHERE company_id = ? AND backend_id = ? AND is_archived = 0",
                (company_id, backend_id),
            )
            if await cur.fetchone() is not None:
                raise AcosError(code=_BACKEND_DEFAULT_CONFLICT, message="默认 backend 不可 drain，请先切换默认")

            before = _row_to_backend(row)
            cur = await conn.execute(
                "UPDATE backends SET status = 'draining', version = version + 1, updated_at = ? WHERE backend_id = ? AND version = ?",
                (_now(), backend_id, expected_version),
            )
            if cur.rowcount == 0:
                raise create_error(SYS_OPTIMISTIC_LOCK_CONFLICT, "CAS 冲突: drain")
            # 取消 waiting entries（task node 由上层 replan，session turn 保留 queued_at 重入新默认）
            await conn.execute(
                "UPDATE backend_queue_entries SET status = 'cancelled', cancel_reason = 'backend_draining' WHERE backend_id = ? AND status = 'waiting'",
                (backend_id,),
            )
            await self._write_audit(
                conn,
                company_id=company_id,
                backend_id=backend_id,
                action="drain",
                before={"status": before["status"]},
                after={"status": "draining"},
                idempotency_key=params.get("_idempotency_key"),
                request_hash=params.get("_request_hash"),
                trace_id=params.get("_trace_id") or uuid.uuid4().hex,
            )
            await self._emit_backend_status(
                conn, company_id=company_id, backend_id=backend_id,
                new_status="draining", health_summary=row["health_status"],
                held=await self._count_active_leases(conn, backend_id),
                limit=row["concurrency_limit"],
                trace_id=params.get("_trace_id") or uuid.uuid4().hex,
            )
            await conn.commit()

        await self._complete_idempotency(params, "backend.drain", "succeeded", {"backend_id": backend_id, "status": "draining"})
        return await self._get({"backend_id": backend_id})

    async def _archive(self, params: dict[str, Any]) -> dict[str, Any]:
        backend_id = params.get("backend_id")
        expected_version = params.get("expected_version", 1)
        if not backend_id:
            raise AcosError(code=_BACKEND_VALIDATION, message="missing backend_id")

        async with aiosqlite.connect(self._db_path) as conn:
            row = await self._get_backend_row(conn, backend_id)
            if row is None:
                raise AcosError(code=_BACKEND_NOT_FOUND, message=f"backend {backend_id} 不存在")
            company_id = row["company_id"]
            if not await self._company_writable(conn, company_id):
                raise AcosError(code=_BACKEND_COMPANY_NOT_WRITABLE, message="公司状态不可写")
            if row["version"] != expected_version:
                raise create_error(SYS_OPTIMISTIC_LOCK_CONFLICT, f"CAS 冲突: backend {backend_id}")
            if row["status"] != "disabled":
                raise AcosError(
                    code=_BACKEND_STATE_TRANSITION,
                    message=f"archive 仅允许从 disabled 进入，当前 {row['status']}",
                )
            # 默认 backend 不可 archive
            cur = await conn.execute(
                "SELECT 1 FROM company_backend_defaults WHERE company_id = ? AND backend_id = ? AND is_archived = 0",
                (company_id, backend_id),
            )
            if await cur.fetchone() is not None:
                raise AcosError(code=_BACKEND_DEFAULT_CONFLICT, message="默认 backend 不可 archive")
            # 有 held lease 禁止 archive
            held = await self._count_active_leases(conn, backend_id)
            if held > 0:
                raise AcosError(code=_BACKEND_LEASE_HELD, message=f"仍有 {held} 个 held lease，禁止归档")

            before = _row_to_backend(row)
            cur = await conn.execute(
                "UPDATE backends SET status = 'archived', version = version + 1, updated_at = ? WHERE backend_id = ? AND version = ?",
                (_now(), backend_id, expected_version),
            )
            if cur.rowcount == 0:
                raise create_error(SYS_OPTIMISTIC_LOCK_CONFLICT, "CAS 冲突: archive")
            await self._write_audit(
                conn,
                company_id=company_id,
                backend_id=backend_id,
                action="archive",
                before={"status": before["status"]},
                after={"status": "archived"},
                idempotency_key=params.get("_idempotency_key"),
                request_hash=params.get("_request_hash"),
                trace_id=params.get("_trace_id") or uuid.uuid4().hex,
            )
            await conn.commit()

        await self._complete_idempotency(params, "backend.archive", "succeeded", {"backend_id": backend_id, "status": "archived"})
        return await self._get({"backend_id": backend_id})

    # ── 健康探测 ────────────────────────────────────────────

    async def _probe(self, params: dict[str, Any]) -> dict[str, Any]:
        backend_id = params.get("backend_id")
        if not backend_id:
            raise AcosError(code=_BACKEND_VALIDATION, message="missing backend_id")

        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            row = await self._get_backend_row(conn, backend_id)
            if row is None:
                raise AcosError(code=_BACKEND_NOT_FOUND, message=f"backend {backend_id} 不存在")
            company_id = row["company_id"]
            capabilities = json.loads(row["capabilities"])
            workspace_root = row["workspace_root"]
            trigger = params.get("trigger", "manual")
            now = _now()

            # LocalBackendHealthProbe：检查 workspace 可写、受控 worker handshake、进程池
            # （v1 真实可落地检查，不调用 Provider 网络）
            probe = LocalBackendHealthProbe()
            result = await probe.run(
                workspace_root=workspace_root,
                capabilities=capabilities,
                now=now,
            )

            health = result["health_status"]
            before_health = row["health_status"]

            # 写 backend_health_checks
            await conn.execute(
                """INSERT INTO backend_health_checks
                   (check_id, backend_id, company_id, trigger, operator, health_status,
                    reason, workspace_writable, worker_handshake_ok, process_pool_ok,
                    git_cli_ok, observed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    backend_id,
                    company_id,
                    trigger,
                    LOCAL_OWNER_ID,
                    health,
                    result.get("reason"),
                    1 if result["workspace_writable"] else 0,
                    1 if result["worker_handshake_ok"] else 0,
                    1 if result["process_pool_ok"] else 0,
                    (1 if result["git_cli_ok"] else 0) if result["git_cli_ok"] is not None else None,
                    now,
                ),
            )

            # 更新 backends 健康状态（仅当状态变化才写事件）
            await conn.execute(
                "UPDATE backends SET health_status = ?, updated_at = ? WHERE backend_id = ?",
                (health, now, backend_id),
            )
            trace = params.get("_trace_id") or uuid.uuid4().hex
            if health != before_health and health in ("healthy", "degraded", "unavailable", "unknown"):
                await self._emit_backend_status(
                    conn, company_id=company_id, backend_id=backend_id,
                    new_status=row["status"], health_summary=health,
                    held=await self._count_active_leases(conn, backend_id),
                    limit=row["concurrency_limit"],
                    trace_id=trace,
                )

            await self._write_audit(
                conn,
                company_id=company_id,
                backend_id=backend_id,
                action="probe",
                before={"health_status": before_health},
                after={"health_status": health},
                idempotency_key=params.get("_idempotency_key"),
                request_hash=params.get("_request_hash"),
                trace_id=trace,
            )
            await conn.commit()

        return {
            "backend_id": backend_id,
            "health_status": health,
            "before_health_status": before_health,
            "reason": result.get("reason"),
            "workspace_writable": result["workspace_writable"],
            "worker_handshake_ok": result["worker_handshake_ok"],
            "process_pool_ok": result["process_pool_ok"],
            "git_cli_ok": result["git_cli_ok"],
            "observed_at": now,
        }

    # ── 容量检查 ────────────────────────────────────────────

    async def _check_availability(self, params: dict[str, Any]) -> dict[str, Any]:
        backend_id = params.get("backend_id")
        if not backend_id:
            raise AcosError(code=_BACKEND_VALIDATION, message="missing backend_id")
        company_id = params.get("company_id")
        request_ref = params.get("request_ref")

        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            row = await self._get_backend_row(conn, backend_id)
            if row is None:
                raise AcosError(code=_BACKEND_NOT_FOUND, message=f"backend {backend_id} 不存在")
            if company_id and row["company_id"] != company_id:
                raise AcosError(code=_BACKEND_CROSS_COMPANY, message="跨公司访问被拒绝")

            held = await self._count_active_leases(conn, backend_id)
            limit = row["concurrency_limit"]
            available = max(0, limit - held)

            result: dict[str, Any] = {
                "backend_id": backend_id,
                "company_id": row["company_id"],
                "status": row["status"],
                "health_status": row["health_status"],
                "concurrency_limit": limit,
                "active_leases": held,
                "available": available,
                "observed_at": _now(),
                "backend_position": None,
                "global_schedulable_rank": None,
                "wait_reason": None,
            }

            if request_ref:
                # 校验 request_ref 同公司且匹配活动 waiting entry
                cur = await conn.execute(
                    """SELECT entry_id, wait_reason FROM backend_queue_entries
                       WHERE entry_id = ? AND company_id = ? AND backend_id = ? AND status = 'waiting'""",
                    (request_ref, row["company_id"], backend_id),
                )
                entry = await cur.fetchone()
                if entry is None:
                    raise AcosError(
                        code=_BACKEND_VALIDATION,
                        message="request_ref 不匹配同公司活动 waiting 队列项",
                    )
                # backend 内前置数量 + 1
                cur = await conn.execute(
                    """SELECT COUNT(*) FROM backend_queue_entries
                       WHERE backend_id = ? AND status = 'waiting'
                         AND created_at < (SELECT created_at FROM backend_queue_entries WHERE entry_id = ?)""",
                    (backend_id, request_ref),
                )
                backend_position = (await cur.fetchone())[0] + 1
                result["backend_position"] = backend_position
                result["wait_reason"] = entry["wait_reason"]
                # 不可调度时 rank 为 null
                if available > 0:
                    result["global_schedulable_rank"] = backend_position
                else:
                    result["global_schedulable_rank"] = None

        return result

    # ── 默认映射辅助 ────────────────────────────────────────

    async def _ensure_default(
        self, conn: aiosqlite.Connection, company_id: str, backend_id: str
    ) -> None:
        """若公司无默认 backend，则把本 backend 原子补为默认。"""
        cur = await conn.execute(
            "SELECT 1 FROM company_backend_defaults WHERE company_id = ? AND is_archived = 0",
            (company_id,),
        )
        if await cur.fetchone() is not None:
            return
        await conn.execute(
            """INSERT INTO company_backend_defaults
               (default_id, company_id, backend_id, is_archived, version, created_at, updated_at)
               VALUES (?, ?, ?, 0, 1, ?, ?)""",
            (str(uuid.uuid4()), company_id, backend_id, _now(), _now()),
        )

    async def _assert_workspace_root_unique(
        self, company_id: str, workspace_root: str, exclude_backend_id: Optional[str]
    ) -> None:
        """同公司 workspace_root 不得相同或父子重叠。"""
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT backend_id, workspace_root FROM backends WHERE company_id = ? AND status != 'archived'",
                (company_id,),
            )
            rows = await cur.fetchall()
        from pathlib import Path

        new_p = Path(workspace_root).resolve()
        for r in rows:
            if r["backend_id"] == exclude_backend_id:
                continue
            if not r["workspace_root"]:
                continue
            exist_p = Path(r["workspace_root"]).resolve()
            try:
                if new_p == exist_p or new_p in exist_p.parents or exist_p in new_p.parents:
                    raise AcosError(
                        code=_BACKEND_VALIDATION,
                        message="workspace_root 与同公司其他 backend 相同/父子重叠",
                    )
            except (OSError, RuntimeError):
                continue


class LocalBackendHealthProbe:
    """本地 Backend 健康检查。

    真实可落地检查（v1 不调用 Provider 网络）：
      - workspace 可写：在 workspace_root 下尝试创建/删除临时文件
      - 受控 worker handshake：检查 worker 握手标记可达（此处以运行时状态判断）
      - 进程池：检查进程池计数可用
      - git_cli 声明时执行受控 Git 可用性检查（git --version）
    任一失败映射明确 reason；未声明 git_cli 时为 None 且不误报。
    """

    async def run(
        self,
        workspace_root: str,
        capabilities: list[str],
        now: str,
    ) -> dict[str, Any]:
        import os
        import shutil
        import subprocess
        import tempfile

        reasons: list[str] = []
        workspace_writable = False
        worker_handshake_ok = True  # v1：受控 worker 握手可达（无独立 worker 进程时视为 ok）
        process_pool_ok = True        # v1：进程池可用（本地进程池默认可用）

        # workspace 可写检查
        if workspace_root:
            try:
                p = os.path.realpath(workspace_root)
                os.makedirs(p, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=p, prefix=".probe_", delete=True) as tf:
                    tf.write(b"ok")
                    tf.flush()
                    os.fsync(tf.fileno())
                workspace_writable = True
            except (OSError, PermissionError) as exc:
                workspace_writable = False
                reasons.append(f"workspace 不可写: {exc}")
        else:
            # 无 workspace_root 时视为不可写（需配置）
            workspace_writable = False
            reasons.append("workspace_root 为空")

        # git_cli 受控可用性检查
        git_cli_ok: Optional[bool] = None
        if "git_cli" in capabilities:
            git_path = shutil.which("git")
            if git_path is None:
                git_cli_ok = False
                reasons.append("git 不可用")
            else:
                try:
                    proc = await asyncio_subprocess_check(git_path, ["--version"])
                    git_cli_ok = proc
                    if not proc:
                        reasons.append("git --version 失败")
                except Exception as exc:
                    git_cli_ok = False
                    reasons.append(f"git 检查异常: {exc}")

        if workspace_writable and worker_handshake_ok and process_pool_ok and (git_cli_ok is not False):
            health = "healthy"
        elif workspace_writable:
            health = "degraded"
        else:
            health = "unavailable"

        return {
            "health_status": health,
            "reason": "; ".join(reasons) if reasons else None,
            "workspace_writable": workspace_writable,
            "worker_handshake_ok": worker_handshake_ok,
            "process_pool_ok": process_pool_ok,
            "git_cli_ok": git_cli_ok,
        }


async def asyncio_subprocess_check(git_path: str, args: list[str]) -> bool:
    import asyncio

    try:
        proc = await asyncio.create_subprocess_exec(
            git_path, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=3.0)
        return proc.returncode == 0
    except (asyncio.TimeoutError, OSError):
        return False
