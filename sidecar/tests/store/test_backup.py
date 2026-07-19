"""备份管理器测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import aiosqlite

from acos.store.backup import BackupManager
from acos.rpc.errors import AcosError


@pytest.fixture
def tmp_db(tmp_path: Path) -> str:
    db_path = tmp_path / "test.db"
    return str(db_path)


@pytest.fixture
def backup_dir(tmp_path: Path) -> str:
    d = tmp_path / "backups"
    d.mkdir()
    return str(d)


@pytest.fixture
def manager(tmp_db: str, backup_dir: str) -> BackupManager:
    return BackupManager(tmp_db, backup_dir)


async def _init_db(db_path: str) -> None:
    """初始化一个带测试表的数据库。"""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, name TEXT)")
        await db.execute("INSERT INTO items (name) VALUES ('test1'), ('test2')")
        await db.commit()


async def test_create_snapshot(tmp_db: str, backup_dir: str) -> None:
    await _init_db(tmp_db)
    mgr = BackupManager(tmp_db, backup_dir)

    backup_id = await mgr.create_snapshot()
    assert backup_id
    assert isinstance(backup_id, str)
    assert len(backup_id) > 0

    snapshots = await mgr.list_snapshots()
    assert len(snapshots) == 1
    assert snapshots[0]["backup_id"] == backup_id
    assert snapshots[0]["status"] == "available"


async def test_snapshot_barrier_blocks_writes(tmp_db: str, backup_dir: str) -> None:
    await _init_db(tmp_db)
    mgr = BackupManager(tmp_db, backup_dir)

    acquired = await mgr.acquire_write_barrier(timeout=1.0)
    assert acquired is True
    assert mgr.is_barrier_active is True

    with pytest.raises(AcosError) as exc_info:
        await mgr.check_write_allowed()
    assert exc_info.value.code == "SYS-BACKUP-IN-PROGRESS"

    await mgr.release_write_barrier()


async def test_snapshot_barrier_releases(tmp_db: str, backup_dir: str) -> None:
    await _init_db(tmp_db)
    mgr = BackupManager(tmp_db, backup_dir)

    await mgr.acquire_write_barrier(timeout=1.0)
    assert mgr.is_barrier_active is True
    await mgr.release_write_barrier()
    assert mgr.is_barrier_active is False

    # 释放后应允许写入
    await mgr.check_write_allowed()


async def test_list_snapshots(tmp_db: str, backup_dir: str) -> None:
    await _init_db(tmp_db)
    mgr = BackupManager(tmp_db, backup_dir)

    # 初始为空
    snapshots = await mgr.list_snapshots()
    assert snapshots == []

    # 创建后应有 1 条
    await mgr.create_snapshot()
    snapshots = await mgr.list_snapshots()
    assert len(snapshots) == 1

    # 再创建一条
    await mgr.create_snapshot()
    snapshots = await mgr.list_snapshots()
    assert len(snapshots) == 2


async def test_delete_snapshot(tmp_db: str, backup_dir: str) -> None:
    await _init_db(tmp_db)
    mgr = BackupManager(tmp_db, backup_dir)

    backup_id = await mgr.create_snapshot()
    assert len(await mgr.list_snapshots()) == 1

    result = await mgr.delete_snapshot(backup_id)
    assert result is True
    assert len(await mgr.list_snapshots()) == 0


async def test_delete_nonexistent_snapshot(tmp_db: str, backup_dir: str) -> None:
    await _init_db(tmp_db)
    mgr = BackupManager(tmp_db, backup_dir)

    result = await mgr.delete_snapshot("nonexistent-id")
    assert result is False


async def test_restore_snapshot(tmp_db: str, backup_dir: str) -> None:
    await _init_db(tmp_db)
    mgr = BackupManager(tmp_db, backup_dir)

    backup_id = await mgr.create_snapshot()

    # 修改数据库
    async with aiosqlite.connect(tmp_db) as db:
        await db.execute("DELETE FROM items")
        await db.commit()

    async with aiosqlite.connect(tmp_db) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM items")
        assert (await cursor.fetchone())[0] == 0

    # 恢复
    success, pre_restore_id = await mgr.restore_snapshot(backup_id)
    assert success is True
    assert pre_restore_id is not None
    assert isinstance(pre_restore_id, str)

    async with aiosqlite.connect(tmp_db) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM items")
        assert (await cursor.fetchone())[0] == 2

    # pre_restore 快照的归档文件应存在（DB 记录在恢复时被覆盖）
    import hashlib
    pre_archive = Path(backup_dir) / f"{pre_restore_id}.db"
    assert pre_archive.exists()
    assert pre_archive.stat().st_size > 0


async def test_restore_nonexistent_snapshot(tmp_db: str, backup_dir: str) -> None:
    await _init_db(tmp_db)
    mgr = BackupManager(tmp_db, backup_dir)

    with pytest.raises(AcosError) as exc_info:
        await mgr.restore_snapshot("nonexistent-id")
    assert exc_info.value.code == "SYS-BACKUP-NOT-FOUND"


async def test_cleanup_old_snapshots(tmp_db: str, backup_dir: str) -> None:
    await _init_db(tmp_db)
    mgr = BackupManager(tmp_db, backup_dir)

    # 创建 6 个快照
    for _ in range(6):
        await mgr.create_snapshot()

    snapshots = await mgr.list_snapshots()
    assert len(snapshots) == 6

    # 清理：保留最多 5 个
    deleted = await mgr.cleanup_old_snapshots(max_count=5, max_days=3650)
    assert deleted >= 1

    snapshots = await mgr.list_snapshots()
    assert len(snapshots) <= 5


async def test_snapshot_idempotent(tmp_db: str, backup_dir: str) -> None:
    await _init_db(tmp_db)
    mgr = BackupManager(tmp_db, backup_dir)

    id1 = await mgr.create_snapshot()
    id2 = await mgr.create_snapshot()

    # 两次创建应产生不同 backup_id
    assert id1 != id2

    snapshots = await mgr.list_snapshots()
    assert len(snapshots) == 2
