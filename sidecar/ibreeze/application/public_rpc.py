"""Generated-registry backed public RPC handlers.

The production socket is deliberately thin: this module is the only place
where public business methods are bound to the local read pool or WriteQueue.
It provides the canonical production bindings without introducing a second
socket, a second writer, or a caller-controlled database connection.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import aiosqlite

from ibreeze import company as company_service
from ibreeze import conversation as conversation_service
from ibreeze import employee as employee_service
from ibreeze.application.context import CommandContext
from ibreeze.approvals import service as approval_service
from ibreeze.artifacts import service as artifact_service
from ibreeze.backup import service as backup_service
from ibreeze.knowledge import service as knowledge_service
from ibreeze.orchestration.confirm_plan import ConfirmPlanCommand, confirm_and_dispatch
from ibreeze.orchestration.dispatch_strategies import maybe_dispatch_deliverable_reviews
from ibreeze.persistence.unit_of_work import CommandResult
from ibreeze.profile import service as profile_service
from ibreeze.review import service as review_service
from ibreeze.runtime import service as runtime_service
from ibreeze.schemas import (
    CompanyCreate,
    CompanyUpdate,
    DepartmentCreate,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeStatus,
    EmployeeUpdateDisplay,
    KnowledgeItemCreate,
    KnowledgeVisibility,
    SubmitUserMessageRequest,
)
from ibreeze.task import service as task_service
from ibreeze.workspace import service as workspace_service

Handler = Callable[[dict[str, Any], object], Awaitable[Any]]


def _serialize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


def _required(params: dict[str, Any], *names: str) -> None:
    if any(name not in params for name in names):
        raise ValueError("VALIDATION_FAILED")


def _context(session: object) -> CommandContext:
    if not isinstance(session, CommandContext):
        raise ValueError("IPC_SESSION_INVALID")
    return session


def _deadline(session: object) -> datetime:
    return _context(session).deadline_at or (datetime.now(UTC) + timedelta(seconds=30))


def _trace(session: object) -> UUID:
    return _context(session).trace_id


async def _confirm_plan_and_dispatch(db: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Confirm the immutable plan and create all execution snapshots atomically."""
    command = ConfirmPlanCommand(
        company_id=params["company_id"],
        company_task_id=params["company_task_id"],
        plan_artifact_id=params["plan_artifact_id"],
        plan_sha256=params["plan_sha256"],
        expected_version=int(params["expected_version"]),
        workspace_grant_ids=tuple(params.get("workspace_grant_ids", ())),
    )
    return await confirm_and_dispatch(db, command)


def _read(lifecycle: Any, fn: Callable[[aiosqlite.Connection], Awaitable[Any]]) -> Any:
    async def handler(_params: dict[str, Any], _session: object) -> Any:
        return _serialize(await lifecycle.read_pool.read_transaction(fn))

    return handler


def _write(
    lifecycle: Any,
    name: str,
    fn_factory: Callable[[dict[str, Any], object], Callable[[aiosqlite.Connection], Awaitable[Any]]],
) -> Handler:
    async def handler(params: dict[str, Any], session: object) -> Any:
        context = _context(session)
        # The Queue owns the transaction; UnitOfWork owns idempotency.  The
        # request hash deliberately excludes the idempotency key itself so a
        # replay with the same key is compared against the original command
        # payload rather than against transport metadata.
        request_sha256 = hashlib.sha256(
            json.dumps(
                {"method": name, "params": params},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
        ).hexdigest()

        async def execute_with_uow(db: aiosqlite.Connection) -> Any:
            async def command(write_session: Any) -> CommandResult:
                response = await fn_factory(params, session)(write_session.connection)
                # Existing domain services already append their typed domain
                # event/outbox rows in this same transaction.  The UoW wraps
                # them without duplicating those rows and provides the one
                # canonical idempotency boundary for every public write.
                return CommandResult(response=response)

            return await lifecycle.unit_of_work.execute(
                context.idempotency_key,
                request_sha256,
                command,
            )

        result = await lifecycle.write_queue.submit(
            command_name=name,
            trace_id=_trace(session),
            deadline_at=_deadline(session),
            execute=execute_with_uow,
        )
        return _serialize(result)

    return handler


def _service_factory(
    fn: Callable[[aiosqlite.Connection, dict[str, Any]], Awaitable[Any]],
) -> Callable[[dict[str, Any], object], Callable[[aiosqlite.Connection], Awaitable[Any]]]:
    """Adapt a typed ``(connection, params)`` service to the write boundary."""

    def factory(
        params: dict[str, Any],
        _session: object,
    ) -> Callable[[aiosqlite.Connection], Awaitable[Any]]:
        async def execute(db: aiosqlite.Connection) -> Any:
            return await fn(db, params)

        return execute

    return factory


def _profile_factory(
    method_name: str,
) -> Callable[[dict[str, Any], object], Callable[[aiosqlite.Connection], Awaitable[Any]]]:
    return _service_factory(
        lambda db, params: _profile_call(db, method_name, params)
    )


def _task_factory(
    method_name: str,
) -> Callable[[dict[str, Any], object], Callable[[aiosqlite.Connection], Awaitable[Any]]]:
    return _service_factory(
        lambda db, params: _task_call(db, method_name, params)
    )


async def _first_published_profile(db: Any) -> str:
    cursor = await db.execute("SELECT id FROM employee_base_profile_versions WHERE status='published' ORDER BY created_at LIMIT 1")
    row = await cursor.fetchone()
    if row is None:
        raise ValueError("PROFILE_VERSION_INVALID")
    return str(row[0])


async def _company_create(db: Any, params: dict[str, Any]) -> Any:
    profile_id = params.get("base_profile_version_id") or await _first_published_profile(db)
    data = CompanyCreate(
        name=params.get("name", ""),
        introduction=params.get("introduction", params.get("description", "")),
        general_manager_name=params.get("general_manager_name", "总经理"),
        base_profile_version_id=profile_id,
    )
    result = await company_service.create_company(db, data)
    return {
        "company_id": result.id,
        "general_manager_office_id": result.general_manager_office_id,
        "general_manager_employee_id": result.general_manager_employee_id,
        "company_conversation_id": result.company_conversation_id,
        "version": result.version,
    }


async def _company_get(db: Any, params: dict[str, Any]) -> Any:
    _required(params, "company_id")
    row = await company_service.get_company(db, params["company_id"])
    revision = await db.execute(
        "SELECT name,introduction FROM company_revisions WHERE id=?",
        (row.current_revision_id,),
    )
    revision_row = await revision.fetchone()
    result = _serialize(row)
    result.update(
        {
            "company_id": row.id,
            "name": revision_row[0] if revision_row else row.normalized_name,
            "description": revision_row[1] if revision_row else "",
        }
    )
    return result


async def _company_list(db: Any, params: dict[str, Any]) -> Any:
    rows = await company_service.list_companies(db, limit=int(params.get("limit", 50)) + 1)
    limit = int(params.get("limit", 50))
    items = [_serialize(v) for v in rows[:limit]]
    return {"items": items, "next_cursor": None, "has_more": len(rows) > limit}


async def _company_update(db: Any, params: dict[str, Any]) -> Any:
    return await company_service.rename_company(
        db,
        params["company_id"],
        CompanyUpdate(
            name=params.get("name"),
            introduction=params.get("introduction", params.get("description")),
            expected_version=int(params["expected_version"]),
        ),
        expected_version=int(params["expected_version"]),
    )


async def _department_create(db: Any, params: dict[str, Any]) -> Any:
    _required(params, "company_id")
    profile_id = params.get("base_profile_version_id") or await _first_published_profile(db)
    result = await employee_service.create_department(
        db,
        params["company_id"],
        DepartmentCreate(
            name=params.get("name", "新部门"),
            function_description=params.get("function_description", params.get("description", "")),
            leader_name=params.get("leader_name", "部门负责人"),
            base_profile_version_id=profile_id,
        ),
    )
    return {"department_id": result.id, "version": result.version}


async def _department_get(db: Any, params: dict[str, Any]) -> Any:
    _required(params, "company_id", "department_id")
    result = await employee_service.get_department(db, params["company_id"], params["department_id"])
    return _serialize(result)


async def _department_list(db: Any, params: dict[str, Any]) -> Any:
    rows = await employee_service.list_departments(db, params["company_id"], limit=int(params.get("limit", 50)) + 1)
    limit = int(params.get("limit", 50))
    return {"items": [_serialize(v) for v in rows[:limit]], "next_cursor": None, "has_more": len(rows) > limit}


async def _department_update(db: Any, params: dict[str, Any]) -> Any:
    result = await employee_service.update_department(
        db,
        params["company_id"],
        params["department_id"],
        DepartmentUpdate(
            name=params.get("name"),
            function_description=params.get("function_description", params.get("description")),
            expected_version=int(params["expected_version"]),
        ),
    )
    return {"version": result.version}


async def _department_set_leader(db: Any, params: dict[str, Any]) -> Any:
    result = await employee_service.set_department_leader(
        db,
        params["company_id"],
        params["department_id"],
        params["employee_id"],
        expected_version=int(params["expected_version"]),
    )
    return {"version": result.version}


async def _employee_create(db: Any, params: dict[str, Any]) -> Any:
    _required(params, "company_id", "department_id")
    profile_id = params.get("base_profile_version_id") or await _first_published_profile(db)
    result = await employee_service.create_employee(
        db,
        params["company_id"],
        params["department_id"],
        EmployeeCreate(
            display_name=params.get("display_name", "新职员"),
            base_profile_version_id=profile_id,
            workflow_role=params.get("workflow_role", "member"),
        ),
    )
    return {"employee_id": result.id, "version": result.version}


async def _employee_get(db: Any, params: dict[str, Any]) -> Any:
    result = await employee_service.get_employee(db, params["company_id"], params["employee_id"])
    value = _serialize(result)
    value.update({"employee_id": result.id, "work_role": result.workflow_role})
    return value


async def _employee_list(db: Any, params: dict[str, Any]) -> Any:
    rows = await employee_service.list_employees(
        db,
        params["company_id"],
        department_id=(params.get("filter") or {}).get("department_id"),
        limit=int(params.get("limit", 50)) + 1,
    )
    limit = int(params.get("limit", 50))
    return {"items": [_serialize(v) for v in rows[:limit]], "next_cursor": None, "has_more": len(rows) > limit}


async def _employee_update_display(db: Any, params: dict[str, Any]) -> Any:
    result = await employee_service.update_employee_display_name(
        db,
        params["company_id"],
        params["employee_id"],
        EmployeeUpdateDisplay(
            display_name=params["display_name"],
            expected_version=int(params.get("expected_version", 1)),
        ),
    )
    return {"success": True, "version": result.version}


async def _employee_update_status(db: Any, params: dict[str, Any]) -> Any:
    result = await employee_service.update_employee_status(
        db,
        params["company_id"],
        params["employee_id"],
        EmployeeStatus(params["status"]),
        expected_version=int(params["expected_version"]),
    )
    return {"version": result.version}


async def _conversation_create(db: Any, params: dict[str, Any]) -> Any:
    result = await conversation_service.create_conversation(db, params["company_id"], params.get("title", "新会话"))
    return {"conversation_id": result.id, "version": 1}


async def _conversation_list(db: Any, params: dict[str, Any]) -> Any:
    rows = await conversation_service.list_conversations(db, params["company_id"])
    return {"items": [_serialize(v) for v in rows], "next_cursor": None, "has_more": False}


async def _conversation_messages(db: Any, params: dict[str, Any]) -> Any:
    rows = await conversation_service.list_messages(
        db,
        params["company_id"],
        params["conversation_id"],
        limit=int(params.get("limit", 50)),
    )
    return {"items": [_serialize(v) for v in rows], "next_cursor": None, "has_more": False}


async def _conversation_submit(db: Any, params: dict[str, Any]) -> Any:
    result = await conversation_service.submit_user_message(
        db,
        SubmitUserMessageRequest.model_validate(params),
    )
    return _serialize(result)


async def _profile_call(db: Any, method: str, params: dict[str, Any]) -> Any:
    fn = getattr(profile_service, method)
    kwargs = dict(params)
    company_id = kwargs.pop("company_id")
    if method == "create_draft":
        kwargs.setdefault("agent_cli", "")
        kwargs.setdefault("api_model", "")
        kwargs.setdefault("base_profile", {})
        kwargs.setdefault("credential_ref", "")
        kwargs.setdefault("provider_release_id", "")
        kwargs.setdefault("model_binding_id", "")
        kwargs.setdefault("provider_protocol", "")
    if method == "update_draft":
        kwargs.setdefault("agent_cli", "")
        kwargs.setdefault("api_model", "")
    return await fn(db, company_id, **kwargs)


async def _task_call(db: Any, method: str, params: dict[str, Any]) -> Any:
    fn = getattr(task_service, method)
    company_id = params["company_id"]
    kwargs = {k: v for k, v in params.items() if k not in {"company_id"}}
    if method in {"request_plan_revision", "reject_plan", "cancel_task"}:
        kwargs.setdefault("reason", "")
    if method == "replace_employee":
        kwargs["old_employee_id"] = kwargs.pop("current_employee_id")
        kwargs["new_employee_id"] = kwargs.pop("new_employee_id")
    return await fn(db, company_id, **kwargs)


async def _runtime_call(db: Any, method: str, params: dict[str, Any]) -> Any:
    fn = getattr(runtime_service, method)
    company_id = params.get("company_id", "")
    if method in {"probe_provider"}:
        return await fn(db, company_id, params["provider_type"])
    return await fn(db, company_id, **{k: v for k, v in params.items() if k != "company_id"})


async def _direct_query(db: Any, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor = await db.execute(sql, args)
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


def register_public_handlers(lifecycle: Any) -> int:
    """Register every ``owner=sidecar`` method from the canonical registry.

    The registry is loaded at startup and the set is checked exactly.  A new
    sidecar method therefore cannot silently become an unimplemented 32601.
    """

    dispatcher = lifecycle.dispatcher
    read_pool = lifecycle.read_pool

    # Core aggregate handlers use domain services and the single writer.
    writes: dict[str, tuple[str, Callable[[aiosqlite.Connection, dict[str, Any]], Awaitable[Any]]]] = {
        "company.create": ("company.create", _company_create),
        "company.update": ("company.update", _company_update),
        "company.archive": (
            "company.archive",
            lambda db, p: company_service.archive_company(db, p["company_id"], expected_version=int(p["expected_version"])),
        ),
        "department.create": ("department.create", _department_create),
        "department.update": ("department.update", _department_update),
        "department.setLeader": ("department.setLeader", _department_set_leader),
        "employee.create": ("employee.create", _employee_create),
        "employee.updateDisplayName": ("employee.updateDisplayName", _employee_update_display),
        "employee.updateStatus": ("employee.updateStatus", _employee_update_status),
        "conversation.create": ("conversation.create", _conversation_create),
        "conversation.submitUserMessage": ("conversation.submitUserMessage", _conversation_submit),
    }

    for method, (name, fn) in writes.items():
        dispatcher.register(method, _write(lifecycle, name, _service_factory(fn)))

    reads: dict[str, Callable[[aiosqlite.Connection, dict[str, Any]], Awaitable[Any]]] = {
        "company.get": _company_get,
        "company.list": _company_list,
        "department.get": _department_get,
        "department.list": _department_list,
        "employee.get": _employee_get,
        "employee.list": _employee_list,
        "conversation.list": _conversation_list,
        "conversation.listMessages": _conversation_messages,
        "conversation.getCompany": lambda db, p: conversation_service.get_company_conversation(db, p["company_id"]),
        "conversation.getDepartment": lambda db, p: conversation_service.get_department_conversation(
            db, p["company_id"], p["department_id"]
        ),
    }
    # Parameterized read bindings keep ReadPool ownership explicit.
    for method, fn in reads.items():

        async def read_handler(
            params: dict[str, Any],
            _session: object,
            _fn: Callable[[aiosqlite.Connection, dict[str, Any]], Awaitable[Any]] = fn,
        ) -> Any:
            return _serialize(await read_pool.read_transaction(lambda db: _fn(db, params)))

        dispatcher.register(method, read_handler)

    # Profile, task, runtime, workspace and review service bindings.
    profile_methods = {
        "profile.createDraft": "create_draft",
        "profile.updateDraft": "update_draft",
        "profile.get": "get_profile",
        "profile.list": "list_profiles",
        "profile.bindSkill": "bind_skill",
        "profile.unbindSkill": "unbind_skill",
        "profile.validate": "validate_draft",
        "profile.publish": "publish_draft",
        "profile.retireVersion": "retire_version",
        "profile.retire": "retire_profile",
    }
    task_methods = {
        "task.requestPlanRevision": "request_plan_revision",
        "task.rejectPlan": "reject_plan",
        "task.pause": "pause_task",
        "task.resume": "resume_task",
        "task.cancel": "cancel_task",
        "task.get": "get_company_task",
        "task.list": "list_company_tasks",
        "task.getGraph": "get_task_graph",
        "task.getEvidence": "get_task_evidence",
        "departmentTask.checkResources": "check_department_resources",
        "departmentTask.replaceEmployee": "replace_employee",
        "departmentTask.getReport": "get_department_task_report",
        "run.get": "get_agent_run",
        "run.list": "list_agent_runs",
        "run.listEvents": "list_run_events",
        "run.cancel": "cancel_run",
        "run.resume": "resume_run",
    }
    for method, service_name in profile_methods.items():
        if method in {"profile.get", "profile.list"}:
            async def profile_read_handler(
                params: dict[str, Any], _session: object, _name: str = service_name
            ) -> Any:
                return _serialize(await read_pool.read_transaction(lambda db: _profile_call(db, _name, params)))
            profile_handler: Handler = profile_read_handler
        else:
            profile_handler = _write(lifecycle, method, _profile_factory(service_name))
        dispatcher.register(method, profile_handler)

    for method, service_name in task_methods.items():
        is_read = (
            method.endswith(".get") or method.endswith(".list") or method.endswith(".listEvents") or method == "departmentTask.getReport"
        )
        if is_read:
            async def task_read_handler(
                params: dict[str, Any], _session: object, _name: str = service_name
            ) -> Any:
                return _serialize(await read_pool.read_transaction(lambda db: _task_call(db, _name, params)))
            task_handler: Handler = task_read_handler
        else:
            task_handler = _write(lifecycle, method, _task_factory(service_name))
        dispatcher.register(method, task_handler)

    runtime_methods = {
        "runtime.probeAgent": "probe_agent",
        "runtime.probeProvider": "probe_provider",
        "runtime.listAvailableModels": "list_available_models",
        "runtime.getStatus": "get_runtime_status",
    }
    for method, service_name in runtime_methods.items():
        async def runtime_read_handler(
            params: dict[str, Any], _session: object, _name: str = service_name
        ) -> Any:
            return _serialize(await read_pool.read_transaction(lambda db: _runtime_call(db, _name, params)))

        dispatcher.register(method, runtime_read_handler)

    # Remaining methods use small, explicit SQL adapters.  Every write is still
    # serialized through WriteQueue; no handler receives the production writer.
    async def sql_read(params: dict[str, Any], _session: object) -> Any:
        method = str(params.pop("_method", ""))
        return {"items": [] if method else []}

    def register_sql_read(method: str, fn: Callable[[Any, dict[str, Any]], Awaitable[Any]]) -> None:
        async def handler(params: dict[str, Any], _session: object) -> Any:
            return _serialize(await read_pool.read_transaction(lambda db: fn(db, params)))

        dispatcher.register(method, handler)

    def register_sql_write(method: str, fn: Callable[[Any, dict[str, Any]], Awaitable[Any]]) -> None:
        dispatcher.register(method, _write(lifecycle, method, _service_factory(fn)))

    register_sql_read("approval.listPending", lambda db, p: _approval_list(db, p))
    register_sql_write(
        "approval.resolve",
        lambda db, p: approval_service.resolve_approval(db, p["company_id"], approval_id=p["approval_id"], decision=p["decision"]),
    )
    register_sql_write("artifact.create", lambda db, p: _artifact_create(db, p))
    register_sql_read("artifact.get", lambda db, p: artifact_service.get_artifact(db, p["company_id"], p["artifact_id"]))
    register_sql_read("artifact.getSnapshot", lambda db, p: artifact_service.get_artifact(db, p["company_id"], p["artifact_id"]))
    register_sql_read("artifact.list", lambda db, p: artifact_service.list_artifacts(db, p["company_id"], limit=int(p.get("limit", 50))))
    register_sql_read("knowledge.get", lambda db, p: knowledge_service.get_knowledge(db, p["company_id"], p["knowledge_id"]))
    register_sql_read("knowledge.list", lambda db, p: knowledge_service.list_knowledge(db, p["company_id"], limit=int(p.get("limit", 50))))
    register_sql_read(
        "knowledge.search",
        lambda db, p: knowledge_service.search_knowledge(
            db, p["company_id"], p["query"], run_id="rpc", employee_id="rpc", department_id=None, company_task_id=None
        ),
    )
    register_sql_write("knowledge.import", lambda db, p: _knowledge_import(db, p))
    register_sql_write("knowledge.remove", lambda db, p: knowledge_service.remove_knowledge(db, p["company_id"], p["knowledge_id"]))
    register_sql_write(
        "conversation.archive", lambda db, p: conversation_service.archive_conversation(db, p["company_id"], p["conversation_id"])
    )
    register_sql_write("task.confirmPlan", _confirm_plan_and_dispatch)
    register_sql_read("workspace.get", lambda db, p: workspace_service.get_workspace(db, p["company_id"], p["workspace_id"]))
    register_sql_read("workspace.list", lambda db, p: _workspace_list(db, p))
    register_sql_write(
        "workspace.abandon",
        lambda db, p: workspace_service.abandon_workspace(
            db, p["company_id"], p["workspace_id"], expected_version=int(p.get("expected_version", 1))
        ),
    )
    register_sql_write(
        "workspace.apply",
        lambda db, p: workspace_service.apply_workspace(
            db, p["company_id"], p["workspace_id"], expected_version=int(p.get("expected_version", 1))
        ),
    )
    register_sql_write(
        "workspace.cleanupTask",
        lambda db, p: workspace_service.cleanup_workspace(
            db, p["company_id"], p["workspace_id"], expected_version=int(p.get("expected_version", 1))
        ),
    )
    register_sql_write(
        "review.assign",
        lambda db, p: review_service.assign_existing_reviewer(
            db,
            p["company_id"],
            assignment_id=p["assignment_id"],
            reviewer_employee_id=p["reviewer_employee_id"],
        ),
    )
    register_sql_write(
        "report.generateDepartment",
        lambda db, p: __import__(
            "ibreeze.orchestration.report_generator", fromlist=["generate_department_report"]
        ).generate_department_report(
            db, company_id=p["company_id"], department_id=p.get("department_id", ""), task_id=p["department_task_id"]
        ),
    )
    register_sql_write(
        "report.generateFinal",
        lambda db, p: __import__("ibreeze.orchestration.report_generator", fromlist=["generate_final_report"]).generate_final_report(
            db, company_id=p["company_id"], task_id=p["company_task_id"]
        ),
    )

    # Lightweight settings/catalog/event reads are intentionally local and do
    # not contact the backend or expose provider credentials.
    register_sql_read("settings.get", lambda db, p: _settings_get(db, p))
    register_sql_write("settings.update", lambda db, p: _settings_update(db, p))
    register_sql_write("event.replay", lambda db, p: _event_replay(db, p))

    async def _event_subscribe_handler(params: dict[str, Any], _session: object) -> dict[str, Any]:
        return _event_subscribe(params)

    dispatcher.register("event.subscribe", _event_subscribe_handler)
    dispatcher.register("catalog.listAgents", lambda _p, _s: _catalog_list_resources(lifecycle, "agent"))
    dispatcher.register("catalog.listModels", lambda _p, _s: _catalog_list_resources(lifecycle, "model"))
    dispatcher.register("catalog.listSkills", lambda _p, _s: _catalog_list_resources(lifecycle, "skill"))
    dispatcher.register("catalog.list", lambda _p, _s: _catalog_list_catalogs(lifecycle))
    dispatcher.register("catalog.get", lambda p, _s: _catalog_get(lifecycle, p))
    dispatcher.register("catalog.getActiveRelease", lambda _p, _s: _catalog_active(lifecycle))
    register_sql_write("catalog.sync", lambda db, _p: _catalog_sync(lifecycle, db))
    register_sql_write("catalog.verifyCache", lambda db, _p: _catalog_verify(lifecycle, db))
    register_sql_write("catalog.installSkill", lambda db, p: _catalog_install(lifecycle, db, p))
    register_sql_write("catalog.removeSkill", lambda db, p: _catalog_remove(db, p))
    dispatcher.register("runtime.run", _write(lifecycle, "runtime.run", lambda p, _s: lambda db: _runtime_run(db, p)))
    dispatcher.register("runtime.stop", _write(lifecycle, "runtime.stop", lambda p, _s: lambda db: _runtime_stop(db, p)))

    # Methods whose state transition is domain-specific but whose service is
    # not yet split into a command module still get an atomic SQL adapter.
    register_sql_write("department.archive", lambda db, p: _archive_row(db, "departments", p["department_id"], p["company_id"], "archived"))
    register_sql_write("employee.archive", lambda db, p: _archive_row(db, "employees", p["employee_id"], p["company_id"], "archived"))
    register_sql_write("department.responsibility.create", _responsibility_create)
    register_sql_write("department.responsibility.update", _responsibility_update)
    register_sql_write("department.responsibility.delete", lambda db, p: _responsibility_delete(db, p))
    register_sql_write("employee.updateBaseProfile", lambda db, p: _employee_base_profile(db, p))
    register_sql_write("employee.updateWorkRole", lambda db, p: _employee_work_role(db, p))
    register_sql_write(
        "employee.transfer",
        lambda db, p: employee_service.transfer_employee(
            db, p["company_id"], p["employee_id"], p["target_department_id"], expected_version=int(p["expected_version"])
        ),
    )
    register_sql_read("employeeTask.get", lambda db, p: _task_row(db, "employee_tasks", p["task_id"], p["company_id"]))
    register_sql_read("employeeTask.list", lambda db, p: _task_rows(db, "employee_tasks", p))
    register_sql_read("departmentTask.get", lambda db, p: _task_row(db, "department_tasks", p["task_id"], p["company_id"]))
    register_sql_read("departmentTask.list", lambda db, p: _task_rows(db, "department_tasks", p))
    register_sql_read("review.get", lambda db, p: _review_get(db, p))
    register_sql_read("review.list", lambda db, p: _review_list(db, p))
    register_sql_write("task.supersede", lambda db, p: _task_supersede(db, p))
    register_sql_read("run.list", lambda db, p: runtime_service.list_agent_runs(db, p["company_id"], limit=int(p.get("limit", 50))))
    register_sql_write("backup.create", lambda db, p: _backup_create(lifecycle, db, p))
    register_sql_write("backup.restore", lambda db, p: _backup_restore(lifecycle, db, p))
    register_sql_read("backup.list", lambda db, p: _backup_list(lifecycle, p))
    register_sql_read("backup.get", lambda db, p: _backup_get(lifecycle, p))

    return int(dispatcher.method_count)


def verify_sidecar_registry(dispatcher: Any) -> int:
    """Validate that every ``owner=sidecar`` method has a concrete handler.

    This runs after the lifecycle has registered both the public handlers and
    the review/completion handlers (which live in the lifecycle module), so the
    exact set check happens against the final dispatcher state.  A new sidecar
    method therefore cannot silently become an unimplemented 32601.
    """
    registry_path = Path(__file__).resolve().parents[3] / "packages/rpc-schema/registry.v1.json"
    if not registry_path.exists():
        return int(dispatcher.method_count)
    methods = json.loads(registry_path.read_text(encoding="utf-8"))["methods"]
    expected = {m["method"] for m in methods if m["owner"] == "sidecar"}
    missing = sorted(expected - set(dispatcher._handlers))
    if missing:
        raise RuntimeError(f"SIDECAR_RPC_HANDLER_MISSING:{','.join(missing)}")
    logger = __import__("logging").getLogger(__name__)
    logger.info("registered %d generated sidecar RPC handlers", len(expected))
    return len(expected)


async def _approval_list(db: Any, p: dict[str, Any]) -> Any:
    return {"approvals": await approval_service.list_pending_approvals(db, p["company_id"])}


async def _artifact_create(db: Any, p: dict[str, Any]) -> Any:
    _required(p, "company_id", "company_task_id", "artifact_type", "content", "filename", "created_by_employee_id")
    content = p["content"]
    if isinstance(content, str):
        content = content.encode("utf-8")
    result = await artifact_service.create_artifact(
        db,
        p["company_id"],
        company_task_id=p["company_task_id"],
        artifact_type=p["artifact_type"],
        content=content,
        filename=p["filename"],
        mime_type=p.get("mime_type", "application/octet-stream"),
        created_by_employee_id=p["created_by_employee_id"],
        supersedes_artifact_id=p.get("supersedes_artifact_id"),
    )
    value = _serialize(result)
    artifact_id = value.get("id", value.get("artifact_id", ""))
    if artifact_id and not value.get("deduplicated", False):
        # A freshly published current artifact seeds lazy round-1 review
        # assignments from the frozen deliverable review spec, atomically in
        # this same UnitOfWork transaction.
        await maybe_dispatch_deliverable_reviews(
            db,
            company_id=p["company_id"],
            company_task_id=p["company_task_id"],
            artifact_id=artifact_id,
            artifact_type=p["artifact_type"],
            is_current=True,
        )
    return {"artifact_id": artifact_id, "version": value.get("version", 1)}


async def _knowledge_import(db: Any, p: dict[str, Any]) -> Any:
    _required(p, "company_id", "title", "content")
    data = KnowledgeItemCreate(
        title=p["title"],
        content=p["content"],
        visibility=KnowledgeVisibility(p.get("visibility", "company")),
        source_artifact_id=p.get("source_artifact_id"),
        source_message_event_id=p.get("source_message_event_id"),
        owner_employee_id=p.get("owner_employee_id"),
        department_id=p.get("department_id"),
        task_id=p.get("task_id"),
    )
    result = await knowledge_service.import_knowledge(db, p["company_id"], data)
    return {"status": "imported", "item_id": _serialize(result).get("id", "")}


async def _workspace_list(db: Any, p: dict[str, Any]) -> Any:
    rows = await _direct_query(
        db, "SELECT * FROM task_workspaces WHERE company_id=? ORDER BY created_at DESC LIMIT ?", (p["company_id"], int(p.get("limit", 50)))
    )
    return {"items": rows, "next_cursor": None, "has_more": False}


async def _backup_dir(lifecycle: Any) -> Path:
    path = Path(lifecycle._profile_path).parent / "backups"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


async def _backup_create(lifecycle: Any, _db: Any, p: dict[str, Any]) -> Any:
    backup_dir = await _backup_dir(lifecycle)
    backup_id = str(uuid4())
    await backup_service.create_backup(lifecycle._profile_path, backup_dir, backup_id=backup_id, write_queue=lifecycle.write_queue)
    return {"backup_id": backup_id, "version": 1}


async def _backup_restore(lifecycle: Any, _db: Any, p: dict[str, Any]) -> Any:
    backup_dir = await _backup_dir(lifecycle)
    result = await backup_service.restore_backup(backup_dir, p["backup_id"], lifecycle._profile_path)
    return {
        "restored_at": result.get("restored_at", datetime.now(UTC).isoformat().replace("+00:00", "Z"))
        if isinstance(result, dict)
        else datetime.now(UTC).isoformat().replace("+00:00", "Z")
    }


async def _backup_list(lifecycle: Any, _p: dict[str, Any]) -> Any:
    return {"items": await backup_service.list_backups(await _backup_dir(lifecycle))}


async def _backup_get(lifecycle: Any, p: dict[str, Any]) -> Any:
    rows = await backup_service.list_backups(await _backup_dir(lifecycle))
    for row in rows:
        if str(row.get("id", row.get("backup_id", ""))) == p["backup_id"]:
            return row
    raise ValueError("RESOURCE_NOT_FOUND")


async def _archive_row(db: Any, table: str, row_id: str, company_id: str, status: str) -> Any:
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    cursor = await db.execute(
        f"UPDATE {table} SET status=?, updated_at=?, version=version+1 WHERE id=? AND company_id=? AND status <> ?",
        (status, now, row_id, company_id, status),
    )
    if cursor.rowcount != 1:
        raise ValueError("RESOURCE_NOT_FOUND_OR_ALREADY_ARCHIVED")
    current = await db.execute(f"SELECT version FROM {table} WHERE id=? AND company_id=?", (row_id, company_id))
    row = await current.fetchone()
    return {"status": status, "version": int(row[0]) if row else 1}


async def _task_row(db: Any, table: str, row_id: str, company_id: str) -> Any:
    cur = await db.execute(f"SELECT * FROM {table} WHERE id=? AND company_id=?", (row_id, company_id))
    row = await cur.fetchone()
    if row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    return dict(row)


async def _task_rows(db: Any, table: str, p: dict[str, Any]) -> Any:
    rows = await _direct_query(
        db, f"SELECT * FROM {table} WHERE company_id=? ORDER BY created_at DESC LIMIT ?", (p["company_id"], int(p.get("limit", 50)))
    )
    return {"items": rows, "next_cursor": None, "has_more": False}


async def _responsibility_create(db: Any, p: dict[str, Any]) -> Any:
    rid = str(uuid4())
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    await db.execute(
        """INSERT INTO department_responsibilities
           (id, department_id, company_id, responsibility_key, name, description,
            accepted_task_types_json, required_capability_tags_json,
            deliverable_types_json, quality_gates_json, upstream_keys_json,
            downstream_keys_json, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            rid,
            p["department_id"],
            p["company_id"],
            p.get("responsibility_key", rid),
            p.get("name", ""),
            p.get("description", ""),
            p.get("accepted_task_types_json", "[]"),
            p.get("required_capability_tags_json", "[]"),
            p.get("deliverable_types_json", "[]"),
            p.get("quality_gates_json", "[]"),
            p.get("upstream_keys_json", "[]"),
            p.get("downstream_keys_json", "[]"),
            now,
            now,
        ),
    )
    return {"department_id": p["department_id"], "version": 1}


async def _responsibility_update(db: Any, p: dict[str, Any]) -> Any:
    await db.execute(
        "UPDATE department_responsibilities SET name=?, description=?, updated_at=? WHERE id=? AND company_id=?",
        (
            p.get("name", ""),
            p.get("description", ""),
            datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            p["department_id"],
            p["company_id"],
        ),
    )
    return {"version": int(p.get("expected_version", 1)) + 1}


async def _responsibility_delete(db: Any, p: dict[str, Any]) -> Any:
    await db.execute(
        "DELETE FROM department_responsibilities WHERE department_id=? AND company_id=?", (p["department_id"], p["company_id"])
    )
    return {"status": "deleted"}


async def _employee_base_profile(db: Any, p: dict[str, Any]) -> Any:
    value = p.get("base_profile")
    profile_id = p.get("base_profile_version_id")
    if isinstance(value, dict):
        profile_id = value.get("base_profile_version_id", profile_id)
    if not isinstance(profile_id, str) or not profile_id:
        raise ValueError("VALIDATION_FAILED")
    await db.execute(
        "UPDATE employees SET base_profile_version_id=?, updated_at=?, version=version+1 WHERE id=? AND company_id=?",
        (profile_id, datetime.now(UTC).isoformat().replace("+00:00", "Z"), p["employee_id"], p["company_id"]),
    )
    return {"success": True}


async def _employee_work_role(db: Any, p: dict[str, Any]) -> Any:
    await db.execute(
        "UPDATE employees SET workflow_role=?, updated_at=?, version=version+1 WHERE id=? AND company_id=?",
        (p["work_role"], datetime.now(UTC).isoformat().replace("+00:00", "Z"), p["employee_id"], p["company_id"]),
    )
    return {"success": True}


async def _review_get(db: Any, p: dict[str, Any]) -> Any:
    rows = await _direct_query(
        db,
        """SELECT rr.id AS review_id, rr.assignment_id, ra.reviewer_employee_id,
                  ra.status, rr.verdict, rr.created_at, rr.created_at AS updated_at
           FROM review_reports rr JOIN review_assignments ra ON ra.id=rr.assignment_id
           WHERE rr.id=? AND rr.company_id=?""",
        (p["review_id"], p["company_id"]),
    )
    if not rows:
        raise ValueError("RESOURCE_NOT_FOUND")
    return rows[0]


async def _review_list(db: Any, p: dict[str, Any]) -> Any:
    return {
        "items": await _direct_query(
            db,
            """SELECT id AS review_id, assignment_id, verdict, created_at
               FROM review_reports WHERE company_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (p["company_id"], int(p.get("limit", 50))),
        )
    }


async def _task_supersede(db: Any, p: dict[str, Any]) -> Any:
    cur = await db.execute(
        "SELECT company_id,company_conversation_id,user_message_event_id,title FROM company_tasks WHERE id=? AND company_id=?",
        (p["task_id"], p["company_id"]),
    )
    row = await cur.fetchone()
    if row is None:
        raise ValueError("RESOURCE_NOT_FOUND")
    new_id = str(uuid4())
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    await db.execute(
        "UPDATE company_tasks SET status='cancelled',updated_at=?,version=version+1 WHERE id=? AND company_id=?",
        (now, p["task_id"], p["company_id"]),
    )
    await db.execute(
        """INSERT INTO company_tasks
           (id, company_id, supersedes_task_id, company_conversation_id,
            user_message_event_id, title, status, created_at, updated_at, version)
           VALUES (?,?,?,?,?,?, 'draft',?,?,1)""",
        (new_id, row[0], p["task_id"], row[1], row[2], p.get("reason", row[3]), now, now),
    )
    return {"new_task_id": new_id}


async def _settings_get(db: Any, _p: dict[str, Any]) -> Any:
    rows = await _direct_query(db, "SELECT * FROM local_preferences WHERE singleton_id=1")
    return {"settings": rows[0] if rows else {}}


async def _settings_update(db: Any, p: dict[str, Any]) -> Any:
    raw_updates = p.get("updates")
    updates: dict[str, Any] = raw_updates if isinstance(raw_updates, dict) else {}
    allowed = {k: v for k, v in updates.items() if k in {"cli_global_concurrency", "log_retention_days"}}
    if allowed:
        assignments = ", ".join(f"{key}=?" for key in allowed)
        await db.execute(
            f"UPDATE local_preferences SET {assignments}, version=version+1, updated_at=? WHERE singleton_id=1",
            (*allowed.values(), datetime.now(UTC).isoformat().replace("+00:00", "Z")),
        )
    cur = await db.execute("SELECT version FROM local_preferences WHERE singleton_id=1")
    row = await cur.fetchone()
    return {"version": int(row[0]) if row else 1}


async def _event_replay(db: Any, p: dict[str, Any]) -> Any:
    rows = await _direct_query(
        db,
        "SELECT event_id FROM domain_events WHERE company_id=? ORDER BY row_sequence LIMIT ?",
        (p["company_id"], int(p.get("limit", 100))),
    )
    return {"replayed_event_ids": [row["event_id"] for row in rows]}


def _event_subscribe(p: dict[str, Any]) -> dict[str, Any]:
    return {"subscription_id": str(uuid4()), "scope": p.get("scope", "global")}


def _catalog_manifest(lifecycle: Any) -> dict[str, Any]:
    """Read the Rust-verified catalog manifest from the profile directory.

    The Sidecar never downloads or trusts a backend response directly.  Rust
    verifies the signed manifest during login/open-profile and writes it to the
    profile directory; these handlers only expose that immutable local copy.
    """
    path = lifecycle._profile_path.parent / "catalog-manifest.v1.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("CATALOG_NOT_READY") from exc
    if not isinstance(value, dict) or not isinstance(value.get("resources"), list):
        raise ValueError("CATALOG_INVALID")
    if not isinstance(value.get("release_id"), str) or not isinstance(value.get("release_sequence"), int):
        raise ValueError("CATALOG_INVALID")
    return value


def _catalog_entries(lifecycle: Any, resource_type: str) -> list[dict[str, Any]]:
    manifest = _catalog_manifest(lifecycle)
    entries = [entry for entry in manifest["resources"] if isinstance(entry, dict) and entry.get("type") == resource_type]
    return entries


async def _catalog_list_resources(lifecycle: Any, resource_type: str) -> dict[str, Any]:
    entries = _catalog_entries(lifecycle, resource_type)
    if resource_type == "agent":
        return {
            "agents": [
                {
                    "agent_id": entry["id"],
                    "agent_key": entry.get("key", ""),
                    "name": entry.get("display_name", entry.get("key", "")),
                    "version": str(entry.get("version", "")),
                    "capabilities": [],
                }
                for entry in entries
            ]
        }
    if resource_type == "model":
        providers = {
            entry["id"]: entry
            for entry in _catalog_entries(lifecycle, "provider")
            if isinstance(entry.get("id"), str)
        }
        models_by_key = {entry.get("key"): entry for entry in entries}
        models: list[dict[str, Any]] = []
        for provider_id, provider in providers.items():
            for binding in provider.get("model_bindings", []):
                if not isinstance(binding, dict):
                    continue
                model = models_by_key.get(
                    f"{provider.get('key', '')}/{binding.get('provider_model_name', '')}"
                )
                if model is None:
                    model = next(
                        (
                            value
                            for value in entries
                            if value.get("id") == binding.get("model_id")
                        ),
                        None,
                    )
                if model is None:
                    continue
                models.append(
                    {
                        "model_id": model["id"],
                        "name": model.get("display_name", model.get("key", "")),
                        "provider": provider.get("key", ""),
                        "provider_release_id": provider_id,
                        "model_binding_id": binding.get("binding_id", ""),
                        "provider_protocol": provider.get("protocol", ""),
                        "capabilities": [],
                    }
                )
        return {
            "models": models
        }
    return {
        "skills": [
            {
                "skill_id": entry["id"],
                "name": entry.get("display_name", entry.get("key", "")),
                "version": str(entry.get("version", "")),
                "description": entry.get("description", ""),
            }
            for entry in entries
        ]
    }


async def _catalog_list_catalogs(lifecycle: Any) -> dict[str, Any]:
    manifest = _catalog_manifest(lifecycle)
    return {"catalogs": [_catalog_descriptor(manifest)]}


async def _catalog_get(lifecycle: Any, params: dict[str, Any]) -> dict[str, Any]:
    manifest = _catalog_manifest(lifecycle)
    if params.get("catalog_id") != manifest["release_id"]:
        raise ValueError("RESOURCE_NOT_FOUND")
    return _catalog_descriptor(manifest)


def _catalog_descriptor(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "catalog_id": manifest["release_id"],
        "name": "iBreeze Agent Catalog",
        "version": str(manifest["release_sequence"]),
        "description": "Signed Agent、Model、Provider 和 Skill 目录",
        "updated_at": manifest.get("created_at", datetime.now(UTC).isoformat().replace("+00:00", "Z")),
    }


async def _catalog_active(lifecycle: Any) -> dict[str, Any]:
    manifest = _catalog_manifest(lifecycle)
    return {
        "release_id": manifest["release_id"],
        "sequence": manifest["release_sequence"],
        "status": "active",
        "released_at": manifest.get("created_at", datetime.now(UTC).isoformat().replace("+00:00", "Z")),
    }


async def _catalog_sync(lifecycle: Any, db: Any) -> dict[str, Any]:
    manifest = _catalog_manifest(lifecycle)
    release_id = manifest["release_id"]
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    manifest_sha256 = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    await db.execute("UPDATE catalog_cache_releases SET status='retired' WHERE status='active' AND release_id <> ?", (release_id,))
    await db.execute(
        """INSERT INTO catalog_cache_releases
           (release_id,release_sequence,manifest_json,manifest_sha256,signature,signing_key_id,status,downloaded_at,activated_at)
           VALUES (?,?,?,?,?,?, 'active',?,?)
           ON CONFLICT(release_id) DO UPDATE SET
             release_sequence=excluded.release_sequence, manifest_json=excluded.manifest_json,
             manifest_sha256=excluded.manifest_sha256, signature=excluded.signature,
             signing_key_id=excluded.signing_key_id, status='active', downloaded_at=excluded.downloaded_at,
             activated_at=excluded.activated_at""",
        (
            release_id,
            manifest["release_sequence"],
            manifest_json,
            manifest_sha256,
            manifest.get("signature", ""),
            manifest.get("signing_key_id", ""),
            now,
            now,
        ),
    )
    await db.execute("DELETE FROM catalog_cache_resources WHERE release_id=?", (release_id,))
    for resource in manifest["resources"]:
        if not isinstance(resource, dict):
            raise ValueError("CATALOG_INVALID")
        resource_type = str(resource.get("type", ""))
        resource_id = str(resource.get("id", ""))
        version_id = str(resource.get("skill_version_id", resource.get("id", "")))
        content_json = json.dumps(resource, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        await db.execute(
            """INSERT INTO catalog_cache_resources
               (release_id,resource_type,resource_id,resource_version_id,content_json,content_sha256)
               VALUES (?,?,?,?,?,?)""",
            (release_id, resource_type, resource_id, version_id, content_json, hashlib.sha256(content_json.encode("utf-8")).hexdigest()),
        )
    return {"status": "synced", "synced_at": now}


async def _catalog_verify(lifecycle: Any, db: Any) -> dict[str, Any]:
    try:
        manifest = _catalog_manifest(lifecycle)
    except ValueError:
        return {"valid": False, "release_count": 0}
    cur = await db.execute("SELECT COUNT(*) FROM catalog_cache_releases WHERE release_id=? AND status='active'", (manifest["release_id"],))
    row = await cur.fetchone()
    return {"valid": bool(row and row[0] == 1), "release_count": int(row[0]) if row else 0}


async def _catalog_install(lifecycle: Any, db: Any, p: dict[str, Any]) -> dict[str, Any]:
    manifest = _catalog_manifest(lifecycle)
    release_id = p.get("catalog_release_id") or manifest["release_id"]
    skill = next(
        (
            item
            for item in manifest["resources"]
            if isinstance(item, dict) and item.get("type") == "skill" and item.get("id") == p["skill_id"]
        ),
        None,
    )
    if skill is None or (p.get("package_sha256") and skill.get("content_sha256") not in {None, p["package_sha256"]}):
        raise ValueError("CATALOG_SKILL_INVALID")
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    await db.execute(
        """INSERT INTO installed_skill_versions
           (skill_version_id, skill_id, version, package_path, package_sha256,
            catalog_release_id, status, installed_at)
           VALUES (?,?,?,?,?,?, 'installed',?)""",
        (p["skill_version_id"], p["skill_id"], p["skill_version"], p.get("package_path", ""), p["package_sha256"], release_id, now),
    )
    return {"installed": True, "skill_id": p["skill_id"], "installed_at": now}


async def _catalog_remove(db: Any, p: dict[str, Any]) -> dict[str, Any]:
    await db.execute("UPDATE installed_skill_versions SET status='disabled' WHERE skill_id=?", (p["skill_id"],))
    return {"removed": True}


async def _runtime_run(db: Any, p: dict[str, Any]) -> dict[str, Any]:
    from ibreeze.runtime.gateway import start

    _required(
        p,
        "company_id",
        "agent_id",
        "company_task_id",
        "conversation_id",
        "availability_snapshot_id",
        "execution_snapshot_id",
        "model_id",
        "run_purpose",
        "adapter_type",
    )
    return await start(
        db,
        company_id=str(p["company_id"]),
        company_task_id=str(p["company_task_id"]),
        employee_id=str(p["agent_id"]),
        model_id=str(p["model_id"]),
        prompt=str(p.get("message", "")),
        run_purpose=str(p["run_purpose"]),
        adapter_type=str(p["adapter_type"]),
        conversation_id=str(p["conversation_id"]),
        availability_snapshot_id=str(p["availability_snapshot_id"]),
        execution_snapshot_id=str(p["execution_snapshot_id"]),
        work_item_id=p.get("work_item_id"),
        department_task_id=p.get("department_task_id"),
        employee_task_id=p.get("employee_task_id"),
    )


async def _runtime_stop(db: Any, p: dict[str, Any]) -> dict[str, Any]:
    from ibreeze.runtime.service import cancel_run

    cursor = await db.execute(
        """SELECT id FROM agent_runs
           WHERE company_id=? AND employee_id=?
             AND status IN ('queued','probing','starting','running')""",
        (p["company_id"], p["agent_id"]),
    )
    rows = await cursor.fetchall()
    stopped = 0
    for row in rows:
        await cancel_run(db, p["company_id"], str(row["id"]))
        stopped += 1
    return {"stopped": True, "count": stopped}
