"""methods_task RPC 方法单元测试。"""

import asyncio
import os
import tempfile

import aiosqlite
import pytest
from acos.rpc.methods_task import TaskMethods
from acos.store.migrator import Migrator

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "migrations")


@pytest.fixture
async def task_methods() -> TaskMethods:
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        migrator = Migrator(db_path)
        await migrator.run_pending_migrations(MIGRATIONS_DIR)
        methods = TaskMethods(db_path)
        yield methods
    finally:
        os.unlink(db_path)


async def _create_task(methods: TaskMethods) -> dict:
    """Helper: 创建一个任务并返回结果。"""
    conn = await aiosqlite.connect(methods._db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute(
        """INSERT INTO tasks (task_id, company_id, title, description, priority, status, version)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("task-001", "comp-001", "Test Task", "desc", 5, "created", 1),
    )
    await conn.commit()
    await conn.close()
    return {"task_id": "task-001", "version": 1}


class TestTaskMethods:
    async def test_register(self, task_methods: TaskMethods) -> None:
        from acos.rpc.server import RPCServer
        server = RPCServer()
        task_methods.register_to(server)
        assert "task.start" in server._handlers
        assert "task.complete" in server._handlers
        assert "task.cancel" in server._handlers

    async def test_start_task(self, task_methods: TaskMethods) -> None:
        await _create_task(task_methods)
        result = await task_methods._task_start({
            "task_id": "task-001",
            "expected_version": 1,
        })
        assert result["task_id"] == "task-001"
        assert result["status"] == "running"
        assert result["version"] == 2

    async def test_start_task_missing_params(self, task_methods: TaskMethods) -> None:
        result = await task_methods._task_start({})
        assert "error" in result

    async def test_start_task_not_found(self, task_methods: TaskMethods) -> None:
        result = await task_methods._task_start({
            "task_id": "nonexistent",
            "expected_version": 1,
        })
        assert "error" in result

    async def test_start_task_version_conflict(self, task_methods: TaskMethods) -> None:
        await _create_task(task_methods)
        result = await task_methods._task_start({
            "task_id": "task-001",
            "expected_version": 99,
        })
        assert "error" in result

    async def test_complete_task(self, task_methods: TaskMethods) -> None:
        await _create_task(task_methods)
        await task_methods._task_start({"task_id": "task-001", "expected_version": 1})
        result = await task_methods._task_complete({
            "task_id": "task-001",
            "expected_version": 2,
        })
        assert result["status"] == "completed"

    async def test_complete_task_wrong_status(self, task_methods: TaskMethods) -> None:
        await _create_task(task_methods)
        result = await task_methods._task_complete({
            "task_id": "task-001",
            "expected_version": 1,
        })
        assert "error" in result

    async def test_cancel_task(self, task_methods: TaskMethods) -> None:
        await _create_task(task_methods)
        result = await task_methods._task_cancel({
            "task_id": "task-001",
            "expected_version": 1,
        })
        assert result["status"] == "cancelled"

    async def test_cancel_task_not_found(self, task_methods: TaskMethods) -> None:
        result = await task_methods._task_cancel({
            "task_id": "nonexistent",
            "expected_version": 1,
        })
        assert "error" in result

    async def test_complete_task_missing_params(self, task_methods: TaskMethods) -> None:
        result = await task_methods._task_complete({})
        assert "error" in result

    async def test_cancel_task_missing_params(self, task_methods: TaskMethods) -> None:
        result = await task_methods._task_cancel({})
        assert "error" in result

    async def test_complete_version_conflict(self, task_methods: TaskMethods) -> None:
        await _create_task(task_methods)
        await task_methods._task_start({"task_id": "task-001", "expected_version": 1})
        result = await task_methods._task_complete({
            "task_id": "task-001",
            "expected_version": 99,
        })
        assert "error" in result

    async def test_cancel_version_conflict(self, task_methods: TaskMethods) -> None:
        await _create_task(task_methods)
        result = await task_methods._task_cancel({
            "task_id": "task-001",
            "expected_version": 99,
        })
        assert "error" in result
