from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from ibreeze.persistence.write_queue import WriteQueue

logger = logging.getLogger(__name__)


@dataclass
class WorkerHealth:
    name: str
    state: str = "stopped"
    heartbeat_at: str = ""
    last_success_at: str | None = None
    last_error_code: str | None = None
    queue_lag: int = 0
    restart_count: int = 0


class BaseWorker:
    name: str = "base"

    def __init__(self) -> None:
        self._state = "stopped"
        self._heartbeat_at = ""
        self._last_success_at: str | None = None
        self._last_error_code: str | None = None
        self._restart_count = 0

    async def work(self) -> None:
        raise NotImplementedError

    def health(self) -> WorkerHealth:
        return WorkerHealth(
            name=self.name,
            state=self._state,
            heartbeat_at=self._heartbeat_at,
            last_success_at=self._last_success_at,
            last_error_code=self._last_error_code,
            restart_count=self._restart_count,
        )

    def update_heartbeat(self) -> None:
        self._heartbeat_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def mark_success(self) -> None:
        self._last_success_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def mark_error(self, code: str) -> None:
        self._last_error_code = code


class KnowledgeWorker(BaseWorker):
    name = "KnowledgeWorker"

    def __init__(self, write_queue: WriteQueue | None = None) -> None:
        super().__init__()
        self._write_queue = write_queue

    async def work(self) -> None:
        wq = self._write_queue
        if wq is None:
            return

        async def _index_pending(conn: Any) -> int:
            now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            cursor = await conn.execute(
                """SELECT id, company_id, content, content_type
                   FROM knowledge_queue
                   WHERE status='pending' AND next_attempt_at <= ?
                   ORDER BY created_at ASC LIMIT 20""",
                (now,),
            )
            rows = await cursor.fetchall()
            if not rows:
                return 0
            for row in rows:
                content_hash = str(hash(row["content"])) if row["content"] else ""
                await conn.execute(
                    """UPDATE knowledge_queue
                       SET status='indexed', indexed_at=?, content_hash=?
                       WHERE id=?""",
                    (now, content_hash, row["id"]),
                )
            return len(rows)

        try:
            deadline = datetime.now(UTC) + timedelta(seconds=25)
            count = await wq.submit("knowledge.index_pending", UUID(int=0), deadline, _index_pending)
            if count:
                logger.info("KnowledgeWorker indexed %d items", count)
        except Exception:
            logger.exception("KnowledgeWorker failed")


class ReconciliationWorker(BaseWorker):
    name = "ReconciliationWorker"

    def __init__(self, write_queue: WriteQueue | None = None) -> None:
        super().__init__()
        self._write_queue = write_queue

    async def work(self) -> None:
        wq = self._write_queue
        if wq is None:
            return

        async def _reconcile(conn: Any) -> int:
            issues = 0
            cursor = await conn.execute("SELECT COUNT(*) AS cnt FROM outbox WHERE status='pending'")
            row = await cursor.fetchone()
            outbox_pending = row["cnt"] if row else 0
            if outbox_pending > 1000:
                logger.warning("Outbox pending count %d exceeds threshold", outbox_pending)
                issues += 1
            cursor = await conn.execute("SELECT COUNT(*) AS cnt FROM runtime_leases")
            row = await cursor.fetchone()
            lease_count = row["cnt"] if row else 0
            if lease_count > 200:
                logger.warning("Runtime lease count %d exceeds threshold", lease_count)
                issues += 1
            return issues

        try:
            deadline = datetime.now(UTC) + timedelta(seconds=55)
            await wq.submit("reconciliation.verify", UUID(int=0), deadline, _reconcile)
        except Exception:
            logger.exception("ReconciliationWorker failed")


class BackupWorker(BaseWorker):
    name = "BackupWorker"

    def __init__(self, write_queue: WriteQueue | None = None) -> None:
        super().__init__()
        self._write_queue = write_queue

    async def work(self) -> None:
        wq = self._write_queue
        if wq is None:
            return

        async def _rotate_backups(conn: Any) -> int:
            now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            cutoff = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
            await conn.execute(
                """UPDATE backup_manifest
                   SET status='expired'
                   WHERE status='active' AND created_at < ?""",
                (cutoff,),
            )
            cursor = await conn.execute(
                "SELECT COUNT(*) AS cnt FROM backup_manifest WHERE status='active'"
            )
            row = await cursor.fetchone()
            active_count = row["cnt"] if row else 0
            if active_count < 3:
                await conn.execute(
                    "INSERT INTO backup_manifest (status, created_at) VALUES ('active', ?)",
                    (now,),
                )
                return 1
            return 0

        try:
            deadline = datetime.now(UTC) + timedelta(seconds=300)
            await wq.submit("backup.rotate", UUID(int=0), deadline, _rotate_backups)
        except Exception:
            logger.exception("BackupWorker failed")


class EventCompactionWorker(BaseWorker):
    name = "EventCompactionWorker"

    def __init__(self, write_queue: WriteQueue | None = None) -> None:
        super().__init__()
        self._write_queue = write_queue

    async def work(self) -> None:
        wq = self._write_queue
        if wq is None:
            return

        async def _compact(conn: Any) -> int:
            cutoff = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            cursor = await conn.execute(
                """DELETE FROM outbox
                   WHERE status='delivered' AND delivered_at < ?""",
                (cutoff,),
            )
            deleted_outbox = cursor.rowcount
            cursor = await conn.execute(
                "SELECT COUNT(*) AS cnt FROM domain_events WHERE occurred_at < ?",
                (cutoff,),
            )
            row = await cursor.fetchone()
            old_events = row["cnt"] if row else 0
            if old_events > 10000:
                cursor = await conn.execute(
                    """DELETE FROM domain_events
                       WHERE occurred_at < ? AND id NOT IN (
                           SELECT domain_event_id FROM outbox WHERE domain_event_id IS NOT NULL
                       )""",
                    (cutoff,),
                )
                deleted_events = cursor.rowcount
            else:
                deleted_events = 0
            return deleted_outbox + deleted_events

        try:
            deadline = datetime.now(UTC) + timedelta(seconds=300)
            await wq.submit("event.compact", UUID(int=0), deadline, _compact)
        except Exception:
            logger.exception("EventCompactionWorker failed")

