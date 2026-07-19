"""并行多 lens 审查（P9-T6）。

CollaborationStrategy 接口 + 首版实现 ParallelReviewStrategy：
N 个 Reviewer 同一轮并发审查同一批产物，每人固定一个维度。
结果取并集（不做加权仲裁）。
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from acos.task.models import new_id
from acos.task.repository import (
    PlanGenerationRepository,
    TaskAssignmentRepository,
    TaskNodeRepository,
)

DEFAULT_LENSES = ("correctness", "security", "test_coverage", "consistency")


class CollaborationStrategy:
    """审查协作策略接口（可插拔，未来接入 DebateStrategy 不改调用方）。"""

    async def review(
        self,
        task_id: str,
        company_id: str,
        generation_id: str,
        target_nodes: list[str],
        reviewers: list[str],
        lenses: list[str],
        reviewer_fn: Callable[[str, str, str], Any],
    ) -> dict:
        raise NotImplementedError


class ParallelReviewStrategy(CollaborationStrategy):
    """N lens 并发审查，结果并集。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._nodes = TaskNodeRepository(db_path)
        self._assignments = TaskAssignmentRepository(db_path)
        self._gens = PlanGenerationRepository(db_path)

    async def review(
        self,
        task_id: str,
        company_id: str,
        generation_id: str,
        target_nodes: list[str],
        reviewers: list[str],
        lenses: list[str],
        reviewer_fn: Callable[[str, str, str], Any],
    ) -> dict:
        """为每个 lens 创建独立 review_task node + reviewer assignment。

        reviewer_fn(lens, node_id, reviewer_id) -> findings（调用方真实执行审查）。
        返回 {lens: {node_id: findings}} 并集。
        """
        tasks: list[asyncio.Task] = []
        meta: list[dict] = []

        for i, lens in enumerate(lenses):
            reviewer_id = reviewers[i % len(reviewers)] if reviewers else "system"
            review_node_id = new_id("rev")
            await self._nodes.create(_node(
                node_id=review_node_id, task_id=task_id, company_id=company_id,
                node_type="review_task", generation_id=generation_id,
                assignee_employee_id=reviewer_id, status="pending",
                goal=f"review lens={lens}",
            ))
            await self._assignments.create(_assign(
                assignment_id=new_id("asg"), task_id=task_id, node_id=review_node_id,
                employee_id=reviewer_id, company_id=company_id,
                generation_id=generation_id, assignment_role="reviewer",
            ))
            for node_id in target_nodes:
                tasks.append(asyncio.create_task(_safe(reviewer_fn, lens, node_id, reviewer_id)))
                meta.append({"lens": lens, "node_id": node_id, "reviewer": reviewer_id})

        results = await asyncio.gather(*tasks)
        union: dict[str, dict] = {}
        for m, res in zip(meta, results):
            union.setdefault(m["lens"], {})[m["node_id"]] = res
        return union


async def _safe(fn, *args):
    try:
        r = fn(*args)
        if asyncio.iscoroutine(r):
            return await r
        return r
    except Exception as exc:
        return {"error": str(exc)}


def _node(**kw):
    from acos.task.models import TaskNode

    return TaskNode(**kw)


def _assign(**kw):
    from acos.task.models import TaskAssignment

    return TaskAssignment(**kw)
