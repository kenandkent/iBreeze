"""系统 RPC 方法集合。

注册 sys.migration.status：包装 Migrator，返回已应用迁移与待执行迁移。
注册 sys.sync.trigger：调用 ConfigPuller 拉取配置到本地 DB。
其他 sys.* 已由 server 内置（sys.health / sys.shutdown）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from acos.store.migrator import Migrator
from acos.rpc.server import RPCServer


class SysMethods:
    """系统相关的 RPC 方法。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._migrations_dir = str(Path(__file__).resolve().parents[2] / "migrations")

    def register_to(self, server: RPCServer) -> None:
        server.register_method("sys.migration.status", self._migration_status)
        server.register_method("sys.sync.trigger", self._sync_trigger)

    async def _migration_status(self, _params: dict[str, Any]) -> dict[str, Any]:
        migrator = Migrator(self._db_path)
        applied = await migrator.get_applied_migrations()

        pending: list[str] = []
        migrations_path = Path(self._migrations_dir)
        if migrations_path.is_dir():
            sql_files = sorted(
                f.stem for f in migrations_path.iterdir() if f.suffix == ".sql"
            )
            pending = [v for v in sql_files if v not in set(applied)]

        return {
            "applied": applied,
            "pending": pending,
            "applied_count": len(applied),
            "pending_count": len(pending),
        }

    async def _sync_trigger(self, params: dict[str, Any]) -> dict[str, Any]:
        """从 Admin Backend 拉取配置数据，写入本地 Sidecar DB。

        params:
            company_id (str): 必填
            since (str, optional): 增量拉取的起始时间戳
        """
        company_id = params.get("company_id")
        if not company_id:
            return {"error": "missing company_id"}
        since = params.get("since")

        admin_api_base = os.environ.get("ACOS_ADMIN_API_BASE", "http://127.0.0.1:50080")
        from acos.sync.puller import ConfigPuller

        puller = ConfigPuller(admin_api_base=admin_api_base, db_path=self._db_path)
        if since:
            data = await puller.pull_incremental(company_id, since=since)
        else:
            data = await puller.pull_full_config(company_id)
        return {"synced": True, "keys": list(data.keys())}
