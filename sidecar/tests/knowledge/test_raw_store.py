"""P8-T1 原始事件存储测试。"""

from __future__ import annotations

import aiosqlite
import pytest

from tests.knowledge._helpers import insert_department, make_employee, seed_company, setup_db
from acos.knowledge.raw_store import RawStore


async def test_raw_store_reads_domain_events(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await seed_company(db_path)
    await insert_department(db_path, "comp_a", "D1", None)
    await make_employee(db_path, "comp_a", "D1", "emp1")

    raw = RawStore()
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """INSERT INTO domain_events
                  (event_id, company_id, event_type, aggregate_type, aggregate_id,
                   aggregate_version, occurred_at, trace_id, actor_type, actor_id, payload)
               VALUES ('e1', 'comp_a', 'task.done', 'task', 't1', 1, ?, 'tr', 'local_owner', 'o', '{}')""",
            ("2024-01-01T00:00:00Z",),
        )
        await db.commit()
        events = await raw.list_domain_events(db, "comp_a")
        assert len(events) == 1
        assert events[0]["event_id"] == "e1"


async def test_raw_store_watermark_idempotent(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await seed_company(db_path)
    raw = RawStore()
    async with aiosqlite.connect(db_path) as db:
        await raw.mark_consumed(db, "e1", "knowledge_consumer")
        await raw.mark_consumed(db, "e1", "knowledge_consumer")
        wm = await raw.get_watermark(db, "e1", "knowledge_consumer")
        assert wm == "delivered"
        # outbox 唯一约束保证幂等不重复
        cur = await db.execute(
            "SELECT COUNT(*) c FROM outbox_deliveries WHERE event_id='e1' AND consumer_name='knowledge_consumer'"
        )
        assert (await cur.fetchone())["c"] == 1


async def test_raw_store_does_not_create_second_event_table(tmp_path) -> None:
    db_path = await setup_db(tmp_path)
    await seed_company(db_path)
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'raw_event%'"
        )
        assert await cur.fetchone() is None
