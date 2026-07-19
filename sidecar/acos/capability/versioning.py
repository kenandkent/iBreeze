"""通用发布状态机。"""

from __future__ import annotations

import aiosqlite

from acos.rpc.errors import CAP_STATE_INVALID, create_error

from .quality_gate import QualityGate


class VersioningService:
    """通用发布状态机。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._quality_gate = QualityGate(db_path)

    async def submit_review(self, entity_type: str, entity_id: str, version: int) -> None:
        """提交审核：draft → review。"""
        await self._transition(entity_type, entity_id, version, "draft", "review")

    async def publish(self, entity_type: str, entity_id: str, version: int) -> None:
        """发布：review → published（先调质量门禁）。"""
        await self._require_status(entity_type, entity_id, version, "review")
        gate_result = await self._quality_gate.run_quality_gate(entity_type, entity_id, version)
        if not gate_result.passed:
            raise create_error(
                "CAP-QUALITY-GATE-FAILED",
                f"质量门禁未通过: {', '.join(gate_result.failed_checks)}",
            )
        await self._transition(entity_type, entity_id, version, "review", "published")

    async def deprecate(self, entity_type: str, entity_id: str, version: int) -> None:
        """弃用：published → deprecated。"""
        await self._transition(entity_type, entity_id, version, "published", "deprecated")

    async def archive(self, entity_type: str, entity_id: str, version: int) -> None:
        """归档：deprecated → archived（必须先弃用）。"""
        await self._transition(entity_type, entity_id, version, "deprecated", "archived")

    async def _require_status(
        self,
        entity_type: str,
        entity_id: str,
        version: int,
        expected: str,
    ) -> None:
        """断言当前版本处于期望状态，否则抛出 CAP_STATE_INVALID。"""
        table = f"{entity_type}_versions"
        id_col = f"{entity_type}_id"
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"SELECT status FROM {table} WHERE {id_col} = ? AND version = ?",
                (entity_id, version),
            )
            row = await cursor.fetchone()
        if row is None or row[0] != expected:
            raise create_error(
                CAP_STATE_INVALID,
                f"当前状态不允许该操作，期望 {expected}",
            )

    async def _transition(
        self,
        entity_type: str,
        entity_id: str,
        version: int,
        from_status: str,
        to_status: str,
    ) -> None:
        """执行状态转换，并同步主表指针的 status/version。"""
        table = f"{entity_type}_versions"
        main_table = {
            "skill": "skills",
            "prompt_asset": "prompt_assets",
            "capability": "capabilities",
        }[entity_type]
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                f"""UPDATE {table}
                    SET status = ?, updated_at = datetime('now')
                    WHERE {entity_type}_id = ? AND version = ? AND status = ?""",
                (to_status, entity_id, version, from_status),
            )
            if cursor.rowcount == 0:
                raise create_error(
                    CAP_STATE_INVALID,
                    f"无法从 {from_status} 转换到 {to_status}",
                )
            await db.execute(
                f"""UPDATE {main_table}
                    SET status = ?, version = ?, updated_at = datetime('now')
                    WHERE {entity_type}_id = ?""",
                (to_status, version, entity_id),
            )
            await db.commit()
