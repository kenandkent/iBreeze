"""会话服务。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite

from acos.rpc.errors import ORG_NOT_FOUND, ORG_STATE_INVALID, create_error
from acos.sessions.models import SessionThread, SessionTurn


class SessionService:
    """会话服务 - 管理会话线程和消息轮次。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    async def get_or_create_thread(
        self, company_id: str, employee_id: str, security_context_key: str
    ) -> SessionThread:
        """获取或创建会话线程。按 company+employee+security_context 隔离。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM session_threads
                   WHERE company_id = ? AND employee_id = ? AND security_context_key = ?
                   AND status = 'active'
                   ORDER BY updated_at DESC LIMIT 1""",
                (company_id, employee_id, security_context_key),
            )
            row = await cursor.fetchone()
            if row is not None:
                return self._row_to_thread(row)

            now = self._now()
            thread_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO session_threads
                   (thread_id, company_id, employee_id, security_context_key,
                    status, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'active', 1, ?, ?)""",
                (thread_id, company_id, employee_id, security_context_key, now, now),
            )
            await db.commit()

            cursor = await db.execute(
                "SELECT * FROM session_threads WHERE thread_id = ?", (thread_id,)
            )
            row = await cursor.fetchone()
            return self._row_to_thread(row)

    async def send_message(
        self, thread_id: str, content: str, role: str = "user"
    ) -> SessionTurn:
        """发送消息到线程。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM session_threads WHERE thread_id = ?", (thread_id,)
            )
            thread_row = await cursor.fetchone()
            if thread_row is None:
                raise create_error(ORG_NOT_FOUND, f"线程 {thread_id} 不存在")
            if thread_row["status"] != "active":
                raise create_error(
                    ORG_STATE_INVALID,
                    f"线程状态为 {thread_row['status']}，无法发送消息",
                )

            now = self._now()
            turn_id = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO session_turns
                   (turn_id, thread_id, company_id, employee_id,
                    role, content, security_context_key, status, version, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 1, ?)""",
                (
                    turn_id,
                    thread_id,
                    thread_row["company_id"],
                    thread_row["employee_id"],
                    role,
                    content,
                    thread_row["security_context_key"],
                    now,
                ),
            )

            await db.execute(
                """UPDATE session_threads
                   SET last_checkpoint_offset = last_checkpoint_offset + 1,
                       version = version + 1, updated_at = ?
                   WHERE thread_id = ?""",
                (now, thread_id),
            )
            await db.commit()

            cursor = await db.execute(
                "SELECT * FROM session_turns WHERE turn_id = ?", (turn_id,)
            )
            row = await cursor.fetchone()
            return self._row_to_turn(row)

    async def get_thread_history(
        self, thread_id: str, limit: int = 100
    ) -> list[SessionTurn]:
        """获取线程消息历史。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM session_turns
                   WHERE thread_id = ?
                   ORDER BY created_at ASC LIMIT ?""",
                (thread_id, limit),
            )
            rows = await cursor.fetchall()
            return [self._row_to_turn(row) for row in rows]

    async def archive_thread(self, thread_id: str) -> None:
        """归档线程。"""
        await self._update_thread_status(thread_id, "archived")

    async def dormant_thread(self, thread_id: str) -> None:
        """置为休眠。"""
        await self._update_thread_status(thread_id, "dormant")

    async def _update_thread_status(self, thread_id: str, status: str) -> None:
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """UPDATE session_threads
                   SET status = ?, version = version + 1, updated_at = ?
                   WHERE thread_id = ?""",
                (status, now, thread_id),
            )
            if cursor.rowcount == 0:
                raise create_error(ORG_NOT_FOUND, f"线程 {thread_id} 不存在")
            await db.commit()

    @staticmethod
    def _row_to_thread(row: aiosqlite.Row) -> SessionThread:
        return SessionThread(
            thread_id=row["thread_id"],
            company_id=row["company_id"],
            employee_id=row["employee_id"],
            security_context_key=row["security_context_key"],
            status=row["status"],
            primary_thread_id=row["primary_thread_id"],
            last_checkpoint_offset=row["last_checkpoint_offset"],
            transcript_path=row["transcript_path"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_turn(row: aiosqlite.Row) -> SessionTurn:
        return SessionTurn(
            turn_id=row["turn_id"],
            thread_id=row["thread_id"],
            company_id=row["company_id"],
            employee_id=row["employee_id"],
            role=row["role"],
            content=row["content"],
            security_context_key=row["security_context_key"],
            status=row["status"],
            version=row["version"],
            created_at=row["created_at"],
        )
