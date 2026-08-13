"""Coverage for ibreeze/orchestration/availability_checker.py.

Closes gaps in: check_agent_cli (available / missing / exception),
check_provider (reachable / unreachable / exception), check_skill (installed
published skill vs. missing), check_version_compatibility range evaluation,
and the optional-check branches of run_availability_checks.
"""

from __future__ import annotations

import hashlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from ibreeze.orchestration.availability_checker import (
    AvailabilityReport,
    CheckStatus,
    check_agent_cli,
    check_provider,
    check_skill,
    check_version_compatibility,
    run_availability_checks,
)


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


async def _publish_skill_with_binding(db: aiosqlite.Connection, company_id: str, skill_id: str) -> None:
    """Create a published profile version that has *skill_id* bound."""
    now = "2026-01-01T00:00:00.000000Z"
    profile_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    release_id = str(uuid.uuid4())
    await db.execute("PRAGMA foreign_keys = OFF")
    try:
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
               VALUES (?, ?, 'SkillProfile', 'skillprofile', 'Skill profile', ?,
                       'active', ?, ?, 1)""",
            (profile_id, company_id, version_id, now, now),
        )
        await db.execute(
            """INSERT INTO employee_base_profile_versions
               (id, profile_id, version_number, name, description, profile_type,
                runtime_binding_json, system_prompt, capability_tags_json,
                tool_policy_json, timeout_seconds, max_retries, workspace_policy,
                catalog_release_id, content_sha256, status, created_at, published_at)
               VALUES (?, ?, 1, 'Skill v1', 'Skill profile', 'agent_cli',
                       '{"adapter_type":"codex_cli"}', 'Act.', '[]', '{}', 300, 2,
                       'workspace_rw_external_ro', ?, ?, 'draft', ?, NULL)""",
            (version_id, profile_id, release_id, _sha256("v1"), now),
        )
        # The insert guard only blocks mutations of non-draft versions, so the
        # binding must be inserted while the version is still 'draft'.
        await db.execute(
            """INSERT INTO profile_skill_bindings
               (profile_version_id, skill_id, skill_version_id, skill_version,
                package_sha256, load_order)
               VALUES (?, ?, 'sv-1', '1.0', ?, 0)""",
            (version_id, skill_id, _sha256("pkg")),
        )
        await db.execute(
            """UPDATE employee_base_profile_versions
               SET status = 'published', published_at = ? WHERE id = ?""",
            (now, version_id),
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()


@pytest.mark.asyncio
class TestCheckAgentCli:
    async def test_pass_when_available(self):
        probe = SimpleNamespace(
            available=True,
            version="1.2.3",
            failure_code=None,
            executable_path="/usr/bin/codex",
        )
        with patch("ibreeze.runtime.cli.probe_agent", new=AsyncMock(return_value=probe)):
            result = await check_agent_cli(None, adapter_type="codex_cli")
        assert result.check_name == "agent_cli"
        assert result.status == CheckStatus.PASS
        assert result.message == "1.2.3"
        assert result.details == {"executable_path": "/usr/bin/codex"}

    async def test_fail_when_unavailable(self):
        probe = SimpleNamespace(
            available=False,
            version=None,
            failure_code="AGENT_EXECUTABLE_NOT_FOUND",
            executable_path=None,
        )
        with patch("ibreeze.runtime.cli.probe_agent", new=AsyncMock(return_value=probe)):
            result = await check_agent_cli(None, adapter_type="codex_cli")
        assert result.status == CheckStatus.FAIL
        assert result.message == "AGENT_EXECUTABLE_NOT_FOUND"

    async def test_fail_on_exception(self):
        with patch("ibreeze.runtime.cli.probe_agent", new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = await check_agent_cli(None, adapter_type="codex_cli")
        assert result.status == CheckStatus.FAIL
        assert result.message == "boom"


@pytest.mark.asyncio
class TestCheckProvider:
    async def test_pass_when_reachable(self):
        transport = SimpleNamespace(probe=AsyncMock(return_value=True))
        with patch("ibreeze.runtime.transport.create_transport", return_value=transport):
            result = await check_provider(None, provider="openai", model="gpt-4o")
        assert result.check_name == "provider"
        assert result.status == CheckStatus.PASS
        assert result.message == "Provider accessible"

    async def test_fail_when_unreachable(self):
        transport = SimpleNamespace(probe=AsyncMock(return_value=False))
        with patch("ibreeze.runtime.transport.create_transport", return_value=transport):
            result = await check_provider(None, provider="openai", model="gpt-4o")
        assert result.status == CheckStatus.FAIL
        assert result.message == "Provider unreachable"

    async def test_fail_on_exception(self):
        with patch("ibreeze.runtime.transport.create_transport", side_effect=RuntimeError("conn refused")):
            result = await check_provider(None, provider="openai", model="gpt-4o")
        assert result.status == CheckStatus.FAIL
        assert result.message == "conn refused"


@pytest.mark.asyncio
class TestCheckSkill:
    async def test_fail_when_not_installed(self, db):
        result = await check_skill(db, skill_id="skill-1", company_id="comp-1")
        assert result.status == CheckStatus.FAIL
        assert result.message == "Skill not installed"

    async def test_pass_when_installed_and_published(self, db):
        await _publish_skill_with_binding(db, "comp-1", "skill-1")
        result = await check_skill(db, skill_id="skill-1", company_id="comp-1")
        assert result.status == CheckStatus.PASS
        assert result.message == "Skill installed"


class TestCheckVersionCompatibility:
    def test_in_range(self):
        assert check_version_compatibility("1.5.0", ">=1.0,<2.0") is True

    def test_out_of_range(self):
        assert check_version_compatibility("2.5.0", ">=1.0,<2.0") is False

    def test_exact_match(self):
        assert check_version_compatibility("1.2.3", "==1.2.3") is True


@pytest.mark.asyncio
class TestRunAvailabilityChecksOptions:
    async def test_runs_all_optional_checks(self, db):
        probe = SimpleNamespace(
            available=True,
            version="1.2.3",
            failure_code=None,
            executable_path="/usr/bin/codex",
        )
        transport = SimpleNamespace(probe=AsyncMock(return_value=True))
        with (
            patch("ibreeze.runtime.cli.probe_agent", new=AsyncMock(return_value=probe)),
            patch("ibreeze.runtime.transport.create_transport", return_value=transport),
        ):
            report = await run_availability_checks(
                db,
                company_id="comp-1",
                adapter_type="codex_cli",
                provider="openai",
                model="gpt-4o",
                skill_id="skill-1",
                max_concurrent=5,
            )
        assert isinstance(report, AvailabilityReport)
        names = {c.check_name for c in report.checks}
        assert {"agent_cli", "provider", "model", "skill", "workspace", "concurrency_slot", "health"} <= names
