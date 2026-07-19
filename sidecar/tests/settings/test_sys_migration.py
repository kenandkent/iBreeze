"""sys.migration.status RPC 测试：返回已应用迁移与待执行迁移，结构正确。"""

from __future__ import annotations

from pathlib import Path

import pytest

from acos.store.migrator import Migrator
from acos.rpc.methods_sys import SysMethods

MIGRATIONS_DIR = str(Path(__file__).resolve().parents[2] / "migrations")


@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    p = str(tmp_path / "test.db")
    migrator = Migrator(p)
    await migrator.run_pending_migrations(MIGRATIONS_DIR)
    return p


async def test_migration_status_non_empty(db_path: str) -> None:
    methods = SysMethods(db_path)
    result = await methods._migration_status({})
    assert result["applied_count"] > 0
    assert isinstance(result["applied"], list)
    assert isinstance(result["pending"], list)
    assert result["pending_count"] == 0
    # 已应用的迁移都不应出现在 pending 中
    assert set(result["pending"]).isdisjoint(set(result["applied"]))
    # 我新增的 settings 迁移应已应用
    assert "0038_settings_policies" in result["applied"]


async def test_migration_status_structure(db_path: str) -> None:
    methods = SysMethods(db_path)
    result = await methods._migration_status({})
    for key in ("applied", "pending", "applied_count", "pending_count"):
        assert key in result
