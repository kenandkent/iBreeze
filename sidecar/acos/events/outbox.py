"""Outbox 写入与轮询投递。"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import aiosqlite


class OutboxWriter:
    """在调用方的同一事务内写入 domain_events 与 outbox_deliveries。"""

    async def emit_event(
        self,
        conn: aiosqlite.Connection,
        company_id: str,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_version: int,
        payload: dict[str, Any],
        trace_id: str,
        actor_type: str,
        actor_id: str,
        consumers: list[str],
        scope_refs: dict[str, str] | None = None,
    ) -> str:
        """写入事件和初始 outbox deliveries，返回 event_id。

        调用方负责管理 conn 的事务（begin/commit/rollback）。
        """
        if not company_id:
            raise ValueError("company_id is required")
        if not trace_id:
            raise ValueError("trace_id is required")
        if not actor_type or not actor_id:
            raise ValueError("actor_type and actor_id are required")

        event_id = str(uuid.uuid4())
        occurred_at = datetime.now(timezone.utc).isoformat()
        meta = dict(scope_refs) if scope_refs else {}

        await conn.execute(
            """INSERT INTO domain_events
               (event_id, company_id, event_type, aggregate_type, aggregate_id,
                aggregate_version, task_id, employee_id, run_id,
                occurred_at, trace_id, actor_type, actor_id, payload, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                company_id,
                event_type,
                aggregate_type,
                aggregate_id,
                aggregate_version,
                None,
                None,
                None,
                occurred_at,
                trace_id,
                actor_type,
                actor_id,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(meta, ensure_ascii=False),
            ),
        )

        for consumer in consumers:
            delivery_id = str(uuid.uuid4())
            await conn.execute(
                """INSERT INTO outbox_deliveries
                   (delivery_id, event_id, consumer_name, status, attempt_count)
                   VALUES (?, ?, ?, 'pending', 0)""",
                (delivery_id, event_id, consumer),
            )

        return event_id


class OutboxWorker:
    """轮询 outbox_deliveries，按 (event_id, consumer_name) 幂等消费。"""

    def __init__(self, db_path: str, poll_interval: float = 1.0) -> None:
        self._db_path = db_path
        self._poll_interval = poll_interval
        self._consumers: dict[str, Callable[[dict], Awaitable[None]]] = {}

    def register_consumer(
        self, name: str, handler: Callable[[dict], Awaitable[None]]
    ) -> None:
        """注册事件消费者。"""
        self._consumers[name] = handler

    async def process_pending(self) -> int:
        """处理所有 pending/可重试的 failed 行，返回处理数量。"""
        processed = 0
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            now_iso = datetime.now(timezone.utc).isoformat()

            # 查找 pending 行，或可重试的 failed 行（next_retry_at 已到）
            cursor = await db.execute(
                """SELECT o.delivery_id, o.event_id, o.consumer_name,
                          o.attempt_count, o.last_error,
                          e.company_id, e.event_type, e.payload
                   FROM outbox_deliveries o
                   JOIN domain_events e ON e.event_id = o.event_id
                   WHERE (o.status = 'pending'
                          OR (o.status = 'failed'
                              AND o.next_retry_at IS NOT NULL
                              AND o.next_retry_at <= ?))
                   ORDER BY o.created_at
                   LIMIT 100""",
                (now_iso,),
            )
            rows = await cursor.fetchall()

            for row in rows:
                consumer_name = row["consumer_name"]
                handler = self._consumers.get(consumer_name)
                if handler is None:
                    # 无注册处理器，标记 failed 并跳过
                    await db.execute(
                        """UPDATE outbox_deliveries
                           SET status = 'failed',
                               attempt_count = attempt_count + 1,
                               last_error = 'no handler registered',
                               updated_at = ?
                           WHERE delivery_id = ?""",
                        (now_iso, row["delivery_id"]),
                    )
                    continue

                event_payload = {
                    "event_id": row["event_id"],
                    "company_id": row["company_id"],
                    "event_type": row["event_type"],
                    "payload": json.loads(row["payload"]),
                }

                try:
                    await handler(event_payload)
                    await db.execute(
                        """UPDATE outbox_deliveries
                           SET status = 'delivered',
                               attempt_count = attempt_count + 1,
                               updated_at = ?
                           WHERE delivery_id = ?""",
                        (now_iso, row["delivery_id"]),
                    )
                    processed += 1
                except Exception as exc:
                    next_retry = datetime.now(timezone.utc).isoformat()
                    await db.execute(
                        """UPDATE outbox_deliveries
                           SET status = 'failed',
                               attempt_count = attempt_count + 1,
                               last_error = ?,
                               next_retry_at = ?,
                               updated_at = ?
                           WHERE delivery_id = ?""",
                        (str(exc), next_retry, now_iso, row["delivery_id"]),
                    )

            await db.commit()
        return processed

    async def run_forever(self) -> None:
        """持续轮询。"""
        while True:
            try:
                await self.process_pending()
            except Exception:
                pass  # 轮询不应因单次异常而中断
            await asyncio.sleep(self._poll_interval)
