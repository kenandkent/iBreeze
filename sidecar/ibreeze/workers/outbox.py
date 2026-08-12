from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from ibreeze.events.outbox import EVENT_COMMAND_MAP, EVENT_TO_STATE_TRIGGER, OutboxWriter
from ibreeze.persistence.write_queue import WriteQueue
from ibreeze.workers.spec import BaseWorker

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50
_PROJECTION_ONLY_TOPICS = frozenset({
    "run.queued",
    "run.started",
    "run.failed",
    "run.cancelled",
    "review.assigned",
    "company_task.status_changed",
})


class OutboxWorker(BaseWorker):
    name = "OutboxWorker"

    def __init__(self, write_queue: WriteQueue | None = None, command_bus: Any | None = None) -> None:
        super().__init__()
        self._write_queue = write_queue
        self._command_bus = command_bus
        # Kept as the worker's writer dependency for observability and
        # dependency injection.  Actual inserts are performed by UnitOfWork;
        # this worker only claims and dispatches already committed rows.
        self._outbox = OutboxWriter()

    async def work(self) -> None:
        wq = self._write_queue
        if wq is None:
            await asyncio.sleep(1)
            return

        async def _deliver(conn: Any) -> int:
            cursor = await conn.execute(
                """SELECT id, topic, payload_json, domain_event_id, attempts
                   FROM outbox_events
                   WHERE status = 'pending' AND next_attempt_at <= ?
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), _BATCH_SIZE),
            )
            rows = await cursor.fetchall()
            if not rows:
                return 0
            processed = 0
            for row in rows:
                topic = row.get("topic") if isinstance(row, dict) else row["topic"]
                if not isinstance(topic, str):
                    await conn.execute(
                        """UPDATE outbox_events
                           SET status='failed', last_error=?, attempts=attempts+1
                           WHERE id=? AND status='pending'""",
                        ("MALFORMED_OUTBOX_ROW", row["id"]),
                    )
                    continue
                command_name = EVENT_COMMAND_MAP.get(topic)
                if command_name is None:
                    if topic in _PROJECTION_ONLY_TOPICS:
                        await conn.execute(
                            """UPDATE outbox_events
                               SET status='delivered', delivered_at=?, attempts=attempts+1
                               WHERE id=? AND status='pending'""",
                            (datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), row["id"]),
                        )
                        processed += 1
                        continue
                    await conn.execute(
                        """UPDATE outbox_events
                           SET status='failed', last_error=?, attempts=attempts+1
                           WHERE id=?""",
                        (f"UNKNOWN_OUTBOX_TOPIC:{topic}", row["id"]),
                    )
                    continue
                try:
                    payload = json.loads(row["payload_json"])
                except (TypeError, ValueError, json.JSONDecodeError):
                    await conn.execute(
                        """UPDATE outbox_events
                           SET status='failed', last_error=?, attempts=attempts+1
                           WHERE id=? AND status='pending'""",
                        ("MALFORMED_OUTBOX_PAYLOAD", row["id"]),
                    )
                    continue
                trigger_states = EVENT_TO_STATE_TRIGGER.get(topic)
                if trigger_states and payload.get("to_state") not in trigger_states:
                    await conn.execute(
                        """UPDATE outbox_events
                           SET status='delivered', delivered_at=?, attempts=attempts+1
                           WHERE id=? AND status='pending'""",
                        (datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), row["id"]),
                    )
                    processed += 1
                    continue
                # The internal command bus is injected by lifecycle.  A missing
                # bus is a hard failure: leave the event pending for retry.
                if self._command_bus is None:
                    raise RuntimeError("INTERNAL_COMMAND_BUS_UNAVAILABLE")
                await self._command_bus.dispatch(
                    command_name,
                    payload,
                    connection=conn,
                )
                await conn.execute(
                    """UPDATE outbox_events
                       SET status = 'delivered', delivered_at = ?, attempts = attempts + 1
                       WHERE id = ? AND status='pending'""",
                    (datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), row["id"]),
                )
                processed += 1
            return processed

        try:
            deadline = datetime.now(UTC) + timedelta(seconds=30)
            delivered = await wq.submit("outbox.deliver", UUID(int=0), deadline, _deliver)
            if delivered:
                logger.info("OutboxWorker delivered %d events", delivered)
        except Exception:
            logger.exception("OutboxWorker deliver failed")
