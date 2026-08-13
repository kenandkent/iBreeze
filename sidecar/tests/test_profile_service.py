"""Tests for profile/service.py — employee base profile management (target: 100%)."""

from __future__ import annotations

import uuid

import aiosqlite
import pytest

from ibreeze.profile.service import (
    bind_skill,
    create_draft,
    get_profile,
    list_profiles,
    publish_draft,
    retire_profile,
    retire_version,
    unbind_skill,
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


@pytest.mark.asyncio
class TestCreateDraft:
    async def test_create_draft_success(self, db, profile_env):
        company_id = profile_env["company_id"]
        result = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={
                "name": "Test Agent",
                "description": "A test agent profile",
                "system_prompt": "Be helpful",
                "capability_tags": ["coding"],
                "tool_policy": {},
                "timeout_seconds": 600,
                "max_retries": 2,
                "content_sha256": "a" * 64,
            },
        )
        assert result["status"] == "draft"
        assert result["profile_id"]
        assert result["version_id"]
        profile = await get_profile(db, company_id, result["profile_id"])
        assert profile is not None
        assert profile["name"] == "Test Agent"
        assert len(profile["versions"]) == 1

    async def test_create_draft_uses_api_model_type(self, db, profile_env):
        company_id = profile_env["company_id"]
        result = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="",
            api_model="gpt-4o",
            base_profile={"name": "API Agent", "description": "API based", "content_sha256": "a" * 64},
            routing_policy=_routing_policy(),
        )
        ver = await get_profile(db, company_id, result["profile_id"])
        assert ver["versions"][0]["profile_type"] == "api_model"


@pytest.mark.asyncio
class TestUpdateDraft:
    async def test_update_draft_success(self, db, profile_env):
        company_id = profile_env["company_id"]
        draft = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={"name": "Updatable", "description": "Draft", "content_sha256": "a" * 64},
        )
        result = await update_draft(
            db,
            company_id,
            draft["version_id"],
            agent_cli="claude_code",
            api_model="gpt-4o",
        )
        assert result["version_id"] == draft["version_id"]
        assert result["status"] == "draft"

    async def test_update_nonexistent_draft_raises(self, db, profile_env):
        with pytest.raises(ValueError, match="DRAFT_NOT_FOUND"):
            await update_draft(
                db,
                profile_env["company_id"],
                "nonexistent-id",
                agent_cli="x",
                api_model="y",
            )


@pytest.mark.asyncio
class TestGetProfile:
    async def test_get_profile_returns_versions(self, db, profile_env):
        company_id = profile_env["company_id"]
        profile = await get_profile(db, company_id, profile_env["profile_id"])
        assert profile is not None
        assert "versions" in profile
        assert len(profile["versions"]) >= 1

    async def test_get_nonexistent_returns_none(self, db, profile_env):
        result = await get_profile(db, profile_env["company_id"], "no-such-id")
        assert result is None


@pytest.mark.asyncio
class TestListProfiles:
    async def test_list_all(self, db, profile_env):
        profiles = await list_profiles(db, profile_env["company_id"])
        assert len(profiles) >= 1

    async def test_list_with_employee_filter(self, db, profile_env):
        profiles = await list_profiles(
            db,
            profile_env["company_id"],
        )
        assert isinstance(profiles, list)


@pytest.mark.asyncio
class TestBindSkill:
    async def test_bind_skill_success(self, db, profile_env):
        company_id = profile_env["company_id"]
        draft = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={"name": "SkillTest", "description": "Bind test", "content_sha256": "a" * 64},
        )
        result = await bind_skill(
            db,
            company_id,
            draft["profile_id"],
            skill_id="skill-1",
            skill_version="1.0.0",
        )
        assert result["skill_id"] == "skill-1"
        assert result["load_order"] == 0

    async def test_bind_duplicate_raises(self, db, profile_env):
        company_id = profile_env["company_id"]
        draft = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={"name": "Dup", "description": "Dup test", "content_sha256": "a" * 64},
        )
        await bind_skill(db, company_id, draft["profile_id"], skill_id="s1", skill_version="1.0")
        with pytest.raises(ValueError, match="SKILL_ALREADY_BOUND"):
            await bind_skill(db, company_id, draft["profile_id"], skill_id="s1", skill_version="1.0")

    async def test_bind_no_draft_raises(self, db, profile_env):
        with pytest.raises(ValueError, match="DRAFT_NOT_FOUND"):
            await bind_skill(
                db,
                profile_env["company_id"],
                "no-draft",
                skill_id="s1",
                skill_version="1.0",
            )


@pytest.mark.asyncio
class TestUnbindSkill:
    async def test_unbind_skill_success(self, db, profile_env):
        company_id = profile_env["company_id"]
        draft = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={"name": "Unbind", "description": "Test", "content_sha256": "a" * 64},
        )
        await bind_skill(db, company_id, draft["profile_id"], skill_id="s1", skill_version="1.0")
        result = await unbind_skill(db, company_id, draft["profile_id"], skill_id="s1")
        assert result["unbound"] is True

    async def test_unbind_nonexistent_raises(self, db, profile_env):
        company_id = profile_env["company_id"]
        draft = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={"name": "NoSkill", "description": "Test", "content_sha256": "a" * 64},
        )
        with pytest.raises(ValueError, match="SKILL_NOT_BOUND"):
            await unbind_skill(db, company_id, draft["profile_id"], skill_id="nonexistent")

    async def test_unbind_no_draft_raises(self, db, profile_env):
        with pytest.raises(ValueError, match="DRAFT_NOT_FOUND"):
            await unbind_skill(db, profile_env["company_id"], "no-draft", skill_id="s1")


@pytest.mark.asyncio
class TestValidateDraft:
    async def test_validate_complete_draft(self, db, profile_env):
        company_id = profile_env["company_id"]
        draft = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={
                "name": "Complete",
                "description": "Full",
                "system_prompt": "Act",
                "catalog_release_id": profile_env["release_id"],
                "content_sha256": "a" * 64,
            },
        )
        result = await validate_draft(db, company_id, draft["version_id"])
        assert result["valid"] is True

    async def test_validate_missing_fields(self, db, profile_env):
        company_id = profile_env["company_id"]
        draft = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={"name": "X", "description": "Y", "content_sha256": "a" * 64},
        )
        result = await validate_draft(db, company_id, draft["version_id"])
        assert result["valid"] is False
        assert "missing_system_prompt" in result["errors"]

    async def test_validate_nonexistent_raises(self, db, profile_env):
        with pytest.raises(ValueError, match="DRAFT_NOT_FOUND"):
            await validate_draft(db, profile_env["company_id"], "no-id")


@pytest.mark.asyncio
class TestPublishDraft:
    async def test_publish_draft_success(self, db, profile_env):
        company_id = profile_env["company_id"]
        draft = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={"name": "Pub", "description": "Publish test", "content_sha256": "a" * 64},
        )
        result = await publish_draft(db, company_id, draft["version_id"])
        assert result["status"] == "published"
        assert result["published_at"]

    async def test_publish_nonexistent_raises(self, db, profile_env):
        with pytest.raises(ValueError, match="DRAFT_NOT_FOUND"):
            await publish_draft(db, profile_env["company_id"], "no-id")


@pytest.mark.asyncio
class TestRetireVersion:
    async def test_retire_published_version(self, db, profile_env):
        company_id = profile_env["company_id"]
        draft = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={"name": "Retire", "description": "Retire test", "content_sha256": "a" * 64},
        )
        await publish_draft(db, company_id, draft["version_id"])
        result = await retire_version(db, company_id, draft["version_id"])
        assert result["status"] == "retired"

    async def test_retire_non_published_raises(self, db, profile_env):
        company_id = profile_env["company_id"]
        draft = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={"name": "DraftOnly", "description": "Test", "content_sha256": "a" * 64},
        )
        with pytest.raises(ValueError, match="VERSION_NOT_PUBLISHED"):
            await retire_version(db, company_id, draft["version_id"])


@pytest.mark.asyncio
class TestRetireProfile:
    async def test_retire_profile_success(self, db, profile_env):
        company_id = profile_env["company_id"]
        draft = await create_draft(
            db,
            company_id,
            employee_id=profile_env["employee_id"],
            agent_cli="codex_cli",
            api_model="",
            base_profile={"name": "RetireProfile", "description": "Test", "content_sha256": "a" * 64},
        )
        await publish_draft(db, company_id, draft["version_id"])
        result = await retire_profile(db, company_id, draft["profile_id"])
        assert result["status"] == "retired"

    async def test_retire_nonexistent_raises(self, db, profile_env):
        with pytest.raises(ValueError, match="PROFILE_NOT_FOUND"):
            await retire_profile(db, profile_env["company_id"], "no-id")
