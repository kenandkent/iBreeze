"""组织服务 - Company 生命周期管理。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.organization.models import Company
from acos.rpc.errors import (
    ORG_COMPANY_DISSOLVED,
    ORG_NOT_FOUND,
    ORG_STATE_INVALID,
    SYS_OPTIMISTIC_LOCK_CONFLICT,
    create_error,
)


class OrganizationService:
    """组织服务。"""

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
    def _row_to_company(row: aiosqlite.Row) -> Company:
        return Company(
            company_id=row["company_id"],
            name=row["name"],
            status=row["status"],
            root_department_id=row["root_department_id"],
            default_provider_policy=json.loads(row["default_provider_policy"]),
            default_budget_policy=json.loads(row["default_budget_policy"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=row["version"],
        )

    async def create_company(self, name: str, owner_id: str) -> Company:
        """创建公司（原子操作），初始为 initializing，待 activate 转 active。"""
        company = Company(name=name, status="initializing")
        now = self._now()
        company.created_at = now
        company.updated_at = now

        dept_id = str(uuid.uuid4())
        company.root_department_id = dept_id

        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            try:
                await db.execute(
                    """INSERT INTO companies
                       (company_id, name, status, root_department_id,
                        default_provider_policy, default_budget_policy,
                        created_at, updated_at, version)
                       VALUES (?, ?, ?, ?, '{}', '{}', ?, ?, 1)""",
                    (company.company_id, company.name, company.status,
                     dept_id, now, now),
                )

                await db.execute(
                    """INSERT INTO departments
                       (department_id, company_id, parent_department_id, name,
                        status, created_at, updated_at, version)
                       VALUES (?, ?, NULL, '总经理办公室', 'active', ?, ?, 1)""",
                    (dept_id, company.company_id, now, now),
                )

                await db.execute(
                    """INSERT INTO department_closure
                       (company_id, ancestor_department_id, descendant_department_id, depth)
                       VALUES (?, ?, ?, 0)""",
                    (company.company_id, dept_id, dept_id),
                )

                for table in ("knowledge_policies", "embedding_policies", "security_policies"):
                    await db.execute(
                        f"""INSERT INTO {table}
                            (policy_id, company_id, version, status, config, created_at)
                            VALUES (?, ?, 1, 'active', '{{}}', ?)""",
                        (str(uuid.uuid4()), company.company_id, now),
                    )

                await db.execute(
                    """INSERT INTO org_change_audit
                       (id, company_id, aggregate_type, aggregate_id, action,
                        before_snapshot, after_snapshot, operator, reason, trace_id, timestamp)
                       VALUES (?, ?, 'company', ?, 'create', '', ?, ?, '', ?, ?)""",
                    (
                        str(uuid.uuid4()), company.company_id, company.company_id,
                        json.dumps({"name": company.name, "status": company.status}),
                        owner_id, str(uuid.uuid4()), now,
                    ),
                )

                await db.commit()
            except Exception:
                await db.rollback()
                raise

        return company

    async def get_company(self, company_id: str) -> Optional[Company]:
        """获取公司。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM companies WHERE company_id = ? AND deleted_at IS NULL",
                (company_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_company(row)

    async def activate_company(self, company_id: str, expected_version: int) -> Company:
        """激活公司。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """UPDATE companies
                   SET status = 'active', version = version + 1, updated_at = ?
                   WHERE company_id = ? AND version = ?
                     AND status = 'initializing' AND deleted_at IS NULL""",
                (now, company_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise create_error(ORG_STATE_INVALID, f"无法激活公司 {company_id}")

            cursor = await db.execute(
                "SELECT * FROM companies WHERE company_id = ?", (company_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_company(row)

    async def start_dissolution(
        self, company_id: str, expected_version: int, operator: str
    ) -> Company:
        """开始解散。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """UPDATE companies
                   SET status = 'dissolving', version = version + 1, updated_at = ?
                   WHERE company_id = ? AND version = ?
                     AND status = 'active' AND deleted_at IS NULL""",
                (now, company_id, expected_version),
            )
            if cursor.rowcount == 0:
                raise create_error(ORG_STATE_INVALID, f"无法解散公司 {company_id}")

            cursor = await db.execute(
                "SELECT * FROM companies WHERE company_id = ?", (company_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_company(row)

    async def complete_dissolution(self, company_id: str) -> Company:
        """完成解散。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """UPDATE companies
                   SET status = 'dissolved', version = version + 1, updated_at = ?
                   WHERE company_id = ? AND status = 'dissolving' AND deleted_at IS NULL""",
                (now, company_id),
            )
            if cursor.rowcount == 0:
                raise create_error(ORG_STATE_INVALID, f"无法完成解散 {company_id}")

            cursor = await db.execute(
                "SELECT * FROM companies WHERE company_id = ?", (company_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_company(row)

    async def update_company(
        self, company_id: str, expected_version: int, updates: dict
    ) -> Company:
        """更新公司（CAS）。"""
        now = self._now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                "SELECT * FROM companies WHERE company_id = ? AND deleted_at IS NULL",
                (company_id,),
            )
            current = await cursor.fetchone()
            if current is None:
                raise create_error(ORG_NOT_FOUND, f"公司 {company_id} 不存在")
            if current["status"] == "dissolved":
                raise create_error(ORG_COMPANY_DISSOLVED, "已解散公司拒绝写入")

            allowed = {"name", "default_provider_policy", "default_budget_policy"}
            set_parts: list[str] = []
            params: list[object] = []
            for key, value in updates.items():
                if key not in allowed:
                    continue
                if key in ("default_provider_policy", "default_budget_policy"):
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
            params.extend([company_id, expected_version])

            sql = f"""UPDATE companies
                      SET {', '.join(set_parts)}
                      WHERE company_id = ? AND version = ? AND deleted_at IS NULL"""
            cursor = await db.execute(sql, params)

            if cursor.rowcount == 0:
                raise create_error(
                    SYS_OPTIMISTIC_LOCK_CONFLICT,
                    f"CAS 冲突: company {company_id}",
                )

            cursor = await db.execute(
                "SELECT * FROM companies WHERE company_id = ?", (company_id,),
            )
            row = await cursor.fetchone()
            await db.commit()
            return self._row_to_company(row)
