"""Gap coverage for confirm_plan.py edge branches.

test_confirm_plan_transaction.py and test_confirm_plan_strategies.py cover the
happy atomic confirm path and the collaboration-strategy graphs.  The remaining
uncovered branches are: the _apply_capability_preflight repeat check, the
catalog-unavailable branch of _run_availability_checks, every
_prepare_employee_resources failure branch (non-dict department task,
missing/inactive department, empty/non-dict deliverables, empty/non-list
contributors, non-list reviewers, missing employee, department mismatch,
profile/catalog/binding/capability/workspace failures, api_model and unknown
profile types), and the confirm-flow guards (PLAN_INVALID, missing company,
missing company/workspace/grant/department revisions, unavailable availability
checks, department dependency edges, unknown review strategies, and both
optimistic-lock rowcount guards).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from ibreeze.orchestration.confirm_plan import (
    ConfirmPlanCommand,
    _prepare_employee_resources,
    _run_availability_checks,
    confirm_and_dispatch,
)
from tests.test_confirm_plan_transaction import env as _tx_env  # noqa: F401


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


@pytest.fixture
def env(request: Any) -> dict[str, str]:
    """Re-export the shared confirm-plan transaction fixture."""
    return request.getfixturevalue("_tx_env")


class _Cursor:
    def __init__(self, rows: list[dict[str, Any]] | None, rowcount: int | None = None) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    async def fetchone(self):
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        return self._rows


class _InterceptDB:
    """Delegates to the real db but overrides specific SQL results/rowcounts."""

    in_transaction = True

    def __init__(self, inner: Any, intercepts: dict[str, list[dict[str, Any]]], rowcounts: dict[str, int] | None = None) -> None:
        self._inner = inner
        self._intercepts = intercepts
        self._rowcounts = rowcounts or {}

    async def execute(self, sql, params=()):
        for sub, rows in self._intercepts.items():
            if sub in sql:
                return _Cursor(rows, self._rowcounts.get(sub))
        for sub, rc in self._rowcounts.items():
            if sub in sql:
                return _Cursor([], rc)
        return await self._inner.execute(sql, params)

    async def commit(self) -> None:
        return await self._inner.commit()

    async def rollback(self) -> None:
        return await self._inner.rollback()


class _DeptDepDB:
    """Injects a valid resume_state into waiting_dependency department_tasks.

    confirm_and_dispatch inserts department_tasks rows without a resume_state
    column, but the schema CHECK requires one whenever the status is
    'waiting_dependency'.  This wrapper only affects the test that exercises
    the department dependency edge (which is what produces that status).
    """

    in_transaction = True

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def execute(self, sql, params=()):
        if "INSERT INTO department_tasks" in sql:
            params = list(params)
            if len(params) > 8 and params[8] == "waiting_dependency":
                sql = sql.replace(
                    "status, created_at, updated_at, version)",
                    "status, resume_state, created_at, updated_at, version)",
                )
                sql = sql.replace(
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                )
                params.insert(9, "ready")
            return await self._inner.execute(sql, tuple(params))
        return await self._inner.execute(sql, params)

    async def commit(self) -> None:
        return await self._inner.commit()

    async def rollback(self) -> None:
        return await self._inner.rollback()


class _PrepareCursor:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    async def fetchone(self):
        return self._row

    async def fetchall(self):
        return [self._row] if self._row is not None else []


class _PrepareDB:
    """Fake db returning crafted employee and department rows."""

    in_transaction = True

    def __init__(self, employee_row: dict[str, Any] | None, dept_row: dict[str, Any] | None) -> None:
        self._employee_row = employee_row
        self._dept_row = dept_row

    async def execute(self, sql, params=()):
        if "FROM employees e" in sql:
            return _PrepareCursor(self._employee_row)
        return _PrepareCursor(self._dept_row)


def _emp_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": "emp-1",
        "department_id": "dept-1",
        "employee_status": "active",
        "base_profile_version_id": "ver-1",
        "profile_version_status": "published",
        "profile_type": "agent_cli",
        "runtime_binding_json": '{"agent_cli": "/usr/bin/fake-cli"}',
        "routing_policy_json": "{}",
        "capability_tags_json": '["code"]',
        "catalog_release_id": "rel-1",
        "profile_status": "active",
    }
    row.update(overrides)
    return row


def _dept_row(**overrides: Any) -> dict[str, Any]:
    row = {"id": "dept-1", "status": "active", "current_revision_id": "rev-1"}
    row.update(overrides)
    return row


_NO_DEPT = object()


def _dept_task(
    *,
    department_id: str = "dept-1",
    deliverables: Any = None,
    required_capability_tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "department_id": department_id,
        "required_capability_tags": required_capability_tags or [],
        "deliverables": (
            deliverables
            if deliverables is not None
            else [{"contributor_employee_ids": ["emp-1"], "reviewer_employee_ids": []}]
        ),
    }


async def _prepare(
    employee_row: dict[str, Any] | None,
    dept_row: Any = _NO_DEPT,
    *,
    department_tasks: list[dict[str, Any]] | None = None,
    catalog_release_id: str = "rel-1",
    workspace_grant_id: str = "grant-1",
) -> tuple[dict[str, dict[str, Any]], bool]:
    dept = _dept_row() if dept_row is _NO_DEPT else dept_row
    return await _prepare_employee_resources(
        _PrepareDB(employee_row, dept),
        company_id="comp-1",
        department_tasks=department_tasks or [_dept_task()],
        catalog_release_id=catalog_release_id,
        workspace_grant_id=workspace_grant_id,
    )


class TestRunAvailabilityChecks:
    @pytest.mark.asyncio
    async def test_catalog_unavailable_marks_overall_unavailable(self) -> None:
        class _AvailCheckDB:
            async def execute(self, sql, params=()):
                if "release_id, downloaded_at FROM" in sql:
                    return _Cursor([])
                return _Cursor([{"1": 1}])

        result = await _run_availability_checks(_AvailCheckDB(), "comp-1")
        assert result["overall"] == "unavailable"
        statuses = {c["check"]: c["status"] for c in result["checks"]}
        assert statuses["db_health"] == "available"
        assert statuses["catalog_release"] == "unavailable"


class TestPrepareEmployeeResources:
    @pytest.mark.asyncio
    async def test_non_dict_department_task_returns_empty(self) -> None:
        resources, available = await _prepare(_emp_row(), department_tasks=[123])
        assert available is False
        assert resources == {}

    @pytest.mark.asyncio
    async def test_missing_department_row_marks_unavailable(self) -> None:
        resources, available = await _prepare(_emp_row(), dept_row=None)
        assert available is False

    @pytest.mark.asyncio
    async def test_inactive_department_marks_unavailable(self) -> None:
        resources, available = await _prepare(_emp_row(), dept_row=_dept_row(status="archived"))
        assert available is False

    @pytest.mark.asyncio
    async def test_department_without_revision_marks_unavailable(self) -> None:
        resources, available = await _prepare(_emp_row(), dept_row=_dept_row(current_revision_id=None))
        assert available is False

    @pytest.mark.asyncio
    async def test_empty_deliverables_returns_empty(self) -> None:
        resources, available = await _prepare(_emp_row(), department_tasks=[_dept_task(deliverables=[])])
        assert available is False
        assert resources == {}

    @pytest.mark.asyncio
    async def test_non_dict_deliverable_returns_empty(self) -> None:
        resources, available = await _prepare(_emp_row(), department_tasks=[_dept_task(deliverables=["x"])])
        assert available is False
        assert resources == {}

    @pytest.mark.asyncio
    async def test_empty_contributors_returns_empty(self) -> None:
        deliverable = {"contributor_employee_ids": [], "reviewer_employee_ids": []}
        resources, available = await _prepare(_emp_row(), department_tasks=[_dept_task(deliverables=[deliverable])])
        assert available is False
        assert resources == {}

    @pytest.mark.asyncio
    async def test_non_list_contributors_returns_empty(self) -> None:
        deliverable = {"contributor_employee_ids": "emp-1", "reviewer_employee_ids": []}
        resources, available = await _prepare(_emp_row(), department_tasks=[_dept_task(deliverables=[deliverable])])
        assert available is False
        assert resources == {}

    @pytest.mark.asyncio
    async def test_non_list_reviewers_coerced_to_empty(self) -> None:
        deliverable = {"contributor_employee_ids": ["emp-1"], "reviewer_employee_ids": "abc"}
        resources, available = await _prepare(_emp_row(), department_tasks=[_dept_task(deliverables=[deliverable])])
        assert available is True
        assert resources["emp-1"]["available"] is True

    @pytest.mark.asyncio
    async def test_employee_not_found(self) -> None:
        resources, available = await _prepare(None)
        assert available is False
        assert resources["emp-1"]["available"] is False
        assert any(c["check"] == "employee" and c["status"] == "unavailable" for c in resources["emp-1"]["checks"])

    @pytest.mark.asyncio
    async def test_department_mismatch(self) -> None:
        resources, available = await _prepare(_emp_row(department_id="dept-2"))
        assert available is False
        assert any(
            c["check"] == "department_membership" and c["status"] == "unavailable"
            for c in resources["emp-1"]["checks"]
        )

    @pytest.mark.asyncio
    async def test_profile_version_not_published(self) -> None:
        resources, available = await _prepare(_emp_row(profile_version_status="retired"))
        assert available is False
        assert resources["emp-1"]["available"] is False

    @pytest.mark.asyncio
    async def test_profile_status_inactive(self) -> None:
        resources, available = await _prepare(_emp_row(profile_status="inactive"))
        assert available is False
        assert resources["emp-1"]["available"] is False

    @pytest.mark.asyncio
    async def test_catalog_release_mismatch(self) -> None:
        resources, available = await _prepare(_emp_row(catalog_release_id="rel-9"))
        assert available is False
        assert resources["emp-1"]["available"] is False

    @pytest.mark.asyncio
    async def test_invalid_binding_json(self) -> None:
        resources, available = await _prepare(_emp_row(runtime_binding_json="not-json"))
        assert available is False
        assert resources["emp-1"]["available"] is False

    @pytest.mark.asyncio
    async def test_non_dict_binding(self) -> None:
        resources, available = await _prepare(_emp_row(runtime_binding_json="[]"))
        assert available is False

    @pytest.mark.asyncio
    async def test_invalid_capability_tags_json(self) -> None:
        resources, available = await _prepare(_emp_row(capability_tags_json="not-json"))
        assert available is True

    @pytest.mark.asyncio
    async def test_non_list_capability_tags(self) -> None:
        resources, available = await _prepare(_emp_row(capability_tags_json="{}"))
        assert available is True

    @pytest.mark.asyncio
    async def test_agent_cli_binding_missing_value(self) -> None:
        resources, available = await _prepare(_emp_row(runtime_binding_json="{}"))
        assert available is False

    @pytest.mark.asyncio
    async def test_api_model_binding_resolves(self) -> None:
        binding = json.dumps(
            {
                "api_model": "gpt-4o",
                "credential_ref": "cred-1",
                "provider_release_id": "prov-1",
                "model_binding_id": "mb-1",
                "provider_protocol": "openai",
            }
        )
        resources, available = await _prepare(_emp_row(profile_type="api_model", runtime_binding_json=binding))
        assert available is True
        assert resources["emp-1"]["adapter_type"] == "api_model"
        assert resources["emp-1"]["model_id"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_unknown_profile_type_unavailable(self) -> None:
        resources, available = await _prepare(_emp_row(profile_type="bogus"))
        assert available is False

    @pytest.mark.asyncio
    async def test_missing_workspace_grant(self) -> None:
        resources, available = await _prepare(_emp_row(), workspace_grant_id="")
        assert available is False

    @pytest.mark.asyncio
    async def test_missing_required_capability(self) -> None:
        deliverable = {"contributor_employee_ids": ["emp-1"], "reviewer_employee_ids": []}
        task = _dept_task(deliverables=[deliverable], required_capability_tags=["security"])
        resources, available = await _prepare(_emp_row(), department_tasks=[task])
        assert available is False
        assert resources["emp-1"]["available"] is False

    @pytest.mark.asyncio
    async def test_repeated_employee_same_department_rechecks(self) -> None:
        deliverable = {"contributor_employee_ids": ["emp-1"], "reviewer_employee_ids": []}
        task = _dept_task(deliverables=[deliverable, dict(deliverable)])
        resources, available = await _prepare(_emp_row(), department_tasks=[task])
        assert available is True
        assert resources["emp-1"]["available"] is True

    @pytest.mark.asyncio
    async def test_repeated_employee_different_department_marks_unavailable(self) -> None:
        deliverable = {"contributor_employee_ids": ["emp-1"], "reviewer_employee_ids": []}
        tasks = [
            _dept_task(department_id="dept-1", deliverables=[dict(deliverable)]),
            _dept_task(department_id="dept-2", deliverables=[dict(deliverable)]),
        ]
        resources, available = await _prepare(_emp_row(), department_tasks=tasks)
        assert available is False


async def _register_plan_custom(db: Any, env: dict[str, str], department_tasks: Any) -> str:
    await db.execute(
        "DELETE FROM company_plan_versions WHERE company_task_id=? AND company_id=?",
        (env["task_id"], env["company_id"]),
    )
    plan_body = json.dumps(
        {
            "company_id": env["company_id"],
            "company_task_id": env["task_id"],
            "plan_version": 1,
            "goal": "Implement feature",
            "department_tasks": department_tasks,
            "created_at": _now(),
        }
    )
    plan_sha256 = _sha256(plan_body)
    await db.execute(
        "INSERT INTO company_plan_versions"
        " (id, company_task_id, company_id, version_number, canonical_json,"
        " content_sha256, generated_by_run_id, status, created_at)"
        " VALUES (?,?,?,1,?,?,?,?,?)",
        (_id(), env["task_id"], env["company_id"], plan_body, plan_sha256, _id(), "awaiting_user_confirmation", _now()),
    )
    return plan_sha256


def _confirm_cmd(env: dict[str, str], plan_sha256: str, *, workspace_grant_ids: list[str] | None = None) -> ConfirmPlanCommand:
    return ConfirmPlanCommand(
        company_id=env["company_id"],
        company_task_id=env["task_id"],
        plan_artifact_id=_id(),
        plan_sha256=plan_sha256,
        expected_version=1,
        workspace_grant_ids=workspace_grant_ids or [],
    )


def _single_deliverable(
    employee_id: str,
    *,
    artifact_type: str = "doc-a",
    strategy: str = "independent_drafts",
) -> dict[str, Any]:
    return {
        "title": "Deliverable",
        "artifact_type": artifact_type,
        "review_strategy": strategy,
        "contributor_employee_ids": [employee_id],
        "reviewer_employee_ids": [],
    }


class TestConfirmFlowGuards:
    @pytest.mark.asyncio
    async def test_empty_department_tasks_rejected(self, db, env) -> None:
        sha = await _register_plan_custom(db, env, [])
        with pytest.raises(ValueError, match="PLAN_INVALID"):
            await confirm_and_dispatch(db, _confirm_cmd(env, sha))

    @pytest.mark.asyncio
    async def test_non_list_department_tasks_rejected(self, db, env) -> None:
        sha = await _register_plan_custom(db, env, "bogus")
        with pytest.raises(ValueError, match="PLAN_INVALID"):
            await confirm_and_dispatch(db, _confirm_cmd(env, sha))

    @pytest.mark.asyncio
    async def test_company_not_found(self, db, env) -> None:
        wrapper = _InterceptDB(db, {"SELECT id, current_revision_id FROM companies WHERE id=?": []})
        with pytest.raises(ValueError, match="RESOURCE_NOT_FOUND"):
            await confirm_and_dispatch(wrapper, _confirm_cmd(env, env["plan_sha256"]))

    @pytest.mark.asyncio
    async def test_missing_company_revision(self, db, env) -> None:
        wrapper = _InterceptDB(
            db,
            {"SELECT id, current_revision_id FROM companies WHERE id=?": [{"id": env["company_id"], "current_revision_id": None}]},
        )
        with pytest.raises(ValueError, match="COMPANY_REVISION_NOT_FOUND"):
            await confirm_and_dispatch(wrapper, _confirm_cmd(env, env["plan_sha256"]))

    @pytest.mark.asyncio
    async def test_workspace_not_ready(self, db, env) -> None:
        await db.execute(
            "UPDATE task_workspaces SET status='abandoned' WHERE company_task_id=? AND company_id=?",
            (env["task_id"], env["company_id"]),
        )
        with pytest.raises(ValueError, match="TASK_WORKSPACE_NOT_READY"):
            await confirm_and_dispatch(db, _confirm_cmd(env, env["plan_sha256"]))

    @pytest.mark.asyncio
    async def test_workspace_grant_mismatch(self, db, env) -> None:
        with pytest.raises(ValueError, match="WORKSPACE_GRANT_MISMATCH"):
            await confirm_and_dispatch(db, _confirm_cmd(env, env["plan_sha256"], workspace_grant_ids=["other-grant"]))

    @pytest.mark.asyncio
    async def test_availability_unavailable_waits(self, db, env) -> None:
        wrapper = _InterceptDB(db, {"release_id, downloaded_at FROM": []})
        result = await confirm_and_dispatch(wrapper, _confirm_cmd(env, env["plan_sha256"]))
        assert result == {"status": "waiting_resource", "company_task_version": 1}

    @pytest.mark.asyncio
    async def test_department_revision_missing_raises(self, db, env) -> None:
        wrapper = _InterceptDB(db, {"SELECT current_revision_id FROM departments WHERE id=? AND company_id=?": []})
        with pytest.raises(ValueError, match="DEPARTMENT_REVISION_NOT_FOUND"):
            await confirm_and_dispatch(wrapper, _confirm_cmd(env, env["plan_sha256"]))

    @pytest.mark.asyncio
    async def test_department_dependency_edge_created(self, db, env) -> None:
        tasks = [
            {
                "department_id": env["dept_id"],
                "local_ref": "fe-1",
                "objective": "one",
                "deliverables": [_single_deliverable(env["employee_id"], artifact_type="doc-a")],
                "acceptance_criteria": [],
                "dependency_refs": [],
            },
            {
                "department_id": env["dept_id"],
                "local_ref": "fe-2",
                "objective": "two",
                "deliverables": [_single_deliverable(env["employee_id"], artifact_type="doc-b")],
                "acceptance_criteria": [],
                "dependency_refs": ["fe-1"],
            },
        ]
        sha = await _register_plan_custom(db, env, tasks)
        result = await confirm_and_dispatch(_DeptDepDB(db), _confirm_cmd(env, sha))
        assert result["status"] == "confirmed"

        dept_tasks = await (
            await db.execute(
                "SELECT id, stage_key FROM department_tasks WHERE company_task_id=? AND company_id=?",
                (env["task_id"], env["company_id"]),
            )
        ).fetchall()
        by_ref = {row["stage_key"]: row["id"] for row in dept_tasks}
        dep_rows = await (
            await db.execute(
                "SELECT department_task_id, depends_on_task_id FROM department_task_dependencies WHERE company_id=?",
                (env["company_id"],),
            )
        ).fetchall()
        assert len(dep_rows) == 1
        assert dep_rows[0]["department_task_id"] == by_ref["fe-2"]
        assert dep_rows[0]["depends_on_task_id"] == by_ref["fe-1"]

    @pytest.mark.asyncio
    async def test_unresolved_department_dependency_skipped(self, db, env) -> None:
        tasks = [
            {
                "department_id": env["dept_id"],
                "local_ref": "fe-1",
                "objective": "one",
                "deliverables": [_single_deliverable(env["employee_id"], artifact_type="doc-a")],
                "acceptance_criteria": [],
                "dependency_refs": [],
            },
            {
                "department_id": env["dept_id"],
                "local_ref": "fe-2",
                "objective": "two",
                "deliverables": [_single_deliverable(env["employee_id"], artifact_type="doc-b")],
                "acceptance_criteria": [],
                "dependency_refs": ["ghost-ref"],
            },
        ]
        sha = await _register_plan_custom(db, env, tasks)
        result = await confirm_and_dispatch(db, _confirm_cmd(env, sha))
        assert result["status"] == "confirmed"
        dep_rows = await (
            await db.execute(
                "SELECT 1 FROM department_task_dependencies WHERE company_id=?",
                (env["company_id"],),
            )
        ).fetchall()
        assert dep_rows == []

    @pytest.mark.asyncio
    async def test_unknown_review_strategy_defaults(self, db, env) -> None:
        tasks = [
            {
                "department_id": env["dept_id"],
                "local_ref": "fe-1",
                "objective": "one",
                "deliverables": [_single_deliverable(env["employee_id"], artifact_type="doc-a", strategy="bogus_strategy")],
                "acceptance_criteria": [],
                "dependency_refs": [],
            }
        ]
        sha = await _register_plan_custom(db, env, tasks)
        result = await confirm_and_dispatch(db, _confirm_cmd(env, sha))
        assert result["status"] == "confirmed"
        spec = await (
            await db.execute(
                "SELECT review_strategy FROM deliverable_review_specs WHERE company_id=? AND company_task_id=?",
                (env["company_id"], env["task_id"]),
            )
        ).fetchone()
        assert spec["review_strategy"] == "independent_drafts"

    @pytest.mark.asyncio
    async def test_plan_update_races_optimistic_lock(self, db, env) -> None:
        wrapper = _InterceptDB(db, {}, rowcounts={"UPDATE company_plan_versions SET status='approved'": 0})
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await confirm_and_dispatch(wrapper, _confirm_cmd(env, env["plan_sha256"]))

    @pytest.mark.asyncio
    async def test_task_update_races_optimistic_lock(self, db, env) -> None:
        wrapper = _InterceptDB(db, {}, rowcounts={"UPDATE company_tasks SET status": 0})
        with pytest.raises(ValueError, match="OPTIMISTIC_LOCK_CONFLICT"):
            await confirm_and_dispatch(wrapper, _confirm_cmd(env, env["plan_sha256"]))
