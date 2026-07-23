"""Catalog release tests — manifest generation, release lifecycle, emergency disable.

Covers design spec sections:
- G.9 Catalog Release (manifest, signing, publish, emergency disable)
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestManifestGeneration:
    """Catalog manifest generation from active skills."""

    @pytest.mark.asyncio
    async def test_generate_manifest_empty(self, mock_db_session):
        from ibreeze_backend.services.catalog_service import generate_manifest

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = result_mock

        manifest = await generate_manifest(mock_db_session)
        assert manifest["version"] is not None
        assert manifest["skills"] == []
        assert "generated_at" in manifest

    @pytest.mark.asyncio
    async def test_generate_manifest_with_skills(self, mock_db_session):
        from ibreeze_backend.services.catalog_service import generate_manifest
        from ibreeze_backend.models.skill import Skill

        skill1 = Skill(name="s1", version="1.0.0", category="dev", is_active=True)
        skill1.id = uuid.uuid4()
        skill2 = Skill(name="s2", version="2.0.0", category="ops", is_active=True)
        skill2.id = uuid.uuid4()

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [skill1, skill2]
        mock_db_session.execute.return_value = result_mock

        manifest = await generate_manifest(mock_db_session)
        assert len(manifest["skills"]) == 2
        assert manifest["skills"][0]["name"] == "s1"
        assert manifest["skills"][1]["name"] == "s2"

    @pytest.mark.asyncio
    async def test_manifest_version_format(self, mock_db_session):
        from ibreeze_backend.services.catalog_service import generate_manifest

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = result_mock

        manifest = await generate_manifest(mock_db_session)
        # Version should be YYYY.MM.DD format
        parts = manifest["version"].split(".")
        assert len(parts) == 3
        assert len(parts[0]) == 4  # Year


class TestReleaseLifecycle:
    """Release creation and publishing."""

    @pytest.mark.asyncio
    async def test_create_release(self, mock_db_session):
        from ibreeze_backend.services.catalog_service import create_release

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = result_mock

        release = await create_release(mock_db_session, version="2026.01.01", notes="First release")
        assert release.version == "2026.01.01"
        assert release.notes == "First release"
        assert release.status == "draft" or release.status is None
        assert release.manifest is not None
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_release(self, mock_db_session):
        from ibreeze_backend.services.catalog_service import publish_release
        from ibreeze_backend.models.catalog_release import CatalogRelease

        release = CatalogRelease(
            version="2026.01.01", manifest={"skills": []}, status="draft"
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = release
        mock_db_session.execute.return_value = mock_result

        result = await publish_release(mock_db_session, uuid.uuid4())
        assert result is not None
        assert result.status == "published"
        assert result.published_at is not None

    @pytest.mark.asyncio
    async def test_publish_nonexistent_release(self, mock_db_session):
        from ibreeze_backend.services.catalog_service import publish_release

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await publish_release(mock_db_session, uuid.uuid4())
        assert result is None


class TestEmergencyDisable:
    """Emergency skill disable."""

    @pytest.mark.asyncio
    async def test_emergency_disable_existing_skill(self, mock_db_session):
        from ibreeze_backend.services.catalog_service import emergency_disable_skill
        from ibreeze_backend.models.skill import Skill

        skill = Skill(name="s", version="1.0.0", category="dev", is_active=True)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = skill
        mock_db_session.execute.return_value = mock_result

        result = await emergency_disable_skill(mock_db_session, uuid.uuid4())
        assert result is True
        assert skill.is_active is False

    @pytest.mark.asyncio
    async def test_emergency_disable_nonexistent_skill(self, mock_db_session):
        from ibreeze_backend.services.catalog_service import emergency_disable_skill

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await emergency_disable_skill(mock_db_session, uuid.uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_emergency_disable_already_disabled(self, mock_db_session):
        from ibreeze_backend.services.catalog_service import emergency_disable_skill
        from ibreeze_backend.models.skill import Skill

        skill = Skill(name="s", version="1.0.0", category="dev", is_active=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = skill
        mock_db_session.execute.return_value = mock_result

        result = await emergency_disable_skill(mock_db_session, uuid.uuid4())
        assert result is True  # Still succeeds
        assert skill.is_active is False
