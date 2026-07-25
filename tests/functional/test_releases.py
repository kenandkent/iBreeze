"""Catalog release tests — manifest generation, release lifecycle, emergency disable.

Covers design spec sections:
- G.9 Catalog Release (manifest, signing, publish, emergency disable)
"""
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest


def _make_skill(**overrides):
    skill = MagicMock()
    skill.id = overrides.get("id", uuid.uuid4())
    skill.key = overrides.get("key", "test-skill")
    skill.display_name = overrides.get("display_name", "Test Skill")
    skill.version = overrides.get("version", 1)
    skill.status = overrides.get("status", "published")
    skill.description = overrides.get("description", "A test skill")
    skill.catalog_revision = overrides.get("catalog_revision", 1)
    return skill


def _make_skill_version(**overrides):
    sv = MagicMock()
    sv.content_sha256 = overrides.get("content_sha256", "abc123hash")
    return sv


class TestManifestGeneration:
    """Catalog manifest generation from active skills."""

    @pytest.mark.asyncio
    async def test_generate_manifest_empty(self, mock_db_session):
        from ibreeze_backend.releases.manifest import build_manifest

        skills_result = MagicMock()
        skills_result.scalars.return_value.all.return_value = []

        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = None

        mock_db_session.execute.side_effect = [skills_result]

        manifest = await build_manifest(mock_db_session, sequence=1)
        assert manifest["release_sequence"] == 1
        assert manifest["resources"] == []

    @pytest.mark.asyncio
    async def test_generate_manifest_with_skills(self, mock_db_session):
        from ibreeze_backend.releases.manifest import build_manifest

        skill1 = _make_skill(key="s1", display_name="Skill One", version=1)
        skill2 = _make_skill(key="s2", display_name="Skill Two", version=2)

        sv1 = _make_skill_version(content_sha256="hash1")
        sv2 = _make_skill_version(content_sha256="hash2")

        skills_result = MagicMock()
        skills_result.scalars.return_value.all.return_value = [skill1, skill2]

        version_result_1 = MagicMock()
        version_result_1.scalar_one_or_none.return_value = sv1
        version_result_2 = MagicMock()
        version_result_2.scalar_one_or_none.return_value = sv2

        mock_db_session.execute.side_effect = [skills_result, version_result_1, version_result_2]

        manifest = await build_manifest(mock_db_session, sequence=3)
        assert manifest["release_sequence"] == 3
        assert len(manifest["resources"]) == 2
        assert manifest["resources"][0]["key"] == "s1"
        assert manifest["resources"][0]["content_sha256"] == "hash1"
        assert manifest["resources"][1]["key"] == "s2"
        assert manifest["resources"][1]["content_sha256"] == "hash2"

    @pytest.mark.asyncio
    async def test_generate_manifest_skill_without_version(self, mock_db_session):
        from ibreeze_backend.releases.manifest import build_manifest

        skill = _make_skill(key="no-ver", display_name="No Version", version=1)

        skills_result = MagicMock()
        skills_result.scalars.return_value.all.return_value = [skill]

        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = None

        mock_db_session.execute.side_effect = [skills_result, version_result]

        manifest = await build_manifest(mock_db_session, sequence=1)
        assert len(manifest["resources"]) == 1
        assert manifest["resources"][0]["content_sha256"] == ""

    @pytest.mark.asyncio
    async def test_manifest_resource_fields(self, mock_db_session):
        from ibreeze_backend.releases.manifest import build_manifest

        skill_id = uuid.uuid4()
        skill = _make_skill(id=skill_id, key="alpha", display_name="Alpha Skill", version=5)
        sv = _make_skill_version(content_sha256="deadbeef")

        skills_result = MagicMock()
        skills_result.scalars.return_value.all.return_value = [skill]
        version_result = MagicMock()
        version_result.scalar_one_or_none.return_value = sv

        mock_db_session.execute.side_effect = [skills_result, version_result]

        manifest = await build_manifest(mock_db_session, sequence=7)
        res = manifest["resources"][0]
        assert res["id"] == str(skill_id)
        assert res["key"] == "alpha"
        assert res["display_name"] == "Alpha Skill"
        assert res["version"] == 5
        assert res["content_sha256"] == "deadbeef"


class TestReleaseLifecycle:
    """Release creation and publishing."""

    @pytest.mark.asyncio
    async def test_publish_release(self, mock_db_session):
        from ibreeze_backend.models.catalog_release import CatalogRelease

        release = CatalogRelease(
            release_sequence=1,
            minimum_client_version="1.0",
            manifest_object_key="",
            manifest_sha256="",
            signature="sig",
            signing_key_id="kid",
            status="draft",
            created_by=uuid.uuid4(),
            created_at=datetime.now(UTC),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = release
        mock_db_session.execute.return_value = mock_result

        from ibreeze_backend.releases.router import publish_release_endpoint
        from fastapi import Request
        from starlette.datastructures import Headers

        request = MagicMock()
        request.state.request_id = str(uuid.uuid4())

        response = await publish_release_endpoint(
            release_id=release.id,
            db=mock_db_session,
            _current_user=MagicMock(),
        )
        assert response["status"] == "published"
        assert response["id"] == str(release.id)

    @pytest.mark.asyncio
    async def test_publish_nonexistent_release(self, mock_db_session):
        from fastapi import HTTPException

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        from ibreeze_backend.releases.router import publish_release_endpoint

        with pytest.raises(HTTPException) as exc_info:
            await publish_release_endpoint(
                release_id=uuid.uuid4(),
                db=mock_db_session,
                _current_user=MagicMock(),
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_publish_already_published(self, mock_db_session):
        from fastapi import HTTPException
        from ibreeze_backend.models.catalog_release import CatalogRelease

        release = CatalogRelease(
            release_sequence=1,
            minimum_client_version="1.0",
            manifest_object_key="",
            manifest_sha256="",
            signature="sig",
            signing_key_id="kid",
            status="published",
            created_by=uuid.uuid4(),
            created_at=datetime.now(UTC),
            published_at=datetime.now(UTC),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = release
        mock_db_session.execute.return_value = mock_result

        from ibreeze_backend.releases.router import publish_release_endpoint

        with pytest.raises(HTTPException) as exc_info:
            await publish_release_endpoint(
                release_id=release.id,
                db=mock_db_session,
                _current_user=MagicMock(),
            )
        assert exc_info.value.status_code == 400


class TestEmergencyDisable:
    """Emergency skill disable."""

    @pytest.mark.asyncio
    async def test_create_emergency_disable(self, mock_db_session):
        from ibreeze_backend.releases.emergency import create_emergency_disable

        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = empty_result

        actor_id = uuid.uuid4()
        result = await create_emergency_disable(
            mock_db_session,
            actor_user_id=actor_id,
            payload_json={"skill_ids": ["some-id"]},
            payload_sha256="sha",
            signature="sig",
            signing_key_id="kid",
        )
        assert result is not None
        assert result.sequence == 1
        assert result.payload_json == {"skill_ids": ["some-id"]}
        assert result.payload_sha256 == "sha"
        assert result.signature == "sig"
        assert result.signing_key_id == "kid"
        assert result.created_by == actor_id
        mock_db_session.add.assert_called_once_with(result)
        mock_db_session.flush.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_emergency_disable_increments_sequence(self, mock_db_session):
        from ibreeze_backend.releases.emergency import create_emergency_disable

        existing = MagicMock()
        existing.sequence = 5
        existing_result = MagicMock()
        existing_result.scalars.return_value.all.return_value = [existing]
        mock_db_session.execute.return_value = existing_result

        result = await create_emergency_disable(
            mock_db_session,
            actor_user_id=uuid.uuid4(),
            payload_json={"skill_ids": []},
            payload_sha256="sha2",
            signature="sig2",
            signing_key_id="kid2",
        )
        assert result.sequence == 6
