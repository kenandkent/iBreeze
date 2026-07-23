"""Catalog service with status machine enforcement."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.catalog.models import (
    AgentCatalog,
    AgentModelBinding,
    AgentVersionRange,
    ModelCatalog,
    ProviderCatalog,
    ProviderModelBinding,
)

VALID_TRANSITIONS = {
    "draft": {"validated"},
    "validated": {"published"},
}


def _validate_transition(current: str, target: str) -> None:
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(
            f"Invalid status transition: {current} -> {target}"
        )


async def create_agent(
    db: AsyncSession, key: str, display_name: str, description: str | None
) -> AgentCatalog:
    existing = await db.execute(
        select(AgentCatalog).where(AgentCatalog.key == key)
    )
    if existing.scalar_one_or_none():
        raise ValueError("Agent key already exists")

    agent = AgentCatalog(
        key=key,
        display_name=display_name,
        description=description,
    )
    db.add(agent)
    await db.flush()
    return agent


async def get_agent(db: AsyncSession, agent_id: uuid.UUID) -> AgentCatalog | None:
    result = await db.execute(
        select(AgentCatalog).where(AgentCatalog.id == agent_id)
    )
    return result.scalar_one_or_none()


async def list_agents(
    db: AsyncSession, skip: int, limit: int
) -> tuple[list[AgentCatalog], int]:
    count_result = await db.execute(select(func.count(AgentCatalog.id)))
    total = count_result.scalar() or 0
    result = await db.execute(
        select(AgentCatalog).order_by(AgentCatalog.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all()), total


async def update_agent(
    db: AsyncSession,
    agent_id: uuid.UUID,
    display_name: str | None,
    description: str | None,
) -> AgentCatalog:
    agent = await get_agent(db, agent_id)
    if not agent:
        raise ValueError("Agent not found")
    if agent.status == "published":
        raise ValueError("Cannot update published agent")
    if display_name is not None:
        agent.display_name = display_name
    if description is not None:
        agent.description = description
    await db.flush()
    return agent


async def transition_agent_status(
    db: AsyncSession, agent_id: uuid.UUID, target_status: str
) -> AgentCatalog:
    agent = await get_agent(db, agent_id)
    if not agent:
        raise ValueError("Agent not found")
    _validate_transition(agent.status, target_status)
    agent.status = target_status
    agent.catalog_revision += 1
    await db.flush()
    return agent


async def delete_agent(db: AsyncSession, agent_id: uuid.UUID) -> None:
    agent = await get_agent(db, agent_id)
    if not agent:
        raise ValueError("Agent not found")
    if agent.status == "published":
        raise ValueError("Cannot delete published agent")
    await db.delete(agent)
    await db.flush()


async def copy_agent_to_draft(
    db: AsyncSession, agent_id: uuid.UUID
) -> AgentCatalog:
    source = await get_agent(db, agent_id)
    if not source:
        raise ValueError("Agent not found")
    if source.status != "published":
        raise ValueError("Can only copy published agent to draft")

    new_agent = AgentCatalog(
        key=f"{source.key}-draft",
        display_name=source.display_name,
        description=source.description,
        status="draft",
    )
    db.add(new_agent)
    await db.flush()

    versions_result = await db.execute(
        select(AgentVersionRange).where(
            AgentVersionRange.agent_id == agent_id
        )
    )
    for v in versions_result.scalars().all():
        new_version = AgentVersionRange(
            agent_id=new_agent.id,
            executable_names=v.executable_names,
            supported_platforms=v.supported_platforms,
            min_version=v.min_version,
            max_version_exclusive=v.max_version_exclusive,
            probe_command=v.probe_command,
            capability_tags=v.capability_tags,
            network_domains=v.network_domains,
            adapter_contract_version=v.adapter_contract_version,
            content_sha256=v.content_sha256,
        )
        db.add(new_version)

    await db.flush()
    return new_agent


async def create_agent_version(
    db: AsyncSession,
    agent_id: uuid.UUID,
    executable_names: list[str] | None,
    supported_platforms: list[str] | None,
    min_version: str | None,
    max_version_exclusive: str | None,
    probe_command: dict | None,
    capability_tags: list[str] | None,
    network_domains: list[str] | None,
    adapter_contract_version: int | None,
    content_sha256: str | None,
) -> AgentVersionRange:
    agent = await get_agent(db, agent_id)
    if not agent:
        raise ValueError("Agent not found")

    version = AgentVersionRange(
        agent_id=agent_id,
        executable_names=executable_names,
        supported_platforms=supported_platforms,
        min_version=min_version,
        max_version_exclusive=max_version_exclusive,
        probe_command=probe_command,
        capability_tags=capability_tags,
        network_domains=network_domains,
        adapter_contract_version=adapter_contract_version,
        content_sha256=content_sha256,
    )
    db.add(version)
    await db.flush()
    return version


async def list_agent_versions(
    db: AsyncSession, agent_id: uuid.UUID, skip: int, limit: int
) -> tuple[list[AgentVersionRange], int]:
    count_result = await db.execute(
        select(func.count(AgentVersionRange.id)).where(
            AgentVersionRange.agent_id == agent_id
        )
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(AgentVersionRange)
        .where(AgentVersionRange.agent_id == agent_id)
        .order_by(AgentVersionRange.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def create_model(
    db: AsyncSession,
    provider_key: str,
    model_key: str,
    display_name: str,
    context_window: int | None,
    supports_tools: bool,
    supports_streaming: bool,
    supports_vision: bool,
) -> ModelCatalog:
    model = ModelCatalog(
        provider_key=provider_key,
        model_key=model_key,
        display_name=display_name,
        context_window=context_window,
        supports_tools=supports_tools,
        supports_streaming=supports_streaming,
        supports_vision=supports_vision,
    )
    db.add(model)
    await db.flush()
    return model


async def get_model(db: AsyncSession, model_id: uuid.UUID) -> ModelCatalog | None:
    result = await db.execute(
        select(ModelCatalog).where(ModelCatalog.id == model_id)
    )
    return result.scalar_one_or_none()


async def list_models(
    db: AsyncSession, skip: int, limit: int
) -> tuple[list[ModelCatalog], int]:
    count_result = await db.execute(select(func.count(ModelCatalog.id)))
    total = count_result.scalar() or 0
    result = await db.execute(
        select(ModelCatalog).order_by(ModelCatalog.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all()), total


async def update_model(
    db: AsyncSession,
    model_id: uuid.UUID,
    display_name: str | None,
    context_window: int | None,
    supports_tools: bool | None,
    supports_streaming: bool | None,
    supports_vision: bool | None,
) -> ModelCatalog:
    model = await get_model(db, model_id)
    if not model:
        raise ValueError("Model not found")
    if model.status == "published":
        raise ValueError("Cannot update published model")
    if display_name is not None:
        model.display_name = display_name
    if context_window is not None:
        model.context_window = context_window
    if supports_tools is not None:
        model.supports_tools = supports_tools
    if supports_streaming is not None:
        model.supports_streaming = supports_streaming
    if supports_vision is not None:
        model.supports_vision = supports_vision
    await db.flush()
    return model


async def transition_model_status(
    db: AsyncSession, model_id: uuid.UUID, target_status: str
) -> ModelCatalog:
    model = await get_model(db, model_id)
    if not model:
        raise ValueError("Model not found")
    _validate_transition(model.status, target_status)
    model.status = target_status
    await db.flush()
    return model


async def delete_model(db: AsyncSession, model_id: uuid.UUID) -> None:
    model = await get_model(db, model_id)
    if not model:
        raise ValueError("Model not found")
    if model.status == "published":
        raise ValueError("Cannot delete published model")
    await db.delete(model)
    await db.flush()


async def copy_model_to_draft(
    db: AsyncSession, model_id: uuid.UUID
) -> ModelCatalog:
    source = await get_model(db, model_id)
    if not source:
        raise ValueError("Model not found")
    if source.status != "published":
        raise ValueError("Can only copy published model to draft")

    new_model = ModelCatalog(
        provider_key=source.provider_key,
        model_key=source.model_key,
        display_name=source.display_name,
        context_window=source.context_window,
        supports_tools=source.supports_tools,
        supports_streaming=source.supports_streaming,
        supports_vision=source.supports_vision,
        status="draft",
    )
    db.add(new_model)
    await db.flush()
    return new_model


async def create_provider(
    db: AsyncSession,
    display_name: str,
    base_url: str | None,
    api_protocol: str,
) -> ProviderCatalog:
    provider = ProviderCatalog(
        display_name=display_name,
        base_url=base_url,
        api_protocol=api_protocol,
    )
    db.add(provider)
    await db.flush()
    return provider


async def get_provider(
    db: AsyncSession, provider_id: uuid.UUID
) -> ProviderCatalog | None:
    result = await db.execute(
        select(ProviderCatalog).where(ProviderCatalog.id == provider_id)
    )
    return result.scalar_one_or_none()


async def list_providers(
    db: AsyncSession, skip: int, limit: int
) -> tuple[list[ProviderCatalog], int]:
    count_result = await db.execute(select(func.count(ProviderCatalog.id)))
    total = count_result.scalar() or 0
    result = await db.execute(
        select(ProviderCatalog).order_by(ProviderCatalog.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all()), total


async def update_provider(
    db: AsyncSession,
    provider_id: uuid.UUID,
    display_name: str | None,
    base_url: str | None,
    api_protocol: str | None,
) -> ProviderCatalog:
    provider = await get_provider(db, provider_id)
    if not provider:
        raise ValueError("Provider not found")
    if provider.status == "published":
        raise ValueError("Cannot update published provider")
    if display_name is not None:
        provider.display_name = display_name
    if base_url is not None:
        provider.base_url = base_url
    if api_protocol is not None:
        provider.api_protocol = api_protocol
    await db.flush()
    return provider


async def transition_provider_status(
    db: AsyncSession, provider_id: uuid.UUID, target_status: str
) -> ProviderCatalog:
    provider = await get_provider(db, provider_id)
    if not provider:
        raise ValueError("Provider not found")
    _validate_transition(provider.status, target_status)
    provider.status = target_status
    await db.flush()
    return provider


async def delete_provider(db: AsyncSession, provider_id: uuid.UUID) -> None:
    provider = await get_provider(db, provider_id)
    if not provider:
        raise ValueError("Provider not found")
    if provider.status == "published":
        raise ValueError("Cannot delete published provider")
    await db.delete(provider)
    await db.flush()


async def copy_provider_to_draft(
    db: AsyncSession, provider_id: uuid.UUID
) -> ProviderCatalog:
    source = await get_provider(db, provider_id)
    if not source:
        raise ValueError("Provider not found")
    if source.status != "published":
        raise ValueError("Can only copy published provider to draft")

    new_provider = ProviderCatalog(
        display_name=source.display_name,
        base_url=source.base_url,
        api_protocol=source.api_protocol,
        status="draft",
    )
    db.add(new_provider)
    await db.flush()
    return new_provider


async def create_agent_model_binding(
    db: AsyncSession,
    agent_id: uuid.UUID,
    model_id: uuid.UUID,
    agent_version_range: dict | None,
) -> AgentModelBinding:
    agent = await get_agent(db, agent_id)
    if not agent:
        raise ValueError("Agent not found")
    model = await get_model(db, model_id)
    if not model:
        raise ValueError("Model not found")

    binding = AgentModelBinding(
        agent_id=agent_id,
        model_id=model_id,
        agent_version_range=agent_version_range,
    )
    db.add(binding)
    await db.flush()
    return binding


async def list_agent_model_bindings(
    db: AsyncSession, agent_id: uuid.UUID, skip: int, limit: int
) -> tuple[list[AgentModelBinding], int]:
    count_result = await db.execute(
        select(func.count(AgentModelBinding.id)).where(
            AgentModelBinding.agent_id == agent_id
        )
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(AgentModelBinding)
        .where(AgentModelBinding.agent_id == agent_id)
        .order_by(AgentModelBinding.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def create_provider_model_binding(
    db: AsyncSession,
    provider_id: uuid.UUID,
    model_id: uuid.UUID,
    api_protocol: str,
    capabilities: dict | None,
) -> ProviderModelBinding:
    provider = await get_provider(db, provider_id)
    if not provider:
        raise ValueError("Provider not found")
    model = await get_model(db, model_id)
    if not model:
        raise ValueError("Model not found")

    binding = ProviderModelBinding(
        provider_id=provider_id,
        model_id=model_id,
        api_protocol=api_protocol,
        capabilities=capabilities,
    )
    db.add(binding)
    await db.flush()
    return binding


async def list_provider_model_bindings(
    db: AsyncSession, provider_id: uuid.UUID, skip: int, limit: int
) -> tuple[list[ProviderModelBinding], int]:
    count_result = await db.execute(
        select(func.count(ProviderModelBinding.id)).where(
            ProviderModelBinding.provider_id == provider_id
        )
    )
    total = count_result.scalar() or 0
    result = await db.execute(
        select(ProviderModelBinding)
        .where(ProviderModelBinding.provider_id == provider_id)
        .order_by(ProviderModelBinding.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total
