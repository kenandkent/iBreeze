"""Session 命名空间 RPC（Phase 7）：session.* 设计命名。

注册：
- session.list
- session.get
- session.sendMessage   （内部惰性 get_or_create_current_thread，按九维 key 分片；单线程一个 active turn 用 DB CAS）
- session.cancel
- session.transcript.get
- session.resume        （内部）

对接点：
- provider.runtime：通过 FakeProviderAdapter 驱动 AgentRuntime.send（不调真实 API）。
- backend.lease：BackendService.select_backend + BackendLeaseManager.bind / release（真实调用）。
- org.permission：消费有效授权计算 effective_grants_hash。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from acos.backends.service import BackendLeaseManager, BackendService
from acos.providers.fake import FakeProviderAdapter
from acos.rpc.errors import (
    AcosError,
    RT_SESSION_BUSY,
    RT_SESSION_NOT_FOUND,
    RT_SESSION_READONLY,
    RT_SESSION_STALE,
    BACKEND_UNAVAILABLE,
    ORG_NOT_FOUND,
    ORG_PERM_DENIED,
    ORG_STATE_INVALID,
    SYS_OPTIMISTIC_LOCK_CONFLICT,
)
from acos.runtime import transcript as tx
from acos.runtime.employee_drain_port import EmployeeDrainRuntimePort
from acos.runtime.handoff import HandoffService
from acos.runtime.resume import resume_session
from acos.runtime.session_thread_store import SessionThreadStore

# 本地新增错误码（沿用既有 RT-* 体系，新增用本地常量，不写 errors.py）
RT_DRAIN_TOKEN_INVALID = "RT-DRAIN-TOKEN-INVALID"
RT_EMPLOYEE_NOT_ACTIVE = "RT-EMPLOYEE-NOT-ACTIVE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionMethods:
    """session.* RPC 方法。"""

    def __init__(
        self, db_path: str, company_root: str = "/tmp/acos_sessions",
        require_backend: bool = False,
    ) -> None:
        self._db_path = db_path
        self._company_root = company_root
        # 生产路径可设 True：无 healthy backend 时失败并触发恢复干预
        self.require_backend = require_backend
        self._store = SessionThreadStore(db_path, company_root)
        self._handoff = HandoffService(db_path, company_root)
        self._drain_port = EmployeeDrainRuntimePort(db_path, company_root)
        self._fake = FakeProviderAdapter()
        self._lease_mgr = BackendLeaseManager(db_path)
        self._backend_svc = BackendService(db_path)

    def register_to(self, server: Any) -> None:
        server.register_method("session.list", self._list)
        server.register_method("session.get", self._get)
        server.register_method("session.sendMessage", self._send_message)
        server.register_method("session.cancel", self._cancel)
        server.register_method("session.transcript.get", self._transcript_get)
        server.register_method("session.resume", self._resume)
        # 内部端口（drain token 调用）
        server.register_method("session._suspend", self._suspend)
        server.register_method("session._archive", self._archive)
        server.register_method("session._handoff", self._handoff_rpc)
        server.register_method("session._reconcile", self._reconcile)

    # ── 安全上下文解析 ───────────────────────────────────

    async def _resolve_security_context(
        self, company_id: str, employee_id: str, task_id: str | None,
        provider_id: str, model_id: str,
    ) -> tuple[str, dict[str, Any]]:
        """服务端根据 Employee/Capability/Provider/Policy/有效授权重算 key（不接受客户端 key）。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ? AND deleted_at IS NULL",
                (employee_id,),
            )
            emp = await cur.fetchone()
            if emp is None:
                raise AcosError(ORG_NOT_FOUND, "职员不存在", cause=employee_id)
            department_id = emp["department_id"]
            capability_snapshot = emp["capability_snapshot"] or "{}"
            cap_checksum = tx._sha256(
                tx.canonical_json(json.loads(capability_snapshot))
            )

            cur = await db.execute(
                "SELECT default_provider_policy FROM companies WHERE company_id = ?",
                (company_id,),
            )
            comp = await cur.fetchone()
            workspace_policy = json.loads(comp["default_provider_policy"]) if comp and comp["default_provider_policy"] else {}

            cur = await db.execute(
                """SELECT grant_id, target_type, target_id, permission, expires_at
                   FROM access_grants
                   WHERE employee_id = ? AND company_id = ? AND status = 'active'
                     AND expires_at > ?""",
                (employee_id, company_id, _now()),
            )
            grants = [dict(r) for r in await cur.fetchall()]

        security_policy: dict[str, Any] = {}  # 暂无独立安全策略表，确定性空对象
        ctx_key = self._store.compute_security_context_key(
            company_id=company_id,
            department_id=department_id,
            task_id=task_id,
            capability_snapshot_checksum=cap_checksum,
            provider_id=provider_id,
            model_id=model_id,
            workspace_policy=workspace_policy,
            security_policy=security_policy,
            effective_grants=grants,
        )
        meta = {
            "capability_snapshot_checksum": cap_checksum,
            "workspace_policy_hash": tx.compute_workspace_policy_hash(workspace_policy),
            "security_policy_hash": tx.compute_security_policy_hash(security_policy),
            "effective_grants_hash": tx.compute_effective_grants_hash(grants),
        }
        return ctx_key, meta

    # ── session.list ─────────────────────────────────────

    async def _list(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        employee_id = params.get("employee_id")
        if not company_id or not employee_id:
            raise AcosError("RT-VALIDATION", "缺少 company_id/employee_id")
        threads = await self._store.list_threads(
            company_id, employee_id, include_archived=bool(params.get("include_archived"))
        )
        return {"threads": threads, "total": len(threads)}

    # ── session.get ──────────────────────────────────────

    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        thread_id = params.get("thread_id")
        if not thread_id:
            raise AcosError("RT-VALIDATION", "缺少 thread_id")
        thread = await self._store.get_thread(thread_id)
        # 跨公司/越权校验
        if params.get("employee_id") and thread["employee_id"] != params["employee_id"]:
            raise AcosError(ORG_PERM_DENIED, "无权访问该线程")
        return {"thread": thread}

    # ── session.sendMessage ──────────────────────────────

    async def _send_message(self, params: dict[str, Any]) -> dict[str, Any]:
        company_id = params.get("company_id")
        employee_id = params.get("employee_id")
        message = params.get("message", "")
        task_id = params.get("task_id") or None
        provider_id = params.get("provider_id", "fake")
        model_id = params.get("model_id", "fake-model-1")
        thread_id = params.get("thread_id")  # 可选；不传走当前通用线程

        if not company_id or not employee_id:
            raise AcosError("RT-VALIDATION", "缺少 company_id/employee_id")
        if not message:
            raise AcosError("RT-VALIDATION", "message 不能为空")

        # 解析安全上下文
        ctx_key, meta = await self._resolve_security_context(
            company_id, employee_id, task_id, provider_id, model_id
        )

        # SC-40-2：员工 suspended / 模板 archived 触发 READONLY（无条件）
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT status, template_id FROM employees WHERE employee_id = ? AND deleted_at IS NULL",
                (employee_id,),
            )
            emp = await cur.fetchone()
            emp_status = emp["status"] if emp else None
            template_id = emp["template_id"] if emp else None
            tpl_status = None
            if template_id is not None:
                cur = await db.execute(
                    "SELECT status FROM employee_templates WHERE template_id = ?",
                    (template_id,),
                )
                tpl = await cur.fetchone()
                tpl_status = tpl["status"] if tpl else None
        if emp_status == "suspended":
            raise AcosError(RT_SESSION_READONLY, "会话为只读(员工已暂停)", cause=employee_id)
        if tpl_status == "archived":
            raise AcosError(RT_SESSION_READONLY, "会话为只读(模板已归档)", cause=template_id)

        if thread_id:
            thread = await self._store.get_thread(thread_id)
            if thread["employee_id"] != employee_id or thread["company_id"] != company_id:
                raise AcosError("ORG-PERM-DENIED", "无权访问该线程")
            # 安全上下文已变化 → STALE
            if thread["security_context_key"] != ctx_key:
                raise AcosError(RT_SESSION_STALE, "会话安全上下文已变化，请使用新线程",
                                cause=thread_id)
        else:
            thread = await self._store.get_or_create_current_thread(
                company_id, employee_id, ctx_key,
                task_id=task_id,
                capability_snapshot_checksum=meta["capability_snapshot_checksum"],
                provider_id=provider_id,
                model_id=model_id,
                workspace_policy_hash=meta["workspace_policy_hash"],
                security_policy_hash=meta["security_policy_hash"],
                effective_grants_hash=meta["effective_grants_hash"],
            )
            thread_id = thread["thread_id"]

        # 只读状态 → READONLY
        if thread["status"] in ("dormant", "archived"):
            raise AcosError(RT_SESSION_READONLY, "会话为只读", cause=thread_id)

        # 单 active turn CAS
        turn_id = str(uuid.uuid4())
        await self._store.acquire_active_turn(
            thread_id, turn_id, expected_version=int(thread["version"])
        )

        try:
            # 写用户消息事件
            await self._store.append_event(
                thread_id, company_id=company_id, employee_id=employee_id,
                event_type="message", role="user", content=message,
            )

            # Backend lease 接入（真实调用；无可用 backend 时跳过，turn 仍可被 FakeProvider 驱动）
            lease_id = await self._try_acquire_lease(company_id, thread_id, turn_id)

            # SC-40-4（方案 A：开关）：无 healthy backend 时失败并触发恢复干预
            if lease_id is None and self.require_backend:
                from acos.interventions.repository import InterventionRepository
                repo = InterventionRepository()
                async with aiosqlite.connect(self._db_path) as db:
                    await db.execute("PRAGMA foreign_keys = OFF")
                    await repo.create_or_get_open(
                        db,
                        company_id=company_id,
                        subtype="backend_recovery",
                        target_ref=f"backend_lease:{company_id}",
                        allowed_actions=["retry", "resolve"],
                        trace_id=turn_id,
                    )
                raise AcosError(
                    BACKEND_UNAVAILABLE, "无可用 healthy backend,已创建恢复干预",
                    cause=company_id,
                )

            # 调用 Provider（FakeProviderAdapter，不调真实 API）
            provider_result = await self._call_provider(
                thread_id, message, company_id, provider_id, model_id
            )

            # 写助手回复事件
            reply = provider_result.get("reply", "")
            await self._store.append_event(
                thread_id, company_id=company_id, employee_id=employee_id,
                event_type="message", role="assistant", content=reply,
            )

            if lease_id:
                await self._lease_mgr.release(lease_id)

            # 释放 active turn
            await self._store.release_active_turn(
                thread_id, turn_id, expected_version=int(thread["version"]) + 1,
                next_status="active",
            )

            # 重建投影
            proj = await self._store.rebuild_projection_from_db(thread_id)
        except Exception:
            # 异常时释放 turn
            await self._store.force_release_active_turn(thread_id, next_status="failed")
            raise

        return {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "reply": provider_result.get("reply", ""),
            "transcript_checksum": proj["transcript_checksum"],
        }

    async def _try_acquire_lease(
        self, company_id: str, thread_id: str, turn_id: str
    ) -> str | None:
        """尝试从公司默认 Backend 取得绑定 turn 的 lease（真实调用）。"""
        try:
            backend = await self._backend_svc.select_backend(company_id)
        except Exception:
            return None
        if backend is None:
            return None
        try:
            lease = await self._lease_mgr.bind(
                backend.backend_id, company_id, session_turn_id=thread_id
            )
            return lease.lease_id
        except Exception:
            return None

    async def _call_provider(
        self, thread_id: str, message: str, company_id: str,
        provider_id: str, model_id: str,
    ) -> dict[str, Any]:
        """驱动 FakeProviderAdapter 执行一次 send（真实调用契约，不调外部 API）。"""
        # 构造最小 runtime session 上下文
        session = type("S", (), {
            "session_id": f"rs-{thread_id}",
            "company_id": company_id,
            "provider_id": provider_id,
            "model": model_id,
            "department_id": "",
            "employee_id": "",
            "native_session_id": f"native-{model_id}",
            "status": "active",
            "version": 1,
        })()
        events: list[Any] = []
        result = await self._fake.send(session, message, stream=True)
        async for ev in result:
            events.append(ev)
        reply = ""
        for ev in events:
            if ev.event_type == "message":
                reply = ev.payload.get("content", "")
        # 记录本次发送给 Provider 的上下文（用于 Handoff 泄漏断言）
        transcript_lines = await self._store.read_transcript(thread_id)
        provider_context = "\n".join(
            f"{ln['role']}: {ln['content']}" for ln in transcript_lines
        )
        return {"reply": reply, "provider_context": provider_context, "events": events}

    # ── session.cancel ───────────────────────────────────

    async def _cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        thread_id = params.get("thread_id")
        turn_id = params.get("turn_id")
        if not thread_id:
            raise AcosError("RT-VALIDATION", "缺少 thread_id")
        thread = await self._store.get_thread(thread_id)
        if turn_id and thread.get("active_turn_id") and thread["active_turn_id"] != turn_id:
            raise AcosError(RT_SESSION_BUSY, "指定的 turn 并非当前 active turn")
        # 释放 active turn（无 turn_id 时强制释放）
        if turn_id:
            ok = await self._store.release_active_turn(
                thread_id, turn_id, expected_version=int(thread["version"]),
                next_status="active",
            )
        else:
            ok = await self._store.force_release_active_turn(thread_id, next_status="active")
        return {"thread_id": thread_id, "cancelled": ok}

    # ── session.transcript.get ───────────────────────────

    async def _transcript_get(self, params: dict[str, Any]) -> dict[str, Any]:
        thread_id = params.get("thread_id")
        if not thread_id:
            raise AcosError("RT-VALIDATION", "缺少 thread_id")
        thread = await self._store.get_thread(thread_id)
        if params.get("employee_id") and thread["employee_id"] != params["employee_id"]:
            raise AcosError("ORG-PERM-DENIED", "无权访问该线程")
        lines = await self._store.read_transcript(thread_id)
        return {"thread_id": thread_id, "transcript": lines, "total": len(lines)}

    # ── session.resume（内部）────────────────────────────

    async def _resume(self, params: dict[str, Any]) -> dict[str, Any]:
        thread_id = params.get("thread_id")
        if not thread_id:
            raise AcosError("RT-VALIDATION", "缺少 thread_id")
        token_budget = int(params.get("token_budget", 8000))
        checkpoint = params.get("checkpoint")
        thread = await self._store.get_thread(thread_id)
        result = await resume_session(
            self._store, self._fake, thread_id,
            company_id=thread["company_id"],
            provider_id=thread.get("provider_id") or "fake",
            model=thread.get("model_id") or "fake-model-1",
            token_budget=token_budget,
            checkpoint=checkpoint,
        )
        return result

    # ── 内部端口 ─────────────────────────────────────────

    async def _suspend(self, params: dict[str, Any]) -> dict[str, Any]:
        employee_id = params.get("employee_id")
        drain_id = params.get("drain_id", "")
        drain_token = params.get("drain_token", "")
        if not employee_id or not drain_id or not drain_token:
            raise AcosError(RT_DRAIN_TOKEN_INVALID, "suspend 需要 drain_id + drain_token")
        return await self._drain_port.suspend(
            employee_id, drain_id=drain_id, drain_token=drain_token
        )

    async def _archive(self, params: dict[str, Any]) -> dict[str, Any]:
        employee_id = params.get("employee_id")
        drain_id = params.get("drain_id", "")
        drain_token = params.get("drain_token", "")
        if not employee_id:
            raise AcosError("RT-VALIDATION", "缺少 employee_id")
        return await self._drain_port.archive_employee(
            employee_id, drain_id=drain_id, drain_token=drain_token
        )

    async def _handoff_rpc(self, params: dict[str, Any]) -> dict[str, Any]:
        employee_id = params.get("employee_id")
        new_department_id = params.get("new_department_id")
        drain_id = params.get("drain_id", "")
        if not employee_id or not new_department_id:
            raise AcosError("RT-VALIDATION", "缺少 employee_id/new_department_id")
        return await self._handoff.handle_transfer(
            employee_id, new_department_id, drain_id=drain_id
        )

    async def _reconcile(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"results": await self._handoff.reconciler_scan_transferring()}
