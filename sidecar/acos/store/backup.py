"""跨存储备份管理器。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite


class BackupManager:
    """跨存储备份管理器。

    提供写门禁、一致性快照创建、恢复、列出、删除和清理功能。
    """

    def __init__(self, db_path: str, backup_dir: str) -> None:
        self._db_path = db_path
        self._backup_dir = Path(backup_dir)
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._write_barrier = False
        self._inflight_writes = 0
        self._drained_event = asyncio.Event()
        self._drained_event.set()  # 初始无进行中的写入

    @property
    def is_barrier_active(self) -> bool:
        return self._write_barrier

    async def acquire_write_barrier(self, timeout: float = 30.0) -> bool:
        """获取写门禁：先设标志位阻止新写入，再等待当前进行中的写入完成。"""
        self._write_barrier = True
        self._drained_event.clear()
        if self._inflight_writes == 0:
            self._drained_event.set()
            return True
        try:
            await asyncio.wait_for(self._drained_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            self._write_barrier = False
            self._drained_event.set()
            return False

    async def release_write_barrier(self) -> None:
        """释放写门禁。"""
        self._write_barrier = False

    async def begin_write(self) -> None:
        """声明一次写入开始（用于门禁计数）。"""
        if self._write_barrier:
            from acos.rpc.errors import create_error

            raise create_error("SYS-BACKUP-IN-PROGRESS", "Backup in progress, retry shortly")
        self._inflight_writes += 1

    async def end_write(self) -> None:
        """声明一次写入结束。"""
        self._inflight_writes -= 1
        if self._inflight_writes <= 0 and self._write_barrier:
            self._drained_event.set()

    async def check_write_allowed(self) -> None:
        """检查是否允许写入，不允许则抛异常。"""
        if self._write_barrier:
            from acos.rpc.errors import create_error

            raise create_error("SYS-BACKUP-IN-PROGRESS", "Backup in progress, retry shortly")

    async def _apply_backup_tables(self) -> None:
        """确保备份相关表存在。"""
        migration_path = (
            Path(__file__).resolve().parent.parent.parent / "migrations" / "0007_backup_tables.sql"
        )
        if migration_path.exists():
            sql = migration_path.read_text()
            async with aiosqlite.connect(self._db_path) as db:
                await db.executescript(sql)
                await db.commit()

    async def create_snapshot(self) -> str:
        """创建跨存储一致快照，返回 backup_id。"""
        import uuid

        await self._apply_backup_tables()

        acquired = await self.acquire_write_barrier(timeout=5.0)
        if not acquired:
            from acos.rpc.errors import create_error

            raise create_error(
                "SYS-BACKUP-QUIESCE-TIMEOUT", "Write barrier acquisition timed out"
            )

        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            backup_id = str(uuid.uuid4())

            async with aiosqlite.connect(self._db_path) as db:
                db.row_factory = aiosqlite.Row

                # 记录 snapshot_epoch 并提交，使备份包含此记录
                cursor = await db.execute(
                    """INSERT INTO snapshot_epochs
                       (state, barrier_started_at)
                       VALUES ('creating', ?)""",
                    (now_iso,),
                )
                epoch = cursor.lastrowid
                await db.commit()

                # SQLite 在线备份（必须在无活跃事务时调用）
                archive_path = self._backup_dir / f"{backup_id}.db"
                dest_db = await aiosqlite.connect(str(archive_path))
                try:
                    await db.backup(dest_db)
                finally:
                    await dest_db.close()

                archive_bytes = archive_path.read_bytes()
                archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()

                # 计算 manifest 内容哈希
                manifest_data = {
                    "backup_id": backup_id,
                    "epoch": epoch,
                    "archive_sha256": archive_sha256,
                    "file_count": 1,
                    "total_bytes": len(archive_bytes),
                }
                manifest_sha256 = hashlib.sha256(
                    json.dumps(manifest_data, sort_keys=True).encode()
                ).hexdigest()

                captured_at = datetime.now(timezone.utc).isoformat()

                # 更新 snapshot_epoch
                await db.execute(
                    """UPDATE snapshot_epochs
                       SET state = 'ready',
                           sqlite_event_watermark = ?,
                           captured_at = ?
                       WHERE snapshot_epoch = ?""",
                    (captured_at, captured_at, epoch),
                )

                # 插入 manifest
                await db.execute(
                    """INSERT INTO backup_manifests
                       (backup_id, snapshot_epoch, kind, app_version, schema_version,
                        archive_path, manifest_sha256, file_count, total_bytes,
                        status, created_at, completed_at)
                       VALUES (?, ?, 'full', '0.1.0', '0007', ?, ?, 1, ?,
                               'available', ?, ?)""",
                    (
                        backup_id,
                        epoch,
                        str(archive_path),
                        manifest_sha256,
                        len(archive_bytes),
                        now_iso,
                        captured_at,
                    ),
                )

                await db.commit()

            return backup_id
        finally:
            await self.release_write_barrier()

    async def restore_snapshot(self, backup_id: str) -> bool:
        """恢复快照。

        校验 backup_id 存在且 status=available，校验 manifest hash，恢复 SQLite。
        """
        await self._apply_backup_tables()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM backup_manifests WHERE backup_id = ? AND status = 'available'",
                (backup_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                from acos.rpc.errors import create_error

                raise create_error("SYS-BACKUP-NOT-FOUND", f"Backup {backup_id} not found")

            archive_path = Path(row["archive_path"])
            if not archive_path.exists():
                from acos.rpc.errors import create_error

                raise create_error("SYS-BACKUP-INCONSISTENT", "Archive file missing")

            # 校验 manifest hash
            archive_bytes = archive_path.read_bytes()
            manifest_data = {
                "backup_id": row["backup_id"],
                "epoch": row["snapshot_epoch"],
                "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
                "file_count": row["file_count"],
                "total_bytes": row["total_bytes"],
            }
            computed_sha = hashlib.sha256(
                json.dumps(manifest_data, sort_keys=True).encode()
            ).hexdigest()
            if computed_sha != row["manifest_sha256"]:
                from acos.rpc.errors import create_error

                raise create_error("SYS-BACKUP-INCONSISTENT", "Manifest checksum mismatch")

        # 恢复 SQLite：用备份文件覆盖当前数据库
        acquired = await self.acquire_write_barrier(timeout=5.0)
        if not acquired:
            from acos.rpc.errors import create_error

            raise create_error(
                "SYS-BACKUP-QUIESCE-TIMEOUT", "Write barrier acquisition timed out"
            )

        try:
            shutil.copy2(str(archive_path), self._db_path)
            return True
        finally:
            await self.release_write_barrier()

    async def list_snapshots(self) -> list[dict]:
        """列出可用快照。"""
        await self._apply_backup_tables()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT backup_id, snapshot_epoch, kind, status,
                          file_count, total_bytes, created_at, completed_at
                   FROM backup_manifests
                   WHERE status = 'available'
                   ORDER BY created_at DESC"""
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def delete_snapshot(self, backup_id: str) -> bool:
        """删除快照。"""
        await self._apply_backup_tables()

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM backup_manifests WHERE backup_id = ? AND status = 'available'",
                (backup_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return False

            archive_path = Path(row["archive_path"])
            if archive_path.exists():
                archive_path.unlink()

            now_iso = datetime.now(timezone.utc).isoformat()
            await db.execute(
                """UPDATE backup_manifests
                   SET status = 'deleted', deleted_at = ?, delete_reason = 'manual'
                   WHERE backup_id = ?""",
                (now_iso, backup_id),
            )
            await db.commit()
            return True

    async def cleanup_old_snapshots(self, max_count: int = 5, max_days: int = 30) -> int:
        """清理旧快照，返回删除数量。"""
        await self._apply_backup_tables()

        deleted = 0
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            now_iso = datetime.now(timezone.utc).isoformat()

            # 超过 max_days 的快照
            cursor = await db.execute(
                """SELECT backup_id, archive_path FROM backup_manifests
                   WHERE status = 'available'
                     AND created_at < datetime(?, '-' || ? || ' days')""",
                (now_iso, max_days),
            )
            for row in await cursor.fetchall():
                archive = Path(row["archive_path"])
                if archive.exists():
                    archive.unlink()
                await db.execute(
                    """UPDATE backup_manifests
                       SET status = 'deleted', deleted_at = ?, delete_reason = 'cleanup_days'
                       WHERE backup_id = ?""",
                    (now_iso, row["backup_id"]),
                )
                deleted += 1

            # 超过 max_count 的快照（保留最新的 max_count 个）
            cursor = await db.execute(
                """SELECT backup_id, archive_path FROM backup_manifests
                   WHERE status = 'available'
                     AND backup_id NOT IN (
                       SELECT backup_id FROM backup_manifests
                       WHERE status = 'available'
                       ORDER BY created_at DESC
                       LIMIT ?
                     )""",
                (max_count,),
            )
            for row in await cursor.fetchall():
                archive = Path(row["archive_path"])
                if archive.exists():
                    archive.unlink()
                await db.execute(
                    """UPDATE backup_manifests
                       SET status = 'deleted', deleted_at = ?, delete_reason = 'cleanup_count'
                       WHERE backup_id = ?""",
                    (now_iso, row["backup_id"]),
                )
                deleted += 1

            await db.commit()
        return deleted
