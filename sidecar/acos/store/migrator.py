"""Forward-only SQLite 迁移执行器。"""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite


class Migrator:
    """SQLite 迁移执行器。

    提供 schema_migrations 表管理、迁移应用、备份快照等功能。
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def ensure_migration_table(self) -> None:
        """创建 schema_migrations 表（如果不存在）。"""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                )"""
            )
            await db.commit()

    async def get_applied_migrations(self) -> list[str]:
        """获取已应用的迁移列表。"""
        await self.ensure_migration_table()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

    async def apply_migration(self, migration_path: str) -> None:
        """应用单个迁移脚本。

        通过文件名提取版本号，检查是否已应用，然后执行 SQL。
        """
        version = Path(migration_path).stem
        applied = await self.get_applied_migrations()
        if version in applied:
            return

        with open(migration_path) as f:
            sql = f.read()

        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(sql)
            await db.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

    async def run_pending_migrations(self, migrations_dir: str) -> None:
        """执行所有待处理的迁移。"""
        await self.ensure_migration_table()
        applied = await self.get_applied_migrations()

        migrations_path = Path(migrations_dir)
        if not migrations_path.is_dir():
            return

        sql_files = sorted(
            f for f in migrations_path.iterdir()
            if f.suffix == ".sql"
        )

        for sql_file in sql_files:
            version = sql_file.stem
            if version not in applied:
                await self.apply_migration(str(sql_file))

    async def create_backup_before_migration(self) -> str:
        """迁移前自动创建备份快照。

        返回备份文件路径。如果 backup.py 可用则委托其 create_snapshot，
        否则执行简单的文件复制。
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_dir = Path(self._db_path).parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"db_backup_{timestamp}.db"

        try:
            from acos.store.backup import create_snapshot
            return await create_snapshot(self._db_path)
        except ImportError:
            shutil.copy2(self._db_path, str(backup_path))
            return str(backup_path)

    async def get_migration_hash(self, migration_path: str) -> str:
        """计算迁移文件内容的 SHA-256 哈希。"""
        with open(migration_path, "rb") as f:
            content = f.read()
        return hashlib.sha256(content).hexdigest()
