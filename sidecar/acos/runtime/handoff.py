"""调岗 Handoff 状态机 + 崩溃对账（Phase 7-T4，安全关键）。

范围仅限职员的**通用会话线程**（task_id 为空）。任务绑定线程天然按 task_id 隔离，
不受调岗影响。

状态机（显式，非 SQLite 事务回滚文件）：
- handle_transfer：staging 写新线程 → 原子 rename → 旧线程置 archived → 短事务更新
  employee.primary_session_thread_id + session_transfer_state='none' + 写 EmployeeTransferred
  （全流程只有这一步写它）+ 写 org_change_audit，提交。
- reconciler_scan_transferring：Sidecar 启动时扫描 session_transfer_state='transferring' 的职员，
  判定 completed / needs_repair。

安全红线：旧部门私有信息不带入新线程的活跃上下文（新建线程，不复制旧 transcript）。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from acos.rpc.errors import AcosError, ORG_NOT_FOUND, RT_SESSION_NOT_FOUND
from acos.runtime import transcript as tx
from acos.runtime.path_broker import ensure_company_dir, resolve_session_path
from acos.runtime.session_thread_store import SessionThreadStore, _now

_RT_PATH_DENIED = "BACKEND-PATH-DENIED"


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class HandoffService:
    """调岗 Handoff 编排。"""

    def __init__(self, db_path: str, company_root: str) -> None:
        self._db_path = db_path
        self._company_root = company_root
        self._store = SessionThreadStore(db_path, company_root)

    # ── 预检 ─────────────────────────────────────────────

    async def _require_employee(self, employee_id: str) -> dict[str, Any]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM employees WHERE employee_id = ? AND deleted_at IS NULL",
                (employee_id,),
            )
            row = await cur.fetchone()
            if row is None:
                raise AcosError(ORG_NOT_FOUND, "职员不存在", cause=employee_id)
            return dict(row)

    # ── 主流程 ───────────────────────────────────────────

    async def handle_transfer(
        self, employee_id: str, new_department_id: str, *, drain_id: str = ""
    ) -> dict[str, Any]:
        """执行通用线程调岗 Handoff（安全关键）。"""
        emp = await self._require_employee(employee_id)
        company_id = emp["company_id"]

        # 取出旧通用线程（task_id IS NULL，取最近活动的一条）
        old_thread = await self._get_general_thread(employee_id)
        if old_thread is None:
            # 无通用线程：直接建新线程并绑定，无需归档
            return await self._bind_new_general_thread(employee_id, company_id, drain_id)

        old_thread_id = old_thread["thread_id"]

        # 1) 在 staging 路径写新通用线程（不复制旧 transcript 内容）
        new_ctx_key = old_thread["security_context_key"]  # 同职员同部门通用线程 key 保持
        staging_dir = resolve_session_path(
            self._company_root, company_id, "sessions", "_staging", employee_id
        )
        ensure_company_dir(self._company_root, company_id)
        staging_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(staging_dir, 0o700)

        new_thread_id = str(uuid.uuid4())
        session_doc = {
            "schema_version": "acos:session:v1",
            "thread_id": new_thread_id,
            "company_id": company_id,
            "employee_id": employee_id,
            "security_context_key": new_ctx_key,
            "status": "active",
            "task_id": None,
            "transferred_from": old_thread_id,
            "version": 1,
        }
        staging_session_path = staging_dir / "session.json"
        tmp = staging_session_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(session_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, staging_session_path)
        staging_checksum = tx._sha256(staging_session_path.read_text(encoding="utf-8"))

        # 2) 原子 rename 到最终位置
        final_dir = resolve_session_path(
            self._company_root, company_id, "sessions", new_thread_id
        )
        final_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(final_dir, 0o700)
        os.replace(staging_session_path, final_dir / "session.json")

        # 3) DB 事务：旧线程 archived + 新线程登记 + employee 绑定 + EmployeeTransferred
        await self._complete_transfer(
            employee_id, company_id, new_thread_id, new_ctx_key,
            old_thread_id, drain_id, staging_checksum, str(final_dir / "session.json"),
        )

        return {
            "employee_id": employee_id,
            "old_thread_id": old_thread_id,
            "new_thread_id": new_thread_id,
            "status": "transferred",
        }

    async def _complete_transfer(
        self, employee_id: str, company_id: str, new_thread_id: str,
        security_context_key: str, old_thread_id: str | None, drain_id: str,
        staging_checksum: str, session_json_path: str,
    ) -> None:
        """提交 Handoff 的 DB 事务（正常路径与对账器补完共用，恰好一次）。"""
        async with aiosqlite.connect(self._db_path) as db:
            now = _stamp()
            if old_thread_id is not None:
                # 旧通用线程置 archived（不删除，留审计引用）
                await db.execute(
                    """UPDATE session_threads
                       SET status = 'archived', archived_at = ?, transfer_state = 'none',
                           version = version + 1, updated_at = ?
                       WHERE thread_id = ?""",
                    (now, now, old_thread_id),
                )
            # 登记新线程
            await db.execute(
                """INSERT INTO session_threads
                   (thread_id, company_id, employee_id, security_context_key, task_id,
                    status, transfer_state, resume_mode, version, created_at, updated_at,
                    session_json_path)
                   VALUES (?, ?, ?, ?, NULL, 'active', 'none', '', 1, ?, ?, ?)""",
                (new_thread_id, company_id, employee_id, security_context_key, now, now,
                 session_json_path),
            )
            # 写 EmployeeTransferred（恰好一次，UNIQUE 索引保护）
            await db.execute(
                """INSERT INTO session_transfer_journal
                   (journal_id, company_id, employee_id, event_type, drain_id,
                    old_thread_id, new_thread_id, detail, created_at)
                   VALUES (?, ?, ?, 'EmployeeTransferred', ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), company_id, employee_id, drain_id,
                 old_thread_id, new_thread_id,
                 json.dumps({"staging_checksum": staging_checksum}), now),
            )
            # employee 绑定新线程 + 状态置回 none
            await db.execute(
                """UPDATE employees
                   SET primary_session_thread_id = ?, session_transfer_state = 'none',
                       updated_at = ?, version = version + 1
                   WHERE employee_id = ?""",
                (new_thread_id, now, employee_id),
            )
            # org_change_audit
            await db.execute(
                """INSERT INTO org_change_audit
                   (id, company_id, aggregate_type, aggregate_id, action,
                    before_snapshot, after_snapshot, operator, reason, trace_id, timestamp)
                   VALUES (?, ?, 'employee', ?, 'session_handoff', ?, ?, 'system',
                           'general thread handoff on transfer', ?, ?)""",
                (str(uuid.uuid4()), company_id, employee_id,
                 json.dumps({"primary_session_thread_id": old_thread_id}),
                 json.dumps({"primary_session_thread_id": new_thread_id}),
                 str(uuid.uuid4()), now),
            )
            await db.commit()

    async def _get_general_thread(self, employee_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT * FROM session_threads
                   WHERE employee_id = ? AND task_id IS NULL
                     AND status NOT IN ('archived')
                   ORDER BY updated_at DESC LIMIT 1""",
                (employee_id,),
            )
            row = await cur.fetchone()
            return dict(row) if row is not None else None

    async def _bind_new_general_thread(
        self, employee_id: str, company_id: str, drain_id: str
    ) -> dict[str, Any]:
        new_thread_id = str(uuid.uuid4())
        now = _stamp()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO session_threads
                   (thread_id, company_id, employee_id, security_context_key, task_id,
                    status, transfer_state, resume_mode, version, created_at, updated_at)
                   VALUES (?, ?, ?, '', NULL, 'active', 'none', '', 1, ?, ?)""",
                (new_thread_id, company_id, employee_id, now, now),
            )
            await db.execute(
                """INSERT INTO session_transfer_journal
                   (journal_id, company_id, employee_id, event_type, drain_id,
                    new_thread_id, detail, created_at)
                   VALUES (?, ?, ?, 'EmployeeTransferred', ?, ?, ?, ?)""",
                (str(uuid.uuid4()), company_id, employee_id, drain_id, new_thread_id,
                 json.dumps({"note": "no prior general thread"}), now),
            )
            await db.execute(
                """UPDATE employees
                   SET primary_session_thread_id = ?, session_transfer_state = 'none',
                       updated_at = ?, version = version + 1
                   WHERE employee_id = ?""",
                (new_thread_id, now, employee_id),
            )
            await db.commit()
        return {
            "employee_id": employee_id,
            "old_thread_id": None,
            "new_thread_id": new_thread_id,
            "status": "transferred",
        }

    # ── 崩溃对账 ─────────────────────────────────────────

    async def reconciler_scan_transferring(self) -> list[dict[str, Any]]:
        """扫描 session_transfer_state='transferring' 的职员，判定 completed/needs_repair。"""
        results: list[dict[str, Any]] = []
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT employee_id, company_id FROM employees WHERE session_transfer_state = 'transferring'"
            )
            rows = await cur.fetchall()
        for r in rows:
            outcome = await self._reconcile_one(r["employee_id"], r["company_id"])
            results.append(outcome)
        return results

    async def _reconcile_one(self, employee_id: str, company_id: str) -> dict[str, Any]:
        company_dir = ensure_company_dir(self._company_root, company_id)
        staging_dir = company_dir / "sessions" / "_staging" / employee_id

        # 是否已写过 EmployeeTransferred（已完成幂等）
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM session_transfer_journal WHERE employee_id = ? AND event_type = 'EmployeeTransferred'",
                (employee_id,),
            )
            already_transferred = await cur.fetchone() is not None

        # 无法安全判定：staging 不完整
        if staging_dir.exists():
            if not self._staging_complete(staging_dir):
                await self._mark_needs_repair(employee_id, company_id, "staging incomplete")
                return {"employee_id": employee_id, "outcome": "needs_repair"}
            # staging 完整但未提交 DB：补完事务
            session_doc = json.loads((staging_dir / "session.json").read_text(encoding="utf-8"))
            new_thread_id = session_doc.get("thread_id")
            if already_transferred:
                # 已写过 journal：仅清理 staging 残留
                self._rm_staging(staging_dir)
                return {"employee_id": employee_id, "outcome": "completed"}
            # 真正补完：登记新线程 + 旧线程归档 + EmployeeTransferred + employee 绑定
            old_thread_id = session_doc.get("transferred_from") or await self._find_archived_general_thread(employee_id)
            await self._complete_transfer(
                employee_id, company_id, new_thread_id,
                session_doc.get("security_context_key", ""),
                old_thread_id, drain_id="",
                staging_checksum="", session_json_path=str(staging_dir / "session.json"),
            )
            self._rm_staging(staging_dir)
            return {"employee_id": employee_id, "outcome": "completed"}

        if already_transferred:
            # 已提交，仅清理 staging
            self._rm_staging(staging_dir)
            return {"employee_id": employee_id, "outcome": "completed"}

        # 未提交且无可判定 staging：needs_repair
        await self._mark_needs_repair(employee_id, company_id, "no staging, no journal")
        return {"employee_id": employee_id, "outcome": "needs_repair"}

    def _staging_complete(self, staging_dir: Path) -> bool:
        session_path = staging_dir / "session.json"
        if not session_path.exists():
            return False
        try:
            doc = json.loads(session_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        return bool(doc.get("thread_id")) and bool(doc.get("security_context_key"))

    def _rm_staging(self, staging_dir: Path) -> None:
        import shutil
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    async def _find_archived_general_thread(self, employee_id: str) -> str | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT thread_id FROM session_threads
                   WHERE employee_id = ? AND task_id IS NULL AND status = 'archived'
                   ORDER BY updated_at DESC LIMIT 1""",
                (employee_id,),
            )
            row = await cur.fetchone()
            return row["thread_id"] if row else None

    async def _mark_needs_repair(
        self, employee_id: str, company_id: str, reason: str
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            # 删除不完整 staging
            company_dir = ensure_company_dir(self._company_root, company_id)
            staging_dir = company_dir / "sessions" / "_staging" / employee_id
            self._rm_staging(staging_dir)
            await db.execute(
                """INSERT INTO session_transfer_journal
                   (journal_id, company_id, employee_id, event_type, detail, created_at)
                   VALUES (?, ?, ?, 'EmployeeTransferNeedsRepair', ?, ?)""",
                (str(uuid.uuid4()), company_id, employee_id, json.dumps({"reason": reason}), _stamp()),
            )
            await db.execute(
                "UPDATE employees SET session_transfer_state = 'needs_repair', updated_at = ?, version = version + 1 WHERE employee_id = ?",
                (_stamp(), employee_id),
            )
            await db.commit()
