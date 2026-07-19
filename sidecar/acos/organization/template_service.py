"""员工模板服务。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.organization.models import EmployeeTemplate
from acos.rpc.errors import (
    ORG_NOT_FOUND,
    ORG_STATE_INVALID,
    SYS_OPTIMISTIC_LOCK_CONFLICT,
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
        """创建模板。"""
        template = EmployeeTemplate(
            template_scope=template_scope,
            company_id=company_id if template_scope == "company" else None,
            provider_type=provider_type,
            provider_id=provider_id,
            model=model,
            capability_id=capability_id,
            capability_version=capability_version,
            capability_snapshot=capability_snapshot or {},
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
        """激活模板 draft→active。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """UPDATE employee_templates
                   SET status = 'active', version = version + 1, updated_at = ?
                   WHERE template_id = ? AND version = ? AND status = 'draft'""",
                (now, template_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise create_error(ORG_STATE_INVALID, f"无法激活模板 {template_id}")

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
