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

    async def _query_snapshot_epochs_extra(self, db: aiosqlite.Connection) -> dict:
        """查询 snapshot_epochs 所需的额外字段值。"""
        extra: dict = {}

        # outbox_delivery_watermark: max created_at from outbox_deliveries
        try:
            cursor = await db.execute(
                "SELECT MAX(created_at) FROM outbox_deliveries"
            )
            row = await cursor.fetchone()
            extra["outbox_delivery_watermark"] = row[0] if row and row[0] else None
        except Exception:
            extra["outbox_delivery_watermark"] = None

        # lancedb_generation_map_json
        try:
            cursor = await db.execute(
                "SELECT company_id, generation_id FROM lancedb_generations WHERE status='active'"
            )
            rows = await cursor.fetchall()
            extra["lancedb_generation_map_json"] = json.dumps(
                {r[0]: r[1] for r in rows} if rows else {}
            )
        except Exception:
            extra["lancedb_generation_map_json"] = "{}"

        # session_watermarks_json
        try:
            cursor = await db.execute(
                """SELECT company_id, employee_id, security_context_key, last_checkpoint_offset
                   FROM session_threads
                   WHERE last_checkpoint_offset IS NOT NULL
                   ORDER BY company_id, employee_id, security_context_key"""
            )
            rows = await cursor.fetchall()
            watermarks = [
                {
                    "company_id": r[0],
                    "employee_id": r[1],
                    "security_context_key": r[2],
                    "last_checkpoint_offset": r[3],
                }
                for r in rows
            ]
            extra["session_watermarks_json"] = json.dumps(watermarks)
        except Exception:
            extra["session_watermarks_json"] = "[]"

        extra["failure_code"] = None
        return extra

    async def create_snapshot(self, *, kind: str = "full") -> str:
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

                extra = await self._query_snapshot_epochs_extra(db)

                # 记录 snapshot_epoch 并提交，使备份包含此记录
                cursor = await db.execute(
                    """INSERT INTO snapshot_epochs
                       (state, barrier_started_at,
                        outbox_delivery_watermark, lancedb_generation_map_json,
                        session_watermarks_json, failure_code)
                       VALUES ('creating', ?, ?, ?, ?, ?)""",
                    (
                        now_iso,
                        extra["outbox_delivery_watermark"],
                        extra["lancedb_generation_map_json"],
                        extra["session_watermarks_json"],
                        extra["failure_code"],
                    ),
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
                    "encrypted_archive_sha256": archive_sha256,
                    "wrapped_dek": "",
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
                        archive_path, manifest_sha256, encrypted_archive_sha256,
                        wrapped_dek, file_count, total_bytes,
                        status, created_at, completed_at)
                       VALUES (?, ?, ?, '0.1.0', '0007', ?, ?, ?, ?, 1, ?,
                               'available', ?, ?)""",
                    (
                        backup_id,
                        epoch,
                        kind,
                        str(archive_path),
                        manifest_sha256,
                        archive_sha256,
                        "",
                        len(archive_bytes),
                        now_iso,
                        captured_at,
                    ),
                )

                await db.commit()

            return backup_id
        finally:
            await self.release_write_barrier()

    async def reconcile_after_restore(self, backup_id: str) -> dict:
        """恢复后校验：比对 session watermarks 与 schema_version。"""
        current_schema_version = "0007"
        details: dict = {}
        consistent = True

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row

            # 查 manifest 中的 schema_version
            cursor = await db.execute(
                "SELECT schema_version FROM backup_manifests WHERE backup_id = ?",
                (backup_id,),
            )
            manifest_row = await cursor.fetchone()
            if manifest_row and manifest_row["schema_version"] != current_schema_version:
                consistent = False
                details["schema_version_mismatch"] = {
                    "expected": current_schema_version,
                    "actual": manifest_row["schema_version"],
                }

            # 查 snapshot_epochs 中的 session_watermarks_json
            cursor = await db.execute(
                """SELECT se.session_watermarks_json
                   FROM snapshot_epochs se
                   JOIN backup_manifests bm ON bm.snapshot_epoch = se.snapshot_epoch
                   WHERE bm.backup_id = ?""",
                (backup_id,),
            )
            epoch_row = await cursor.fetchone()
            if epoch_row and epoch_row["session_watermarks_json"]:
                try:
                    saved_watermarks = json.loads(epoch_row["session_watermarks_json"])
                except (json.JSONDecodeError, TypeError):
                    saved_watermarks = []
            else:
                saved_watermarks = []

            # 查当前 session_threads 中的实际 watermarks
            try:
                cursor = await db.execute(
                    """SELECT company_id, employee_id, security_context_key,
                              last_checkpoint_offset
                       FROM session_threads
                       WHERE last_checkpoint_offset IS NOT NULL
                       ORDER BY company_id, employee_id, security_context_key"""
                )
                actual_rows = await cursor.fetchall()
                actual_watermarks = [
                    {
                        "company_id": r[0],
                        "employee_id": r[1],
                        "security_context_key": r[2],
                        "last_checkpoint_offset": r[3],
                    }
                    for r in actual_rows
                ]
            except Exception:
                actual_watermarks = []

            # 比对 watermarks
            if saved_watermarks != actual_watermarks:
                consistent = False
                details["session_watermarks_diff"] = {
                    "saved_count": len(saved_watermarks),
                    "actual_count": len(actual_watermarks),
                }

        details["consistent"] = consistent
        return {"consistent": consistent, "details": details}

    async def restore_snapshot(self, backup_id: str) -> tuple[bool, str | None]:
        """恢复快照。

        校验 backup_id 存在且 status=available，校验 manifest hash，恢复 SQLite。
        恢复前自动创建 pre_restore 快照；恢复后调用 reconcile 校验一致性。
        返回 (success, pre_restore_backup_id)。
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

            # schema_version 校验
            current_schema_version = "0007"
            if row["schema_version"] != current_schema_version:
                from acos.rpc.errors import create_error

                raise create_error(
                    "SYS-BACKUP-SCHEMA-INCOMPATIBLE",
                    f"Backup schema {row['schema_version']} != current {current_schema_version}",
                )

            archive_path = Path(row["archive_path"])
            if not archive_path.exists():
                from acos.rpc.errors import create_error

                raise create_error("SYS-BACKUP-INCONSISTENT", "Archive file missing")

            # 校验 manifest hash（含新增字段）
            archive_bytes = archive_path.read_bytes()
            manifest_data = {
                "backup_id": row["backup_id"],
                "epoch": row["snapshot_epoch"],
                "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
                "encrypted_archive_sha256": row["encrypted_archive_sha256"] or "",
                "wrapped_dek": row["wrapped_dek"] or "",
                "file_count": row["file_count"],
                "total_bytes": row["total_bytes"],
            }
            computed_sha = hashlib.sha256(
                json.dumps(manifest_data, sort_keys=True).encode()
            ).hexdigest()
            if computed_sha != row["manifest_sha256"]:
                from acos.rpc.errors import create_error

                raise create_error("SYS-BACKUP-INCONSISTENT", "Manifest checksum mismatch")

        # 恢复前自动创建 pre_restore 快照
        pre_restore_backup_id = await self.create_snapshot(kind="pre_restore")

        # 恢复 SQLite：用备份文件覆盖当前数据库
        acquired = await self.acquire_write_barrier(timeout=5.0)
        if not acquired:
            from acos.rpc.errors import create_error

            raise create_error(
                "SYS-BACKUP-QUIESCE-TIMEOUT", "Write barrier acquisition timed out"
            )

        try:
            shutil.copy2(str(archive_path), self._db_path)

            # 恢复后校验
            reconciliation = await self.reconcile_after_restore(backup_id)
            if not reconciliation["consistent"]:
                # 尝试从 pre_restore 快照恢复
                pre_archive_cursor_result = await self._restore_from_pre_restore(
                    pre_restore_backup_id
                )
                if pre_archive_cursor_result:
                    from acos.rpc.errors import create_error

                    raise create_error(
                        "SYS-BACKUP-INCONSISTENT",
                        "Restore produced inconsistent state; rolled back to pre-restore snapshot",
                    )

            return True, pre_restore_backup_id
        finally:
            await self.release_write_barrier()

    async def _restore_from_pre_restore(self, pre_restore_backup_id: str) -> bool:
        """从 pre_restore 快照恢复。返回 True 表示恢复成功。"""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT archive_path FROM backup_manifests WHERE backup_id = ? AND status = 'available'",
                (pre_restore_backup_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return False

        pre_archive_path = Path(row["archive_path"])
        if not pre_archive_path.exists():
            return False

        shutil.copy2(str(pre_archive_path), self._db_path)
        return True

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
