"""Coverage for ibreeze/orchestration/report_generator.py.

Closes gaps in the completion-gate path: the _id() helper, _check_completion_gates
for an empty table / all-passed gates / a blocking gate, and the blocked shortcut
inside generate_final_report.
"""

from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.orchestration.report_generator import (
    _check_completion_gates,
    _id,
    generate_final_report,
)


async def _create_completion_gates_table(db: aiosqlite.Connection) -> None:
    """The completion_gates table is not part of the shipped migrations, so tests
    that exercise the gate query must create it themselves."""
    await db.execute(
        """CREATE TABLE IF NOT EXISTS completion_gates (
               id TEXT PRIMARY KEY,
               company_id TEXT NOT NULL,
               task_id TEXT,
               gate_type TEXT NOT NULL,
               status TEXT NOT NULL,
               failed_at TEXT,
               error_message TEXT
           )"""
    )


async def _insert_gate(
    db: aiosqlite.Connection,
    *,
    company_id: str,
    task_id: str,
    gate_type: str,
    status: str,
    error_message: str | None = None,
) -> None:
    now = "2026-01-01T00:00:00.000000Z"
    await db.execute(
        """INSERT INTO completion_gates
           (id, company_id, task_id, gate_type, status, failed_at, error_message)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (str(uuid.uuid4()), company_id, task_id, gate_type, status, now if status != "passed" else None, error_message),
    )


class TestId:
    def test_returns_uuid_string(self):
        value = _id()
        uuid.UUID(value)  # should not raise


@pytest.mark.asyncio
class TestCheckCompletionGates:
    async def test_returns_none_when_table_has_no_rows(self, db):
        await _create_completion_gates_table(db)
        result = await _check_completion_gates(db, company_id="c1", task_id="t1")
        assert result is None

    async def test_returns_none_when_all_passed(self, db):
        await _create_completion_gates_table(db)
        await _insert_gate(db, company_id="c1", task_id="t1", gate_type="review", status="passed")
        result = await _check_completion_gates(db, company_id="c1", task_id="t1")
        assert result is None

    async def test_returns_blocking_when_gate_failed(self, db):
        await _create_completion_gates_table(db)
        await _insert_gate(
            db,
            company_id="c1",
            task_id="t1",
            gate_type="verification",
            status="failed",
            error_message="boom",
        )
        result = await _check_completion_gates(db, company_id="c1", task_id="t1")
        assert result is not None
        assert result["gate_blocked"] is True
        assert len(result["blocking_gates"]) == 1
        assert result["blocking_gates"][0]["status"] == "failed"
        assert result["blocking_gates"][0]["error_message"] == "boom"


@pytest.mark.asyncio
class TestGenerateFinalReportBlocked:
    async def test_returns_blocked_dict_when_gate_failed(self, db):
        await _create_completion_gates_table(db)
        await _insert_gate(db, company_id="c1", task_id="t1", gate_type="verification", status="failed")
        result = await generate_final_report(db, company_id="c1", task_id="t1")
        assert result["gate_blocked"] is True
        assert len(result["blocking_gates"]) == 1
