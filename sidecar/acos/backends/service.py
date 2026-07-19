"""Backend 服务：CRUD、调度、Lease 管理。"""

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


class BackendScheduler:
    """Backend 调度器：选择 Backend、入队、获取下一个。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def select_backend(
        self,
        company_id: str,
        required_capabilities: Optional[list[str]] = None,
    ) -> Optional[Backend]:
        """选择可用的 Backend。"""
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
    """Backend Lease 管理：bind、heartbeat、release。"""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    async def bind(
        self,
        backend_id: str,
        company_id: str,
        run_id: Optional[str] = None,
        session_turn_id: Optional[str] = None,
        worker_pid: Optional[int] = None,
    ) -> BackendLease:
        lease = BackendLease(
            lease_id=str(uuid.uuid4()),
            backend_id=backend_id,
            company_id=company_id,
            run_id=run_id,
            session_turn_id=session_turn_id,
            worker_pid=worker_pid,
        )
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM backend_leases WHERE backend_id = ? AND status = 'active'",
                (backend_id,),
            )
            row = await cursor.fetchone()
            db.row_factory = aiosqlite.Row
            cursor2 = await db.execute(
                "SELECT concurrency_limit FROM backends WHERE backend_id = ?",
                (backend_id,),
            )
            backend_row = await cursor2.fetchone()

            if backend_row and row[0] >= backend_row["concurrency_limit"]:
                raise create_error(BACKEND_CAPACITY_FULL, f"Backend {backend_id} 容量已满")

            await db.execute(
                """INSERT INTO backend_leases
                   (lease_id, backend_id, company_id, run_id, session_turn_id,
                    worker_pid, status, heartbeat_at, version, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'active', ?, 1, ?, ?)""",
                (
                    lease.lease_id,
                    lease.backend_id,
                    lease.company_id,
                    lease.run_id,
                    lease.session_turn_id,
                    lease.worker_pid,
                    _now(),
                    _now(),
                    _now(),
                ),
            )
            await db.commit()
        return lease

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
