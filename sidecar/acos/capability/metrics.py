"""能力度量（只读聚合器）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import aiosqlite


@dataclass
class CapabilityMetrics:
    capability_id: str
    capability_version: int
    success_rate: float = 0.0
    avg_cost: float = 0.0
    review_pass_rate: float = 0.0
    avg_downgrade_count: float = 0.0
    over_budget_rate: float = 0.0
    avg_duration: float = 0.0
    updated_at: str = ""


class MetricsReader:
    """只读度量聚合器。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def get_metrics(
        self,
        capability_id: str,
        capability_version: int,
    ) -> Optional[CapabilityMetrics]:
        """获取单个能力版本的度量。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM capability_metrics
                   WHERE capability_id = ? AND capability_version = ?""",
                (capability_id, capability_version),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return CapabilityMetrics(
                capability_id=row["capability_id"],
                capability_version=row["capability_version"],
                success_rate=row["success_rate"],
                avg_cost=row["avg_cost"],
                review_pass_rate=row["review_pass_rate"],
                avg_downgrade_count=row["avg_downgrade_count"],
                over_budget_rate=row["over_budget_rate"],
                avg_duration=row["avg_duration"],
                updated_at=row["updated_at"],
            )

    async def get_capability_aggregate(self, capability_id: str) -> dict[str, float]:
        """获取能力所有版本的聚合度量。"""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """SELECT
                       AVG(success_rate) as avg_success_rate,
                       AVG(avg_cost) as avg_cost,
                       AVG(review_pass_rate) as avg_review_pass_rate,
                       AVG(avg_downgrade_count) as avg_downgrade_count,
                       AVG(over_budget_rate) as avg_over_budget_rate,
                       AVG(avg_duration) as avg_duration
                   FROM capability_metrics
                   WHERE capability_id = ?""",
                (capability_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return {}
            return {
                "avg_success_rate": row[0] or 0.0,
                "avg_cost": row[1] or 0.0,
                "avg_review_pass_rate": row[2] or 0.0,
                "avg_downgrade_count": row[3] or 0.0,
                "avg_over_budget_rate": row[4] or 0.0,
                "avg_duration": row[5] or 0.0,
            }

    async def list_metrics(
        self,
        capability_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[CapabilityMetrics]:
        """列出度量记录。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if capability_id:
                cursor = await db.execute(
                    """SELECT * FROM capability_metrics
                       WHERE capability_id = ?
                       ORDER BY capability_version DESC
                       LIMIT ?""",
                    (capability_id, limit),
                )
            else:
                cursor = await db.execute(
                    """SELECT * FROM capability_metrics
                       ORDER BY capability_id, capability_version
                       LIMIT ?""",
                    (limit,),
                )
            rows = await cursor.fetchall()
            return [
                CapabilityMetrics(
                    capability_id=row["capability_id"],
                    capability_version=row["capability_version"],
                    success_rate=row["success_rate"],
                    avg_cost=row["avg_cost"],
                    review_pass_rate=row["review_pass_rate"],
                    avg_downgrade_count=row["avg_downgrade_count"],
                    over_budget_rate=row["over_budget_rate"],
                    avg_duration=row["avg_duration"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]
