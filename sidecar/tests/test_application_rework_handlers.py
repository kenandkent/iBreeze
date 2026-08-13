from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest

from ibreeze.application.rework_handlers import AdvanceReworkAttemptHandler, RequestReworkHandler


@pytest.fixture
def uow():
    uow = Mock()
    uow.execute = AsyncMock()
    return uow


@pytest.fixture
def company_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def company_task_id() -> UUID:
    return uuid.uuid4()


def _make_session(side_effect_fn=None):
    """Create a mock session that delegates execute to side_effect_fn."""
    session = AsyncMock()
    if side_effect_fn:
        session.execute = AsyncMock(side_effect=side_effect_fn)
    return session


def _ok_cursor(rowcount: int = 1):
    c = AsyncMock()
    c.rowcount = rowcount
    return c


def _fetchone_cursor(row):
    c = AsyncMock()
    c.fetchone = AsyncMock(return_value=row)
    return c


class TestRequestReworkHandler:
    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_creates_rework_attempt_and_links_issues(self, mock_hash, uow, company_id, company_task_id):
        handler = RequestReworkHandler(uow)
        request = Mock(
            company_id=company_id,
            company_task_id=company_task_id,
            source_review_issue_ids=[uuid.uuid4(), uuid.uuid4()],
            expected_version=1,
        )

        call_count = 0

        async def exec_side_effect(sql, params=None):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return _fetchone_cursor({"1": 1})
            if call_count == 3:
                return _fetchone_cursor([1])
            return _ok_cursor()

        async def fake_execute(context, sha, command):
            result = await command(_make_session(exec_side_effect))
            return result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        result = await handler.handle("ctx", request)

        assert result["status"] == "planned"
        assert "attempt_id" in result
        assert result["attempt_no"] == 1

    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_raises_when_no_issues(self, mock_hash, uow, company_id, company_task_id):
        handler = RequestReworkHandler(uow)
        request = Mock(
            company_id=company_id,
            company_task_id=company_task_id,
            source_review_issue_ids=[],
            expected_version=1,
        )

        async def fake_execute(context, sha, command):
            session = _make_session()
            return await command(session)

        uow.execute = AsyncMock(side_effect=fake_execute)

        with pytest.raises(ValueError, match="REWORK_REQUIRES_AT_LEAST_ONE_ISSUE"):
            await handler.handle("ctx", request)

    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_raises_issue_not_open(self, mock_hash, uow, company_id, company_task_id):
        handler = RequestReworkHandler(uow)
        issue_id = uuid.uuid4()
        request = Mock(
            company_id=company_id,
            company_task_id=company_task_id,
            source_review_issue_ids=[issue_id],
            expected_version=1,
        )

        async def exec_side_effect(sql, params=None):
            return _fetchone_cursor(None)

        async def fake_execute(context, sha, command):
            session = _make_session(exec_side_effect)
            return await command(session)

        uow.execute = AsyncMock(side_effect=fake_execute)

        with pytest.raises(ValueError, match=f"ISSUE_NOT_OPEN:{issue_id}"):
            await handler.handle("ctx", request)

    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_raises_optimistic_lock_conflict(self, mock_hash, uow, company_id, company_task_id):
        handler = RequestReworkHandler(uow)
        request = Mock(
            company_id=company_id,
            company_task_id=company_task_id,
            source_review_issue_ids=[uuid.uuid4()],
            expected_version=1,
        )

        call_count = 0

        async def exec_side_effect(sql, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _fetchone_cursor({"1": 1})
            if call_count == 2:
                return _fetchone_cursor([1])
            c = AsyncMock()
            c.rowcount = 0
            return c

        async def fake_execute(context, sha, command):
            session = _make_session(exec_side_effect)
            return await command(session)

        uow.execute = AsyncMock(side_effect=fake_execute)

        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await handler.handle("ctx", request)

    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_increments_attempt_no(self, mock_hash, uow, company_id, company_task_id):
        handler = RequestReworkHandler(uow)
        request = Mock(
            company_id=company_id,
            company_task_id=company_task_id,
            source_review_issue_ids=[uuid.uuid4()],
            expected_version=1,
        )

        call_count = 0

        async def exec_side_effect(sql, params=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _fetchone_cursor({"1": 1})
            if call_count == 2:
                return _fetchone_cursor([5])
            return _ok_cursor()

        async def fake_execute(context, sha, command):
            result = await command(_make_session(exec_side_effect))
            return result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        result = await handler.handle("ctx", request)
        assert result["attempt_no"] == 5

    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_department_task_path(self, mock_hash, uow, company_id, company_task_id):
        request = Mock(
            company_id=company_id,
            company_task_id=company_task_id,
            source_review_issue_ids=[uuid.uuid4()],
            expected_version=1,
            department_task_id=uuid.uuid4(),
        )
        handler = RequestReworkHandler(uow)

        async def exec_side_effect(sql, params=None):
            if "SELECT 1 FROM review_issues" in sql:
                return _fetchone_cursor({"1": 1})
            if "COALESCE(MAX(attempt_no)" in sql:
                return _fetchone_cursor([1])
            return _ok_cursor()

        async def fake_execute(context, sha, command):
            result = await command(_make_session(exec_side_effect))
            return result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        result = await handler.handle("ctx", request)
        assert result["status"] == "planned"

    async def test_no_for_update_in_production_code(self):
        import inspect

        source = inspect.getsource(RequestReworkHandler.handle)
        assert "FOR UPDATE" not in source.upper()


class TestAdvanceReworkAttemptHandler:
    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_transitions_planned_to_running(self, mock_hash, uow, company_id):
        handler = AdvanceReworkAttemptHandler(uow)
        attempt_id = uuid.uuid4()

        async def fake_execute(context, sha, command):
            session = _make_session(
                lambda sql, p=None: _fetchone_cursor(
                    {
                        "id": str(attempt_id),
                        "company_task_id": str(uuid.uuid4()),
                        "department_task_id": None,
                        "attempt_no": 1,
                        "status": "planned",
                        "version": 1,
                    }
                )
            )
            result = await command(session)
            return result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        result = await handler.handle("ctx", attempt_id, company_id, "running")
        assert result["status"] == "running"

    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_transitions_running_to_completed(self, mock_hash, uow, company_id):
        handler = AdvanceReworkAttemptHandler(uow)
        attempt_id = uuid.uuid4()

        async def fake_execute(context, sha, command):
            session = _make_session(
                lambda sql, p=None: _fetchone_cursor(
                    {
                        "id": str(attempt_id),
                        "company_task_id": str(uuid.uuid4()),
                        "department_task_id": None,
                        "attempt_no": 1,
                        "status": "running",
                        "version": 1,
                    }
                )
            )
            result = await command(session)
            return result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        result = await handler.handle("ctx", attempt_id, company_id, "completed")
        assert result["status"] == "completed"

    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_transitions_running_to_failed(self, mock_hash, uow, company_id):
        handler = AdvanceReworkAttemptHandler(uow)
        attempt_id = uuid.uuid4()

        async def fake_execute(context, sha, command):
            session = _make_session(
                lambda sql, p=None: _fetchone_cursor(
                    {
                        "id": str(attempt_id),
                        "company_task_id": str(uuid.uuid4()),
                        "department_task_id": None,
                        "attempt_no": 1,
                        "status": "running",
                        "version": 1,
                    }
                )
            )
            result = await command(session)
            return result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        result = await handler.handle("ctx", attempt_id, company_id, "failed")
        assert result["status"] == "failed"

    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_transitions_planned_to_cancelled(self, mock_hash, uow, company_id):
        handler = AdvanceReworkAttemptHandler(uow)
        attempt_id = uuid.uuid4()

        async def fake_execute(context, sha, command):
            session = _make_session(
                lambda sql, p=None: _fetchone_cursor(
                    {
                        "id": str(attempt_id),
                        "company_task_id": str(uuid.uuid4()),
                        "department_task_id": None,
                        "attempt_no": 1,
                        "status": "planned",
                        "version": 1,
                    }
                )
            )
            result = await command(session)
            return result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        result = await handler.handle("ctx", attempt_id, company_id, "cancelled")
        assert result["status"] == "cancelled"

    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_uses_optimistic_lock_not_for_update(self, mock_hash, uow, company_id):
        handler = AdvanceReworkAttemptHandler(uow)
        attempt_id = uuid.uuid4()
        executed_sqls = []

        async def record_exec(sql, params=None):
            executed_sqls.append(sql)
            return _fetchone_cursor(
                {
                    "id": str(attempt_id),
                    "company_task_id": str(uuid.uuid4()),
                    "department_task_id": None,
                    "attempt_no": 1,
                    "status": "planned",
                    "version": 1,
                }
            )

        async def fake_execute(context, sha, command):
            session = _make_session(record_exec)
            await command(session)
            return None

        uow.execute = AsyncMock(side_effect=fake_execute)

        await handler.handle("ctx", attempt_id, company_id, "running")

        assert "FOR UPDATE" not in " ".join(executed_sqls).upper()
        assert any("version=?" in sql for sql in executed_sqls)

    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_raises_resource_not_found(self, mock_hash, uow, company_id):
        handler = AdvanceReworkAttemptHandler(uow)
        attempt_id = uuid.uuid4()

        async def fake_execute(context, sha, command):
            session = _make_session(lambda sql, p=None: _fetchone_cursor(None))
            return await command(session)

        uow.execute = AsyncMock(side_effect=fake_execute)

        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await handler.handle("ctx", attempt_id, company_id, "running")

    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_raises_state_transition_invalid(self, mock_hash, uow, company_id):
        handler = AdvanceReworkAttemptHandler(uow)
        attempt_id = uuid.uuid4()

        async def fake_execute(context, sha, command):
            session = _make_session(
                lambda sql, p=None: _fetchone_cursor(
                    {
                        "id": str(attempt_id),
                        "company_task_id": str(uuid.uuid4()),
                        "department_task_id": None,
                        "attempt_no": 1,
                        "status": "completed",
                        "version": 1,
                    }
                )
            )
            return await command(session)

        uow.execute = AsyncMock(side_effect=fake_execute)

        with pytest.raises(ValueError, match="STATE_TRANSITION_INVALID"):
            await handler.handle("ctx", attempt_id, company_id, "running")

    @patch("ibreeze.application.rework_handlers._hash", return_value="fakehash")
    async def test_update_sql_has_version_check(self, mock_hash, uow, company_id):
        """AdvanceReworkAttemptHandler uses version= in UPDATE WHERE but does NOT
        check cursor.rowcount (production gap vs ReviewRepository)."""
        handler = AdvanceReworkAttemptHandler(uow)
        attempt_id = uuid.uuid4()
        executed_sqls = []

        async def record_exec(sql, params=None):
            executed_sqls.append(sql)
            return _fetchone_cursor(
                {
                    "id": str(attempt_id),
                    "company_task_id": str(uuid.uuid4()),
                    "department_task_id": None,
                    "attempt_no": 1,
                    "status": "running",
                    "version": 1,
                }
            )

        async def fake_execute(context, sha, command):
            session = _make_session(record_exec)
            result = await command(session)
            return result.response

        uow.execute = AsyncMock(side_effect=fake_execute)

        result = await handler.handle("ctx", attempt_id, company_id, "completed")
        assert result["status"] == "completed"
        update_sqls = [s for s in executed_sqls if s.strip().upper().startswith("UPDATE")]
        assert any("version=?" in s for s in update_sqls)

    async def test_no_for_update_in_production_code(self):
        import inspect

        source = inspect.getsource(AdvanceReworkAttemptHandler.handle)
        assert "FOR UPDATE" not in source.upper()
