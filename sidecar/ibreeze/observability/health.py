from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.workers.spec import WorkerHealth
from ibreeze.workers.supervisor import WorkerSupervisor

_last_heartbeat: float = 0.0


def tick_heartbeat() -> None:
    global _last_heartbeat
    _last_heartbeat = time.monotonic()


@dataclass
class ProfileHealth:
    schema_epoch: int = 1
    migration_version: int = 0
    database_status: str = "unknown"


@dataclass
class QueueHealth:
    write_depth: int = 0
    runtime_ready: int = 0
    outbox_pending: int = 0


@dataclass
class HealthSnapshot:
    status: str = "unhealthy"
    observed_at: str = ""
    profile: ProfileHealth = field(default_factory=ProfileHealth)
    queues: QueueHealth = field(default_factory=QueueHealth)
    workers: tuple[WorkerHealth, ...] = field(default_factory=tuple)
    event_loop_lag_ms: int = 0
    disk_free_bytes: int = 0


def _get_loop_lag_ms() -> int:
    global _last_heartbeat
    if _last_heartbeat == 0:
        return 0
    return int((time.monotonic() - _last_heartbeat) * 1000)


def _get_disk_free(path: Path) -> int:
    db_dir = path if path.is_dir() else path.parent
    try:
        total, used, free = shutil.disk_usage(db_dir)
        return free
    except OSError:
        return 0


async def _get_migration_version_async(writer: aiosqlite.Connection | None) -> int:
    if writer is None:
        return 0
    try:
        cursor = await writer.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations WHERE status='completed'"
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


async def health_snapshot_async(
    writer: aiosqlite.Connection | None,
    write_queue: WriteQueue | None,
    workers: WorkerSupervisor | None,
    db_dir: Path,
) -> HealthSnapshot:
    profile_health = ProfileHealth(database_status="ready" if writer is not None else "unknown")
    profile_health.migration_version = await _get_migration_version_async(writer)
    queue_health = QueueHealth(write_depth=write_queue.depth if write_queue else 0)
    worker_health_list: list[WorkerHealth] = []
    if workers is not None:
        for wh in workers.health():
            worker_health_list.append(wh)

    any_failed = any(wh.state == "failed" for wh in worker_health_list)
    any_degraded = any(wh.state in ("starting", "degraded") for wh in worker_health_list)
    writer_failed = writer is None
    migration_missing = profile_health.migration_version == 0

    if writer_failed or migration_missing:
        status = "unhealthy"
    elif any_failed:
        status = "degraded"
    elif any_degraded:
        status = "degraded"
    else:
        status = "healthy"

    return HealthSnapshot(
        status=status,
        observed_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        profile=profile_health,
        queues=queue_health,
        workers=tuple(worker_health_list),
        event_loop_lag_ms=_get_loop_lag_ms(),
        disk_free_bytes=_get_disk_free(db_dir),
    )
