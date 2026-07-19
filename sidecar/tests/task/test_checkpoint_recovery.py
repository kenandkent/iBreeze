"""test_checkpoint_recovery：落点 / checksum 校验 / 跨公司拒绝 / 分页（P9-T8）。"""

from __future__ import annotations

import pytest

from acos.task.checkpoint import CheckpointService
from acos.task.models import Task
from acos.task.repository import CheckpointRepository, TaskRepository
from tests.task.conftest import migrated_db, seed_backend, seed_company_employee


async def _mk_task(db, task_id="task-cp", company="co1"):
    repo = TaskRepository(db)
    return await repo.create(Task(task_id=task_id, company_id=company, title="t",
                                  status="created", department_id="dep1",
                                  created_by_employee_id="emp1"))


@pytest.mark.asyncio
async def test_create_and_verify(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db)
    svc = CheckpointService(db)
    cp = await svc.create(task_id="task-cp", company_id="co1", task_cursor=1,
                          executor_state="secret-state")
    assert await svc.verify(cp.checkpoint_id) is True
    # 篡改 DB 中的 task_cursor（模拟篡改）
    async with aiosqlite_fix(db) as d:
        await d.execute("UPDATE checkpoints SET task_cursor = 999 WHERE checkpoint_id = ?",
                        (cp.checkpoint_id,))
        await d.commit()
    assert await svc.verify(cp.checkpoint_id) is False


@pytest.mark.asyncio
async def test_list_for_task_cross_company_rejected(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_company_employee(db, company_id="co2")
    await seed_backend(db)
    await _mk_task(db)
    svc = CheckpointService(db)
    await svc.create(task_id="task-cp", company_id="co1", task_cursor=1)
    with pytest.raises(Exception):
        await svc.list_for_task("task-cp", "co2")


@pytest.mark.asyncio
async def test_list_hides_executor_state_and_paginates(migrated_db):
    db = migrated_db
    await seed_company_employee(db)
    await seed_backend(db)
    await _mk_task(db)
    svc = CheckpointService(db)
    for i in range(5):
        await svc.create(task_id="task-cp", company_id="co1", task_cursor=i + 1,
                         executor_state=f"state-{i}")
    res = await svc.list_for_task("task-cp", "co1", page_limit=2)
    assert len(res["items"]) == 2
    assert res["has_more"] is True
    assert all("executor_state" not in it for it in res["items"])
    # 翻页
    res2 = await svc.list_for_task("task-cp", "co1", page_limit=2, cursor=res["next_cursor"])
    assert len(res2["items"]) == 2
    assert res2["has_more"] is True


def aiosqlite_fix(db):
    import aiosqlite
    return aiosqlite.connect(db)
