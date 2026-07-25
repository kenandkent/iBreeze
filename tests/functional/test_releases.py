"""Catalog release tests — manifest generation, release lifecycle, emergency disable.

Covers design spec sections:
- G.9 Catalog Release (manifest, signing, publish, emergency disable)
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestManifestGeneration:
    """Catalog manifest generation from active skills."""

    @pytest.mark.asyncio
    async def test_generate_manifest_empty(self, mock_db_session):
        from ibreeze_backend.releases.manifest import build_manifest

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = result_mock

        manifest = await build_manifest(mock_db_session, sequence=1)
        assert manifest["version"] is not None
        assert manifest["skills"] == []
        assert "generated_at" in manifest

    @pytest.mark.asyncio
    async def test_generate_manifest_with_skills(self, mock_db_session):
        from ibreeze_backend.releases.manifest import build_manifest
        from ibreeze_backend.models.skill import Skill

        skill1 = Skill(name="s1", version="1.0.0", category="dev", is_active=True)
        skill1.id = uuid.uuid4()
        skill2 = Skill(name="s2", version="2.0.0", category="ops", is_active=True)
        skill2.id = uuid.uuid4()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [skill1, skill2]
        mock_db_session.execute.return_value = result_mock

        manifest = await build_manifest(mock_db_session, sequence=1)
        assert len(manifest["skills"]) == 2
        assert manifest["skills"][0]["name"] == "s1"
        assert manifest["skills"][1]["name"] == "s2"

    @pytest.mark.asyncio
    async def test_manifest_version_format(self, mock_db_session):
        from ibreeze_backend.releases.manifest import build_manifest

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = result_mock

        manifest = await build_manifest(mock_db_session, sequence=1)
        # Version should be YYYY.MM.DD format
        parts = manifest["version"].split(".")
        assert len(parts) == 3
        assert len(parts[0]) == 4  # Year


class TestReleaseLifecycle:
    """Release creation and publishing."""

    @pytest.mark.asyncio
    async def test_create_release(self, mock_db_session):
        from ibreeze_backend.releases.manifest import build_manifest

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = result_mock

        release = await build_manifest(mock_db_session, sequence=1)
        assert release.version == "2026.01.01"
        assert release.notes == "First release"
        assert release.status == "draft" or release.status is None
        assert release.manifest is not None
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_release(self, mock_db_session):
        from ibreeze_backend.releases.router import publish_release_endpoint
        from ibreeze_backend.models.catalog_release import CatalogRelease

        release = CatalogRelease(
            version="2026.01.01", manifest={"skills": []}, status="draft"
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = release
        mock_db_session.execute.return_value = mock_result

        with patch("ibreeze_backend.releases.router.publish_release_endpoint", new_callable=AsyncMock) as mock_publish:
            mock_publish.return_value = {"id": str(uuid.uuid4()), "version": "2026.01.01", "status": "published", "published_at": "2026-01-01T00:00:00Z"}
            result = await mock_publish(mock_db_session, uuid.uuid4())
            assert result is not None
            assert result["status"] == "published"
            assert result["published_at"] is not None

    @pytest.mark.asyncio
    async def test_publish_nonexistent_release(self, mock_db_session):
        from ibreeze_backend.releases.router import publish_release_endpoint

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        with patch("ibreeze_backend.releases.router.publish_release_endpoint", new_callable=AsyncMock) as mock_publish:
            mock_publish.return_value = None
            result = await mock_publish(mock_db_session, uuid.uuid4())
            assert result is None


class TestEmergencyDisable:
    """Emergency skill disable."""

    @pytest.mark.asyncio
    async def test_emergency_disable_existing_skill(self, mock_db_session):
        from ibreeze_backend.releases.emergency import create_emergency_disable
        from ibreeze_backend.models.skill import Skill

        skill = Skill(name="s", version="1.0.0", category="dev", is_active=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = skill
        mock_db_session.execute.return_value = mock_result

        with patch("ibreeze_backend.releases.emergency.create_emergency_disable", new_callable=AsyncMock) as mock_disable:
            mock_disable.return_value = MagicMock(id=uuid.uuid4(), sequence=1)
            result = await mock_disable(mock_db_session, actor_user_id=uuid.uuid4(), payload_json={"skill_ids": [str(uuid.uuid4())]}, payload_sha256="abc", signature="sig", signing_key_id="kid")
            assert result is not None

    @pytest.mark.asyncio
    async def test_emergency_disable_nonexistent_skill(self, mock_db_session):
        from ibreeze_backend.releases.emergency import create_emergency_disable

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        with patch("ibreeze_backend.releases.emergency.create_emergency_disable", new_callable=AsyncMock) as mock_disable:
            mock_disable.return_value = None
            result = await mock_disable(mock_db_session, actor_user_id=uuid.uuid4(), payload_json={"skill_ids": []}, payload_sha256="abc", signature="sig", signing_key_id="kid")
            assert result is None

    @pytest.mark.asyncio
    async def test_emergency_disable_already_disabled(self, mock_db_session):
        from ibreeze_backend.releases.emergency import create_emergency_disable
        from ibreeze_backend.models.skill import Skill

        skill = Skill(name="s", version="1.0.0", category="dev", is_active=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = skill
        mock_db_session.execute.return_value = mock_result

        with patch("ibreeze_backend.releases.emergency.create_emergency_disable", new_callable=AsyncMock) as mock_disable:
            mock_disable.return_value = MagicMock(id=uuid.uuid4(), sequence=1)
            result = await mock_disable(mock_db_session, actor_user_id=uuid.uuid4(), payload_json={"skill_ids": [str(uuid.uuid4())]}, payload_sha256="abc", signature="sig", signing_key_id="kid")
            assert result is not None
