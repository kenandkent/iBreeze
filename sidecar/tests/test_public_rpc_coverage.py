"""Cover public_rpc branches the main suite does not reach.

Targets: ``_profile_public_response`` filters, ``_profile_list_response``,
the dead ``_read``/``sql_read`` adapters (called directly), the
credential preflight decision tree, the ``create_draft`` routing-policy
default, the ``profile.list``/``profile.publish`` handler branches, the
bytes-content artifact create path and the catalog model-list guards.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from ibreeze.application import public_rpc as rpc
from ibreeze.application.context import CommandContext
from ibreeze.rpc.dispatcher import Dispatcher

C1 = "00000000-0000-0000-0000-000000000001"
T1 = "00000000-0000-0000-0000-000000000002"


def _ctx() -> CommandContext:
    return CommandContext(
        trace_id=uuid4(),
        ipc_session_id=uuid4(),
        window_session_id=None,
        idempotency_key=str(uuid4()),
    )


def _full_routing_model(**overrides) -> dict:
    base = {
        "type": "model",
        "id": "model-1",
        "key": "openai/gpt-4o",
        "display_name": "GPT-4o",
        "version": "1",
        "routing_tier": 1,
        "quality_prior": 0.9,
        "tool_reliability_prior": 0.8,
        "latency_prior_ms": 120,
        "model_family": "gpt",
        "model_vendor": "openai",
        "architecture_class": "decoder",
        "supports_reasoning": True,
        "reasoning_levels": ["low"],
        "input_price_microusd_per_million": 5,
        "output_price_microusd_per_million": 15,
        "routing_enabled": True,
    }
    base.update(overrides)
    return base


class _FakeReadPool:
    def __init__(self, db) -> None:
        self._db = db

    async def read_transaction(self, fn):
        return await fn(self._db)


class _FakeWriteQueue:
    def __init__(self, db) -> None:
        self._db = db

    async def submit(self, *, command_name, trace_id, deadline_at, execute):
        return await execute(self._db)


class _FakeUnitOfWork:
    def __init__(self, db) -> None:
        self._db = db

    async def execute(self, idempotency_key, request_sha256, command):
        result = await command(SimpleNamespace(connection=self._db))
        return result.response


class _FakeLifecycle:
    def __init__(self, profile_path: Path, db) -> None:
        self._profile_path = profile_path
        self.dispatcher = Dispatcher()
        self.read_pool = _FakeReadPool(db)
        self.write_queue = _FakeWriteQueue(db)
        self.unit_of_work = _FakeUnitOfWork(db)

    @property
    def method_count(self) -> int:
        return self.dispatcher.method_count


def _preflight_lifecycle(record):
    """Lifecycle whose read_transaction returns a scripted draft row."""
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=record)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=cursor)

    async def read_transaction(fn):
        return await fn(db)

    return SimpleNamespace(read_pool=SimpleNamespace(read_transaction=read_transaction))


class TestProfilePublicResponse:
    def test_skips_non_dict_version(self) -> None:
        out = rpc._profile_public_response({"id": "p1", "versions": [42, {"id": "ok"}]})
        assert [v["id"] for v in out["versions"]] == ["ok"]

    def test_skips_non_str_version_id(self) -> None:
        out = rpc._profile_public_response({"id": "p1", "versions": [{"id": 7}, {"id": "ok"}]})
        assert [v["id"] for v in out["versions"]] == ["ok"]

    def test_non_list_versions_ignored(self) -> None:
        out = rpc._profile_public_response({"id": "p1", "versions": "nope"})
        assert out["versions"] == []

    def test_falls_back_to_first_version_when_current_missing(self) -> None:
        out = rpc._profile_public_response(
            {
                "id": "p1",
                "name": "Draft",
                "version": 3,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "current_version_id": "missing",
                "versions": [{"id": "v1", "status": "draft"}],
            }
        )
        assert out["current_version_id"] == "v1"
        assert out["status"] == "draft"


class TestProfileListResponse:
    def test_projects_profiles_with_and_without_current(self) -> None:
        with_current = {
            "id": "p1",
            "name": "A",
            "version": 2,
            "created_at": "t",
            "updated_at": "t",
            "current_version_id": "v2",
            "versions": [
                {"id": "v1", "status": "draft"},
                {"id": "v2", "status": "published"},
            ],
        }
        without_current = {
            "id": "p2",
            "name": "B",
            "version": 1,
            "created_at": "t",
            "updated_at": "t",
            "current_version_id": None,
            "versions": [],
        }
        out = rpc._profile_list_response([with_current, without_current])
        items = out["profiles"]
        assert len(items) == 2
        assert items[0]["current_version_status"] == "published"
        assert items[0]["status"] == "published"
        assert items[1]["current_version_status"] == items[1]["status"]


class TestReadAdapter:
    async def test_read_serializes_transaction_result(self) -> None:
        lc = _FakeLifecycle(Path("/tmp/p.db"), None)
        when = datetime(2026, 1, 1, tzinfo=UTC)

        async def fn(_db):
            return {"nested": {"value": 1}, "when": when}

        handler = rpc._read(lc, fn)
        result = await handler({}, None)
        assert result["nested"]["value"] == 1
        assert result["when"].endswith("Z")


class TestPreflightProfileCredentials:
    @patch("ibreeze.application.public_rpc.ReverseRpcClient")
    async def test_returns_for_non_api_model(self, client_cls) -> None:
        lc = _preflight_lifecycle(("cli_model", "{}"))
        await rpc._preflight_profile_credentials(lc, {"draft_id": "d1", "company_id": C1}, None)
        client_cls.assert_not_called()

    @patch("ibreeze.application.public_rpc.ReverseRpcClient")
    async def test_returns_when_draft_missing(self, client_cls) -> None:
        lc = _preflight_lifecycle(None)
        await rpc._preflight_profile_credentials(lc, {"draft_id": "d1", "company_id": C1}, None)
        client_cls.assert_not_called()

    @patch("ibreeze.application.public_rpc.ReverseRpcClient")
    async def test_raises_for_invalid_policy_json(self, client_cls) -> None:
        lc = _preflight_lifecycle(("api_model", "{not-json"))
        with pytest.raises(ValueError, match="ROUTING_POLICY_INVALID"):
            await rpc._preflight_profile_credentials(lc, {"draft_id": "d1", "company_id": C1}, None)

    @patch("ibreeze.application.public_rpc.ReverseRpcClient")
    async def test_skips_non_dict_candidates(self, client_cls) -> None:
        client = Mock()
        client.call = AsyncMock(return_value={"state": "ready", "active_secret_version": 1})
        client_cls.return_value = client
        lc = _preflight_lifecycle(("api_model", '{"candidates": ["not-a-dict"]}'))
        await rpc._preflight_profile_credentials(lc, {"draft_id": "d1", "company_id": C1}, None)
        client.call.assert_not_called()

    @patch("ibreeze.application.public_rpc.ReverseRpcClient")
    async def test_raises_when_credential_not_ready(self, client_cls) -> None:
        client = Mock()
        client.call = AsyncMock(return_value={"state": "provisioning"})
        client_cls.return_value = client
        lc = _preflight_lifecycle(("api_model", '{"candidates": [{"credential_ref": "c1", "provider_release_id": "p1"}]}'))
        with pytest.raises(ValueError, match="CREDENTIAL_NOT_READY"):
            await rpc._preflight_profile_credentials(lc, {"draft_id": "d1", "company_id": C1}, None)

    @patch("ibreeze.application.public_rpc.ReverseRpcClient")
    async def test_raises_on_secret_version_mismatch(self, client_cls) -> None:
        client = Mock()
        client.call = AsyncMock(return_value={"state": "ready", "active_secret_version": 3})
        client_cls.return_value = client
        policy = {"candidates": [{"credential_ref": "c1", "provider_release_id": "p1", "credential_secret_version": 5}]}
        lc = _preflight_lifecycle(("api_model", json.dumps(policy)))
        with pytest.raises(ValueError, match="CREDENTIAL_VERSION_MISMATCH"):
            await rpc._preflight_profile_credentials(lc, {"draft_id": "d1", "company_id": C1}, None)

    @patch("ibreeze.application.public_rpc.ReverseRpcClient")
    async def test_accepts_matching_secret_version(self, client_cls) -> None:
        client = Mock()
        client.call = AsyncMock(return_value={"state": "ready", "active_secret_version": 5})
        client_cls.return_value = client
        policy = {"candidates": [{"credential_ref": "c1", "provider_release_id": "p1", "credential_secret_version": 5}]}
        lc = _preflight_lifecycle(("api_model", json.dumps(policy)))
        await rpc._preflight_profile_credentials(lc, {"draft_id": "d1", "company_id": C1}, None)
        client.call.assert_awaited_once()


class TestProfileCallRoutingPolicy:
    async def test_create_draft_defaults_routing_policy_from_base_profile(self) -> None:
        with patch.object(rpc.profile_service, "create_draft", new=AsyncMock(return_value={"id": "p1"})) as m:
            result = await rpc._profile_call(
                None,
                "create_draft",
                {
                    "company_id": C1,
                    "api_model": "gpt-4o",
                    "base_profile": {"routing_policy": {"tier": 1}},
                },
            )
        assert result == {"id": "p1"}
        kwargs = m.await_args.kwargs
        assert kwargs["routing_policy"] == {"tier": 1}


class TestProfileReadHandlerBranches:
    def _registered(self) -> _FakeLifecycle:
        lc = _FakeLifecycle(Path("/tmp/p.db"), None)
        rpc.register_public_handlers(lc)
        return lc

    async def test_list_profiles_branch(self) -> None:
        lc = self._registered()
        with patch.object(
            rpc.profile_service,
            "list_profiles",
            new=AsyncMock(
                return_value=[
                    {
                        "id": "p1",
                        "name": "A",
                        "version": 1,
                        "created_at": "t",
                        "updated_at": "t",
                        "current_version_id": "v1",
                        "versions": [{"id": "v1", "status": "draft"}],
                    }
                ]
            ),
        ):
            result = await lc.dispatcher._handlers["profile.list"]({"company_id": C1}, None)
        assert result["profiles"][0]["profile_id"] == "p1"

    async def test_default_branch_serializes_other_service(self) -> None:
        lc = self._registered()
        with patch.object(rpc.profile_service, "validate_draft", new=AsyncMock(return_value={"valid": True})) as m:
            result = await lc.dispatcher._handlers["profile.list"]({"company_id": C1}, None, "validate_draft")
        m.assert_awaited_once()
        assert result == {"valid": True}


class TestProfilePublishHandler:
    async def test_publish_preflights_and_delegates(self) -> None:
        lc = _FakeLifecycle(Path("/tmp/p.db"), AsyncMock())
        rpc.register_public_handlers(lc)
        with (
            patch.object(rpc, "_preflight_profile_credentials", new=AsyncMock()) as m_pre,
            patch.object(rpc.profile_service, "publish_draft", new=AsyncMock(return_value={"id": "p1"})) as m_pub,
        ):
            result = await lc.dispatcher._handlers["profile.publish"](
                {"company_id": C1, "base_profile_version_id": "v1", "version": 2},
                _ctx(),
            )
        m_pre.assert_awaited_once()
        m_pub.assert_awaited_once()
        assert result == {"id": "p1"}


class TestArtifactCreate:
    async def test_bytes_content_skips_encode(self) -> None:
        db = AsyncMock()
        with patch.object(rpc.artifact_service, "create_artifact", new=AsyncMock(return_value={})) as m:
            result = await rpc._artifact_create(
                db,
                {
                    "company_id": C1,
                    "company_task_id": T1,
                    "artifact_type": "document",
                    "content": b"raw bytes",
                    "filename": "x.py",
                    "created_by_employee_id": "e1",
                },
            )
        content = m.await_args.kwargs["content"]
        assert isinstance(content, bytes)
        assert result == {"artifact_id": "", "version": 1}


class TestCatalogModelRoutingMetadata:
    def test_rejects_reasoning_levels_without_reasoning_support(self) -> None:
        resource = _full_routing_model(supports_reasoning=False, reasoning_levels=["high"])
        with pytest.raises(ValueError, match="CATALOG_ROUTING_METADATA_MISSING"):
            rpc._validate_catalog_model_routing_metadata(resource)

    def test_accepts_complete_routing_metadata(self) -> None:
        rpc._validate_catalog_model_routing_metadata(_full_routing_model())


class TestCatalogListModelsGuards:
    def _manifest_lifecycle(self, tmp_path, resources) -> _FakeLifecycle:
        (tmp_path / "catalog-manifest.v1.json").write_text(
            json.dumps({"release_id": "rel-1", "release_sequence": 1, "resources": resources}),
            encoding="utf-8",
        )
        return _FakeLifecycle(tmp_path / "p.db", None)

    async def test_skips_non_dict_binding_and_missing_model(self, tmp_path) -> None:
        provider = {
            "type": "provider",
            "id": "prov-1",
            "key": "openai",
            "protocol": "openai",
            "model_bindings": [
                {"binding_id": "b1", "provider_model_name": "gpt-4o", "model_id": "model-1"},
                "not-a-dict",
                {"binding_id": "b3", "provider_model_name": "unknown", "model_id": "model-9"},
            ],
        }
        model = _full_routing_model(id="model-1", key="openai/gpt-4o")
        lc = self._manifest_lifecycle(tmp_path, [provider, model])
        out = await rpc._catalog_list_resources(lc, "model")
        assert len(out["models"]) == 1
        assert out["models"][0]["model_id"] == "model-1"

    async def test_fallback_by_model_id_when_key_missing(self, tmp_path) -> None:
        provider = {
            "type": "provider",
            "id": "prov-1",
            "key": "openai",
            "protocol": "openai",
            "model_bindings": [{"binding_id": "b2", "provider_model_name": "gpt-4o-mini", "model_id": "model-2"}],
        }
        model = _full_routing_model(id="model-2", key="other/gpt-4o-mini", display_name="Mini")
        lc = self._manifest_lifecycle(tmp_path, [provider, model])
        out = await rpc._catalog_list_resources(lc, "model")
        assert len(out["models"]) == 1
        assert out["models"][0]["model_id"] == "model-2"
