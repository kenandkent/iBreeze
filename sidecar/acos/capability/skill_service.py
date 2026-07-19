"""Skill 服务。

主表 `skills` 保留 inline status/version 作为"当前发布指针"；
所有版本内容写入 `skill_versions` 表，状态机在 `skill_versions` 上操作。
每次写操作同步更新主表指针。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.capability.models import Skill
from acos.rpc.errors import (
    ASSET_CROSS_COMPANY_REF_DENIED,
    CAP_VALIDATION,
    CAP_VERSION_IMMUTABLE,
    SYS_OPTIMISTIC_LOCK_CONFLICT,
    create_error,
)


class SkillService:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row_to_skill(row: aiosqlite.Row) -> Skill:
        return Skill(
            skill_id=row["skill_id"],
            company_scope=row["company_scope"],
            company_id=row["company_id"],
            name=row["name"],
            prompt_asset_id=row["prompt_asset_id"],
            prompt_asset_version=row["prompt_asset_version"],
            prompt_asset_checksum=row["prompt_asset_checksum"],
            tool_bindings=json.loads(row["tool_bindings"]),
            knowledge_refs=json.loads(row["knowledge_refs"]),
            input_schema=json.loads(row["input_schema"]),
            output_schema=json.loads(row["output_schema"]),
            checksum=row["checksum"],
            version=row["version"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _vrow_to_skill(row: aiosqlite.Row) -> Skill:
        return Skill(
            skill_id=row["skill_id"],
            name=row["name"],
            prompt_asset_id=row["prompt_asset_id"],
            prompt_asset_version=row["prompt_asset_version"],
            prompt_asset_checksum=row["prompt_asset_checksum"],
            tool_bindings=json.loads(row["tool_bindings"]),
            knowledge_refs=json.loads(row["knowledge_refs"]),
            input_schema=json.loads(row["input_schema"]),
            output_schema=json.loads(row["output_schema"]),
            checksum=row["checksum"],
            version=row["version"],
            status=row["status"],
            created_at=row["created_at"],
        )

    async def _validate_asset_ref(
        self, db: aiosqlite.Connection, skill: Skill
    ) -> None:
        cursor = await db.execute(
            "SELECT * FROM prompt_assets WHERE prompt_asset_id = ?",
            (skill.prompt_asset_id,),
        )
        asset = await cursor.fetchone()
        if asset is None:
            raise create_error(CAP_VALIDATION, f"引用的 PromptAsset {skill.prompt_asset_id} 不存在")
        if skill.company_scope == "company" and asset["company_scope"] == "company":
            if skill.company_id != asset["company_id"]:
                raise create_error(
                    ASSET_CROSS_COMPANY_REF_DENIED,
                    "Skill 不可引用其他公司的 PromptAsset",
                )

    async def _insert_version(self, db: aiosqlite.Connection, skill: Skill) -> None:
        now = self._now()
        await db.execute(
            """INSERT INTO skill_versions
               (skill_version_id, skill_id, version, name, prompt_asset_id,
                prompt_asset_version, prompt_asset_checksum, tool_bindings,
                knowledge_refs, input_schema, output_schema, checksum, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                skill.skill_id,
                skill.version,
                skill.name,
                skill.prompt_asset_id,
                skill.prompt_asset_version,
                skill.prompt_asset_checksum,
                json.dumps(skill.tool_bindings, ensure_ascii=False),
                json.dumps(skill.knowledge_refs, ensure_ascii=False),
                json.dumps(skill.input_schema, ensure_ascii=False),
                json.dumps(skill.output_schema, ensure_ascii=False),
                skill.checksum,
                skill.status,
                now,
            ),
        )

    async def _sync_main(self, db: aiosqlite.Connection, skill: Skill) -> None:
        now = self._now()
        cursor = await db.execute(
            """UPDATE skills
               SET name = ?, prompt_asset_id = ?, prompt_asset_version = ?,
                   prompt_asset_checksum = ?, tool_bindings = ?, knowledge_refs = ?,
                   input_schema = ?, output_schema = ?, checksum = ?,
                   version = ?, status = ?, updated_at = ?
               WHERE skill_id = ?""",
            (
                skill.name,
                skill.prompt_asset_id,
                skill.prompt_asset_version,
                skill.prompt_asset_checksum,
                json.dumps(skill.tool_bindings, ensure_ascii=False),
                json.dumps(skill.knowledge_refs, ensure_ascii=False),
                json.dumps(skill.input_schema, ensure_ascii=False),
                json.dumps(skill.output_schema, ensure_ascii=False),
                skill.checksum,
                skill.version,
                skill.status,
                now,
                skill.skill_id,
            ),
        )
        if cursor.rowcount == 0:
            await db.execute(
                """INSERT INTO skills
                   (skill_id, company_scope, company_id, name, prompt_asset_id,
                    prompt_asset_version, prompt_asset_checksum, tool_bindings,
                    knowledge_refs, input_schema, output_schema, checksum,
                    version, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    skill.skill_id,
                    skill.company_scope,
                    skill.company_id,
                    skill.name,
                    skill.prompt_asset_id,
                    skill.prompt_asset_version,
                    skill.prompt_asset_checksum,
                    json.dumps(skill.tool_bindings, ensure_ascii=False),
                    json.dumps(skill.knowledge_refs, ensure_ascii=False),
                    json.dumps(skill.input_schema, ensure_ascii=False),
                    json.dumps(skill.output_schema, ensure_ascii=False),
                    skill.checksum,
                    skill.version,
                    skill.status,
                    now,
                    now,
                ),
            )

    async def create(self, skill: Skill) -> Skill:
        now = self._now()
        skill.created_at = now
        skill.updated_at = now
        skill.version = 1
        skill.status = "draft"
        skill.checksum = skill.compute_checksum()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await self._validate_asset_ref(db, skill)
            await self._sync_main(db, skill)
            await self._insert_version(db, skill)
            await db.commit()
        return skill

    async def save_draft(self, skill: Skill, expected_version: int) -> Skill:
        now = self._now()
        new_checksum = skill.compute_checksum()
        new_version = expected_version + 1

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await self._validate_asset_ref(db, skill)

            cursor = await db.execute(
                """UPDATE skill_versions
                   SET name = ?, prompt_asset_id = ?, prompt_asset_version = ?,
                       prompt_asset_checksum = ?, tool_bindings = ?, knowledge_refs = ?,
                       input_schema = ?, output_schema = ?, checksum = ?,
                       version = ?, updated_at = ?
                   WHERE skill_id = ? AND version = ? AND status = 'draft'""",
                (
                    skill.name,
                    skill.prompt_asset_id,
                    skill.prompt_asset_version,
                    skill.prompt_asset_checksum,
                    json.dumps(skill.tool_bindings, ensure_ascii=False),
                    json.dumps(skill.knowledge_refs, ensure_ascii=False),
                    json.dumps(skill.input_schema, ensure_ascii=False),
                    json.dumps(skill.output_schema, ensure_ascii=False),
                    new_checksum,
                    new_version,
                    now,
                    skill.skill_id,
                    expected_version,
                ),
            )
            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突或版本已不可变: skill {skill.skill_id}",
                )

            cursor = await db.execute(
                "SELECT * FROM skill_versions WHERE skill_id = ? AND version = ?",
                (skill.skill_id, new_version),
            )
            vrow = await cursor.fetchone()
            updated = self._vrow_to_skill(vrow)

            await self._sync_main(db, updated)
            await db.commit()
            return updated

    async def get(self, skill_id: str) -> Optional[Skill]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM skills WHERE skill_id = ?",
                (skill_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_skill(row)

    async def list_versions(self, skill_id: str) -> list[Skill]:
        """列出某 skill 的所有版本（按版本号倒序）。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM skill_versions
                   WHERE skill_id = ?
                   ORDER BY version DESC""",
                (skill_id,),
            )
            rows = await cursor.fetchall()
            return [self._vrow_to_skill(r) for r in rows]

    async def create_version(self, skill_id: str, from_version: int) -> Skill:
        """从指定版本派生出一个新的 draft 版本。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM skill_versions WHERE skill_id = ? AND version = ?",
                (skill_id, from_version),
            )
            src = await cursor.fetchone()
            if src is None:
                raise create_error(CAP_VERSION_IMMUTABLE, f"源版本 {from_version} 不存在")

            now = self._now()
            new_version = from_version + 1
            new_skill = Skill(
                skill_id=src["skill_id"],
                name=src["name"],
                prompt_asset_id=src["prompt_asset_id"],
                prompt_asset_version=src["prompt_asset_version"],
                prompt_asset_checksum=src["prompt_asset_checksum"],
                tool_bindings=json.loads(src["tool_bindings"]),
                knowledge_refs=json.loads(src["knowledge_refs"]),
                input_schema=json.loads(src["input_schema"]),
                output_schema=json.loads(src["output_schema"]),
                status="draft",
            )
            new_checksum = new_skill.compute_checksum()
            new_skill.checksum = new_checksum
            new_skill.version = new_version
            new_skill.created_at = now

            await self._insert_version(db, new_skill)
            await self._sync_main(db, new_skill)
            await db.commit()
            new_skill.created_at = now
            new_skill.updated_at = now
            return new_skill

    async def list_by_company(
        self,
        company_id: Optional[str],
        status: Optional[str] = None,
    ) -> list[Skill]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if company_id is not None:
                if status is not None:
                    cursor = await db.execute(
                        """SELECT * FROM skills
                           WHERE company_id = ? AND status = ?
                           ORDER BY version DESC""",
                        (company_id, status),
                    )
                else:
                    cursor = await db.execute(
                        """SELECT * FROM skills
                           WHERE company_id = ?
                           ORDER BY version DESC""",
                        (company_id,),
                    )
            else:
                if status is not None:
                    cursor = await db.execute(
                        """SELECT * FROM skills
                           WHERE company_scope = 'global' AND status = ?
                           ORDER BY version DESC""",
                        (status,),
                    )
                else:
                    cursor = await db.execute(
                        """SELECT * FROM skills
                           WHERE company_scope = 'global'
                           ORDER BY version DESC""",
                    )
            rows = await cursor.fetchall()
            return [self._row_to_skill(r) for r in rows]
