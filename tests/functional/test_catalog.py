"""Skill catalog tests — CRUD, validation.

Covers design spec sections:
- G.5 Skill Catalog (Agent/Model/Provider CRUD)
- Skill schema validation
"""

import uuid
from unittest.mock import AsyncMock

import pytest


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSkillSchemas:
    """Pydantic schema validation for skills."""

    def test_skill_create_valid(self):
        from ibreeze_backend.skills.schemas import SkillCreate

        skill = SkillCreate(
            key="my-skill", display_name="My Skill", description="A test skill"
        )
        assert skill.key == "my-skill"
        assert skill.display_name == "My Skill"

    def test_skill_create_minimal_key_pattern(self):
        from ibreeze_backend.skills.schemas import SkillCreate

        skill = SkillCreate(key="a1-b", display_name="S", description="d")
        assert skill.key == "a1-b"

    def test_skill_create_empty_key_rejected(self):
        from ibreeze_backend.skills.schemas import SkillCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SkillCreate(key="", display_name="S", description="d")

    def test_skill_create_invalid_key_pattern_rejected(self):
        from ibreeze_backend.skills.schemas import SkillCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SkillCreate(key="UPPER", display_name="S", description="d")

    def test_skill_create_empty_display_name_rejected(self):
        from ibreeze_backend.skills.schemas import SkillCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SkillCreate(key="s", display_name="", description="d")

    def test_skill_create_empty_description_rejected(self):
        from ibreeze_backend.skills.schemas import SkillCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SkillCreate(key="s", display_name="S", description="")

    def test_skill_update_partial(self):
        from ibreeze_backend.skills.schemas import SkillUpdate

        update = SkillUpdate(display_name="Updated Skill")
        assert update.display_name == "Updated Skill"
        assert update.description is None

    def test_skill_response_from_attributes(self):
        from ibreeze_backend.skills.schemas import SkillResponse

        resp = SkillResponse(
            id=uuid.uuid4(),
            key="s",
            display_name="S",
            description="desc",
            catalog_revision=1,
            status="draft",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
            version=1,
        )
        assert resp.status == "draft"


# ---------------------------------------------------------------------------
# Skill service
# ---------------------------------------------------------------------------


class TestSkillService:
    """Skill service CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_skill(self, mock_db_session):
        from ibreeze_backend.skills.schemas import SkillCreate
        from ibreeze_backend.skills.service import create_skill

        body = SkillCreate(
            key="my-skill", display_name="My Skill", description="A skill"
        )
        mock_db_session.scalar = AsyncMock(return_value=0)
        skill = await create_skill(mock_db_session, body)
        assert skill.key == "my-skill"
        assert skill.display_name == "My Skill"
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_skill_found(self, mock_db_session, mock_scalar_result):
        from ibreeze_backend.skills.service import get_skill

        mock_db_session.execute.return_value = mock_scalar_result("item")
        result = await get_skill(mock_db_session, uuid.uuid4())
        assert result == "item"

    @pytest.mark.asyncio
    async def test_get_skill_not_found(self, mock_db_session, mock_scalar_result):
        from ibreeze_backend.skills.service import get_skill

        mock_db_session.execute.return_value = mock_scalar_result(None)
        result = await get_skill(mock_db_session, uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_list_skills(self, mock_db_session):
        from ibreeze_backend.skills.service import list_skills

        mock_db_session.scalars = AsyncMock(return_value=["s1", "s2"])
        result = await list_skills(mock_db_session)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_skills_with_limit(self, mock_db_session):
        from ibreeze_backend.skills.service import list_skills

        mock_db_session.scalars = AsyncMock(return_value=[])
        result = await list_skills(mock_db_session, limit=5)
        assert result == []
