"""ConfigPuller - 从 Admin Backend 拉取配置数据，写入本地 Sidecar DB。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import aiosqlite
import httpx

logger = logging.getLogger(__name__)

# 配置表清单（不含业务数据表）
SYNC_TABLES = {
    "capabilities": "capabilities",
    "capability_versions": "capability_versions",
    "skills": "skills",
    "skill_versions": "skill_versions",
    "skill_bindings": "skill_bindings",
    "prompt_assets": "prompt_assets",
    "prompt_asset_versions": "prompt_asset_versions",
    "employee_templates": "employee_templates",
    "knowledge_policies": "knowledge_policies",
    "security_policies": "security_policies",
    "workspace_policies": "workspace_policies",
    "notification_policies": "notification_policies",
    "budget_policies": "budget_policies",
    "backends": "backends",
    "company_backend_defaults": "company_backend_defaults",
    "providers": "providers",
    "provider_pricing_versions": "provider_pricing_versions",
    "provider_tier_mappings": "provider_tier_mappings",
}


class ConfigPuller:
    """从 Admin Backend 拉取配置数据，写入本地 Sidecar DB"""

    def __init__(self, admin_api_base: str, db_path: str) -> None:
        self.admin_api_base = admin_api_base.rstrip("/")
        self.db_path = db_path

    async def pull_full_config(self, company_id: str) -> dict:
        """全量拉取（启动时）"""
        url = f"{self.admin_api_base}/api/sync/config"
        params = {"company_id": company_id}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.error("Sync failed: %s", resp.status_code)
                return {}
            data = resp.json()

        await self._upsert_config(company_id, data)
        return data

    async def pull_incremental(self, company_id: str, since: str | None = None) -> dict:
        """增量拉取（定期）"""
        url = f"{self.admin_api_base}/api/sync/config"
        params: dict[str, str] = {"company_id": company_id}
        if since:
            params["since"] = since

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.error("Incremental sync failed: %s", resp.status_code)
                return {}
            data = resp.json()

        await self._upsert_config(company_id, data)
        return data

    async def _upsert_config(self, company_id: str, data: dict) -> None:
        """将拉取的配置数据写入本地 DB（INSERT OR REPLACE）"""
        async with aiosqlite.connect(self.db_path) as db:
            for api_key, table_name in SYNC_TABLES.items():
                rows = data.get(api_key, [])
                if not rows:
                    continue
                for row in rows:
                    # Remove 'id' auto-increment fields for tables that use them
                    columns = [k for k in row.keys() if k != "id"]
                    if not columns:
                        continue
                    placeholders = ", ".join(["?"] * len(columns))
                    col_names = ", ".join(columns)
                    values = [row.get(c) for c in columns]

                    # Use INSERT OR REPLACE with primary key
                    pk = self._get_pk(table_name)
                    if pk and pk in row:
                        update_cols = [c for c in columns if c != pk]
                        if update_cols:
                            set_clause = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
                            sql = f"""
                                INSERT INTO {table_name} ({col_names})
                                VALUES ({placeholders})
                                ON CONFLICT({pk}) DO UPDATE SET {set_clause}
                            """
                        else:
                            sql = f"""
                                INSERT OR IGNORE INTO {table_name} ({col_names})
                                VALUES ({placeholders})
                            """
                    else:
                        sql = f"INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})"

                    await db.execute(sql, values)
            await db.commit()
            logger.info("Config synced for company %s: %s", company_id, list(data.keys()))

    @staticmethod
    def _get_pk(table_name: str) -> str | None:
        """返回表的主键列名"""
        pk_map = {
            "capabilities": "capability_id",
            "capability_versions": "id",
            "skills": "skill_id",
            "skill_versions": "id",
            "skill_bindings": "binding_id",
            "prompt_assets": "prompt_id",
            "prompt_asset_versions": "id",
            "employee_templates": "template_id",
            "knowledge_policies": "id",
            "security_policies": "id",
            "workspace_policies": "id",
            "notification_policies": "id",
            "budget_policies": "id",
            "backends": "backend_id",
            "company_backend_defaults": "company_id",
            "providers": "provider_id",
            "provider_pricing_versions": "id",
            "provider_tier_mappings": "id",
        }
        return pk_map.get(table_name)
