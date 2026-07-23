"""Skill management tests — install, remove, emergency disable, binding.

Covers design spec sections:
- G.8 Skill Management (install, remove, disable)
"""
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestSkillManagement:
    """Skill management operations."""

    @pytest.mark.asyncio
    async def test_install_skill(self, mock_db_session):
        from ibreeze_backend.skills.service import install_skill

        with (
            patch("ibreeze_backend.skills.service.validate_zip_structure") as mock_validate,
            patch("ibreeze_backend.skills.service.validate_zip_size") as mock_size,
            patch("ibreeze_backend.skills.service.validate_uncompressed_size") as mock_uncompressed,
            patch("ibreeze_backend.skills.service.compute_zip_checksum") as mock_checksum,
            patch("ibreeze_backend.skills.service.storage") as mock_storage,
        ):
            mock_validate.return_value = (True, [])
            mock_size.return_value = True
            mock_uncompressed.return_value = True
            mock_checksum.return_value = "abc123hash"
            mock_storage.store.return_value = Path("/tmp/test.zip")

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db_session.execute.return_value = mock_result

            skill = await install_skill(mock_db_session, str(uuid.uuid4()), "1.0.0", Path("/tmp/test.zip"))
            assert skill.version == "1.0.0"
            assert skill.is_active is True
            assert skill.checksum == "abc123hash"
            mock_storage.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_skill(self, mock_db_session):
        from ibreeze_backend.skills.service import remove_skill

        skill = MagicMock()
        skill.is_active = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = skill
        mock_db_session.execute.return_value = mock_result

        with patch("ibreeze_backend.skills.service.storage") as mock_storage:
            mock_storage.delete.return_value = True
            result = await remove_skill(mock_db_session, str(uuid.uuid4()), "1.0.0")
            assert result is True
            mock_db_session.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remove_active_skill_raises(self, mock_db_session):
        from ibreeze_backend.skills.service import remove_skill

        skill = MagicMock()
        skill.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = skill
        mock_db_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Cannot remove active version"):
            await remove_skill(mock_db_session, str(uuid.uuid4()), "1.0.0")

    @pytest.mark.asyncio
    async def test_emergency_disable_skill(self, mock_db_session):
        from ibreeze_backend.skills.service import emergency_disable_skill

        skill = MagicMock()
        skill.is_active = True

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = skill
        mock_db_session.execute.return_value = mock_result

        result = await emergency_disable_skill(mock_db_session, str(uuid.uuid4()))
        assert result is True
        assert skill.is_active is False

    @pytest.mark.asyncio
    async def test_skill_agent_binding(self, mock_db_session):
        from ibreeze_backend.catalog.service import create_agent_model_binding

        agent = MagicMock()
        agent.id = uuid.uuid4()
        model = MagicMock()
        model.id = uuid.uuid4()

        call_idx = [0]
        def side_effect(stmt):
            call_idx[0] += 1
            if call_idx[0] == 1:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=agent))
            return MagicMock(scalar_one_or_none=MagicMock(return_value=model))
        mock_db_session.execute.side_effect = side_effect

        binding = await create_agent_model_binding(
            mock_db_session, agent.id, model.id, {"min": "1.0"}
        )
        assert binding.agent_id == agent.id
        assert binding.model_id == model.id
