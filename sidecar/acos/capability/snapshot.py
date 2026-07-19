"""Capability 快照与锁文件。"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import aiosqlite

from .models import compute_checksum


@dataclass
class SnapshotLock:
    snapshot_id: str
    capability_id: str
    capability_version: int
    snapshot_checksum: str
    dependency_tree: list[dict[str, Any]] = field(default_factory=list)


class CapabilitySnapshot:
    """能力快照构建与校验。"""

    async def build_snapshot(
        self,
        conn: aiosqlite.Connection,
        capability_id: str,
        version: int,
    ) -> SnapshotLock:
        conn.row_factory = aiosqlite.Row
        """构建完整快照。

        1. 加载 Capability
        2. 按 ordinal 加载 skill_bindings
        3. 对每个 binding 校验 checksum
        4. 构建 dependency_tree
        5. 计算 snapshot_checksum
        6. 持久化
        7. 返回 lock
        """
        cursor = await conn.execute(
            "SELECT * FROM capabilities WHERE capability_id = ? AND version = ?",
            (capability_id, version),
        )
        cap_row = await cursor.fetchone()
        if cap_row is None:
            raise ValueError(f"Capability not found: {capability_id} v{version}")

        cursor = await conn.execute(
            """SELECT * FROM skill_bindings
               WHERE capability_id = ? AND capability_version = ?
               ORDER BY ordinal""",
            (capability_id, version),
        )
        bindings = await cursor.fetchall()

        dependency_tree: list[dict[str, Any]] = []
        for binding in bindings:
            binding_checksum = binding["skill_version_checksum"]
            cursor = await conn.execute(
                "SELECT checksum FROM skills WHERE skill_id = ?",
                (binding["skill_id"],),
            )
            skill_row = await cursor.fetchone()
            if skill_row is None:
                raise ValueError(f"Skill not found: {binding['skill_id']}")
            if skill_row["checksum"] != binding_checksum:
                raise ValueError(
                    f"Checksum mismatch for skill {binding['skill_id']}: "
                    f"expected {binding_checksum}, got {skill_row['checksum']}"
                )
            dependency_tree.append({
                "skill_id": binding["skill_id"],
                "ordinal": binding["ordinal"],
                "checksum": binding_checksum,
            })

        snapshot_data = {
            "capability_id": capability_id,
            "version": version,
            "dependencies": dependency_tree,
        }
        snapshot_checksum = compute_checksum(snapshot_data)
        snapshot_id = str(uuid.uuid4())
        snapshot_json = json.dumps(snapshot_data, ensure_ascii=False)

        await conn.execute(
            """INSERT INTO capability_snapshots
               (snapshot_id, capability_id, capability_version,
                snapshot_json, dependency_tree, snapshot_checksum)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                capability_id,
                version,
                snapshot_json,
                json.dumps(dependency_tree, ensure_ascii=False),
                snapshot_checksum,
            ),
        )
        await conn.commit()

        return SnapshotLock(
            snapshot_id=snapshot_id,
            capability_id=capability_id,
            capability_version=version,
            snapshot_checksum=snapshot_checksum,
            dependency_tree=dependency_tree,
        )

    async def verify_snapshot(
        self,
        conn: aiosqlite.Connection,
        snapshot_id: str,
    ) -> bool:
        """校验快照完整性。"""
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM capability_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return False

        snapshot_data = json.loads(row["snapshot_json"])
        expected_checksum = compute_checksum(snapshot_data)
        return row["snapshot_checksum"] == expected_checksum
