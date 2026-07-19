"""Settings service: 版本化策略与 company 设置的读写。

覆盖 settings.company.* / settings.knowledgePolicy.* / settings.securityPolicy.*
/ settings.workspacePolicy.* / settings.notification.*。

版本化策略采用乐观锁 CAS：update 必须携带 get 返回的 expected_version，
以当前 active version 做 CAS，写入 version+1 active、旧版置 superseded，
原子切换。并发冲突返回 SYS-OPTIMISTIC-LOCK-CONFLICT。
"""

from __future__ import annotations

import aiosqlite
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from acos.rpc.errors import AcosError, create_error

_POLICY_TABLES = {
    "knowledge": "knowledge_policies",
    "security": "security_policies",
    "workspace": "workspace_policies",
    "notification": "notification_policies",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class SettingsService:
    """设置领域的读写服务。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    # ── company ───────────────────────────────────────────────

    async def get_company(self, company_id: str) -> Optional[dict[str, Any]]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM companies WHERE company_id = ?", (company_id,)
            )
            row = await cur.fetchone()
        return dict(row) if row else None

    async def update_company(
        self, company_id: str, expected_version: int, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """CAS 更新公司可编辑字段（name 等）。"""
        allowed = {"name"}
        changes = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if not changes:
            raise create_error("ORG-VALIDATION", "无可更新字段")
        if "name" in changes and not str(changes["name"]).strip():
            raise create_error("ORG-VALIDATION", "name 不能为空")
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT version FROM companies WHERE company_id = ?", (company_id,)
            )
            row = await cur.fetchone()
            if row is None:
                raise create_error("ORG-NOT-FOUND", "公司不存在")
            if row["version"] != expected_version:
                raise create_error(
                    "SYS-OPTIMISTIC-LOCK-CONFLICT",
                    "company version 冲突",
                    cause=f"expected {expected_version}, got {row['version']}",
                )
            vals = list(changes.values()) + [_now(), company_id, expected_version]
            await db.execute(
                f"UPDATE companies SET "
                f"{', '.join(f'{k} = ?' for k in changes)}, "
                f"version = version + 1, updated_at = ? "
                f"WHERE company_id = ? AND version = ?",
                vals,
            )
            await db.commit()
            cur = await db.execute(
                "SELECT version FROM companies WHERE company_id = ?", (company_id,)
            )
            new_version = (await cur.fetchone())["version"]
        return {"company_id": company_id, "version": new_version}

    # ── 版本化策略通用逻辑 ────────────────────────────────────

    async def get_policy(self, kind: str, company_id: str) -> Optional[dict[str, Any]]:
        table = _POLICY_TABLES[kind]
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"SELECT * FROM {table} WHERE company_id = ? AND status = 'active' "
                f"ORDER BY version DESC LIMIT 1",
                (company_id,),
            )
            row = await cur.fetchone()
            if row is None:
                # 懒初始化：bootstrap 未建默认行的策略（workspace/notification）
                await self._ensure_default_policy(db, kind, company_id)
                cur = await db.execute(
                    f"SELECT * FROM {table} WHERE company_id = ? AND status = 'active' "
                    f"ORDER BY version DESC LIMIT 1",
                    (company_id,),
                )
                row = await cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        d["config"] = json.loads(d["config"])
        return d

    async def _ensure_default_policy(
        self, db: aiosqlite.Connection, kind: str, company_id: str
    ) -> None:
        """为尚无默认行的策略表创建 version=1 active 默认行。"""
        table = _POLICY_TABLES[kind]
        cur = await db.execute(
            f"SELECT 1 FROM {table} WHERE company_id = ? LIMIT 1", (company_id,)
        )
        if await cur.fetchone() is not None:
            return
        await db.execute(
            f"INSERT INTO {table} "
            f"(policy_id, company_id, version, status, config, created_at) "
            f"VALUES (?, ?, 1, 'active', '{{}}', ?)",
            (_new_id(), company_id, _now()),
        )
        await db.commit()

    async def update_policy(
        self,
        kind: str,
        company_id: str,
        expected_version: int,
        config: dict[str, Any],
        *,
        consent_required: bool = False,
    ) -> dict[str, Any]:
        """CAS 更新版本化策略，写入 version+1 active，旧版置 superseded。"""
        table = _POLICY_TABLES[kind]
        if not isinstance(config, dict) or not config:
            raise create_error("ORG-VALIDATION", "config 必须为非空对象")

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"SELECT * FROM {table} WHERE company_id = ? AND status = 'active' "
                f"ORDER BY version DESC LIMIT 1",
                (company_id,),
            )
            current = await cur.fetchone()
            if current is None:
                await self._ensure_default_policy(db, kind, company_id)
                cur = await db.execute(
                    f"SELECT * FROM {table} WHERE company_id = ? AND status = 'active' "
                    f"ORDER BY version DESC LIMIT 1",
                    (company_id,),
                )
                current = await cur.fetchone()
            if current is None:
                raise create_error("SYS-INTERNAL", "未找到 active 策略，无法更新")
            if current["version"] != expected_version:
                raise create_error(
                    "SYS-OPTIMISTIC-LOCK-CONFLICT",
                    "policy version 冲突",
                    cause=f"expected {expected_version}, got {current['version']}",
                )

            new_version = current["version"] + 1
            now = _now()

            if consent_required:
                allow_cloud = bool(config.get("allow_cloud")) or config.get(
                    "extraction_mode"
                ) == "cloud"
                if allow_cloud:
                    consent = config.get("consent")
                    if not consent or not consent.get("consented_by"):
                        raise create_error(
                            "KG-CLOUD-CONSENT-REQUIRED",
                            "云端模式需要当前版本的显式同意",
                            cause=f"policy version {new_version}",
                        )
                    consent["consent_version"] = new_version
                    consent["consented_at"] = now
                    config["consent"] = consent
                else:
                    config["consent"] = None

            await db.execute(
                f"UPDATE {table} SET status = 'superseded' WHERE policy_id = ?",
                (current["policy_id"],),
            )
            policy_id = _new_id()
            await db.execute(
                f"INSERT INTO {table} "
                f"(policy_id, company_id, version, status, config, created_at) "
                f"VALUES (?, ?, ?, 'active', ?, ?)",
                (policy_id, company_id, new_version, json.dumps(config), now),
            )
            await db.commit()

        return {
            "policy_id": policy_id,
            "company_id": company_id,
            "version": new_version,
            "status": "active",
            "config": config,
        }
