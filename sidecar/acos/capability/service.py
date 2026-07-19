"""Capability 服务。

主表 `capabilities` 保留 inline status/version 作为"当前发布指针"；
所有版本内容写入 `capability_versions` 表，状态机在 `capability_versions` 上操作。
skill_bindings 按 capability_version 投影，进入 review 后不可修改。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.capability.models import Capability
from acos.rpc.errors import (
    ASSET_CROSS_COMPANY_REF_DENIED,
    CAP_VALIDATION,
    CAP_VERSION_IMMUTABLE,
    SYS_OPTIMISTIC_LOCK_CONFLICT,
    create_error,
)


class CapabilityService:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row_to_capability(row: aiosqlite.Row) -> Capability:
        return Capability(
            capability_id=row["capability_id"],
            company_scope=row["company_scope"],
            company_id=row["company_id"],
            name=row["name"],
            description=row["description"],
            source_category=row["source_category"],
            visibility=row["visibility"],
            cost_policy=json.loads(row["cost_policy"]),
            checksum=row["checksum"],
            version=row["version"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _vrow_to_capability(row: aiosqlite.Row) -> Capability:
        return Capability(
            capability_id=row["capability_id"],
            name=row["name"],
            description=row["description"],
            cost_policy=json.loads(row["cost_policy"]),
            checksum=row["checksum"],
            version=row["version"],
            status=row["status"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _compute_checksum(cap: Capability) -> str:
        from acos.capability.models import compute_checksum

        return compute_checksum(
            {
                "name": cap.name,
                "description": cap.description,
                "source_category": cap.source_category,
                "visibility": cap.visibility,
                "cost_policy": cap.cost_policy,
            }
        )

    async def _validate_cost_policy(self, cost_policy: dict) -> None:
        level = cost_policy.get("stability_level")
        if level is not None:
            if not isinstance(level, int) or not (1 <= level <= 10):
                raise create_error(
                    CAP_VALIDATION,
                    f"stability_level 必须在 1-10 之间，当前值: {level}",
                )

    async def _validate_skill_bindings(
        self, db: aiosqlite.Connection, cap: Capability, bindings: list[dict]
    ) -> None:
        for binding in bindings:
            skill_id = binding.get("skill_id")
            cursor = await db.execute(
                "SELECT company_scope, company_id FROM skills WHERE skill_id = ?",
                (skill_id,),
            )
            skill_row = await cursor.fetchone()
            if skill_row is None:
                raise create_error(CAP_VALIDATION, f"引用的 Skill {skill_id} 不存在")
            if cap.company_scope == "company" and skill_row["company_scope"] == "company":
                if cap.company_id != skill_row["company_id"]:
                    raise create_error(
                        ASSET_CROSS_COMPANY_REF_DENIED,
                        "Capability 不可引用其他公司的 Skill",
                    )

    async def _write_bindings(
        self, db: aiosqlite.Connection, cap_id: str, version: int, bindings: list[dict]
    ) -> None:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT status FROM capability_versions WHERE capability_id = ? AND version = ?",
            (cap_id, version),
        )
        vrow = await cursor.fetchone()
        if vrow and vrow["status"] != "draft":
            raise create_error(
                CAP_VERSION_IMMUTABLE,
                f"版本 {cap_id} v{version} 状态为 {vrow['status']}，不可修改 bindings",
            )
        now = self._now()
        await db.execute(
            "DELETE FROM skill_bindings WHERE capability_id = ? AND capability_version = ?",
            (cap_id, version),
        )
        for ordinal, binding in enumerate(bindings, start=1):
            await db.execute(
                """INSERT INTO skill_bindings
                   (binding_id, capability_id, capability_version, ordinal,
                    skill_id, skill_version, skill_version_checksum, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    cap_id,
                    version,
                    ordinal,
                    binding["skill_id"],
                    binding.get("skill_version", 1),
                    binding.get("skill_version_checksum", ""),
                    now,
                ),
            )

    async def _insert_version(self, db: aiosqlite.Connection, cap: Capability) -> None:
        now = self._now()
        await db.execute(
            """INSERT INTO capability_versions
               (capability_version_id, capability_id, version, name, description,
                cost_policy, skill_bindings, stability_level, checksum, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                cap.capability_id,
                cap.version,
                cap.name,
                cap.description,
                json.dumps(cap.cost_policy, ensure_ascii=False),
                "[]",
                cap.cost_policy.get("stability_level"),
                cap.checksum,
                cap.status,
                now,
            ),
        )

    async def _sync_main(self, db: aiosqlite.Connection, cap: Capability) -> None:
        now = self._now()
        cursor = await db.execute(
            """UPDATE capabilities
               SET name = ?, description = ?, source_category = ?, visibility = ?,
                   cost_policy = ?, checksum = ?, version = ?, status = ?, updated_at = ?
               WHERE capability_id = ?""",
            (
                cap.name,
                cap.description,
                cap.source_category,
                cap.visibility,
                json.dumps(cap.cost_policy, ensure_ascii=False),
                cap.checksum,
                cap.version,
                cap.status,
                now,
                cap.capability_id,
            ),
        )
        if cursor.rowcount == 0:
            await db.execute(
                """INSERT INTO capabilities
                   (capability_id, company_scope, company_id, name, description,
                    source_category, visibility, cost_policy, checksum,
                    version, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)""",
                (
                    cap.capability_id,
                    cap.company_scope,
                    cap.company_id,
                    cap.name,
                    cap.description,
                    cap.source_category,
                    cap.visibility,
                    json.dumps(cap.cost_policy, ensure_ascii=False),
                    cap.checksum,
                    cap.version,
                    now,
                    now,
                ),
            )

    async def create(
        self, cap: Capability, bindings: list[dict] | None = None
    ) -> Capability:
        now = self._now()
        cap.created_at = now
        cap.updated_at = now
        cap.version = 1
        cap.status = "draft"
        cap.checksum = self._compute_checksum(cap)
        bindings = bindings or []

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await self._validate_cost_policy(cap.cost_policy)
            await self._validate_skill_bindings(db, cap, bindings)

            await self._sync_main(db, cap)
            await self._insert_version(db, cap)
            await self._write_bindings(db, cap.capability_id, 1, bindings)
            await db.commit()
        return cap

    async def save_draft(
        self,
        cap: Capability,
        expected_version: int,
        bindings: list[dict] | None = None,
    ) -> Capability:
        now = self._now()
        new_checksum = self._compute_checksum(cap)
        new_version = expected_version + 1

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await self._validate_cost_policy(cap.cost_policy)
            if bindings is not None:
                await self._validate_skill_bindings(db, cap, bindings)

            cursor = await db.execute(
                """UPDATE capability_versions
                   SET name = ?, description = ?, cost_policy = ?, checksum = ?,
                       version = ?, updated_at = ?
                   WHERE capability_id = ? AND version = ? AND status = 'draft'""",
                (
                    cap.name,
                    cap.description,
                    json.dumps(cap.cost_policy, ensure_ascii=False),
                    new_checksum,
                    new_version,
                    now,
                    cap.capability_id,
                    expected_version,
                ),
            )
            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突或版本已不可变: capability {cap.capability_id}",
                )

            cursor = await db.execute(
                "SELECT * FROM capability_versions WHERE capability_id = ? AND version = ?",
                (cap.capability_id, new_version),
            )
            vrow = await cursor.fetchone()
            updated = self._vrow_to_capability(vrow)

            if bindings is not None:
                await self._write_bindings(db, cap.capability_id, new_version, bindings)

            await self._sync_main(db, updated)
            await db.commit()
            return updated

    async def get(self, capability_id: str) -> Optional[Capability]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM capabilities WHERE capability_id = ?",
                (capability_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_capability(row)

    async def list_versions(self, capability_id: str) -> list[Capability]:
        """列出某 capability 的所有版本（按版本号倒序）。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM capability_versions
                   WHERE capability_id = ?
                   ORDER BY version DESC""",
                (capability_id,),
            )
            rows = await cursor.fetchall()
            return [self._vrow_to_capability(r) for r in rows]

    async def create_version(self, capability_id: str, from_version: int) -> Capability:
        """从指定版本派生出一个新的 draft 版本。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM capability_versions WHERE capability_id = ? AND version = ?",
                (capability_id, from_version),
            )
            src = await cursor.fetchone()
            if src is None:
                raise create_error(CAP_VERSION_IMMUTABLE, f"源版本 {from_version} 不存在")

            now = self._now()
            new_version = from_version + 1
            new_cap = Capability(
                capability_id=src["capability_id"],
                name=src["name"],
                description=src["description"],
                cost_policy=json.loads(src["cost_policy"]),
                status="draft",
            )
            new_checksum = self._compute_checksum(new_cap)
            new_cap.checksum = new_checksum
            new_cap.version = new_version
            new_cap.created_at = now

            await self._insert_version(db, new_cap)
            cursor = await db.execute(
                "SELECT * FROM skill_bindings WHERE capability_id = ? AND capability_version = ? ORDER BY ordinal",
                (capability_id, from_version),
            )
            old_bindings = await cursor.fetchall()
            bindings = [
                {
                    "skill_id": b["skill_id"],
                    "skill_version": b["skill_version"],
                    "skill_version_checksum": b["skill_version_checksum"],
                }
                for b in old_bindings
            ]
            await self._write_bindings(db, capability_id, new_version, bindings)
            await self._sync_main(db, new_cap)
            await db.commit()
            new_cap.created_at = now
            new_cap.updated_at = now
            return new_cap

    async def get_bindings(
        self, capability_id: str, version: int
    ) -> list[dict]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM skill_bindings
                   WHERE capability_id = ? AND capability_version = ?
                   ORDER BY ordinal""",
                (capability_id, version),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "binding_id": r["binding_id"],
                    "skill_id": r["skill_id"],
                    "skill_version": r["skill_version"],
                    "skill_version_checksum": r["skill_version_checksum"],
                    "ordinal": r["ordinal"],
                }
                for r in rows
            ]

    async def list_by_company(
        self,
        company_id: Optional[str],
        status: Optional[str] = None,
    ) -> list[Capability]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if company_id is not None:
                if status is not None:
                    cursor = await db.execute(
                        """SELECT * FROM capabilities
                           WHERE company_id = ? AND status = ?
                           ORDER BY version DESC""",
                        (company_id, status),
                    )
                else:
                    cursor = await db.execute(
                        """SELECT * FROM capabilities
                           WHERE company_id = ?
                           ORDER BY version DESC""",
                        (company_id,),
                    )
            else:
                if status is not None:
                    cursor = await db.execute(
                        """SELECT * FROM capabilities
                           WHERE company_scope = 'global' AND status = ?
                           ORDER BY version DESC""",
                        (status,),
                    )
                else:
                    cursor = await db.execute(
                        """SELECT * FROM capabilities
                           WHERE company_scope = 'global'
                           ORDER BY version DESC""",
                    )
            rows = await cursor.fetchall()
            return [self._row_to_capability(r) for r in rows]
