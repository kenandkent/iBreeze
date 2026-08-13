"""Additional coverage tests for ibreeze/profile/service.py.

Targets the unreached branches of create_draft / update_draft / list_profiles /
validate_draft / publish_draft / retire_profile, including the api_model
validation and catalog-policy error paths.
"""

from __future__ import annotations

import json
import uuid

import aiosqlite
import pytest

from ibreeze.profile import service as svc
from ibreeze.profile.service import (
    create_draft,
    get_profile,
    list_profiles,
    publish_draft,
    retire_profile,
    update_draft,
    validate_draft,
)


def _sha256(data: str) -> str:
    import hashlib

    return hashlib.sha256(data.encode()).hexdigest()


def _routing_policy() -> dict[str, object]:
    anchor = "11111111-1111-4111-8111-111111111111"
    second = "22222222-2222-4222-8222-222222222222"
    return {
        "schema_version": 1,
        "mode": "smart_single",
        "anchor_candidate_id": anchor,
        "candidates": [
            {
                "candidate_id": anchor,
                "provider_release_id": "33333333-3333-4333-8333-333333333333",
                "model_binding_id": "44444444-4444-4444-8444-444444444444",
                "credential_ref": "55555555-5555-4555-8555-555555555555",
                "enabled": True,
                "eligible_roles": ["single", "fallback"],
                "routing_enabled": True,
            },
            {
                "candidate_id": second,
                "provider_release_id": "66666666-6666-4666-8666-666666666666",
                "model_binding_id": "77777777-7777-4777-8777-777777777777",
                "credential_ref": "88888888-8888-4888-8888-888888888888",
                "enabled": True,
                "eligible_roles": ["single", "fallback"],
                "routing_enabled": True,
            },
        ],
        "fallback_order": [second, anchor],
        "ensemble": {
            "max_proposers": 2,
            "min_successful_proposers": 1,
            "proposer_timeout_seconds": 30,
            "aggregator_timeout_seconds": 60,
            "proposer_max_retries": 0,
        },
    }


async def _setup_profile_tables(
    db: aiosqlite.Connection,
    company_id: str,
    version_id: str,
    profile_id: str,
    release_id: str,
    employee_id: str,
    dept_id: str,
):
    """Insert minimal prerequisite rows for profile tests."""
    now = "2026-01-01T00:00:00Z"
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        rev_id = str(uuid.uuid4())
        dept_rev_id = str(uuid.uuid4())
        conv_id = str(uuid.uuid4())
        dept_conv_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO company_revisions
               (id, company_id, revision_number, name, introduction, content_sha256, created_by_type, created_at)
               VALUES (?, ?, 1, 'Co', 'Intro', ?, 'system', ?)""",
            (rev_id, company_id, _sha256("co"), now),
        )
        await db.execute(
            """INSERT INTO conversations
               (id, company_id, conversation_type, status, created_at)
               VALUES (?, ?, 'department', 'active', ?)""",
            (dept_conv_id, company_id, now),
        )
        await db.execute(
            """INSERT INTO department_revisions
               (id, department_id, company_id, revision_number, name, function_description, content_sha256, created_at)
               VALUES (?, ?, ?, 1, 'Root', 'Root', ?, ?)""",
            (dept_rev_id, dept_id, company_id, _sha256("root"), now),
        )
        await db.execute(
            """INSERT INTO employees
               (id, company_id, department_id, display_name, normalized_display_name,
                base_profile_version_id, workflow_role, status, created_at, updated_at, version)
               VALUES (?, ?, ?, 'GM', 'gm', ?, 'general_manager', 'active', ?, ?, 1)""",
            (employee_id, company_id, dept_id, version_id, now, now),
        )
        await db.execute(
            """INSERT INTO departments
               (id, company_id, department_type, normalized_name, current_revision_id,
                leader_employee_id, department_conversation_id, status, created_at, updated_at, version)
               VALUES (?, ?, 'general_manager_office', 'root', ?, ?, ?, 'active', ?, ?, 1)""",
            (dept_id, company_id, dept_rev_id, employee_id, dept_conv_id, now, now),
        )
        await db.execute(
            """INSERT INTO conversations
               (id, company_id, conversation_type, status, created_at)
               VALUES (?, ?, 'company', 'active', ?)""",
            (conv_id, company_id, now),
        )
        await db.execute(
            """INSERT INTO companies
               (id, normalized_name, current_revision_id, general_manager_office_id,
                general_manager_employee_id, company_conversation_id, status, created_at, updated_at, version)
               VALUES (?, 't', ?, ?, ?, ?, 'active', ?, ?, 1)""",
            (company_id, rev_id, dept_id, employee_id, conv_id, now, now),
        )
        await db.execute(
            """INSERT INTO catalog_cache_releases
               (release_id, release_sequence, manifest_json, manifest_sha256,
                signature, signing_key_id, status, downloaded_at, activated_at)
               VALUES (?, 1, '{}', ?, 'sig', 'key', 'active', ?, ?)""",
            (release_id, _sha256("{}"), now, now),
        )
        await db.execute(
            """INSERT INTO employee_base_profiles
               (id, company_id, name, normalized_name, description, current_version_id,
                status, created_at, updated_at, version)
               VALUES (?, ?, 'Default', 'default', 'Default', ?, 'active', ?, ?, 1)""",
            (profile_id, company_id, version_id, now, now),
        )
        await db.execute(
            """INSERT INTO employee_base_profile_versions
               (id, profile_id, version_number, name, description, profile_type,
                runtime_binding_json, system_prompt, capability_tags_json,
                tool_policy_json, timeout_seconds, max_retries, workspace_policy,
                catalog_release_id, content_sha256, status, created_at, published_at)
               VALUES (?, ?, 1, 'Default v1', 'Default', 'agent_cli', '{"adapter_type":"codex_cli"}',
                       'Act.', '[]', '{}', 300, 2, 'workspace_rw_external_ro', ?, ?,
                       'published', ?, ?)""",
            (version_id, profile_id, release_id, _sha256("v1"), now, now),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


@pytest.fixture
async def profile_env(db: aiosqlite.Connection):
    company_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    profile_id = str(uuid.uuid4())
    release_id = str(uuid.uuid4())
    employee_id = str(uuid.uuid4())
    dept_id = str(uuid.uuid4())
    await _setup_profile_tables(db, company_id, version_id, profile_id, release_id, employee_id, dept_id)
    return {
        "company_id": company_id,
        "version_id": version_id,
        "profile_id": profile_id,
        "release_id": release_id,
        "employee_id": employee_id,
        "dept_id": dept_id,
    }


def _mock_one(monkeypatch, row):
    async def fake_one(_cursor):
        return row

    monkeypatch.setattr(svc, "_one", fake_one)


def _draft_row(**overrides) -> dict[str, object]:
    row = {
        "id": "draft-1",
        "profile_type": "agent_cli",
        "name": "Name",
        "description": "Desc",
        "system_prompt": "Prompt",
        "runtime_binding_json": "{}",
        "routing_policy_json": "{}",
        "catalog_release_id": "release-1",
    }
    row.update(overrides)
    return row


async def _insert_provider(db: aiosqlite.Connection, release_id: str, value) -> None:
    await db.execute(
        """INSERT INTO catalog_cache_resources
           (release_id, resource_type, resource_id, resource_version_id, content_json, content_sha256)
           VALUES (?, 'provider', ?, ?, ?, ?)""",
        (release_id, str(uuid.uuid4()), str(uuid.uuid4()), json.dumps(value), "a" * 64),
    )


@pytest.mark.asyncio
class TestCreateDraftExtra:
    async def test_employee_not_found(self, db, profile_env):
        with pytest.raises(ValueError, match="EMPLOYEE_NOT_FOUND"):
            await create_draft(
                db,
                profile_env["company_id"],
                employee_id="missing-employee",
                agent_cli="codex_cli",
                api_model="",
                base_profile={"name": "X", "description": "Y", "content_sha256": "a" * 64},
            )

    async def test_draft_already_exists(self, db, profile_env, monkeypatch):
        calls = {"n": 0}

        async def fake_one(_cursor):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"id": profile_env["employee_id"]}
            return {"id": "existing-draft"}

        monkeypatch.setattr(svc, "_one", fake_one)
        with pytest.raises(ValueError, match="DRAFT_ALREADY_EXISTS"):
            await create_draft(
                db,
                profile_env["company_id"],
                employee_id=profile_env["employee_id"],
                agent_cli="codex_cli",
                api_model="",
                base_profile={"name": "X", "description": "Y", "content_sha256": "a" * 64},
            )

    async def test_agent_cli_rejects_routing_policy(self, db, profile_env):
        with pytest.raises(ValueError, match="ROUTING_POLICY_FORBIDDEN"):
            await create_draft(
                db,
                profile_env["company_id"],
                employee_id=profile_env["employee_id"],
                agent_cli="codex_cli",
                api_model="",
                base_profile={"name": "X", "description": "Y", "content_sha256": "a" * 64},
                routing_policy=_routing_policy(),
            )


@pytest.mark.asyncio
class TestUpdateDraftExtra:
    async def test_agent_cli_rejects_routing_policy(self, db, profile_env):
        draft = await create_draft(
            db,
            profile_env["company_id"],
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={"name": "X", "description": "Y", "content_sha256": "a" * 64},
        )
        with pytest.raises(ValueError, match="ROUTING_POLICY_FORBIDDEN"):
            await update_draft(
                db,
                profile_env["company_id"],
                draft["version_id"],
                agent_cli="codex_cli",
                api_model="",
                routing_policy=_routing_policy(),
            )

    async def test_api_model_updates_routing_policy(self, db, profile_env):
        draft = await create_draft(
            db,
            profile_env["company_id"],
            employee_id=profile_env["employee_id"],
            agent_cli="",
            api_model="gpt-4o",
            base_profile={"name": "API", "description": "d", "content_sha256": "a" * 64},
            routing_policy=_routing_policy(),
        )
        result = await update_draft(
            db,
            profile_env["company_id"],
            draft["version_id"],
            agent_cli="",
            api_model="gpt-4o",
            routing_policy=_routing_policy(),
        )
        assert result["status"] == "draft"
        ver = await get_profile(db, profile_env["company_id"], draft["profile_id"])
        assert json.loads(ver["versions"][0]["routing_policy_json"])["schema_version"] == 1

    async def test_corrupt_runtime_binding_is_tolerated(self, db, profile_env, monkeypatch):
        _mock_one(monkeypatch, {"profile_type": "agent_cli", "runtime_binding_json": "{not-json"})
        result = await update_draft(
            db,
            profile_env["company_id"],
            "draft-1",
            agent_cli="codex_cli",
            api_model="",
        )
        assert result["status"] == "draft"


@pytest.mark.asyncio
class TestListProfilesExtra:
    async def test_filter_by_employee(self, db, profile_env):
        profiles = await list_profiles(
            db,
            profile_env["company_id"],
            employee_id=profile_env["employee_id"],
        )
        assert any(p["id"] == profile_env["profile_id"] for p in profiles)


@pytest.mark.asyncio
class TestValidateDraftExtra:
    async def test_missing_name_and_description(self, db, profile_env, monkeypatch):
        _mock_one(monkeypatch, _draft_row(name="", description=""))
        result = await validate_draft(db, profile_env["company_id"], "draft-1")
        assert result["valid"] is False
        assert "missing_name" in result["errors"]
        assert "missing_description" in result["errors"]

    async def test_missing_runtime_binding(self, db, profile_env, monkeypatch):
        _mock_one(monkeypatch, _draft_row(runtime_binding_json=""))
        result = await validate_draft(db, profile_env["company_id"], "draft-1")
        assert "missing_runtime_binding" in result["errors"]

    async def test_invalid_runtime_binding(self, db, profile_env, monkeypatch):
        _mock_one(monkeypatch, _draft_row(runtime_binding_json="{bad"))
        result = await validate_draft(db, profile_env["company_id"], "draft-1")
        assert "invalid_runtime_binding" in result["errors"]

    async def test_agent_cli_missing_binding(self, db, profile_env, monkeypatch):
        _mock_one(monkeypatch, _draft_row(profile_type="agent_cli", runtime_binding_json="{}"))
        result = await validate_draft(db, profile_env["company_id"], "draft-1")
        assert "missing_agent_cli" in result["errors"]

    async def test_api_model_invalid_policy_skips_catalog(self, db, profile_env, monkeypatch):
        _mock_one(
            monkeypatch,
            _draft_row(
                profile_type="api_model",
                runtime_binding_json='{"credential_ref":"c","provider_release_id":"p","model_binding_id":"m","provider_protocol":"x"}',
                routing_policy_json='{"candidates":"nope"}',
            ),
        )
        result = await validate_draft(db, profile_env["company_id"], "draft-1")
        assert result["valid"] is False
        assert "ROUTING_POLICY_INVALID" in result["errors"]

    async def test_api_model_invalid_policy_json(self, db, profile_env, monkeypatch):
        _mock_one(
            monkeypatch,
            _draft_row(
                profile_type="api_model",
                runtime_binding_json='{"credential_ref":"c","provider_release_id":"p","model_binding_id":"m","provider_protocol":"x"}',
                routing_policy_json="{bad",
            ),
        )
        result = await validate_draft(db, profile_env["company_id"], "draft-1")
        assert "ROUTING_POLICY_REQUIRED" in result["errors"]

    async def test_api_model_missing_fields_and_catalog_errors(self, db, profile_env):
        draft = await create_draft(
            db,
            profile_env["company_id"],
            employee_id=profile_env["employee_id"],
            agent_cli="",
            api_model="gpt-4o",
            base_profile={
                "name": "API",
                "description": "d",
                "system_prompt": "s",
                "catalog_release_id": profile_env["release_id"],
                "content_sha256": "a" * 64,
            },
            routing_policy=_routing_policy(),
        )
        result = await validate_draft(db, profile_env["company_id"], draft["version_id"])
        assert result["valid"] is False
        for field in ("credential_ref", "provider_release_id", "model_binding_id", "provider_protocol"):
            assert f"missing_{field}" in result["errors"]
        assert any(e.startswith("routing_candidate_outside_release") for e in result["errors"])
        assert any(e.startswith("routing_candidate_disabled") for e in result["errors"])

    async def test_api_model_valid_with_catalog_match(self, db, profile_env):
        release_id = profile_env["release_id"]
        draft = await create_draft(
            db,
            profile_env["company_id"],
            employee_id=profile_env["employee_id"],
            agent_cli="",
            api_model="gpt-4o",
            credential_ref="55555555-5555-4555-8555-555555555555",
            provider_release_id="33333333-3333-4333-8333-333333333333",
            model_binding_id="44444444-4444-4444-8444-444444444444",
            provider_protocol="openai",
            base_profile={
                "name": "API",
                "description": "d",
                "system_prompt": "s",
                "catalog_release_id": release_id,
                "content_sha256": "a" * 64,
            },
            routing_policy=_routing_policy(),
        )
        await _insert_provider(
            db,
            release_id,
            {
                "id": "33333333-3333-4333-8333-333333333333",
                "model_bindings": [{"binding_id": "44444444-4444-4444-8444-444444444444", "routing_enabled": True}],
            },
        )
        await _insert_provider(
            db,
            release_id,
            {
                "id": "66666666-6666-4666-8666-666666666666",
                "model_bindings": [{"binding_id": "77777777-7777-4777-8777-777777777777", "routing_enabled": True}],
            },
        )
        # A provider whose model_bindings entry lacks binding_id exercises the
        # skip branch while building the bindings map.
        await _insert_provider(
            db,
            release_id,
            {"id": "99999999-9999-4999-8999-999999999999", "model_bindings": [{"routing_enabled": True}]},
        )
        # A non-dict provider content exercises the parse-skip branch.
        await _insert_provider(db, release_id, "not-a-dict")
        result = await validate_draft(db, profile_env["company_id"], draft["version_id"])
        assert result["valid"] is True


@pytest.mark.asyncio
class TestPublishDraftExtra:
    async def test_publish_api_model_invalid_raises(self, db, profile_env):
        draft = await create_draft(
            db,
            profile_env["company_id"],
            employee_id=profile_env["employee_id"],
            agent_cli="",
            api_model="gpt-4o",
            base_profile={"name": "API", "description": "d", "content_sha256": "a" * 64},
            routing_policy=_routing_policy(),
        )
        await db.execute(
            "UPDATE employee_base_profile_versions SET routing_policy_json='{}' WHERE id=?",
            (draft["version_id"],),
        )
        with pytest.raises(ValueError, match="PROFILE_NOT_VALID"):
            await publish_draft(db, profile_env["company_id"], draft["version_id"])


@pytest.mark.asyncio
class TestRetireProfileExtra:
    async def test_retire_profile_with_draft(self, db, profile_env, monkeypatch):
        # A real draft row cannot be transitioned to 'retired' (CHECK requires
        # published_at NOT NULL for non-draft rows), so mock the draft lookup to
        # exercise the draft-retirement UPDATE branch; it then matches no real rows.
        calls = {"n": 0}

        async def fake_one(_cursor):
            calls["n"] += 1
            return {"id": "x"} if calls["n"] <= 2 else None

        monkeypatch.setattr(svc, "_one", fake_one)
        result = await retire_profile(db, profile_env["company_id"], profile_env["profile_id"])
        assert result["status"] == "retired"
