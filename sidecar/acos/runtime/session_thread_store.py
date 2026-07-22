"""会话线程存储（Phase 7 核心）：SQLite 事实源 + 文件投影重建。

设计要点（对照设计方案 §11.4）：
- `session_threads` 是线程元数据事实源，`conversation_events` 是消息/工具事件事实源。
- 文件投影（session.json / transcript.jsonl / context-summary.md）由 SQLite 重建，
  原子写（临时文件 rename），目录 0700。禁止用旧文件覆盖数据库。
- 单个线程同时一个 active turn：由 DB CAS `active_turn_id` 作为唯一权威。
- 九维安全上下文 key 通过 transcript.compute_security_context_key 计算。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from acos.rpc.errors import (
    AcosError,
    RT_SESSION_BUSY,
    RT_SESSION_NOT_FOUND,
    RT_SESSION_READONLY,
    RT_SESSION_STALE,
    ORG_NOT_FOUND,
)
from acos.runtime import transcript as tx
from acos.runtime.path_broker import ensure_company_dir, resolve_session_path

# 线程状态机（P7-T5）
ALLOWED_STATUSES = (
    "active", "running", "waiting_backend", "waiting_approval",
    "dormant", "archived", "failed", "recovering",
)

# 仅读状态：dormant / archived 仍可分页读 transcript，但拒绝新 turn
_READONLY_STATES = ("dormant", "archived")

# 状态机合法转换（P7-T5）：active 即 idle。
_ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "active": ("running", "waiting_backend", "dormant", "archived"),
    "running": ("active", "waiting_approval", "waiting_backend", "dormant", "archived", "failed"),
    "waiting_backend": ("running", "active", "dormant", "archived"),
    "waiting_approval": ("running", "dormant", "archived"),
    "dormant": ("active", "archived"),
    "failed": ("recovering", "archived"),
    "recovering": ("running", "archived"),
    "archived": (),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_thread(row: aiosqlite.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


class SessionThreadStore:
    """会话线程事实源与投影管理。"""

    def __init__(self, db_path: str, company_root: str) -> None:
        self._db_path = db_path
        self._company_root = company_root

    # ── 安全上下文 key 计算 ──────────────────────────────

    def compute_security_context_key(
        self,
        company_id: str,
        department_id: str,
        task_id: str | None,
        capability_snapshot_checksum: str,
        provider_id: str,
        model_id: str,
        workspace_policy: dict,
        security_policy: dict,
        effective_grants: list[dict],
    ) -> str:
        """计算九维安全上下文 key（确定性）。"""
        ws_hash = tx.compute_workspace_policy_hash(workspace_policy)
        sec_hash = tx.compute_security_policy_hash(security_policy)
        grants_hash = tx.compute_effective_grants_hash(effective_grants)
        return tx.compute_security_context_key(
            company_id=company_id,
            department_id=department_id,
            task_id=task_id,
            capability_snapshot_checksum=capability_snapshot_checksum,
            provider_id=provider_id,
            model_id=model_id,
            workspace_policy_hash=ws_hash,
            security_policy_hash=sec_hash,
            effective_grants_hash=grants_hash,
        )

    # ── 线程惰性创建/复用 ────────────────────────────────

    async def get_or_create_current_thread(
        self,
        company_id: str,
        employee_id: str,
        security_context_key: str,
        *,
        task_id: str | None = None,
        capability_snapshot_checksum: str = "",
        provider_id: str = "",
        model_id: str = "",
        workspace_policy_hash: str = "",
        security_policy_hash: str = "",
        effective_grants_hash: str = "",
    ) -> dict[str, Any]:
        """按 (employee_id, security_context_key) 复用或创建活动线程。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT * FROM session_threads
                   WHERE company_id = ? AND employee_id = ? AND security_context_key = ?
                     AND status NOT IN ('archived')
                   ORDER BY updated_at DESC LIMIT 1""",
                (company_id, employee_id, security_context_key),
            )
            row = await cur.fetchone()
            if row is not None:
                return _row_to_thread(row)

            thread_id = str(uuid.uuid4())
            now = _now()
            await db.execute(
                """INSERT INTO session_threads
                   (thread_id, company_id, employee_id, security_context_key, task_id,
                    capability_snapshot_checksum, provider_id, model_id,
                    workspace_policy_hash, security_policy_hash, effective_grants_hash,
                    status, transfer_state, resume_mode, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 'none', '', 1, ?, ?)""",
                (thread_id, company_id, employee_id, security_context_key, task_id,
                 capability_snapshot_checksum, provider_id, model_id,
                 workspace_policy_hash, security_policy_hash, effective_grants_hash,
                 now, now),
            )
            await db.commit()
            cur = await db.execute(
                "SELECT * FROM session_threads WHERE thread_id = ?", (thread_id,)
            )
            return _row_to_thread(await cur.fetchone())

    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM session_threads WHERE thread_id = ?", (thread_id,)
            )
            row = await cur.fetchone()
            if row is None:
                raise AcosError(RT_SESSION_NOT_FOUND, "线程不存在", cause=thread_id)
            return _row_to_thread(row)

    async def list_threads(
        self, company_id: str, employee_id: str = "", *, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if employee_id:
                if include_archived:
                    cur = await db.execute(
                        "SELECT * FROM session_threads WHERE company_id = ? AND employee_id = ? ORDER BY updated_at DESC",
                        (company_id, employee_id),
                    )
                else:
                    cur = await db.execute(
                        "SELECT * FROM session_threads WHERE company_id = ? AND employee_id = ? AND status != 'archived' ORDER BY updated_at DESC",
                        (company_id, employee_id),
                    )
            else:
                if include_archived:
                    cur = await db.execute(
                        "SELECT * FROM session_threads WHERE company_id = ? ORDER BY updated_at DESC",
                        (company_id,),
                    )
                else:
                    cur = await db.execute(
                        "SELECT * FROM session_threads WHERE company_id = ? AND status != 'archived' ORDER BY updated_at DESC",
                        (company_id,),
                    )
            return [_row_to_thread(r) for r in await cur.fetchall()]

    # ── 事件追加 ─────────────────────────────────────────

    async def append_event(
        self,
        thread_id: str,
        *,
        company_id: str,
        employee_id: str,
        event_type: str,
        role: str = "",
        content: str = "",
        tool_name: str | None = None,
        tool_request_hash: str | None = None,
        artifact_ref: str | None = None,
        provider_native_event_id: str | None = None,
    ) -> dict[str, Any]:
        """在单事务内追加一条 conversation_event，并更新线程 last_event_seq。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT last_event_seq FROM session_threads WHERE thread_id = ?",
                (thread_id,),
            )
            row = await cur.fetchone()
            if row is None:
                raise AcosError(RT_SESSION_NOT_FOUND, "线程不存在", cause=thread_id)
            seq = int(row["last_event_seq"]) + 1
            token_estimate = tx.estimate_tokens(content)
            line = tx.build_transcript_line(
                sequence=seq,
                event_type=event_type,
                role=role,
                content=content,
                tool_name=tool_name,
                tool_request_hash=tool_request_hash,
                artifact_ref=artifact_ref,
                token_estimate=token_estimate,
                provider_native_event_id=provider_native_event_id,
            )
            event_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO conversation_events
                   (event_id, thread_id, company_id, employee_id, sequence,
                    schema_version, event_type, role, content, tool_name,
                    tool_request_hash, artifact_ref, token_estimate,
                    provider_native_event_id, canonical_checksum, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, thread_id, company_id, employee_id, seq,
                 tx.CONVERSATION_EVENT_SCHEMA_VERSION, event_type, role, content,
                 tool_name, tool_request_hash, artifact_ref, token_estimate,
                 provider_native_event_id, line["canonical_checksum"], _now()),
            )
            await db.execute(
                "UPDATE session_threads SET last_event_seq = ?, updated_at = ? WHERE thread_id = ?",
                (seq, _now(), thread_id),
            )
            await db.commit()
            return {"event_id": event_id, "sequence": seq, "line": line}

    async def get_events(
        self, thread_id: str, *, limit: int = 1000, offset: int = 0
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """SELECT * FROM conversation_events
                   WHERE thread_id = ? ORDER BY sequence ASC
                   LIMIT ? OFFSET ?""",
                (thread_id, limit, offset),
            )
            return [dict(r) for r in await cur.fetchall()]

    # ── 单 active turn CAS ───────────────────────────────

    async def acquire_active_turn(
        self, thread_id: str, turn_id: str, *, expected_version: int
    ) -> bool:
        """CAS 占有 active turn。命中 affected=1 返回 True，否则 RT-SESSION-BUSY。"""
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """UPDATE session_threads
                   SET active_turn_id = ?, status = 'running', version = version + 1
                   WHERE thread_id = ? AND active_turn_id IS NULL AND version = ?""",
                (turn_id, thread_id, expected_version),
            )
            await db.commit()
            if cur.rowcount != 1:
                raise AcosError(RT_SESSION_BUSY, "会话正忙（已有 active turn）", cause=thread_id)
            return True

    async def release_active_turn(
        self, thread_id: str, turn_id: str, *, expected_version: int, next_status: str = "active"
    ) -> bool:
        """CAS 释放 active turn。"""
        if next_status not in ALLOWED_STATUSES:
            raise AcosError(RT_SESSION_READONLY, "非法状态", cause=next_status)
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """UPDATE session_threads
                   SET active_turn_id = NULL, status = ?, version = version + 1
                   WHERE thread_id = ? AND active_turn_id = ? AND version = ?""",
                (next_status, thread_id, turn_id, expected_version),
            )
            await db.commit()
            return cur.rowcount == 1

    async def force_release_active_turn(
        self, thread_id: str, *, next_status: str = "active"
    ) -> bool:
        """对账器用：忽略当前 turn_id 强制释放（进程已不在）。"""
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """UPDATE session_threads
                   SET active_turn_id = NULL, status = ?, version = version + 1
                   WHERE thread_id = ? AND active_turn_id IS NOT NULL""",
                (next_status, thread_id),
            )
            await db.commit()
            return cur.rowcount == 1

    # ── 状态机转换 ───────────────────────────────────────

    async def transition_status(
        self, thread_id: str, new_status: str, *, expected_version: int
    ) -> bool:
        if new_status not in ALLOWED_STATUSES:
            raise AcosError(RT_SESSION_READONLY, "非法状态", cause=new_status)
        thread = await self.get_thread(thread_id)
        current = thread["status"]
        if new_status not in _ALLOWED_TRANSITIONS.get(current, ()):
            raise AcosError(RT_SESSION_READONLY, "非法状态转换", cause=f"{current}->{new_status}")
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                """UPDATE session_threads
                   SET status = ?, version = version + 1, updated_at = ?
                   WHERE thread_id = ? AND version = ?""",
                (new_status, _now(), thread_id, expected_version),
            )
            await db.commit()
            return cur.rowcount == 1

    # ── 文件投影（原子写 + 重建）─────────────────────────

    def _thread_dir(self, company_id: str, thread_id: str) -> Path:
        return resolve_session_path(self._company_root, company_id, "sessions", thread_id)

    def _atomic_write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(path.parent, 0o700)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    async def rebuild_projection_from_db(self, thread_id: str) -> dict[str, Any]:
        """由 SQLite 事实重建 session.json / transcript.jsonl / context-summary.md。

        返回重建的路径与 checksum 摘要。旧文件不会被反向覆盖 DB。
        """
        thread = await self.get_thread(thread_id)
        company_id = thread["company_id"]
        thread_dir = self._thread_dir(company_id, thread_id)
        ensure_company_dir(self._company_root, company_id)
        thread_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        os.chmod(thread_dir, 0o700)

        events = await self.get_events(thread_id)
        lines = [tx.build_transcript_line(
            sequence=int(e["sequence"]),
            event_type=e["event_type"],
            role=e["role"],
            content=e["content"],
            tool_name=e.get("tool_name"),
            tool_request_hash=e.get("tool_request_hash"),
            artifact_ref=e.get("artifact_ref"),
            token_estimate=int(e.get("token_estimate", 0)),
            provider_native_event_id=e.get("provider_native_event_id"),
        ) for e in events]

        # session.json
        session_doc = {
            "schema_version": "acos:session:v1",
            "thread_id": thread_id,
            "company_id": company_id,
            "employee_id": thread["employee_id"],
            "security_context_key": thread["security_context_key"],
            "status": thread["status"],
            "task_id": thread.get("task_id"),
            "last_event_seq": thread.get("last_event_seq", 0),
            "version": thread.get("version", 1),
        }
        session_path = thread_dir / "session.json"
        self._atomic_write(session_path, json.dumps(session_doc, ensure_ascii=False, indent=2))

        # transcript.jsonl（canonical checksum 行）
        transcript_path = thread_dir / "transcript.jsonl"
        transcript_text = "".join(
            json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n" for line in lines
        )
        self._atomic_write(transcript_path, transcript_text)
        transcript_checksum = tx._sha256(transcript_text)

        # context-summary.md
        summary_path = thread_dir / "context-summary.md"
        summary_text = tx.build_context_summary(lines)
        self._atomic_write(summary_path, summary_text)
        summary_checksum = tx._sha256(summary_text)

        # 回写投影路径 + watermark 到 DB（不覆盖事件事实）
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """UPDATE session_threads
                   SET session_json_path = ?, transcript_path = ?, summary_path = ?,
                       watermark = ?, watermark_checksum = ?, updated_at = ?
                   WHERE thread_id = ?""",
                (str(session_path), str(transcript_path), str(summary_path),
                 transcript_checksum, transcript_checksum, _now(), thread_id),
            )
            await db.commit()

        return {
            "thread_id": thread_id,
            "session_json_path": str(session_path),
            "transcript_path": str(transcript_path),
            "summary_path": str(summary_path),
            "transcript_checksum": transcript_checksum,
            "summary_checksum": summary_checksum,
            "event_count": len(lines),
        }

    async def read_transcript(self, thread_id: str) -> list[dict[str, Any]]:
        """读取 transcript 行（dormant/archived 只读开放）。"""
        thread = await self.get_thread(thread_id)
        if thread["status"] == "archived":
            # 仍可读取（只读）
            pass
        events = await self.get_events(thread_id)
        return [tx.build_transcript_line(
            sequence=int(e["sequence"]),
            event_type=e["event_type"],
            role=e["role"],
            content=e["content"],
            tool_name=e.get("tool_name"),
            tool_request_hash=e.get("tool_request_hash"),
            artifact_ref=e.get("artifact_ref"),
            token_estimate=int(e.get("token_estimate", 0)),
            provider_native_event_id=e.get("provider_native_event_id"),
        ) for e in events]

    async def build_resume_context(
        self, thread_id: str, *, token_budget: int
    ) -> tuple[list[dict[str, Any]], str]:
        """构造 resume 上下文：最近检查点 + 之后有界 tail（按 token 预算裁剪）。

        返回 (selected_lines, resume_mode)。
        """
        thread = await self.get_thread(thread_id)
        checkpoint = int(thread.get("checkpoint_offset", 0))
        events = await self.get_events(thread_id)
        # 检查点之后的 tail
        tail = [e for e in events if int(e["sequence"]) > checkpoint]
        selected: list[dict[str, Any]] = []
        used = 0
        for e in tail:
            t = int(e.get("token_estimate", 0))
            # 超过预算且已有内容则停止
            if used + t > token_budget and selected:
                break
            selected.append(e)
            used += t
        # 若 tail 为空或预算不足，fallback 到检查点附近的若干条
        if not selected and events:
            selected = [events[-1]]
        lines = [tx.build_transcript_line(
            sequence=int(e["sequence"]),
            event_type=e["event_type"],
            role=e["role"],
            content=e["content"],
            tool_name=e.get("tool_name"),
            tool_request_hash=e.get("tool_request_hash"),
            artifact_ref=e.get("artifact_ref"),
            token_estimate=int(e.get("token_estimate", 0)),
            provider_native_event_id=e.get("provider_native_event_id"),
        ) for e in selected]
        return lines, "transcript"
