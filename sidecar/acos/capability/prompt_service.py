"""PromptAsset 服务。

主表 `prompt_assets` 保留 inline status/version 作为"当前发布指针"；
所有版本内容写入 `prompt_asset_versions` 表，状态机在 `prompt_asset_versions` 上操作。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.capability.models import PromptAsset
from acos.rpc.errors import (
    CAP_VERSION_IMMUTABLE,
    SYS_OPTIMISTIC_LOCK_CONFLICT,
    create_error,
)


class PromptAssetService:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row_to_asset(row: aiosqlite.Row) -> PromptAsset:
        return PromptAsset(
            prompt_asset_id=row["prompt_asset_id"],
            company_scope=row["company_scope"],
            company_id=row["company_id"],
            name=row["name"],
            segments=json.loads(row["segments"]),
            variables=json.loads(row["variables"]),
            context_slots=json.loads(row["context_slots"]),
            checksum=row["checksum"],
            version=row["version"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _vrow_to_asset(row: aiosqlite.Row) -> PromptAsset:
        return PromptAsset(
            prompt_asset_id=row["prompt_asset_id"],
            name=row["name"],
            segments=json.loads(row["segments"]),
            variables=json.loads(row["variables"]),
            context_slots=json.loads(row["context_slots"]),
            checksum=row["checksum"],
            version=row["version"],
            status=row["status"],
            created_at=row["created_at"],
        )

    async def _insert_version(self, db: aiosqlite.Connection, asset: PromptAsset) -> None:
        now = self._now()
        await db.execute(
            """INSERT INTO prompt_asset_versions
               (prompt_asset_version_id, prompt_asset_id, version, name, segments,
                variables, context_slots, checksum, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                asset.prompt_asset_id,
                asset.version,
                asset.name,
                json.dumps(asset.segments, ensure_ascii=False),
                json.dumps(asset.variables, ensure_ascii=False),
                json.dumps(asset.context_slots, ensure_ascii=False),
                asset.checksum,
                asset.status,
                now,
            ),
        )

    async def _sync_main(self, db: aiosqlite.Connection, asset: PromptAsset) -> None:
        now = self._now()
        cursor = await db.execute(
            """UPDATE prompt_assets
               SET name = ?, segments = ?, variables = ?, context_slots = ?,
                   checksum = ?, version = ?, status = ?, updated_at = ?
               WHERE prompt_asset_id = ?""",
            (
                asset.name,
                json.dumps(asset.segments, ensure_ascii=False),
                json.dumps(asset.variables, ensure_ascii=False),
                json.dumps(asset.context_slots, ensure_ascii=False),
                asset.checksum,
                asset.version,
                asset.status,
                now,
                asset.prompt_asset_id,
            ),
        )
        if cursor.rowcount == 0:
            await db.execute(
                """INSERT INTO prompt_assets
                   (prompt_asset_id, company_scope, company_id, name, segments,
                    variables, context_slots, checksum, version, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    asset.prompt_asset_id,
                    asset.company_scope,
                    asset.company_id,
                    asset.name,
                    json.dumps(asset.segments, ensure_ascii=False),
                    json.dumps(asset.variables, ensure_ascii=False),
                    json.dumps(asset.context_slots, ensure_ascii=False),
                    asset.checksum,
                    asset.version,
                    asset.status,
                    now,
                    now,
                ),
            )

    async def create(self, asset: PromptAsset) -> PromptAsset:
        now = self._now()
        asset.created_at = now
        asset.updated_at = now
        asset.version = 1
        asset.status = "draft"
        asset.checksum = asset.compute_checksum()

        async with aiosqlite.connect(self._db_path) as db:
            await self._sync_main(db, asset)
            await self._insert_version(db, asset)
            await db.commit()
        return asset

    async def save_draft(
        self, asset: PromptAsset, expected_version: int
    ) -> PromptAsset:
        now = self._now()
        new_checksum = asset.compute_checksum()
        new_version = expected_version + 1

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """UPDATE prompt_asset_versions
                   SET name = ?, segments = ?, variables = ?, context_slots = ?,
                       checksum = ?, version = ?, updated_at = ?
                   WHERE prompt_asset_id = ? AND version = ? AND status = 'draft'""",
                (
                    asset.name,
                    json.dumps(asset.segments, ensure_ascii=False),
                    json.dumps(asset.variables, ensure_ascii=False),
                    json.dumps(asset.context_slots, ensure_ascii=False),
                    new_checksum,
                    new_version,
                    now,
                    asset.prompt_asset_id,
                    expected_version,
                ),
            )
            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突或版本已不可变: prompt_asset {asset.prompt_asset_id}",
                )
            cursor = await db.execute(
                "SELECT * FROM prompt_asset_versions WHERE prompt_asset_id = ? AND version = ?",
                (asset.prompt_asset_id, new_version),
            )
            vrow = await cursor.fetchone()
            updated = self._vrow_to_asset(vrow)
            await self._sync_main(db, updated)
            await db.commit()
            return updated

    async def get(self, asset_id: str) -> Optional[PromptAsset]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM prompt_assets WHERE prompt_asset_id = ?",
                (asset_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_asset(row)

    async def list_by_company(
        self,
        company_id: Optional[str],
        status: Optional[str] = None,
    ) -> list[PromptAsset]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if company_id is not None:
                if status is not None:
                    cursor = await db.execute(
                        """SELECT * FROM prompt_assets
                           WHERE company_id = ? AND status = ?
                           ORDER BY version DESC""",
                        (company_id, status),
                    )
                else:
                    cursor = await db.execute(
                        """SELECT * FROM prompt_assets
                           WHERE company_id = ?
                           ORDER BY version DESC""",
                        (company_id,),
                    )
            else:
                if status is not None:
                    cursor = await db.execute(
                        """SELECT * FROM prompt_assets
                           WHERE company_scope = 'global' AND status = ?
                           ORDER BY version DESC""",
                        (status,),
                    )
                else:
                    cursor = await db.execute(
                        """SELECT * FROM prompt_assets
                           WHERE company_scope = 'global'
                           ORDER BY version DESC""",
                    )
            rows = await cursor.fetchall()
            return [self._row_to_asset(r) for r in rows]

    async def create_version(self, asset_id: str, from_version: int) -> PromptAsset:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM prompt_asset_versions WHERE prompt_asset_id = ? AND version = ?",
                (asset_id, from_version),
            )
            src = await cursor.fetchone()
            if src is None:
                raise create_error(CAP_VERSION_IMMUTABLE, f"源版本 {from_version} 不存在")

            now = self._now()
            new_version = from_version + 1
            new_asset = PromptAsset(
                prompt_asset_id=src["prompt_asset_id"],
                name=src["name"],
                segments=json.loads(src["segments"]),
                variables=json.loads(src["variables"]),
                context_slots=json.loads(src["context_slots"]),
                status="draft",
            )
            new_checksum = new_asset.compute_checksum()
            new_asset.checksum = new_checksum
            new_asset.version = new_version
            new_asset.created_at = now

            await self._insert_version(db, new_asset)
            await self._sync_main(db, new_asset)
            await db.commit()
            new_asset.created_at = now
            new_asset.updated_at = now
            return new_asset

    async def list_versions(self, asset_id: str) -> list[PromptAsset]:
        """列出某 prompt_asset 的所有版本（按版本号倒序）。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM prompt_asset_versions
                   WHERE prompt_asset_id = ?
                   ORDER BY version DESC""",
                (asset_id,),
            )
            rows = await cursor.fetchall()
            return [self._vrow_to_asset(r) for r in rows]

    async def get_version(self, asset_id: str, version: int) -> Optional[PromptAsset]:
        """获取某 prompt_asset 的指定版本。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM prompt_asset_versions WHERE prompt_asset_id = ? AND version = ?",
                (asset_id, version),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._vrow_to_asset(row)
