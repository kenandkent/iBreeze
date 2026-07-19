"""Backend 服务：CRUD、调度（全局进程上限）、Lease 管理（process_start_token）。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from acos.backends.models import Backend, BackendLease, BackendQueueEntry
from acos.rpc.errors import (
    BACKEND_CAPACITY_FULL,
    BACKEND_UNAVAILABLE,
    create_error,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_backend(row: aiosqlite.Row) -> Backend:
    return Backend(
        backend_id=row["backend_id"],
        company_id=row["company_id"],
        name=row["name"],
        backend_type=row["backend_type"],
        status=row["status"],
        health_status=row["health_status"],
        capabilities=json.loads(row["capabilities"]),
        workspace_types=json.loads(row["workspace_types"]),
        workspace_root=row["workspace_root"],
        concurrency_limit=row["concurrency_limit"],
        last_health_probe_at=row["last_health_probe_at"] if "last_health_probe_at" in row.keys() else None,
        version=row["version"],
    )


def _row_to_lease(row: aiosqlite.Row) -> BackendLease:
    return BackendLease(
        lease_id=row["lease_id"],
        backend_id=row["backend_id"],
        company_id=row["company_id"],
        run_id=row["run_id"],
        session_turn_id=row["session_turn_id"],
        worker_pid=row["worker_pid"],
        status=row["status"],
        version=row["version"],
    )


def _row_to_queue_entry(row: aiosqlite.Row) -> BackendQueueEntry:
    return BackendQueueEntry(
        entry_id=row["entry_id"],
        backend_id=row["backend_id"],
        company_id=row["company_id"],
        run_id=row["run_id"],
        session_turn_id=row["session_turn_id"],
        wait_reason=row["wait_reason"],
        status=row["status"],
    )


class BackendService:
    """Backend CRUD 服务。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def create(self, backend: Backend) -> Backend:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO backends
                   (backend_id, company_id, name, backend_type, status,
                    health_status, capabilities, workspace_types, workspace_root,
                    concurrency_limit, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (
                    backend.backend_id,
                    backend.company_id,
                    backend.name,
                    backend.backend_type,
                    backend.status,
                    backend.health_status,
                    json.dumps(backend.capabilities, ensure_ascii=False),
                    json.dumps(backend.workspace_types, ensure_ascii=False),
                    backend.workspace_root,
                    backend.concurrency_limit,
                    now,
                    now,
                ),
            )
            await db.commit()
        return backend

    async def get(self, backend_id: str) -> Optional[Backend]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM backends WHERE backend_id = ?", (backend_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return _row_to_backend(row)

    async def list_by_company(self, company_id: str) -> list[Backend]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM backends WHERE company_id = ? ORDER BY name",
                (company_id,),
            )
            rows = await cursor.fetchall()
            return [_row_to_backend(r) for r in rows]

    async def update_status(
        self, backend_id: str, status: str, health_status: Optional[str] = None
    ) -> Optional[Backend]:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if health_status is not None:
                cursor = await db.execute(
                    """UPDATE backends
                       SET status = ?, health_status = ?, version = version + 1, updated_at = ?
                       WHERE backend_id = ?""",
                    (status, health_status, now, backend_id),
                )
            else:
                cursor = await db.execute(
                    """UPDATE backends
                       SET status = ?, version = version + 1, updated_at = ?
                       WHERE backend_id = ?""",
                    (status, now, backend_id),
                )
            if cursor.rowcount == 0:
                return None
            await db.commit()
            return await self.get(backend_id)

    async def probe_health(self, backend_id: str) -> dict:
        """健康探针：写入 last_health_probe_at，返回最新健康状态。

        设计 §10.3：Backend 每 30s 发送 probe，超 90s 未更新标记 stale。
        """
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """UPDATE backends
                   SET last_health_probe_at = ?, version = version + 1, updated_at = ?
                   WHERE backend_id = ?""",
                (now, now, backend_id),
            )
            await db.commit()
            cursor = await db.execute(
                "SELECT backend_id, health_status, last_health_probe_at FROM backends WHERE backend_id = ?",
                (backend_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return {"backend_id": backend_id, "health_status": "unknown", "stale": True}
        return {
            "backend_id": row["backend_id"],
            "health_status": row["health_status"],
            "last_probe": row["last_health_probe_at"],
            "stale": False,
        }

    async def get_stale_backends(self, stale_seconds: int = 90) -> list[str]:
        """返回超过 stale_seconds 未 probe 的 backend_id 列表。"""
        now = datetime.now(timezone.utc)
        stale_threshold = now.timestamp() - stale_seconds
        stale_iso = datetime.fromtimestamp(stale_threshold, tz=timezone.utc).isoformat()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """SELECT backend_id FROM backends
                   WHERE status = 'enabled'
                     AND (last_health_probe_at IS NULL OR last_health_probe_at < ?)""",
                (stale_iso,),
            )
            return [row[0] for row in await cursor.fetchall()]


class BackendScheduler:
    """Backend 调度器：选择 Backend、入队、获取下一个（含全局进程上限）。"""

    def __init__(self, db_path: str, global_process_limit: int = 0) -> None:
        self._db_path = db_path
        self._global_process_limit = global_process_limit

    async def _count_global_active_leases(self) -> int:
        """查询所有 backend 的 active lease 总数。"""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM backend_leases WHERE status = 'active'",
            )
            row = await cursor.fetchone()
            return row[0]

    async def select_backend(
        self,
        company_id: str,
        required_capabilities: Optional[list[str]] = None,
    ) -> Optional[Backend]:
        """选择可用的 Backend（含全局进程上限检查）。"""
        if self._global_process_limit > 0:
            global_count = await self._count_global_active_leases()
            if global_count >= self._global_process_limit:
                return None

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM backends
                   WHERE company_id = ? AND status = 'enabled' AND health_status != 'unhealthy'
                   ORDER BY concurrency_limit DESC""",
                (company_id,),
            )
            rows = await cursor.fetchall()

        backends = [_row_to_backend(r) for r in rows]
        if required_capabilities:
            backends = [
                b for b in backends
                if set(required_capabilities).issubset(set(b.capabilities))
            ]

        for backend in backends:
            lease_count = await self._count_active_leases(backend.backend_id)
            if lease_count < backend.concurrency_limit:
                return backend
        return None

    async def _count_active_leases(self, backend_id: str) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM backend_leases WHERE backend_id = ? AND status = 'active'",
                (backend_id,),
            )
            row = await cursor.fetchone()
            return row[0]

    async def enqueue(
        self,
        backend_id: str,
        company_id: str,
        run_id: Optional[str] = None,
        session_turn_id: Optional[str] = None,
        wait_reason: Optional[str] = None,
    ) -> BackendQueueEntry:
        entry = BackendQueueEntry(
            entry_id=str(uuid.uuid4()),
            backend_id=backend_id,
            company_id=company_id,
            run_id=run_id,
            session_turn_id=session_turn_id,
            wait_reason=wait_reason,
        )
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO backend_queue_entries
                   (entry_id, backend_id, company_id, run_id, session_turn_id,
                    wait_reason, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'waiting', ?)""",
                (
                    entry.entry_id,
                    entry.backend_id,
                    entry.company_id,
                    entry.run_id,
                    entry.session_turn_id,
                    entry.wait_reason,
                    _now(),
                ),
            )
            await db.commit()
        return entry

    async def acquire_next(self, backend_id: str) -> Optional[BackendQueueEntry]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM backend_queue_entries
                   WHERE backend_id = ? AND status = 'waiting'
                   ORDER BY created_at ASC LIMIT 1""",
                (backend_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            await db.execute(
                """UPDATE backend_queue_entries
                   SET status = 'processing' WHERE entry_id = ?""",
                (row["entry_id"],),
            )
            await db.commit()
            return _row_to_queue_entry(row)


class BackendLeaseManager:
    """Backend Lease 管理：bind（含 process_start_token）、heartbeat、release。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def bind(
        self,
        backend_id: str,
        company_id: str,
        run_id: Optional[str] = None,
        session_turn_id: Optional[str] = None,
        worker_pid: Optional[int] = None,
        process_start_token: Optional[str] = None,
    ) -> BackendLease:
        """原子获取 lease（修复 TOCTOU 竞态）+ 写入 process_start_token。"""
        lease_id = str(uuid.uuid4())
        now = _now()
        if not process_start_token:
            process_start_token = uuid.uuid4().hex
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """INSERT INTO backend_leases
                   (lease_id, backend_id, company_id, run_id, session_turn_id,
                    worker_pid, process_start_token, status, heartbeat_at,
                    version, created_at, updated_at)
                   SELECT ?, ?, ?, ?, ?, ?, ?, 'active', ?, 1, ?, ?
                   FROM backends
                   WHERE backend_id = ?
                     AND (SELECT COUNT(*) FROM backend_leases
                          WHERE backend_id = ? AND status = 'active') < concurrency_limit""",
                (lease_id, backend_id, company_id, run_id, session_turn_id,
                 worker_pid, process_start_token, now, now, now, backend_id, backend_id),
            )
            if cursor.rowcount == 0:
                raise create_error(
                    BACKEND_CAPACITY_FULL,
                    f"Backend {backend_id} 容量已满或不存在"
                )
            await db.commit()
        return BackendLease(
            lease_id=lease_id,
            backend_id=backend_id,
            company_id=company_id,
            run_id=run_id,
            session_turn_id=session_turn_id,
            worker_pid=worker_pid,
        )

    async def verify_process_token(self, lease_id: str, process_start_token: str) -> bool:
        """CAS 验证 process_start_token（防止 PID 复用攻击）。"""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """SELECT 1 FROM backend_leases
                   WHERE lease_id = ? AND process_start_token = ? AND status = 'active'""",
                (lease_id, process_start_token),
            )
            return (await cursor.fetchone()) is not None

    async def heartbeat(self, lease_id: str) -> bool:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """UPDATE backend_leases
                   SET heartbeat_at = ?, version = version + 1, updated_at = ?
                   WHERE lease_id = ? AND status = 'active'""",
                (now, now, lease_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def release(self, lease_id: str) -> bool:
        now = _now()
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """UPDATE backend_leases
                   SET status = 'released', version = version + 1, updated_at = ?
                   WHERE lease_id = ? AND status = 'active'""",
                (now, lease_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def list_active(self, backend_id: str) -> list[BackendLease]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM backend_leases
                   WHERE backend_id = ? AND status = 'active'
                   ORDER BY created_at""",
                (backend_id,),
            )
            rows = await cursor.fetchall()
            return [_row_to_lease(r) for r in rows]
