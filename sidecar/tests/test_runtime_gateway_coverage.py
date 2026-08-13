"""Coverage tests for ibreeze/runtime/gateway.py (validation branches, happy paths, cancel/resume/status)."""

from __future__ import annotations

import hashlib
import json
import uuid

import pytest

from ibreeze.runtime.gateway import RunNotFoundError, RunValidationError, cancel, get_status, resume, start


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


class _Row(dict):
    pass


class _Cursor:
    def __init__(self, rows=None) -> None:
        self._rows = rows or []

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeDb:
    """Deterministic fake db returning a scripted cursor per execute call."""

    def __init__(self, responses) -> None:
        self._responses = list(responses)

    async def execute(self, sql, parameters=()):
        if self._responses:
            return self._responses.pop(0)
        return _Cursor()


def _gateway_fake_db(*, execution: dict):
    """Script the 5 SELECT reads that happen before the error branches."""
    return _FakeDb(
        [
            _Cursor([_Row(id="task")]),  # company_tasks
            _Cursor([_Row(id="emp")]),  # employees
            _Cursor([_Row(id="conv")]),  # conversations
            _Cursor(  # employee_availability_snapshots
                [
                    _Row(
                        employee_id="emp",
                        company_task_id="task",
                        department_task_id="dept",
                        work_item_type="task_execution",
                        work_item_id="wi",
                        overall_status="available",
                        expires_at="2099-01-01T00:00:00.000000Z",
                    )
                ]
            ),
            _Cursor([_Row(**execution)]),  # execution_snapshots
        ]
    )


def _gateway_args(**overrides):
    args = {
        "company_id": "co",
        "company_task_id": "task",
        "employee_id": "emp",
        "model_id": "codex_cli",
        "prompt": "run",
        "run_purpose": "task_execution",
        "adapter_type": "codex_cli",
        "conversation_id": "conv",
        "availability_snapshot_id": "avail",
        "execution_snapshot_id": "exec",
        "department_task_id": "dept",
    }
    args.update(overrides)
    return args


async def _base(db, published_profile):
    """Create company/task context needed by gateway.start()."""
    company = await (await db.execute("SELECT * FROM companies LIMIT 1")).fetchone()
    department = await (
        await db.execute("SELECT * FROM departments WHERE company_id=? LIMIT 1", (company["id"],))
    ).fetchone()
    employee = await (
        await db.execute("SELECT * FROM employees WHERE company_id=? LIMIT 1", (company["id"],))
    ).fetchone()
    profile = await (
        await db.execute("SELECT * FROM employee_base_profile_versions WHERE id=?", (published_profile,))
    ).fetchone()
    now = "2026-08-01T00:00:00.000000Z"
    company_task_id = str(uuid.uuid4())
    department_task_id = str(uuid.uuid4())
    employee_task_id = str(uuid.uuid4())
    message_event_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO domain_events
           (event_id, company_id, aggregate_type, aggregate_id,
            aggregate_version, event_type, payload_json, trace_id, occurred_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            message_event_id,
            company["id"],
            "company_task",
            company_task_id,
            1,
            "conversation.user_message",
            json.dumps({"company_id": company["id"]}),
            str(uuid.uuid4()),
            now,
        ),
    )
    await db.execute(
        """INSERT INTO company_tasks
           (id, company_id, company_conversation_id, user_message_event_id,
            title, status, created_at, updated_at, version)
           VALUES (?,?,?,?,?,'executing',?,?,1)""",
        (
            company_task_id,
            company["id"],
            company["company_conversation_id"],
            message_event_id,
            "Gateway task",
            now,
            now,
        ),
    )
    await db.execute(
        """INSERT INTO department_tasks
           (id, company_id, company_task_id, department_id, stage_key,
            objective, deliverables_json, acceptance_criteria_json,
            status, created_at, updated_at, version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,1)""",
        (
            department_task_id,
            company["id"],
            company_task_id,
            department["id"],
            "implementation",
            "Implement the gateway test",
            "[]",
            "[]",
            "ready",
            now,
            now,
        ),
    )
    await db.execute(
        """INSERT INTO employee_tasks
           (id, company_id, department_task_id, employee_id, task_kind,
            objective, acceptance_criteria_json, status, created_at,
            updated_at, version)
           VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
        (
            employee_task_id,
            company["id"],
            department_task_id,
            employee["id"],
            "standard",
            "Implement the gateway test",
            "[]",
            "assigned",
            now,
            now,
        ),
    )
    await db.commit()
    return {
        "company_id": company["id"],
        "company_task_id": company_task_id,
        "employee_id": employee["id"],
        "conversation_id": company["company_conversation_id"],
        "department_id": department["id"],
        "department_task_id": department_task_id,
        "employee_task_id": employee_task_id,
        "current_revision_id": company["current_revision_id"],
        "department_revision_id": department["current_revision_id"],
        "profile_id": published_profile,
        "catalog_release_id": profile["catalog_release_id"],
        "now": now,
    }


_UNSET = object()


async def _snapshots(
    db,
    ctx,
    *,
    purpose: str,
    work_item_type: str | None = None,
    work_item_id: str | None = None,
    department_task_id=_UNSET,
    employee_task_id=_UNSET,
    execution_department_task_id=None,
    execution_employee_task_id=None,
    availability_work_item_id=None,
    execution_work_item_id=None,
    availability_status: str = "available",
    expires_at: str = "2099-01-01T00:00:00.000000Z",
    binding_json: str = '{"agent_cli": "codex_cli"}',
    availability_company_task_id=None,
    execution_company_task_id=None,
    availability_employee_id=None,
    execution_employee_id=None,
    execution_purpose: str | None = None,
):
    """Create an availability + execution snapshot pair for a gateway run."""
    if employee_task_id is _UNSET:
        employee_task_id = ctx["employee_task_id"] if purpose in ("task_execution", "merge") else None
    if department_task_id is _UNSET:
        department_task_id = ctx["department_task_id"] if purpose in ("task_execution", "merge") else None
    if work_item_type is None:
        work_item_type = purpose
    if work_item_id is None:
        if purpose in ("task_execution", "merge"):
            work_item_id = employee_task_id or ctx["employee_task_id"]
        elif purpose in ("company_plan", "summary"):
            work_item_id = ctx["company_task_id"]
        elif purpose == "interactive_turn":
            work_item_id = ctx["conversation_id"]
        else:
            raise AssertionError(f"work_item_id is required for purpose {purpose}")
    if execution_purpose is None:
        execution_purpose = purpose
    if execution_department_task_id is None:
        execution_department_task_id = department_task_id
    if execution_employee_task_id is None:
        execution_employee_task_id = employee_task_id
    if availability_work_item_id is None:
        availability_work_item_id = work_item_id
    if execution_work_item_id is None:
        execution_work_item_id = work_item_id

    now = ctx["now"]
    content_sha = "a" * 64
    availability_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO employee_availability_snapshots
           (id, company_id, company_task_id, department_task_id,
            work_item_type, work_item_id, employee_id, base_profile_version_id,
            prospective_execution_sha256, catalog_release_id, checks_json,
            overall_status, checked_at, expires_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            availability_id,
            ctx["company_id"],
            availability_company_task_id or ctx["company_task_id"],
            department_task_id,
            work_item_type,
            availability_work_item_id,
            availability_employee_id or ctx["employee_id"],
            ctx["profile_id"],
            content_sha,
            ctx["catalog_release_id"],
            json.dumps({"checks": []}),
            availability_status,
            now,
            expires_at,
        ),
    )
    await db.execute(
        """INSERT INTO execution_snapshots
           (id, company_id, company_task_id, department_id,
            department_task_id, employee_task_id, employee_id,
            snapshot_purpose, work_item_id, company_revision_id,
            department_revision_id, base_profile_version_id, catalog_release_id,
            runtime_binding_json, skill_lock_json, tool_policy_json,
            workspace_policy_json, verification_commands_json, content_sha256,
            created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            execution_id,
            ctx["company_id"],
            execution_company_task_id or ctx["company_task_id"],
            ctx["department_id"],
            execution_department_task_id,
            execution_employee_task_id,
            execution_employee_id or ctx["employee_id"],
            execution_purpose,
            execution_work_item_id,
            ctx["current_revision_id"],
            ctx["department_revision_id"],
            ctx["profile_id"],
            ctx["catalog_release_id"],
            binding_json,
            "{}",
            "{}",
            "{}",
            "[]",
            content_sha,
            now,
        ),
    )
    await db.commit()
    return {
        "availability_snapshot_id": availability_id,
        "execution_snapshot_id": execution_id,
    }


def _start_kwargs(ctx, snap, purpose, *, model_id="codex_cli", adapter_type="codex_cli", **extra):
    kwargs = {
        "company_id": ctx["company_id"],
        "company_task_id": ctx["company_task_id"],
        "employee_id": ctx["employee_id"],
        "model_id": model_id,
        "prompt": "run",
        "run_purpose": purpose,
        "adapter_type": adapter_type,
        "conversation_id": ctx["conversation_id"],
        "availability_snapshot_id": snap["availability_snapshot_id"],
        "execution_snapshot_id": snap["execution_snapshot_id"],
    }
    kwargs.update(extra)
    return kwargs


async def _add_employee(db, ctx):
    now = ctx["now"]
    employee_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO employees
           (id, company_id, department_id, display_name, normalized_display_name,
            base_profile_version_id, workflow_role, status, created_at, updated_at, version)
           VALUES (?,?,?,?,?,?,'member','active',?,?,1)""",
        (
            employee_id,
            ctx["company_id"],
            ctx["department_id"],
            "Emp2",
            "emp2",
            ctx["profile_id"],
            now,
            now,
        ),
    )
    await db.commit()
    return employee_id


async def _add_employee_task(db, ctx, *, employee_id=None, task_kind="standard"):
    now = ctx["now"]
    task_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO employee_tasks
           (id, company_id, department_task_id, employee_id, task_kind,
            objective, acceptance_criteria_json, status, created_at, updated_at, version)
           VALUES (?,?,?,?,?,?,?,'assigned',?,?,1)""",
        (
            task_id,
            ctx["company_id"],
            ctx["department_task_id"],
            employee_id or ctx["employee_id"],
            task_kind,
            "obj",
            "[]",
            now,
            now,
        ),
    )
    await db.commit()
    return task_id


async def _add_company_task(db, ctx):
    now = ctx["now"]
    task_id = str(uuid.uuid4())
    msg_event_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO domain_events
           (event_id, company_id, aggregate_type, aggregate_id,
            aggregate_version, event_type, payload_json, trace_id, occurred_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            msg_event_id,
            ctx["company_id"],
            "company_task",
            task_id,
            1,
            "conversation.user_message",
            json.dumps({"company_id": ctx["company_id"]}),
            str(uuid.uuid4()),
            now,
        ),
    )
    await db.execute(
        """INSERT INTO company_tasks
           (id, company_id, company_conversation_id, user_message_event_id,
            title, status, created_at, updated_at, version)
           VALUES (?,?,?,?,?,'executing',?,?,1)""",
        (task_id, ctx["company_id"], ctx["conversation_id"], msg_event_id, "Other task", now, now),
    )
    await db.commit()
    return task_id


async def _add_artifact(db, ctx, *, company_task_id=None, artifact_type="review_report"):
    now = ctx["now"]
    artifact_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO artifacts
           (id, company_id, company_task_id, artifact_type, logical_name,
            object_sha256, object_size, media_type, metadata_json, is_current,
            created_by_type, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,1,'system',?)""",
        (
            artifact_id,
            ctx["company_id"],
            company_task_id or ctx["company_task_id"],
            artifact_type,
            "artifact",
            "a" * 64,
            10,
            "text/plain",
            "{}",
            now,
        ),
    )
    await db.commit()
    return artifact_id


async def _add_review_assignment(db, ctx, *, artifact_id, reviewer_employee_id=None):
    now = ctx["now"]
    assignment_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO review_assignments
           (id, company_id, artifact_id, reviewer_employee_id, review_round,
            reviewed_sha256, status, assigned_at)
           VALUES (?,?,?,?,1,?,'assigned',?)""",
        (
            assignment_id,
            ctx["company_id"],
            artifact_id,
            reviewer_employee_id or ctx["employee_id"],
            "a" * 64,
            now,
        ),
    )
    await db.commit()
    return assignment_id


async def _add_agent_run(db, ctx, *, snap, run_purpose, work_item_id):
    now = ctx["now"]
    run_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO agent_runs
           (id, company_id, company_task_id, work_item_id, employee_id, conversation_id,
            availability_snapshot_id, execution_snapshot_id, run_purpose, adapter_type,
            run_spec_json, run_spec_sha256, status, resume_state, attempt, created_at, updated_at, version)
           VALUES (?,?,?,?,?,?,?,?,?,?,'{}',?,'queued',NULL,1,?,?,1)""",
        (
            run_id,
            ctx["company_id"],
            ctx["company_task_id"],
            work_item_id,
            ctx["employee_id"],
            ctx["conversation_id"],
            snap["availability_snapshot_id"],
            snap["execution_snapshot_id"],
            run_purpose,
            "codex_cli",
            _sha256("{}"),
            now,
            now,
        ),
    )
    await db.commit()
    return run_id


async def _add_review_report(db, ctx, *, assignment_id, artifact_id, reviewer_run_id):
    now = ctx["now"]
    report_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO review_reports
           (id, company_id, assignment_id, reviewer_run_id, reviewed_artifact_id,
            reviewed_sha256, verdict, report_artifact_id, created_at)
           VALUES (?,?,?,?,?,?,'needs_changes',?,?)""",
        (
            report_id,
            ctx["company_id"],
            assignment_id,
            reviewer_run_id,
            artifact_id,
            "a" * 64,
            artifact_id,
            now,
        ),
    )
    await db.commit()
    return report_id


async def _add_review_issue(db, ctx, *, report_id):
    now = ctx["now"]
    issue_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO review_issues
           (id, company_id, review_report_id, severity, category, description,
            expected, actual, suggested_fix, evidence_refs_json, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,'open',?,?)""",
        (
            issue_id,
            ctx["company_id"],
            report_id,
            "high",
            "cat",
            "desc",
            "exp",
            "act",
            "fix",
            "[]",
            now,
            now,
        ),
    )
    await db.commit()
    return issue_id


# ---------------------------------------------------------------------------
# start() validation branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStartValidation:
    async def test_required_field_blank(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        with pytest.raises(RunValidationError, match="RUNTIME_EXECUTION_SNAPSHOT_REQUIRED"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution", model_id=""))

    async def test_invalid_run_purpose(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        with pytest.raises(RunValidationError, match="RUN_PURPOSE_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "employee_task"))

    async def test_invalid_adapter_type(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        with pytest.raises(RunValidationError, match="ADAPTER_TYPE_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution", adapter_type="nope"))

    async def test_company_task_not_found(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        with pytest.raises(RunNotFoundError, match="CompanyTask"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution", company_task_id=str(uuid.uuid4())))

    async def test_employee_unavailable(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        with pytest.raises(RunValidationError, match="EMPLOYEE_UNAVAILABLE"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution", employee_id=str(uuid.uuid4())))

    async def test_conversation_not_found(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        with pytest.raises(RunNotFoundError, match="Conversation"):
            await start(
                db,
                **_start_kwargs(ctx, snap, "task_execution", conversation_id=str(uuid.uuid4())),
            )

    async def test_availability_snapshot_missing(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        snap = {"availability_snapshot_id": str(uuid.uuid4()), "execution_snapshot_id": snap["execution_snapshot_id"]}
        with pytest.raises(RunValidationError, match="AVAILABILITY_SNAPSHOT_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution"))

    async def test_availability_snapshot_unavailable_status(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution", availability_status="unavailable")
        with pytest.raises(RunValidationError, match="AVAILABILITY_SNAPSHOT_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution"))

    async def test_availability_department_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        with pytest.raises(RunValidationError, match="AVAILABILITY_SNAPSHOT_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution", department_task_id="wrong-id"))

    async def test_availability_snapshot_bad_date(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution", expires_at="not-a-date")
        with pytest.raises(RunValidationError, match="AVAILABILITY_SNAPSHOT_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution"))

    async def test_availability_snapshot_expired(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution", expires_at="2000-01-01T00:00:00.000000Z")
        with pytest.raises(RunValidationError, match="AVAILABILITY_SNAPSHOT_EXPIRED"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution"))

    async def test_execution_snapshot_missing(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        snap = {"availability_snapshot_id": snap["availability_snapshot_id"], "execution_snapshot_id": str(uuid.uuid4())}
        with pytest.raises(RunValidationError, match="EXECUTION_SNAPSHOT_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution"))

    async def test_execution_snapshot_company_task_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        other_task = await _add_company_task(db, ctx)
        snap = await _snapshots(db, ctx, purpose="task_execution", execution_company_task_id=other_task)
        with pytest.raises(RunValidationError, match="EXECUTION_SNAPSHOT_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution"))

    async def test_execution_snapshot_bad_binding(self):
        # SQLite's json_valid CHECK prevents storing invalid binding JSON, so
        # drive the gateway's json.loads guard through a scripted fake db.
        fake_db = _gateway_fake_db(
            execution={
                "company_task_id": "task",
                "department_task_id": "dept",
                "employee_task_id": "emp-task",
                "employee_id": "emp",
                "snapshot_purpose": "task_execution",
                "work_item_id": "wi",
                "runtime_binding_json": "{not json",
            }
        )
        with pytest.raises(RunValidationError, match="EXECUTION_SNAPSHOT_INVALID"):
            await start(fake_db, **_gateway_args())

    async def test_execution_snapshot_binding_not_dict(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution", binding_json="[1, 2]")
        with pytest.raises(RunValidationError, match="EXECUTION_SNAPSHOT_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution"))

    async def test_binding_model_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        with pytest.raises(RunValidationError, match="EXECUTION_SNAPSHOT_BINDING_MISMATCH"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution", model_id="gpt-4o"))

    async def test_binding_adapter_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        with pytest.raises(RunValidationError, match="EXECUTION_SNAPSHOT_BINDING_MISMATCH"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution", adapter_type="claude_code"))

    async def test_employee_task_id_param_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        with pytest.raises(RunValidationError, match="EXECUTION_SNAPSHOT_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution", employee_task_id="wrong-id"))

    async def test_task_execution_requires_employee_task(self):
        # The execution_snapshots CHECK enforces employee_task_id NOT NULL for
        # snapshot_purpose='task_execution', so the missing-task branch is only
        # reachable through a scripted fake db.
        fake_db = _gateway_fake_db(
            execution={
                "company_task_id": "task",
                "department_task_id": "dept",
                "employee_task_id": None,
                "employee_id": "emp",
                "snapshot_purpose": "task_execution",
                "work_item_id": "wi",
                "runtime_binding_json": '{"agent_cli": "codex_cli"}',
            }
        )
        with pytest.raises(RunValidationError, match="EMPLOYEE_TASK_REQUIRED"):
            await start(fake_db, **_gateway_args())

    async def test_employee_task_scope_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        other_employee = await _add_employee(db, ctx)
        other_task = await _add_employee_task(db, ctx, employee_id=other_employee)
        snap = await _snapshots(
            db,
            ctx,
            purpose="task_execution",
            work_item_id=other_task,
            employee_task_id=other_task,
        )
        with pytest.raises(RunValidationError, match="EMPLOYEE_TASK_SCOPE_MISMATCH"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution"))

    async def test_availability_work_item_type_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution", work_item_type="company_plan")
        with pytest.raises(RunValidationError, match="AVAILABILITY_SNAPSHOT_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution"))

    async def test_execution_snapshot_purpose_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution", execution_purpose="review")
        with pytest.raises(RunValidationError, match="EXECUTION_SNAPSHOT_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution"))

    async def test_task_execution_missing_department(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(
            db,
            ctx,
            purpose="task_execution",
            department_task_id=None,
            employee_task_id=ctx["employee_task_id"],
            work_item_id=ctx["employee_task_id"],
        )
        with pytest.raises(RunValidationError, match="EXECUTION_SNAPSHOT_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution"))

    async def test_merge_task_required(self, db, published_profile):
        ctx = await _base(db, published_profile)
        # standard employee task (task_kind != 'merge') -> MERGE_TASK_REQUIRED
        snap = await _snapshots(
            db,
            ctx,
            purpose="merge",
            work_item_id=ctx["employee_task_id"],
        )
        with pytest.raises(RunValidationError, match="MERGE_TASK_REQUIRED"):
            await start(db, **_start_kwargs(ctx, snap, "merge"))

    async def test_company_plan_scope_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(
            db,
            ctx,
            purpose="company_plan",
            employee_task_id=ctx["employee_task_id"],
            work_item_id=ctx["company_task_id"],
        )
        with pytest.raises(RunValidationError, match="RUN_SCOPE_MISMATCH"):
            await start(db, **_start_kwargs(ctx, snap, "company_plan"))

    async def test_interactive_turn_scope_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(
            db,
            ctx,
            purpose="interactive_turn",
            employee_task_id=ctx["employee_task_id"],
            work_item_id=ctx["conversation_id"],
        )
        with pytest.raises(RunValidationError, match="RUN_SCOPE_MISMATCH"):
            await start(db, **_start_kwargs(ctx, snap, "interactive_turn"))

    async def test_work_item_required(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(
            db,
            ctx,
            purpose="review",
            work_item_id=str(uuid.uuid4()),
        )
        with pytest.raises(RunValidationError, match="WORK_ITEM_REQUIRED"):
            await start(db, **_start_kwargs(ctx, snap, "review", work_item_id=None))

    async def test_review_work_item_not_found(self, db, published_profile):
        ctx = await _base(db, published_profile)
        missing = str(uuid.uuid4())
        snap = await _snapshots(db, ctx, purpose="review", work_item_id=missing)
        with pytest.raises(RunValidationError, match="WORK_ITEM_NOT_FOUND"):
            await start(db, **_start_kwargs(ctx, snap, "review", work_item_id=missing))

    async def test_review_work_item_scope_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        other_task = await _add_company_task(db, ctx)
        artifact_id = await _add_artifact(db, ctx, company_task_id=other_task)
        assignment_id = await _add_review_assignment(db, ctx, artifact_id=artifact_id)
        snap = await _snapshots(db, ctx, purpose="review", work_item_id=assignment_id)
        with pytest.raises(RunValidationError, match="WORK_ITEM_SCOPE_MISMATCH"):
            await start(db, **_start_kwargs(ctx, snap, "review", work_item_id=assignment_id))

    async def test_reviewer_scope_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        other_employee = await _add_employee(db, ctx)
        artifact_id = await _add_artifact(db, ctx)
        assignment_id = await _add_review_assignment(
            db, ctx, artifact_id=artifact_id, reviewer_employee_id=other_employee
        )
        snap = await _snapshots(db, ctx, purpose="review", work_item_id=assignment_id)
        with pytest.raises(RunValidationError, match="REVIEWER_SCOPE_MISMATCH"):
            await start(db, **_start_kwargs(ctx, snap, "review", work_item_id=assignment_id))

    async def test_work_item_param_scope_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        with pytest.raises(RunValidationError, match="WORK_ITEM_SCOPE_MISMATCH"):
            await start(db, **_start_kwargs(ctx, snap, "task_execution", work_item_id=str(uuid.uuid4())))

    async def test_execution_snapshot_work_item_mismatch(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(
            db,
            ctx,
            purpose="company_plan",
            availability_work_item_id=str(uuid.uuid4()),
        )
        with pytest.raises(RunValidationError, match="EXECUTION_SNAPSHOT_INVALID"):
            await start(db, **_start_kwargs(ctx, snap, "company_plan"))


# ---------------------------------------------------------------------------
# start() happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStartHappyPaths:
    async def _assert_run_created(self, db, result, *, purpose, work_item_type):
        run = await (await db.execute("SELECT * FROM agent_runs WHERE id=?", (result["run_id"],))).fetchone()
        queue = await (
            await db.execute("SELECT * FROM runtime_queue WHERE run_id=?", (result["run_id"],))
        ).fetchone()
        event = await (
            await db.execute("SELECT * FROM agent_run_events WHERE run_id=?", (result["run_id"],))
        ).fetchone()
        outbox = await (
            await db.execute("SELECT * FROM outbox_events WHERE topic='run.queued'")
        ).fetchone()
        assert result["status"] == "queued"
        assert run["run_purpose"] == purpose
        assert queue["work_item_type"] == work_item_type
        assert event["event_type"] == "run.queued"
        assert outbox["status"] == "pending"

    async def test_task_execution_happy(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        result = await start(db, **_start_kwargs(ctx, snap, "task_execution"))
        await self._assert_run_created(db, result, purpose="task_execution", work_item_type="employee_task")

    async def test_merge_happy(self, db, published_profile):
        ctx = await _base(db, published_profile)
        merge_task_id = await _add_employee_task(db, ctx, task_kind="merge")
        snap = await _snapshots(db, ctx, purpose="merge", work_item_id=merge_task_id, employee_task_id=merge_task_id)
        result = await start(db, **_start_kwargs(ctx, snap, "merge"))
        await self._assert_run_created(db, result, purpose="merge", work_item_type="merge")

    async def test_company_plan_happy_api_model(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(
            db,
            ctx,
            purpose="company_plan",
            binding_json='{"api_model": "gpt-4o", "adapter_type": "api_model"}',
        )
        result = await start(
            db,
            **_start_kwargs(
                ctx,
                snap,
                "company_plan",
                model_id="gpt-4o",
                adapter_type="api_model",
            ),
        )
        await self._assert_run_created(db, result, purpose="company_plan", work_item_type="company_plan")

    async def test_summary_happy_no_tz_expiry(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="summary", expires_at="2099-01-01T00:00:00")
        result = await start(db, **_start_kwargs(ctx, snap, "summary"))
        await self._assert_run_created(db, result, purpose="summary", work_item_type="summary")

    async def test_interactive_turn_happy(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="interactive_turn")
        result = await start(db, **_start_kwargs(ctx, snap, "interactive_turn"))
        await self._assert_run_created(db, result, purpose="interactive_turn", work_item_type="interactive_turn")

    async def test_review_happy_claude(self, db, published_profile):
        ctx = await _base(db, published_profile)
        artifact_id = await _add_artifact(db, ctx)
        assignment_id = await _add_review_assignment(db, ctx, artifact_id=artifact_id)
        snap = await _snapshots(
            db,
            ctx,
            purpose="review",
            work_item_id=assignment_id,
            binding_json='{"agent_cli": "claude_code"}',
        )
        result = await start(
            db,
            **_start_kwargs(
                ctx,
                snap,
                "review",
                model_id="claude_code",
                adapter_type="claude_code",
                work_item_id=assignment_id,
            ),
        )
        await self._assert_run_created(db, result, purpose="review", work_item_type="review")

    async def test_verification_happy(self, db, published_profile):
        ctx = await _base(db, published_profile)
        artifact_id = await _add_artifact(db, ctx)
        snap = await _snapshots(db, ctx, purpose="verification", work_item_id=artifact_id)
        result = await start(db, **_start_kwargs(ctx, snap, "verification", work_item_id=artifact_id))
        await self._assert_run_created(db, result, purpose="verification", work_item_type="verification")

    async def test_repair_happy(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="repair", work_item_id=str(uuid.uuid4()))
        artifact_id = await _add_artifact(db, ctx)
        assignment_id = await _add_review_assignment(db, ctx, artifact_id=artifact_id)
        reviewer_run_id = await _add_agent_run(
            db, ctx, snap=snap, run_purpose="repair", work_item_id=str(uuid.uuid4())
        )
        report_id = await _add_review_report(
            db, ctx, assignment_id=assignment_id, artifact_id=artifact_id, reviewer_run_id=reviewer_run_id
        )
        issue_id = await _add_review_issue(db, ctx, report_id=report_id)
        snap = await _snapshots(db, ctx, purpose="repair", work_item_id=issue_id)
        result = await start(db, **_start_kwargs(ctx, snap, "repair", work_item_id=issue_id))
        await self._assert_run_created(db, result, purpose="repair", work_item_type="repair")


# ---------------------------------------------------------------------------
# cancel / resume / get_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLifecycle:
    async def test_cancel_delegates(self, db, published_profile):
        from unittest.mock import AsyncMock, patch

        ctx = await _base(db, published_profile)
        with patch(
            "ibreeze.runtime.service.cancel_run",
            new=AsyncMock(return_value={"status": "cancelled"}),
        ) as cancel_run:
            result = await cancel(db, ctx["company_id"], "run-1", reason="user request")
        cancel_run.assert_awaited_once_with(db, ctx["company_id"], "run-1")
        assert result["status"] == "cancelled"
        assert result["reason"] == "user request"

    async def test_resume_delegates(self, db, published_profile):
        from unittest.mock import AsyncMock, patch

        ctx = await _base(db, published_profile)
        with patch(
            "ibreeze.runtime.service.resume_run",
            new=AsyncMock(return_value={"status": "running"}),
        ) as resume_run:
            result = await resume(db, ctx["company_id"], "run-1")
        resume_run.assert_awaited_once_with(db, ctx["company_id"], "run-1")
        assert result["status"] == "running"
        assert result["resumed_at"]

    async def test_get_status_found(self, db, published_profile):
        ctx = await _base(db, published_profile)
        snap = await _snapshots(db, ctx, purpose="task_execution")
        created = await start(db, **_start_kwargs(ctx, snap, "task_execution"))
        status = await get_status(db, ctx["company_id"], created["run_id"])
        assert status["run_purpose"] == "task_execution"
        assert status["status"] == "queued"

    async def test_get_status_not_found(self, db, published_profile):
        ctx = await _base(db, published_profile)
        with pytest.raises(RunNotFoundError, match="Run .* not found"):
            await get_status(db, ctx["company_id"], "missing-run")
