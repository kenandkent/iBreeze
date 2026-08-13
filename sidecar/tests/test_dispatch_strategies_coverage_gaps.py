"""Gap coverage for dispatch_strategies.py edge branches.

test_employee_task_dependencies.py and test_deliverable_review_dispatch.py
cover the happy dispatch/advance paths.  The remaining uncovered branches are:
corrupt frozen capability-tag specs (_parse_frozen_capability_tags), malformed
review-spec JSON and empty/inactive/contributor reviewers in
maybe_dispatch_deliverable_reviews, missing dispatch specs and zero-row
transition guards in advance_employee_task_graph, and the profile-version /
capability-tags / catalog_release failure paths of _lazy_availability_checks.
"""

from __future__ import annotations

import json
import uuid

import pytest

from ibreeze.orchestration.dispatch_strategies import (
    _lazy_availability_checks,
    _parse_frozen_capability_tags,
    advance_employee_task_graph,
    maybe_dispatch_deliverable_reviews,
)
from tests.test_deliverable_review_dispatch import review_env as _review_env  # noqa: F401
from tests.test_employee_task_dependencies import (
    _accept,
    _confirm,
    _register_plan,
    _rows,
)
from tests.test_employee_task_dependencies import chain_env as _chain_env  # noqa: F401


@pytest.fixture
def chain_env(request):
    """Re-export the shared sequential-refinement chain fixture."""
    return request.getfixturevalue("_chain_env")


@pytest.fixture
def review_env(request):
    """Re-export the shared review-spec fixture."""
    return request.getfixturevalue("_review_env")


def _id() -> str:
    return str(uuid.uuid4())


class TestParseFrozenCapabilityTags:
    def test_none_returns_empty(self) -> None:
        assert _parse_frozen_capability_tags(None) == ()

    def test_invalid_json_returns_none(self) -> None:
        assert _parse_frozen_capability_tags("{not-json") is None

    def test_non_string_item_returns_none(self) -> None:
        assert _parse_frozen_capability_tags('["ok", 123]') is None

    def test_whitespace_item_returns_none(self) -> None:
        assert _parse_frozen_capability_tags('["ok", "  bad  "]') is None

    def test_valid_items_sorted(self) -> None:
        assert _parse_frozen_capability_tags('["b", "a", "b"]') == ("a", "b")


class _RowcountZeroCursor:
    def __init__(self) -> None:
        self.rowcount = 0

    async def fetchone(self):
        return None

    async def fetchall(self):
        return []


class _RowcountZeroDB:
    """Delegates to the real db but zeroes out a specific transition UPDATE."""

    def __init__(self, inner, *, failed: bool = False, assigned: bool = False) -> None:
        self._inner = inner
        self._failed = failed
        self._assigned = assigned
        self.in_transaction = True

    async def execute(self, sql, params=()):
        if self._failed and "SET status='failed'" in sql:
            return _RowcountZeroCursor()
        if self._assigned and "SET status='assigned'" in sql:
            return _RowcountZeroCursor()
        return await self._inner.execute(sql, params)

    async def commit(self) -> None:
        return await self._inner.commit()

    async def rollback(self) -> None:
        return await self._inner.rollback()


class _SpecCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows


class _SpecInterceptDB:
    """Fake reviewer-spec row (bypasses the json_valid column constraint)."""

    def __init__(self, inner, spec: dict[str, object]) -> None:
        self._inner = inner
        self._spec = spec
        self.in_transaction = True

    async def execute(self, sql, params=()):
        if "FROM deliverable_review_specs" in sql:
            return _SpecCursor([self._spec])
        return await self._inner.execute(sql, params)

    async def commit(self) -> None:
        return await self._inner.commit()

    async def rollback(self) -> None:
        return await self._inner.rollback()


class TestMaybeDispatchMalformedSpec:
    @pytest.mark.asyncio
    async def test_invalid_reviewer_json_returns_empty(self, db) -> None:
        spec = {
            "id": _id(),
            "review_strategy": "independent_drafts",
            "reviewer_employee_ids_json": "not-json",
            "contributor_employee_ids_json": "[]",
        }
        created = await maybe_dispatch_deliverable_reviews(
            _SpecInterceptDB(db, spec),
            company_id=str(uuid.uuid4()),
            company_task_id=str(uuid.uuid4()),
            artifact_id=str(uuid.uuid4()),
            artifact_type="document",
            is_current=True,
        )
        assert created == []

    @pytest.mark.asyncio
    async def test_empty_reviewers_returns_empty(self, db) -> None:
        spec = {
            "id": _id(),
            "review_strategy": "independent_drafts",
            "reviewer_employee_ids_json": "[]",
            "contributor_employee_ids_json": "[]",
        }
        created = await maybe_dispatch_deliverable_reviews(
            _SpecInterceptDB(db, spec),
            company_id=str(uuid.uuid4()),
            company_task_id=str(uuid.uuid4()),
            artifact_id=str(uuid.uuid4()),
            artifact_type="document",
            is_current=True,
        )
        assert created == []

    @pytest.mark.asyncio
    async def test_non_list_reviewers_returns_empty(self, db) -> None:
        spec = {
            "id": _id(),
            "review_strategy": "independent_drafts",
            "reviewer_employee_ids_json": "{}",
            "contributor_employee_ids_json": "[]",
        }
        created = await maybe_dispatch_deliverable_reviews(
            _SpecInterceptDB(db, spec),
            company_id=str(uuid.uuid4()),
            company_task_id=str(uuid.uuid4()),
            artifact_id=str(uuid.uuid4()),
            artifact_type="document",
            is_current=True,
        )
        assert created == []


class TestMaybeDispatchBranchFilters:
    @pytest.mark.asyncio
    async def test_missing_current_artifact_returns_empty(self, db, review_env: dict[str, str]) -> None:
        env = review_env
        created = await maybe_dispatch_deliverable_reviews(
            db,
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            artifact_id=str(uuid.uuid4()),
            artifact_type="document",
            is_current=True,
        )
        assert created == []

    @pytest.mark.asyncio
    async def test_inactive_reviewer_is_skipped(self, db, review_env: dict[str, str]) -> None:
        env = review_env
        artifact_id = _id()
        await db.execute(
            "INSERT INTO artifacts"
            " (id, company_id, company_task_id, artifact_type, logical_name,"
            " object_sha256, object_size, media_type, metadata_json, is_current,"
            " created_by_type, created_at)"
            " VALUES (?,?,?,'document','x.py',?,10,'text/x-python','{}',1,'user',?)",
            (artifact_id, env["company_id"], env["task_id"], _sha256("v1"), env["now"]),
        )
        # Add an inactive reviewer to the frozen reviewers list.
        inactive_id = _id()
        profile_version_row = await (
            await db.execute("SELECT base_profile_version_id FROM employees WHERE id=?", (env["alice_id"],))
        ).fetchone()
        await db.execute(
            "INSERT INTO employees"
            " (id, company_id, department_id, display_name, normalized_display_name,"
            " base_profile_version_id, workflow_role, status, created_at, updated_at, version)"
            " VALUES (?,?,?,?,'inactive-reviewer',?,'member','inactive',?,?,1)",
            (
                inactive_id,
                env["company_id"],
                env["dept_id"],
                "Inactive",
                profile_version_row["base_profile_version_id"],
                env["now"],
                env["now"],
            ),
        )
        await db.execute(
            "UPDATE deliverable_review_specs SET reviewer_employee_ids_json=? WHERE company_id=?",
            (json.dumps([env["bob_id"], inactive_id]), env["company_id"]),
        )
        created = await maybe_dispatch_deliverable_reviews(
            db,
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            artifact_id=artifact_id,
            artifact_type="document",
            is_current=True,
        )
        # Bob is active and not a contributor -> one assignment; inactive is skipped.
        assert [c["reviewer_employee_id"] for c in created] == [env["bob_id"]]

    @pytest.mark.asyncio
    async def test_contributor_reviewer_is_skipped(self, db, review_env: dict[str, str]) -> None:
        """Reviewer already on artifact_contributors (but not the frozen list)."""
        env = review_env
        artifact_id = _id()
        await db.execute(
            "INSERT INTO artifacts"
            " (id, company_id, company_task_id, artifact_type, logical_name,"
            " object_sha256, object_size, media_type, metadata_json, is_current,"
            " created_by_type, created_at)"
            " VALUES (?,?,?,'document','x.py',?,10,'text/x-python','{}',1,'user',?)",
            (artifact_id, env["company_id"], env["task_id"], _sha256("v1"), env["now"]),
        )
        # Bob is not in the frozen contributor list but contributed to THIS artifact.
        await db.execute(
            "INSERT INTO artifact_contributors (artifact_id, company_id, employee_id) VALUES (?,?,?)",
            (artifact_id, env["company_id"], env["bob_id"]),
        )
        created = await maybe_dispatch_deliverable_reviews(
            db,
            company_id=env["company_id"],
            company_task_id=env["task_id"],
            artifact_id=artifact_id,
            artifact_type="document",
            is_current=True,
        )
        assert created == []
        assert await _rows(db, "SELECT * FROM review_assignments WHERE company_id=?", (env["company_id"],)) == []


class TestAdvanceEmployeeTaskGraphGuards:
    @pytest.mark.asyncio
    async def test_missing_dispatch_spec_is_skipped(self, db, chain_env: dict[str, str]) -> None:
        env = chain_env
        sha = await _register_plan(db, env, [env["alice_id"], env["bob_id"], env["carol_id"]])
        assert (await _confirm(db, env, sha))["status"] == "confirmed"
        tasks = await _rows(
            db,
            "SELECT id, employee_id FROM employee_tasks WHERE company_id=? ORDER BY created_at",
            (env["company_id"],),
        )
        alice, bob, _carol = tasks
        # Bob's frozen dispatch spec disappears; the dependent must be skipped,
        # not left failed nor dispatched.
        await db.execute("DELETE FROM employee_task_dispatch_specs WHERE employee_task_id=?", (bob["id"],))

        await _accept(db, alice["id"], env["company_id"], _now())
        result = await advance_employee_task_graph(
            db,
            company_id=env["company_id"],
            accepted_task_id=alice["id"],
        )
        assert result["dispatched"] == []
        assert result["failed"] == []
        bob_row = await (await db.execute("SELECT status FROM employee_tasks WHERE id=?", (bob["id"],))).fetchone()
        assert bob_row["status"] == "waiting_resource"

    @pytest.mark.asyncio
    async def test_failed_transition_zero_rows_is_skipped(self, db, chain_env: dict[str, str]) -> None:
        """274->282: the failed-UPDATE races to 0 rows; the segment is skipped."""
        env = chain_env
        sha = await _register_plan(db, env, [env["alice_id"], env["bob_id"], env["carol_id"]])
        assert (await _confirm(db, env, sha))["status"] == "confirmed"
        tasks = await _rows(
            db,
            "SELECT id, employee_id FROM employee_tasks WHERE company_id=? ORDER BY created_at",
            (env["company_id"],),
        )
        alice, bob, _carol = tasks
        # Force the availability check to fail (inactive employee), then zero the
        # failed transition so the segment is neither failed nor dispatched.
        await db.execute("UPDATE employees SET status='inactive' WHERE id=?", (env["bob_id"],))
        wrapper = _RowcountZeroDB(db, failed=True)

        await _accept(db, alice["id"], env["company_id"], _now())
        result = await advance_employee_task_graph(
            wrapper,
            company_id=env["company_id"],
            accepted_task_id=alice["id"],
        )
        assert result["dispatched"] == []
        assert result["failed"] == []
        bob_row = await (await db.execute("SELECT status FROM employee_tasks WHERE id=?", (bob["id"],))).fetchone()
        assert bob_row["status"] == "waiting_resource"

    @pytest.mark.asyncio
    async def test_assigned_transition_zero_rows_is_skipped(self, db, chain_env: dict[str, str]) -> None:
        """290: the assigned-UPDATE races to 0 rows; the segment is not dispatched."""
        env = chain_env
        sha = await _register_plan(db, env, [env["alice_id"], env["bob_id"], env["carol_id"]])
        assert (await _confirm(db, env, sha))["status"] == "confirmed"
        tasks = await _rows(
            db,
            "SELECT id, employee_id FROM employee_tasks WHERE company_id=? ORDER BY created_at",
            (env["company_id"],),
        )
        alice, bob, _carol = tasks
        wrapper = _RowcountZeroDB(db, assigned=True)

        await _accept(db, alice["id"], env["company_id"], _now())
        result = await advance_employee_task_graph(
            wrapper,
            company_id=env["company_id"],
            accepted_task_id=alice["id"],
        )
        assert result["dispatched"] == []
        assert result["failed"] == []
        bob_row = await (await db.execute("SELECT status FROM employee_tasks WHERE id=?", (bob["id"],))).fetchone()
        assert bob_row["status"] == "waiting_resource"


class _FakeRowCursor:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    async def fetchone(self):
        return self._row

    async def fetchall(self):
        return [self._row] if self._row is not None else []


class _FakeLazyDB:
    """Fake db returning crafted employee/profile and workspace rows."""

    def __init__(self, employee_row: dict[str, object], workspace_row: dict[str, object]) -> None:
        self._employee_row = employee_row
        self._workspace_row = workspace_row
        self.in_transaction = True

    async def execute(self, sql, params=()):
        if "FROM employees e" in sql:
            return _FakeRowCursor(self._employee_row)
        return _FakeRowCursor(self._workspace_row)


def _base_employee_row(**overrides: object) -> dict[str, object]:
    row = {
        "employee_status": "active",
        "department_id": "dept-1",
        "profile_version_id": "ver-1",
        "profile_version_status": "published",
        "catalog_release_id": "rel-1",
        "capability_tags_json": "[]",
        "profile_status": "active",
    }
    row.update(overrides)
    return row


def _base_workspace_row(**overrides: object) -> dict[str, object]:
    row = {
        "task_workspace_status": "active",
        "workspace_grant_id": "grant-1",
        "grant_status": "active",
    }
    row.update(overrides)
    return row


async def _checks(
    employee_row: dict[str, object],
    workspace_row: dict[str, object],
    *,
    required: tuple[str, ...] = (),
) -> tuple[list[dict[str, str]], bool]:
    return await _lazy_availability_checks(
        _FakeLazyDB(employee_row, workspace_row),
        company_id="comp-1",
        employee_id="emp-1",
        department_id="dept-1",
        profile_version_id="ver-1",
        catalog_release_id="rel-1",
        required_capability_tags=required,
        task_workspace_id="ws-1",
        workspace_grant_id="grant-1",
    )


class TestLazyAvailabilityChecks:
    @pytest.mark.asyncio
    async def test_profile_not_published(self) -> None:
        _checks_ok, available = await _checks(
            _base_employee_row(profile_version_status="retired"),
            _base_workspace_row(),
        )
        assert available is False

    @pytest.mark.asyncio
    async def test_capability_tags_invalid_json(self) -> None:
        _checks_ok, available = await _checks(
            _base_employee_row(capability_tags_json="not-json"),
            _base_workspace_row(),
        )
        assert available is True

    @pytest.mark.asyncio
    async def test_capability_tags_non_list(self) -> None:
        _checks_ok, available = await _checks(
            _base_employee_row(capability_tags_json="{}"),
            _base_workspace_row(),
        )
        assert available is True

    @pytest.mark.asyncio
    async def test_missing_capability(self) -> None:
        _checks_ok, available = await _checks(
            _base_employee_row(),
            _base_workspace_row(),
            required=("needed-tag",),
        )
        assert available is False

    @pytest.mark.asyncio
    async def test_catalog_release_mismatch(self) -> None:
        _checks_ok, available = await _checks(
            _base_employee_row(catalog_release_id="rel-2"),
            _base_workspace_row(),
        )
        assert available is False


def _sha256(data: str) -> str:
    import hashlib

    return hashlib.sha256(data.encode()).hexdigest()


def _now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
