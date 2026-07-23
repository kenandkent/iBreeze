"""Catalog service tests — Agent/Model/Provider CRUD, status transitions, bindings.

Covers design spec sections:
- G.5 Catalog Service (status machine, immutable published, draft copy)
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _mock_count_result(count):
    r = MagicMock()
    r.scalar.return_value = count
    return r


def _mock_scalars(items):
    r = MagicMock()
    r.scalars.return_value.all.return_value = items
    return r


# ---------------------------------------------------------------------------
# Agent CRUD
# ---------------------------------------------------------------------------

class TestAgentCatalog:
    """Agent catalog CRUD."""

    @pytest.mark.asyncio
    async def test_create_agent_catalog(self, mock_db_session):
        from ibreeze_backend.catalog.service import create_agent

        mock_db_session.execute.return_value = _mock_result(None)
        agent = await create_agent(mock_db_session, "test-agent", "Test Agent", "A test agent")
        assert agent.key == "test-agent"
        assert agent.display_name == "Test Agent"
        # status 由 mapped_column(default="draft") 在 INSERT 时设置，实例化时为 None
        assert agent.status is None
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_agent_duplicate_key(self, mock_db_session):
        from ibreeze_backend.catalog.service import create_agent

        mock_db_session.execute.return_value = _mock_result(MagicMock())
        with pytest.raises(ValueError, match="Agent key already exists"):
            await create_agent(mock_db_session, "dup-agent", "Dup", None)

    @pytest.mark.asyncio
    async def test_agent_status_draft_to_validated(self, mock_db_session):
        from ibreeze_backend.catalog.service import transition_agent_status

        agent = MagicMock()
        agent.status = "draft"
        agent.catalog_revision = 1

        call_idx = [0]
        def side_effect(stmt):
            call_idx[0] += 1
            if call_idx[0] <= 2:
                return _mock_result(agent)
            return _mock_result(None)
        mock_db_session.execute.side_effect = side_effect

        result = await transition_agent_status(mock_db_session, agent.id, "validated")
        assert agent.status == "validated"
        assert agent.catalog_revision == 2

    @pytest.mark.asyncio
    async def test_agent_status_validated_to_published(self, mock_db_session):
        from ibreeze_backend.catalog.service import transition_agent_status

        agent = MagicMock()
        agent.status = "validated"
        agent.catalog_revision = 2

        call_idx = [0]
        def side_effect(stmt):
            call_idx[0] += 1
            if call_idx[0] <= 2:
                return _mock_result(agent)
            return _mock_result(None)
        mock_db_session.execute.side_effect = side_effect

        result = await transition_agent_status(mock_db_session, agent.id, "published")
        assert agent.status == "published"
        assert agent.catalog_revision == 3

    @pytest.mark.asyncio
    async def test_agent_status_invalid_transition(self, mock_db_session):
        from ibreeze_backend.catalog.service import transition_agent_status

        agent = MagicMock()
        agent.status = "draft"

        mock_db_session.execute.return_value = _mock_result(agent)

        with pytest.raises(ValueError, match="Invalid status transition"):
            await transition_agent_status(mock_db_session, agent.id, "published")

    @pytest.mark.asyncio
    async def test_published_agent_immutable(self, mock_db_session):
        from ibreeze_backend.catalog.service import update_agent

        agent = MagicMock()
        agent.status = "published"
        mock_db_session.execute.return_value = _mock_result(agent)

        with pytest.raises(ValueError, match="Cannot update published agent"):
            await update_agent(mock_db_session, agent.id, "New Name", None)

    @pytest.mark.asyncio
    async def test_draft_copy_agent(self, mock_db_session):
        from ibreeze_backend.catalog.service import copy_agent_to_draft

        source = MagicMock()
        source.id = uuid.uuid4()
        source.key = "original-agent"
        source.display_name = "Original"
        source.description = "desc"
        source.status = "published"

        version = MagicMock()
        version.executable_names = ["test"]
        version.supported_platforms = ["linux"]
        version.min_version = "1.0"
        version.max_version_exclusive = "2.0"
        version.probe_command = {"cmd": "test"}
        version.capability_tags = ["tag1"]
        version.network_domains = ["default"]
        version.adapter_contract_version = 1
        version.content_sha256 = "abc"

        call_idx = [0]
        def side_effect(stmt):
            call_idx[0] += 1
            if call_idx[0] <= 2:
                return _mock_result(source)
            return _mock_scalars([version])
        mock_db_session.execute.side_effect = side_effect

        new_agent = await copy_agent_to_draft(mock_db_session, source.id)
        assert new_agent.key == "original-agent-draft"
        assert new_agent.status == "draft"
        assert mock_db_session.add.call_count >= 1  # 至少添加了新 agent


# ---------------------------------------------------------------------------
# Model CRUD
# ---------------------------------------------------------------------------

class TestModelCatalog:
    """Model catalog CRUD."""

    @pytest.mark.asyncio
    async def test_create_model_catalog(self, mock_db_session):
        from ibreeze_backend.catalog.service import create_model

        model = await create_model(
            mock_db_session, "openai", "gpt-4", "GPT-4",
            context_window=8192, supports_tools=True,
            supports_streaming=True, supports_vision=False,
        )
        assert model.provider_key == "openai"
        assert model.model_key == "gpt-4"
        # status 由 mapped_column(default="draft") 在 INSERT 时设置，实例化时为 None
        assert model.status is None
        mock_db_session.add.assert_called_once()


# ---------------------------------------------------------------------------
# Provider CRUD
# ---------------------------------------------------------------------------

class TestProviderCatalog:
    """Provider catalog CRUD."""

    @pytest.mark.asyncio
    async def test_create_provider_catalog(self, mock_db_session):
        from ibreeze_backend.catalog.service import create_provider

        provider = await create_provider(
            mock_db_session, "OpenAI", "https://api.openai.com", "openai"
        )
        assert provider.display_name == "OpenAI"
        assert provider.api_protocol == "openai"
        # status 由 mapped_column(default="draft") 在 INSERT 时设置，实例化时为 None
        assert provider.status is None
        mock_db_session.add.assert_called_once()


# ---------------------------------------------------------------------------
# Agent-Model binding
# ---------------------------------------------------------------------------

class TestAgentModelBinding:
    """Agent-Model and Provider-Model bindings."""

    @pytest.mark.asyncio
    async def test_create_agent_model_binding(self, mock_db_session):
        from ibreeze_backend.catalog.service import create_agent_model_binding

        agent = MagicMock()
        agent.id = uuid.uuid4()
        model = MagicMock()
        model.id = uuid.uuid4()

        call_idx = [0]
        def side_effect(stmt):
            call_idx[0] += 1
            if call_idx[0] == 1:
                return _mock_result(agent)
            return _mock_result(model)
        mock_db_session.execute.side_effect = side_effect

        binding = await create_agent_model_binding(mock_db_session, agent.id, model.id, {"min": "1.0"})
        assert binding.agent_id == agent.id
        assert binding.model_id == model.id
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_provider_model_binding(self, mock_db_session):
        from ibreeze_backend.catalog.service import create_provider_model_binding

        provider = MagicMock()
        provider.id = uuid.uuid4()
        model = MagicMock()
        model.id = uuid.uuid4()

        call_idx = [0]
        def side_effect(stmt):
            call_idx[0] += 1
            if call_idx[0] == 1:
                return _mock_result(provider)
            return _mock_result(model)
        mock_db_session.execute.side_effect = side_effect

        binding = await create_provider_model_binding(
            mock_db_session, provider.id, model.id, "openai", {"stream": True}
        )
        assert binding.provider_id == provider.id
        assert binding.model_id == model.id
        mock_db_session.add.assert_called_once()
