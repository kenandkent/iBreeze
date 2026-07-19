"""Checkpoint 落点与恢复（P9-T8）。

checkpoint 结构对照 §10.5。workflow.checkpoint.list 按 (created_at DESC, checkpoint_id DESC)
分页；不暴露 executor_state；跨公司拒绝。
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

import aiosqlite

from acos.rpc.errors import AcosError
from acos.task.models import Checkpoint, new_id
from acos.task.repository import CheckpointRepository

WF_NOT_FOUND = "WF-NOT-FOUND"
SYS_PAGE_CURSOR_INVALID = "SYS-PAGE-CURSOR-INVALID"


def compute_checksum(data: dict) -> str:
    """覆盖除 self/checksum 外的全部不可变内容。"""
    payload = {k: v for k, v in data.items() if k not in ("checksum", "executor_state")}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class CheckpointService:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._repo = CheckpointRepository(db_path)

    async def create(
        self,
        task_id: str,
        company_id: str,
        task_cursor: int,
        plan_hash: Optional[str] = None,
        generation_id: Optional[str] = None,
        run_id: Optional[str] = None,
        context_hash: Optional[str] = None,
        executor_state: Optional[str] = None,
        event_offset: int = 0,
    ) -> Checkpoint:
        checksum = compute_checksum({
            "task_id": task_id,
            "task_cursor": task_cursor,
            "plan_hash": plan_hash,
            "generation_id": generation_id,
            "run_id": run_id,
            "context_hash": context_hash,
            "event_offset": event_offset,
            "other": executor_state,
        })
        cp = Checkpoint(
            checkpoint_id=new_id("cp"), company_id=company_id, task_id=task_id,
            task_cursor=task_cursor, checksum=checksum, plan_hash=plan_hash,
            context_hash=context_hash, generation_id=generation_id, run_id=run_id,
            event_offset=event_offset, executor_state=executor_state,
        )
        return await self._repo.create(cp)

    async def verify(self, checkpoint_id: str) -> bool:
        """恢复时校验 checksum 未被篡改。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM checkpoints WHERE checkpoint_id = ?", (checkpoint_id,)
            )
            row = await cur.fetchone()
        if row is None:
            return False
        recomputed = compute_checksum({
            "task_id": row["task_id"],
            "task_cursor": row["task_cursor"],
            "plan_hash": row["plan_hash"],
            "generation_id": row["generation_id"],
            "run_id": row["run_id"],
            "context_hash": row["context_hash"],
            "event_offset": row["event_offset"],
            "other": row["executor_state"],
        })
        return recomputed == row["checksum"]

    async def list_for_task(
        self, task_id: str, company_id: str, page_limit: int = 50, cursor: Optional[str] = None
    ) -> dict:
        """workflow.checkpoint.list：跨公司拒绝 + 分页 + 不暴露 executor_state。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT company_id FROM tasks WHERE task_id = ?", (task_id,))
            row = await cur.fetchone()
        if row is None:
            raise AcosError(code=WF_NOT_FOUND, message="任务不存在")
        if row["company_id"] != company_id:
            raise AcosError(
                code="GOV-BUDGET-CROSS-COMPANY",
                message="跨公司 checkpoint 查询被拒绝",
            )
        cps, has_more = await self._repo.list_by_task_desc(task_id, limit=page_limit, cursor=cursor)
        items = []
        next_cursor = None
        for cp in cps:
            items.append({
                "checkpoint_id": cp.checkpoint_id,
                "company_id": cp.company_id,
                "task_id": cp.task_id,
                "task_cursor": cp.task_cursor,
                "generation_id": cp.generation_id,
                "run_id": cp.run_id,
                "plan_hash": cp.plan_hash,
                "event_offset": cp.event_offset,
                "checksum": cp.checksum,
            })
            next_cursor = cp.checkpoint_id
        return {
            "items": items,
            "next_cursor": next_cursor if has_more else None,
            "has_more": has_more,
        }
