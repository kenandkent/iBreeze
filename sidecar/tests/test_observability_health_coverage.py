"""Coverage tests for ibreeze/observability/health.py (uncovered branches)."""

from __future__ import annotations

import pytest

from ibreeze.observability.health import _get_migration_version_async


class _FakeCursor:
    def __init__(self, row) -> None:
        self._row = row

    async def fetchone(self):
        return self._row


class _FakeWriter:
    def __init__(self, row=None, error: bool = False) -> None:
        self._row = row
        self._error = error

    async def execute(self, sql, parameters=()):
        if self._error:
            raise RuntimeError("db down")
        return _FakeCursor(self._row)


@pytest.mark.asyncio
class TestMigrationVersionCoverage:
    async def test_none_writer_returns_zero(self) -> None:
        assert await _get_migration_version_async(None) == 0

    async def test_happy_path_returns_max_version(self) -> None:
        assert await _get_migration_version_async(_FakeWriter(row=(3,))) == 3

    async def test_empty_row_returns_zero(self) -> None:
        assert await _get_migration_version_async(_FakeWriter(row=None)) == 0

    async def test_execute_error_returns_zero(self) -> None:
        assert await _get_migration_version_async(_FakeWriter(error=True)) == 0
