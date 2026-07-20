"""员工模板服务。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.capability.snapshot import CapabilitySnapshot
from acos.capability.service import CapabilityService
from acos.organization.models import EmployeeTemplate
from acos.rpc.errors import (
    CAP_VALIDATION,
    CAP_VERSION_IMMUTABLE,
    ORG_NOT_FOUND,
    ORG_STATE_INVALID,
    SYS_OPTIMISTIC_LOCK_CONFLICT,
    TEMPLATE_CROSS_COMPANY_DENIED,
    create_error,
)


class TemplateService:
    """员工模板服务。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row_to_template(row: aiosqlite.Row) -> EmployeeTemplate:
        return EmployeeTemplate(
            template_id=row["template_id"],
            template_scope=row["template_scope"],
            company_id=row["company_id"],
            provider_type=row["provider_type"],
            provider_id=row["provider_id"],
            model=row["model"],
            capability_id=row["capability_id"],
            capability_version=row["capability_version"],
            capability_snapshot=json.loads(row["capability_snapshot"]),
            default_role=row["default_role"],
            version=row["version"],
            status=row["status"],
        )

    async def create(
        self,
        company_id: str,
        capability_id: str,
        capability_version: int,
        default_role: str,
        capability_snapshot: dict | None = None,
        template_scope: str = "company",
        provider_type: str = "openai",
        provider_id: str = "openai",
        model: str = "gpt-4",
    ) -> EmployeeTemplate:
        """创建模板。

        校验：
        1. Capability 必须存在且 status=published
        2. 跨公司复用校验：global 模板只能引用 global capability
        3. 构建 capability_snapshot (lock 文件)
        """
        # 1. 校验 capability 存在且已发布
        cap_svc = CapabilityService(self._db_path)
        cap = await cap_svc.get(capability_id)
        if cap is None:
            raise create_error(CAP_VALIDATION, f"Capability {capability_id} 不存在")
        if cap.status != "published":
            raise create_error(CAP_VALIDATION, f"Capability {capability_id} 非发布状态，不可被模板引用")

        # 2. 跨公司复用校验
        cap_scope = cap.company_scope
        if template_scope == "global" and cap_scope == "company":
            raise create_error(TEMPLATE_CROSS_COMPANY_DENIED, "全局模板不可引用公司私有 Capability")
        if template_scope == "company" and cap_scope == "company" and cap.company_id != company_id:
            raise create_error(TEMPLATE_CROSS_COMPANY_DENIED, "公司模板不可引用其他公司私有 Capability")

        # 3. 构建 capability_snapshot
        snapshot_builder = CapabilitySnapshot()
        async with aiosqlite.connect(self._db_path) as db:
            lock = await snapshot_builder.build_snapshot(db, capability_id, capability_version)
            capability_snapshot = {
                "snapshot_id": lock.snapshot_id,
                "capability_id": lock.capability_id,
                "capability_version": lock.capability_version,
                "snapshot_checksum": lock.snapshot_checksum,
                "dependency_tree": lock.dependency_tree,
            }

        template = EmployeeTemplate(
            template_scope=template_scope,
            company_id=company_id if template_scope == "company" else None,
            provider_type=provider_type,
            provider_id=provider_id,
            model=model,
            capability_id=capability_id,
            capability_version=capability_version,
            capability_snapshot=capability_snapshot,
            default_role=default_role,
            status="draft",
        )
        now = self._now()

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO employee_templates
                   (template_id, template_scope, company_id, provider_type, provider_id,
                    model, capability_id, capability_version, capability_snapshot,
                    default_role, version, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'draft', ?, ?)""",
                (
                    template.template_id, template.template_scope, template.company_id,
                    template.provider_type, template.provider_id, template.model,
                    template.capability_id, template.capability_version,
                    json.dumps(template.capability_snapshot), template.default_role,
                    now, now,
                ),
            )
            await db.commit()
        return template

    async def save_draft(
        self,
        template_id: str,
        company_id: str,
        expected_version: int,
        updates: dict,
    ) -> EmployeeTemplate:
        """CAS 保存草稿。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                "SELECT * FROM employee_templates WHERE template_id = ?",
                (template_id,),
            )
            current = await cursor.fetchone()
            if current is None:
                raise create_error(ORG_NOT_FOUND, f"模板 {template_id} 不存在")
            if current["status"] != "draft":
                raise create_error(ORG_STATE_INVALID, "只能编辑草稿模板")

            allowed = {"capability_id", "capability_version", "capability_snapshot", "default_role",
                        "provider_type", "provider_id", "model"}

            # 改绑 capability 时需校验目标能力为已发布状态（SC-20-2）
            if "capability_id" in updates and updates["capability_id"]:
                cap_svc = CapabilityService(self._db_path)
                cap = await cap_svc.get(updates["capability_id"])
                if cap is None:
                    raise create_error(CAP_VALIDATION, f"Capability {updates['capability_id']} 不存在")
                if cap.status != "published":
                    raise create_error(CAP_VALIDATION, f"Capability {updates['capability_id']} 非发布状态，不可被模板引用")

            set_parts: list[str] = []
            params: list[object] = []
            for key, value in updates.items():
                if key not in allowed:
                    continue
                if key == "capability_snapshot":
                    set_parts.append(f"{key} = ?")
                    params.append(json.dumps(value))
                else:
                    set_parts.append(f"{key} = ?")
                    params.append(value)

            if not set_parts:
                raise create_error(ORG_STATE_INVALID, "无可更新字段")

            set_parts.append("version = version + 1")
            set_parts.append("updated_at = ?")
            params.append(now)
            params.extend([template_id, expected_version])

            sql = f"""UPDATE employee_templates
                      SET {', '.join(set_parts)}
                      WHERE template_id = ? AND version = ?"""
            cursor = await db.execute(sql, params)
            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突: template {template_id}",
                )

            cursor = await db.execute(
                "SELECT * FROM employee_templates WHERE template_id = ?", (template_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_template(row)

    async def activate(self, template_id: str, company_id: str, expected_version: int) -> EmployeeTemplate:
        """激活模板 draft→active。

        如果 capability_snapshot 为空（旧数据），则在激活时构建快照。
        """
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            # 先获取当前模板
            cursor = await db.execute(
                "SELECT * FROM employee_templates WHERE template_id = ?", (template_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise create_error(ORG_NOT_FOUND, f"模板 {template_id} 不存在")
            if row["status"] != "draft":
                raise create_error(ORG_STATE_INVALID, "只能激活草稿模板")
            if row["version"] != expected_version:
                raise create_error(SYS_OPTIMISTIC_LOCK_CONFLICT, f"CAS 冲突: template {template_id}")

            # 如果 capability_snapshot 为空，构建快照
            capability_snapshot = json.loads(row["capability_snapshot"])
            if not capability_snapshot:
                cap_svc = CapabilityService(self._db_path)
                cap = await cap_svc.get(row["capability_id"])
                if cap is None or cap.status != "published":
                    raise create_error(CAP_VALIDATION, "引用的 Capability 不存在或未发布")
                snapshot_builder = CapabilitySnapshot()
                lock = await snapshot_builder.build_snapshot(db, row["capability_id"], row["capability_version"])
                capability_snapshot = {
                    "snapshot_id": lock.snapshot_id,
                    "capability_id": lock.capability_id,
                    "capability_version": lock.capability_version,
                    "snapshot_checksum": lock.snapshot_checksum,
                    "dependency_tree": lock.dependency_tree,
                }

            cursor = await db.execute(
                """UPDATE employee_templates
                   SET status = 'active', version = version + 1, updated_at = ?,
                       capability_snapshot = ?
                   WHERE template_id = ? AND version = ? AND status = 'draft'""",
                (now, json.dumps(capability_snapshot), template_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise create_error(SYS_OPTIMISTIC_LOCK_CONFLICT, f"CAS 冲突: template {template_id}")

            cursor = await db.execute(
                "SELECT * FROM employee_templates WHERE template_id = ?", (template_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_template(row)

    async def archive(self, template_id: str, company_id: str, expected_version: int) -> EmployeeTemplate:
        """归档模板 active→archived。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """UPDATE employee_templates
                   SET status = 'archived', version = version + 1, updated_at = ?
                   WHERE template_id = ? AND version = ? AND status = 'active'""",
                (now, template_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise create_error(ORG_STATE_INVALID, f"无法归档模板 {template_id}")

            cursor = await db.execute(
                "SELECT * FROM employee_templates WHERE template_id = ?", (template_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_template(row)

    async def get(self, template_id: str) -> Optional[EmployeeTemplate]:
        """获取模板。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM employee_templates WHERE template_id = ?", (template_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_template(row)

    async def list_by_company(self, company_id: str, status: str | None = None) -> list[EmployeeTemplate]:
        """按公司列出模板。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                cursor = await db.execute(
                    """SELECT * FROM employee_templates
                       WHERE company_id = ? AND status = ?
                       ORDER BY created_at""",
                    (company_id, status),
                )
            else:
                cursor = await db.execute(
                    """SELECT * FROM employee_templates
                       WHERE company_id = ?
                       ORDER BY created_at""",
                    (company_id,),
                )
            rows = await cursor.fetchall()
            return [self._row_to_template(r) for r in rows]
