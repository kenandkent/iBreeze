"""Skill catalog tests — CRUD, compatibility checking, validation.

Covers design spec sections:
- G.5 Skill Catalog (Agent/Model/Provider CRUD, compatibility rules)
- Skill schema validation (semver, category)
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestSkillSchemas:
    """Pydantic schema validation for skills."""

    def test_skill_create_valid(self):
        from ibreeze_backend.schemas.skill import SkillCreate

        skill = SkillCreate(name="my-skill", version="1.0.0", category="productivity")
        assert skill.name == "my-skill"
        assert skill.version == "1.0.0"

    def test_skill_create_with_compatibility(self):
        from ibreeze_backend.schemas.skill import SkillCreate

        skill = SkillCreate(
            name="my-skill",
            version="2.1.0",
            category="dev",
            compatibility={"min_platform": "1.0.0", "max_platform": "3.0.0"},
        )
        assert skill.compatibility["min_platform"] == "1.0.0"

    def test_skill_create_invalid_version_rejected(self):
        from ibreeze_backend.schemas.skill import SkillCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SkillCreate(name="s", version="not-semver", category="cat")

    def test_skill_create_empty_name_rejected(self):
        from ibreeze_backend.schemas.skill import SkillCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SkillCreate(name="", version="1.0.0", category="cat")

    def test_skill_create_empty_category_rejected(self):
        from ibreeze_backend.schemas.skill import SkillCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SkillCreate(name="s", version="1.0.0", category="")

    def test_skill_update_partial(self):
        from ibreeze_backend.schemas.skill import SkillUpdate

        update = SkillUpdate(description="new desc")
        assert update.description == "new desc"
        assert update.category is None
        assert update.is_active is None

    def test_skill_response_from_attributes(self):
        from ibreeze_backend.schemas.skill import SkillResponse

        resp = SkillResponse(
            id=str(uuid.uuid4()),
            name="s",
            version="1.0.0",
            description=None,
            category="cat",
            compatibility=None,
            is_active=True,
            checksum=None,
        )
        assert resp.is_active is True

    def test_skill_list_response(self):
        from ibreeze_backend.schemas.skill import SkillListResponse, SkillResponse

        skills = [SkillResponse(
            id=str(uuid.uuid4()), name="s", version="1.0.0", description=None,
            category="cat", compatibility=None, is_active=True, checksum=None,
        )]
        resp = SkillListResponse(skills=skills, total=1)
        assert len(resp.skills) == 1


# ---------------------------------------------------------------------------
# Skill service
# ---------------------------------------------------------------------------

class TestSkillService:
    """Skill service CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_skill(self, mock_db_session):
        from ibreeze_backend.services.skill_service import create_skill

        skill = await create_skill(
            mock_db_session, name="my-skill", version="1.0.0", category="dev",
            description="A skill", compatibility={"min_platform": "1.0.0"},
        )
        assert skill.name == "my-skill"
        assert skill.version == "1.0.0"
        assert skill.category == "dev"
        assert skill.is_active is None

    @pytest.mark.asyncio
    async def test_get_skill_found(self, mock_db_session, mock_scalar_result):
        from ibreeze_backend.services.skill_service import get_skill
        from ibreeze_backend.models.skill import Skill

        skill = Skill(name="s", version="1.0.0", category="dev", is_active=True)
        mock_db_session.execute.return_value = mock_scalar_result(skill)

        result = await get_skill(mock_db_session, uuid.uuid4())
        assert result == skill

    @pytest.mark.asyncio
    async def test_get_skill_not_found(self, mock_db_session, mock_scalar_result):
        from ibreeze_backend.services.skill_service import get_skill

        mock_db_session.execute.return_value = mock_scalar_result(None)
        result = await get_skill(mock_db_session, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_list_skills(self, mock_db_session):
        from ibreeze_backend.services.skill_service import list_skills
        from ibreeze_backend.models.skill import Skill

        skills = [Skill(name="s1", version="1.0.0", category="dev", is_active=True)]

        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = skills
        mock_db_session.execute.side_effect = [count_result, list_result]

        result, total = await list_skills(mock_db_session)
        assert total == 1
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_skills_by_category(self, mock_db_session):
        from ibreeze_backend.services.skill_service import list_skills

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.side_effect = [count_result, list_result]

        result, total = await list_skills(mock_db_session, category="nonexistent")
        assert total == 0
        assert result == []

    @pytest.mark.asyncio
    async def test_update_skill(self, mock_db_session):
        from ibreeze_backend.services.skill_service import update_skill
        from ibreeze_backend.models.skill import Skill

        skill = Skill(name="s", version="1.0.0", category="dev", is_active=True)
        updated = await update_skill(mock_db_session, skill, description="new", is_active=False)
        assert updated.description == "new"
        assert updated.is_active is False

    @pytest.mark.asyncio
    async def test_update_skill_no_changes(self, mock_db_session):
        from ibreeze_backend.services.skill_service import update_skill
        from ibreeze_backend.models.skill import Skill

        skill = Skill(name="s", version="1.0.0", category="dev", is_active=True)
        await update_skill(mock_db_session, skill)
        assert skill.is_active is True  # Unchanged


class TestSkillCompatibility:
    """Skill compatibility checking."""

    @pytest.mark.asyncio
    async def test_compatible_with_no_constraints(self):
        from ibreeze_backend.services.skill_service import check_compatibility
        from ibreeze_backend.models.skill import Skill

        skill = Skill(name="s", version="1.0.0", category="dev", is_active=True)
        assert await check_compatibility(skill) is True

    @pytest.mark.asyncio
    async def test_compatible_within_range(self):
        from ibreeze_backend.services.skill_service import check_compatibility
        from ibreeze_backend.models.skill import Skill

        skill = Skill(
            name="s", version="1.0.0", category="dev", is_active=True,
            compatibility={"min_platform": "1.0.0", "max_platform": "3.0.0"},
        )
        assert await check_compatibility(skill, min_platform_version="2.0.0") is True

    @pytest.mark.asyncio
    async def test_incompatible_below_min(self):
        from ibreeze_backend.services.skill_service import check_compatibility
        from ibreeze_backend.models.skill import Skill

        skill = Skill(
            name="s", version="1.0.0", category="dev", is_active=True,
            compatibility={"min_platform": "2.0.0"},
        )
        assert await check_compatibility(skill, min_platform_version="1.0.0") is False

    @pytest.mark.asyncio
    async def test_incompatible_above_max(self):
        from ibreeze_backend.services.skill_service import check_compatibility
        from ibreeze_backend.models.skill import Skill

        skill = Skill(
            name="s", version="1.0.0", category="dev", is_active=True,
            compatibility={"max_platform": "2.0.0"},
        )
        assert await check_compatibility(skill, max_platform_version="3.0.0") is False

    @pytest.mark.asyncio
    async def test_compatible_at_boundary(self):
        from ibreeze_backend.services.skill_service import check_compatibility
        from ibreeze_backend.models.skill import Skill

        skill = Skill(
            name="s", version="1.0.0", category="dev", is_active=True,
            compatibility={"min_platform": "2.0.0", "max_platform": "2.0.0"},
        )
        assert await check_compatibility(skill, min_platform_version="2.0.0") is True
        assert await check_compatibility(skill, max_platform_version="2.0.0") is True
