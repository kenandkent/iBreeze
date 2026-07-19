"""第一层原始事件存储访问（Phase 8 P8-T1）。

设计 §9.1 / §9.3：禁止建立第二套 raw_event/message 表。会话原始事实来自
`conversation_events`，任务/领域事实来自 `domain_events`。本模块只提供按 company /
事件 watermark 读取与保留策略接口，以及 ingestion watermark 记录（落 knowledge_sources
派生链的 source 状态），保证知识提炼失败不影响原始事件。

Knowledge consumer 通过 `outbox_deliveries` 消费上述事实并记录 ingestion watermark；
文件 transcript 是投影，不作为摄取事实源。
"""

from __future__ import annotations

import hashlib
from typing import Any

import aiosqlite


def _canonical_checksum(payload: str) -> str:
    return hashlib.sha256(payload.encode()).hexdigest()


class RawStore:
    """原始事件读取与 watermark 管理。"""

    async def list_domain_events(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        *,
        after_event_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """读取公司领域事件（原始事实源之一），按 watermark 增量。"""
        if after_event_id is None:
            cur = await conn.execute(
                """SELECT event_id, company_id, event_type, aggregate_type, aggregate_id,
                          task_id, employee_id, occurred_at, actor_type, actor_id, payload
                   FROM domain_events
                   WHERE company_id = ?
                   ORDER BY occurred_at ASC LIMIT ?""",
                (company_id, limit),
            )
        else:
            cur = await conn.execute(
                """SELECT event_id, company_id, event_type, aggregate_type, aggregate_id,
                          task_id, employee_id, occurred_at, actor_type, actor_id, payload
                   FROM domain_events
                   WHERE company_id = ? AND event_id > ?
                   ORDER BY event_id ASC LIMIT ?""",
                (company_id, after_event_id, limit),
            )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def list_conversation_events(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        *,
        thread_id: str | None = None,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """读取会话消息事件（原始事实源之一），按 thread + sequence watermark。"""
        if thread_id is None:
            cur = await conn.execute(
                """SELECT event_id, thread_id, company_id, employee_id, sequence,
                          event_type, role, content, canonical_checksum
                   FROM conversation_events
                   WHERE company_id = ? AND sequence > ?
                   ORDER BY sequence ASC LIMIT ?""",
                (company_id, after_sequence, limit),
            )
        else:
            cur = await conn.execute(
                """SELECT event_id, thread_id, company_id, employee_id, sequence,
                          event_type, role, content, canonical_checksum
                   FROM conversation_events
                   WHERE company_id = ? AND thread_id = ? AND sequence > ?
                   ORDER BY sequence ASC LIMIT ?""",
                (company_id, thread_id, after_sequence, limit),
            )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def mark_consumed(
        self,
        conn: aiosqlite.Connection,
        event_id: str,
        consumer_name: str,
        *,
        status: str = "delivered",
    ) -> None:
        """记录 outbox 投递（幂等），作为 ingestion watermark。"""
        await conn.execute(
            """INSERT INTO outbox_deliveries
                  (delivery_id, event_id, consumer_name, status, attempt_count, updated_at)
               VALUES (?, ?, ?, ?, 1, datetime('now'))
               ON CONFLICT(event_id, consumer_name)
               DO UPDATE SET status = excluded.status, updated_at = datetime('now')""",
            (f"{event_id}:{consumer_name}", event_id, consumer_name, status),
        )
        await conn.commit()

    async def get_watermark(
        self,
        conn: aiosqlite.Connection,
        event_id: str,
        consumer_name: str,
    ) -> str | None:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT status FROM outbox_deliveries
               WHERE event_id = ? AND consumer_name = ? LIMIT 1""",
            (event_id, consumer_name),
        )
        row = await cur.fetchone()
        return row["status"] if row else None

    async def soft_delete_source(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        source_type: str,
        source_id: str,
    ) -> None:
        """保留矩阵：正常软删除路径（标记 deleted_at）。"""
        await conn.execute(
            """UPDATE knowledge_sources
               SET status = 'deleted', updated_at = datetime('now')
               WHERE company_id = ? AND source_type = ? AND source_id = ?""",
            (company_id, source_type, source_id),
        )
        await conn.commit()
