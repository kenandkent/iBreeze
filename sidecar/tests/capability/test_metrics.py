"""能力度量测试。"""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from acos.capability.metrics import CapabilityMetrics, MetricsReader
from acos.store.migrator import Migrator


@pytest.fixture
async def db(tmp_path: Path) -> str:
    db_path = tmp_path / "test.db"
    migrator = Migrator(str(db_path))
    await migrator.run_pending_migrations(
        str(Path(__file__).resolve().parents[2] / "migrations")
    )
    return str(db_path)


async def test_get_metrics_empty(db: str) -> None:
    reader = MetricsReader(db)
    result = await reader.get_metrics("nonexistent", 1)
    assert result is None


async def test_get_metrics_with_data(db: str) -> None:
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            """INSERT INTO capability_metrics
               (capability_id, capability_version, success_rate, avg_cost)
               VALUES ('cap-1', 1, 0.95, 0.01)"""
        )
        await conn.commit()

    reader = MetricsReader(db)
    result = await reader.get_metrics("cap-1", 1)
    assert result is not None
    assert result.capability_id == "cap-1"
    assert result.capability_version == 1
    assert result.success_rate == 0.95
    assert result.avg_cost == 0.01


async def test_get_capability_aggregate(db: str) -> None:
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            """INSERT INTO capability_metrics
               (capability_id, capability_version, success_rate, avg_cost)
               VALUES ('cap-2', 1, 0.90, 0.02)"""
        )
        await conn.execute(
            """INSERT INTO capability_metrics
               (capability_id, capability_version, success_rate, avg_cost)
               VALUES ('cap-2', 2, 0.98, 0.01)"""
        )
        await conn.commit()

    reader = MetricsReader(db)
    result = await reader.get_capability_aggregate("cap-2")
    assert result["avg_success_rate"] == pytest.approx(0.94)
    assert result["avg_cost"] == pytest.approx(0.015)


async def test_list_metrics(db: str) -> None:
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            """INSERT INTO capability_metrics
               (capability_id, capability_version, success_rate)
               VALUES ('cap-3', 1, 0.85)"""
        )
        await conn.execute(
            """INSERT INTO capability_metrics
               (capability_id, capability_version, success_rate)
               VALUES ('cap-3', 2, 0.92)"""
        )
        await conn.commit()

    reader = MetricsReader(db)
    results = await reader.list_metrics("cap-3")
    assert len(results) == 2
    assert all(m.capability_id == "cap-3" for m in results)


async def test_capability_metrics_dataclass() -> None:
    m = CapabilityMetrics(
        capability_id="cap-4",
        capability_version=1,
        success_rate=0.88,
        avg_cost=0.05,
    )
    assert m.capability_id == "cap-4"
    assert m.success_rate == 0.88
