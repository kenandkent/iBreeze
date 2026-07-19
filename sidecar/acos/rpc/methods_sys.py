"""系统 RPC 方法集合。

注册 sys.migration.status：包装 Migrator，返回已应用迁移与待执行迁移。
其他 sys.* 已由 server 内置（sys.health / sys.shutdown）。
"""

from __future__ import annotations

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
