"""Catalog revision state machines and deterministic validation."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import uuid
from collections.abc import Sequence
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.catalog.models import (
    AgentCatalog,
    AgentModelBinding,
    AgentVersionRange,
    ModelCatalog,
    ProviderCatalog,
    ProviderModelBinding,
)
from ibreeze_backend.catalog.schemas import (
    AgentCreate,
    AgentModelBindingCreate,
    AgentUpdate,
    AgentVersionCreate,
    ModelCreate,
    ModelUpdate,
    ProviderCreate,
    ProviderModelBindingCreate,
    ProviderUpdate,
)

_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_DOMAIN = re.compile(
    r"^(?:\*\.)?(?=.{1,253}\.?$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_FORBIDDEN_REQUEST_KEYS = {
    "model",
    "stream",
    "tools",
    "messages",
    "input",
    "authorization",
    "api_key",
    "url",
}

class MutableCatalogResource(Protocol):
    status: str
    version: int


def _semver(value: str) -> tuple[int, int, int, tuple[str, ...]]:
    match = _SEMVER.fullmatch(value)
    if match is None:
        raise ValueError("CATALOG_SEMVER_INVALID")
    prerelease = tuple((match.group(4) or "").split(".")) if match.group(4) else ()
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease


def _validate_range(minimum: str, maximum: str) -> None:
    if _semver(minimum) >= _semver(maximum):
        raise ValueError("CATALOG_VERSION_RANGE_INVALID")


def _content_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _assert_mutable[CatalogParent: MutableCatalogResource](resource: CatalogParent) -> None:
    if resource.status == "published":
        raise ValueError("CATALOG_REVISION_IMMUTABLE")


def _assert_version[CatalogParent: MutableCatalogResource](
    resource: CatalogParent,
    expected_version: int,
) -> None:
    if resource.version != expected_version:
        raise ValueError("OPTIMISTIC_LOCK_CONFLICT")


def _normalize_provider_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("PROVIDER_BASE_URL_INVALID")
    try:
        host = parsed.hostname.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("PROVIDER_BASE_URL_INVALID") from exc
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        address = None
    if address is not None and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise ValueError("PROVIDER_BASE_URL_FORBIDDEN")
    port = f":{parsed.port}" if parsed.port is not None else ""
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", f"{host}{port}", path, "", ""))


def _validate_domains(domains: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for value in domains:
        domain = value.rstrip(".").encode("idna").decode("ascii").lower()
        if not _DOMAIN.fullmatch(domain):
            raise ValueError("CATALOG_NETWORK_DOMAIN_INVALID")
        normalized.append(domain)
    if len(normalized) != len(set(normalized)):
        raise ValueError("CATALOG_NETWORK_DOMAIN_DUPLICATE")
    return normalized


def _validate_model_values(model: ModelCatalog) -> None:
    if model.context_window < 8192 or not 1 <= model.max_output_tokens <= model.context_window - 4096:
        raise ValueError("MODEL_CAPABILITY_INVALID")
    if not model.supports_streaming:
        raise ValueError("MODEL_STREAMING_REQUIRED")


async def create_agent(db: AsyncSession, body: AgentCreate) -> AgentCatalog:
    exists = await db.scalar(
        select(func.count()).select_from(AgentCatalog).where(AgentCatalog.key == body.key)
    )
    if exists:
        raise ValueError("CATALOG_LOGICAL_KEY_EXISTS")
    resource = AgentCatalog(**body.model_dump(), catalog_revision=1, status="draft", version=1)
    db.add(resource)
    await db.flush()
    return resource


async def get_agent(db: AsyncSession, resource_id: uuid.UUID) -> AgentCatalog | None:
    result = await db.execute(select(AgentCatalog).where(AgentCatalog.id == resource_id))
    return result.scalar_one_or_none()


async def list_agents(db: AsyncSession, limit: int = 50) -> list[AgentCatalog]:
    result = await db.scalars(select(AgentCatalog).order_by(AgentCatalog.created_at.desc()).limit(limit))
    return list(result)


async def update_agent(
    db: AsyncSession,
    resource_id: uuid.UUID,
    body: AgentUpdate,
    expected_version: int,
) -> AgentCatalog:
    resource = await _locked(db, AgentCatalog, resource_id)
    _assert_mutable(resource)
    _assert_version(resource, expected_version)
    for name, value in body.model_dump(exclude_unset=True).items():
        setattr(resource, name, value)
    resource.status = "draft"
    resource.version += 1
    await db.flush()
    return resource


async def delete_agent(db: AsyncSession, resource_id: uuid.UUID, expected_version: int) -> None:
    resource = await _locked(db, AgentCatalog, resource_id)
    _assert_mutable(resource)
    _assert_version(resource, expected_version)
    await db.delete(resource)
    await db.flush()


async def validate_agent(db: AsyncSession, resource_id: uuid.UUID) -> AgentCatalog:
    resource = await _locked(db, AgentCatalog, resource_id)
    _assert_mutable(resource)
    versions = list(
        await db.scalars(
            select(AgentVersionRange).where(AgentVersionRange.agent_id == resource_id)
        )
    )
    if not versions:
        raise ValueError("AGENT_VERSION_REQUIRED")
    for item in versions:
        _validate_range(item.min_version, item.max_version_exclusive)
        _validate_domains(item.network_domains)
    for index, left in enumerate(versions):
        for right in versions[index + 1 :]:
            if set(left.supported_platforms) & set(right.supported_platforms) and (
                _semver(left.min_version) < _semver(right.max_version_exclusive)
                and _semver(right.min_version) < _semver(left.max_version_exclusive)
            ):
                raise ValueError("AGENT_VERSION_RANGE_OVERLAP")
    resource.status = "validated"
    await db.flush()
    return resource


async def clone_agent_revision(db: AsyncSession, resource_id: uuid.UUID) -> AgentCatalog:
    source = await _locked(db, AgentCatalog, resource_id)
    if source.status != "published":
        raise ValueError("CATALOG_REVISION_SOURCE_NOT_PUBLISHED")
    revision = (
        await db.scalar(
            select(func.max(AgentCatalog.catalog_revision)).where(AgentCatalog.key == source.key)
        )
        or 0
    ) + 1
    clone = AgentCatalog(
        key=source.key,
        catalog_revision=revision,
        display_name=source.display_name,
        description=source.description,
        status="draft",
        version=1,
    )
    db.add(clone)
    await db.flush()
    versions = await db.scalars(
        select(AgentVersionRange).where(AgentVersionRange.agent_id == source.id)
    )
    for version_item in versions:
        db.add(
            AgentVersionRange(
                agent_id=clone.id,
                min_version=version_item.min_version,
                max_version_exclusive=version_item.max_version_exclusive,
                executable_names=version_item.executable_names,
                supported_platforms=version_item.supported_platforms,
                probe_argv=version_item.probe_argv,
                capability_tags=version_item.capability_tags,
                network_domains=version_item.network_domains,
                adapter_contract_version=version_item.adapter_contract_version,
                content_sha256=version_item.content_sha256,
            )
        )
    bindings = await db.scalars(
        select(AgentModelBinding).where(AgentModelBinding.agent_id == source.id)
    )
    for binding_item in bindings:
        db.add(
            AgentModelBinding(
                agent_id=clone.id,
                model_id=binding_item.model_id,
                min_agent_version=binding_item.min_agent_version,
                max_agent_version_exclusive=binding_item.max_agent_version_exclusive,
            )
        )
    await db.flush()
    return clone


async def create_agent_version(
    db: AsyncSession,
    agent_id: uuid.UUID,
    body: AgentVersionCreate,
) -> AgentVersionRange:
    agent = await _locked(db, AgentCatalog, agent_id)
    _assert_mutable(agent)
    _validate_range(body.min_version, body.max_version_exclusive)
    domains = _validate_domains(body.network_domains)
    payload = {**body.model_dump(), "network_domains": domains}
    version = AgentVersionRange(
        agent_id=agent_id,
        **payload,
        content_sha256=_content_sha256(payload),
    )
    db.add(version)
    agent.status = "draft"
    agent.version += 1
    await db.flush()
    return version


async def list_agent_versions(db: AsyncSession, agent_id: uuid.UUID) -> list[AgentVersionRange]:
    return list(
        await db.scalars(
            select(AgentVersionRange)
            .where(AgentVersionRange.agent_id == agent_id)
            .order_by(AgentVersionRange.created_at)
        )
    )


async def delete_agent_version(
    db: AsyncSession,
    agent_id: uuid.UUID,
    version_id: uuid.UUID,
) -> None:
    agent = await _locked(db, AgentCatalog, agent_id)
    _assert_mutable(agent)
    item = await db.scalar(
        select(AgentVersionRange)
        .where(
            AgentVersionRange.id == version_id,
            AgentVersionRange.agent_id == agent_id,
        )
        .with_for_update()
    )
    if item is None or item.published_at is not None:
        raise ValueError("CATALOG_CHILD_IMMUTABLE_OR_MISSING")
    await db.delete(item)
    agent.status = "draft"
    agent.version += 1
    await db.flush()


async def create_model(db: AsyncSession, body: ModelCreate) -> ModelCatalog:
    exists = await db.scalar(
        select(func.count())
        .select_from(ModelCatalog)
        .where(
            ModelCatalog.provider_key == body.provider_key,
            ModelCatalog.model_key == body.model_key,
        )
    )
    if exists:
        raise ValueError("CATALOG_LOGICAL_KEY_EXISTS")
    resource = ModelCatalog(**body.model_dump(), catalog_revision=1, status="draft", version=1)
    _validate_model_values(resource)
    db.add(resource)
    await db.flush()
    return resource


async def get_model(db: AsyncSession, resource_id: uuid.UUID) -> ModelCatalog | None:
    result = await db.execute(select(ModelCatalog).where(ModelCatalog.id == resource_id))
    return result.scalar_one_or_none()


async def list_models(db: AsyncSession, limit: int = 50) -> list[ModelCatalog]:
    return list(
        await db.scalars(select(ModelCatalog).order_by(ModelCatalog.created_at.desc()).limit(limit))
    )


async def update_model(
    db: AsyncSession,
    resource_id: uuid.UUID,
    body: ModelUpdate,
    expected_version: int,
) -> ModelCatalog:
    resource = await _locked(db, ModelCatalog, resource_id)
    _assert_mutable(resource)
    _assert_version(resource, expected_version)
    for name, value in body.model_dump(exclude_unset=True).items():
        setattr(resource, name, value)
    _validate_model_values(resource)
    resource.status = "draft"
    resource.version += 1
    await db.flush()
    return resource


async def delete_model(db: AsyncSession, resource_id: uuid.UUID, expected_version: int) -> None:
    resource = await _locked(db, ModelCatalog, resource_id)
    _assert_mutable(resource)
    _assert_version(resource, expected_version)
    await db.delete(resource)
    await db.flush()


async def validate_model(db: AsyncSession, resource_id: uuid.UUID) -> ModelCatalog:
    resource = await _locked(db, ModelCatalog, resource_id)
    _assert_mutable(resource)
    _validate_model_values(resource)
    resource.status = "validated"
    await db.flush()
    return resource


async def clone_model_revision(db: AsyncSession, resource_id: uuid.UUID) -> ModelCatalog:
    source = await _locked(db, ModelCatalog, resource_id)
    if source.status != "published":
        raise ValueError("CATALOG_REVISION_SOURCE_NOT_PUBLISHED")
    revision = (
        await db.scalar(
            select(func.max(ModelCatalog.catalog_revision)).where(
                ModelCatalog.provider_key == source.provider_key,
                ModelCatalog.model_key == source.model_key,
            )
        )
        or 0
    ) + 1
    clone = ModelCatalog(
        provider_key=source.provider_key,
        model_key=source.model_key,
        display_name=source.display_name,
        context_window=source.context_window,
        max_output_tokens=source.max_output_tokens,
        tokenizer_key=source.tokenizer_key,
        supports_tools=source.supports_tools,
        supports_streaming=source.supports_streaming,
        supports_vision=source.supports_vision,
        catalog_revision=revision,
        status="draft",
        version=1,
    )
    db.add(clone)
    await db.flush()
    return clone


async def create_provider(db: AsyncSession, body: ProviderCreate) -> ProviderCatalog:
    exists = await db.scalar(
        select(func.count()).select_from(ProviderCatalog).where(ProviderCatalog.key == body.key)
    )
    if exists:
        raise ValueError("CATALOG_LOGICAL_KEY_EXISTS")
    values = body.model_dump()
    values["base_url"] = _normalize_provider_url(body.base_url)
    resource = ProviderCatalog(**values, catalog_revision=1, status="draft", version=1)
    db.add(resource)
    await db.flush()
    return resource


async def get_provider(db: AsyncSession, resource_id: uuid.UUID) -> ProviderCatalog | None:
    result = await db.execute(select(ProviderCatalog).where(ProviderCatalog.id == resource_id))
    return result.scalar_one_or_none()


async def list_providers(db: AsyncSession, limit: int = 50) -> list[ProviderCatalog]:
    return list(
        await db.scalars(
            select(ProviderCatalog).order_by(ProviderCatalog.created_at.desc()).limit(limit)
        )
    )


async def update_provider(
    db: AsyncSession,
    resource_id: uuid.UUID,
    body: ProviderUpdate,
    expected_version: int,
) -> ProviderCatalog:
    resource = await _locked(db, ProviderCatalog, resource_id)
    _assert_mutable(resource)
    _assert_version(resource, expected_version)
    values = body.model_dump(exclude_unset=True)
    if "base_url" in values:
        values["base_url"] = _normalize_provider_url(str(values["base_url"]))
    for name, value in values.items():
        setattr(resource, name, value)
    resource.status = "draft"
    resource.version += 1
    await db.flush()
    return resource


async def delete_provider(db: AsyncSession, resource_id: uuid.UUID, expected_version: int) -> None:
    resource = await _locked(db, ProviderCatalog, resource_id)
    _assert_mutable(resource)
    _assert_version(resource, expected_version)
    await db.delete(resource)
    await db.flush()


async def validate_provider(db: AsyncSession, resource_id: uuid.UUID) -> ProviderCatalog:
    resource = await _locked(db, ProviderCatalog, resource_id)
    _assert_mutable(resource)
    resource.base_url = _normalize_provider_url(resource.base_url)
    resource.status = "validated"
    await db.flush()
    return resource


async def clone_provider_revision(db: AsyncSession, resource_id: uuid.UUID) -> ProviderCatalog:
    source = await _locked(db, ProviderCatalog, resource_id)
    if source.status != "published":
        raise ValueError("CATALOG_REVISION_SOURCE_NOT_PUBLISHED")
    revision = (
        await db.scalar(
            select(func.max(ProviderCatalog.catalog_revision)).where(
                ProviderCatalog.key == source.key
            )
        )
        or 0
    ) + 1
    clone = ProviderCatalog(
        key=source.key,
        catalog_revision=revision,
        display_name=source.display_name,
        protocol=source.protocol,
        base_url=source.base_url,
        auth_scheme=source.auth_scheme,
        status="draft",
        version=1,
    )
    db.add(clone)
    await db.flush()
    bindings = await db.scalars(
        select(ProviderModelBinding).where(ProviderModelBinding.provider_id == source.id)
    )
    for item in bindings:
        db.add(
            ProviderModelBinding(
                provider_id=clone.id,
                model_id=item.model_id,
                provider_model_name=item.provider_model_name,
                request_defaults=item.request_defaults,
            )
        )
    await db.flush()
    return clone


async def create_agent_model_binding(
    db: AsyncSession,
    agent_id: uuid.UUID,
    body: AgentModelBindingCreate,
) -> AgentModelBinding:
    agent = await _locked(db, AgentCatalog, agent_id)
    _assert_mutable(agent)
    model = await get_model(db, body.model_id)
    if model is None:
        raise ValueError("MODEL_NOT_FOUND")
    _validate_range(body.min_agent_version, body.max_agent_version_exclusive)
    versions = await list_agent_versions(db, agent_id)
    if not any(
        _semver(item.min_version) <= _semver(body.min_agent_version)
        and _semver(body.max_agent_version_exclusive) <= _semver(item.max_version_exclusive)
        for item in versions
    ):
        raise ValueError("AGENT_MODEL_BINDING_RANGE_INVALID")
    item = AgentModelBinding(agent_id=agent_id, **body.model_dump())
    db.add(item)
    agent.status = "draft"
    agent.version += 1
    await db.flush()
    return item


async def list_agent_model_bindings(
    db: AsyncSession,
    agent_id: uuid.UUID,
) -> list[AgentModelBinding]:
    return list(
        await db.scalars(
            select(AgentModelBinding)
            .where(AgentModelBinding.agent_id == agent_id)
            .order_by(AgentModelBinding.created_at)
        )
    )


async def delete_agent_model_binding(
    db: AsyncSession,
    agent_id: uuid.UUID,
    binding_id: uuid.UUID,
) -> None:
    agent = await _locked(db, AgentCatalog, agent_id)
    _assert_mutable(agent)
    item = await db.scalar(
        select(AgentModelBinding)
        .where(
            AgentModelBinding.id == binding_id,
            AgentModelBinding.agent_id == agent_id,
        )
        .with_for_update()
    )
    if item is None:
        raise ValueError("CATALOG_BINDING_NOT_FOUND")
    await db.delete(item)
    agent.status = "draft"
    agent.version += 1
    await db.flush()


async def create_provider_model_binding(
    db: AsyncSession,
    provider_id: uuid.UUID,
    body: ProviderModelBindingCreate,
) -> ProviderModelBinding:
    provider = await _locked(db, ProviderCatalog, provider_id)
    _assert_mutable(provider)
    if await get_model(db, body.model_id) is None:
        raise ValueError("MODEL_NOT_FOUND")
    lowered = {key.lower() for key in body.request_defaults}
    if lowered & _FORBIDDEN_REQUEST_KEYS:
        raise ValueError("PROVIDER_REQUEST_DEFAULTS_FORBIDDEN")
    item = ProviderModelBinding(provider_id=provider_id, **body.model_dump())
    db.add(item)
    provider.status = "draft"
    provider.version += 1
    await db.flush()
    return item


async def list_provider_model_bindings(
    db: AsyncSession,
    provider_id: uuid.UUID,
) -> list[ProviderModelBinding]:
    return list(
        await db.scalars(
            select(ProviderModelBinding)
            .where(ProviderModelBinding.provider_id == provider_id)
            .order_by(ProviderModelBinding.created_at)
        )
    )


async def delete_provider_model_binding(
    db: AsyncSession,
    provider_id: uuid.UUID,
    binding_id: uuid.UUID,
) -> None:
    provider = await _locked(db, ProviderCatalog, provider_id)
    _assert_mutable(provider)
    item = await db.scalar(
        select(ProviderModelBinding)
        .where(
            ProviderModelBinding.id == binding_id,
            ProviderModelBinding.provider_id == provider_id,
        )
        .with_for_update()
    )
    if item is None:
        raise ValueError("CATALOG_BINDING_NOT_FOUND")
    await db.delete(item)
    provider.status = "draft"
    provider.version += 1
    await db.flush()


async def _locked[CatalogParent: AgentCatalog | ModelCatalog | ProviderCatalog](
    db: AsyncSession,
    model: type[CatalogParent],
    resource_id: uuid.UUID,
) -> CatalogParent:
    statement: Select[tuple[CatalogParent]] = select(model).where(model.id == resource_id).with_for_update()
    resource = await db.scalar(statement)
    if resource is None:
        raise ValueError("CATALOG_RESOURCE_NOT_FOUND")
    return resource
