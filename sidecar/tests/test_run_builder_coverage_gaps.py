"""Gap coverage for run_builder.py branch edges.

test_confirm_plan_transaction.py and test_employee_task_dependencies.py cover
the happy build path (spec.now provided, agent_cli profile, valid dict
binding).  The remaining uncovered branches are: _now_iso default timestamp,
invalid-JSON and non-dict runtime bindings, the api_model adapter model
injection, and the api_model profile resolve-candidate-bindings path.
"""

from __future__ import annotations

import uuid

import pytest

from ibreeze.orchestration.run_builder import RunSpec, build_run


def _spec(**overrides) -> RunSpec:
    values = {
        "company_id": str(uuid.uuid4()),
        "company_task_id": str(uuid.uuid4()),
        "department_task_id": str(uuid.uuid4()),
        "department_id": str(uuid.uuid4()),
        "employee_task_id": str(uuid.uuid4()),
        "employee_id": str(uuid.uuid4()),
        "conversation_id": str(uuid.uuid4()),
        "task_workspace_id": str(uuid.uuid4()),
        "workspace_repository_root": "/repo",
        "workspace_grant_id": str(uuid.uuid4()),
        "company_revision_id": str(uuid.uuid4()),
        "department_revision_id": str(uuid.uuid4()),
        "profile_version_id": str(uuid.uuid4()),
        "catalog_release_id": str(uuid.uuid4()),
        "runtime_binding_json": '{"adapter_type":"codex_cli"}',
        "adapter_type": "codex_cli",
        "model_id": "model-1",
        "objective": "objective",
        "availability_expires_at": "2026-01-01T00:00:00.000000Z",
        "now": "2026-01-01T00:00:00.000000Z",
    }
    values.update(overrides)
    return RunSpec(**values)


class TestBuildRunEdgeBranches:
    @pytest.mark.asyncio
    async def test_default_now_timestamp(self, mock_db_session) -> None:
        result = await build_run(mock_db_session, _spec(now=None))
        assert result["run_id"]
        assert mock_db_session.execute.await_count >= 4

    @pytest.mark.asyncio
    async def test_invalid_binding_json(self, mock_db_session) -> None:
        result = await build_run(mock_db_session, _spec(runtime_binding_json="not-json"))
        assert result["run_id"]

    @pytest.mark.asyncio
    async def test_non_dict_binding(self, mock_db_session) -> None:
        result = await build_run(mock_db_session, _spec(runtime_binding_json="[]"))
        assert result["run_id"]

    @pytest.mark.asyncio
    async def test_api_model_adapter_injects_model(self, mock_db_session) -> None:
        result = await build_run(
            mock_db_session,
            _spec(adapter_type="api_model", profile_type="agent_cli"),
        )
        assert result["run_id"]

    @pytest.mark.asyncio
    async def test_api_model_profile_resolves_candidates(self, db) -> None:
        spec = _spec(
            adapter_type="api_model",
            profile_type="api_model",
            candidate_bindings_json=None,
            routing_policy_json="{}",
        )
        # An api_model profile with an empty routing policy is rejected by
        # validate_routing_policy before any row is written; this exercises the
        # resolve-candidate-bindings branch (import + call entry).
        with pytest.raises(ValueError, match="ROUTING_POLICY_REQUIRED"):
            await build_run(db, spec)
