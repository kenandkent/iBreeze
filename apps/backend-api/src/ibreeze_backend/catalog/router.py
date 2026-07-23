"""Catalog CRUD router."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.catalog.schemas import (
    AgentCreate,
    AgentListResponse,
    AgentModelBindingCreate,
    AgentModelBindingListResponse,
    AgentModelBindingResponse,
    AgentResponse,
    AgentUpdate,
    AgentVersionCreate,
    AgentVersionListResponse,
    AgentVersionResponse,
    ModelCreate,
    ModelListResponse,
    ModelResponse,
    ModelUpdate,
    ProviderCreate,
    ProviderListResponse,
    ProviderModelBindingCreate,
    ProviderModelBindingListResponse,
    ProviderModelBindingResponse,
    ProviderResponse,
    ProviderUpdate,
    StatusTransitionRequest,
)
from ibreeze_backend.catalog.service import (
    copy_agent_to_draft,
    copy_model_to_draft,
    copy_provider_to_draft,
    create_agent,
    create_agent_model_binding,
    create_agent_version,
    create_model,
    create_provider,
    create_provider_model_binding,
    delete_agent,
    delete_model,
    delete_provider,
    get_agent,
    get_model,
    get_provider,
    list_agent_model_bindings,
    list_agent_versions,
    list_agents,
    list_models,
    list_provider_model_bindings,
    list_providers,
    transition_agent_status,
    transition_model_status,
    transition_provider_status,
    update_agent,
    update_model,
    update_provider,
)
from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.user import User

router = APIRouter(prefix="/admin/api/v1/catalog", tags=["catalog"])


# --- Agents ---


@router.post(
    "/agents",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_endpoint(
    body: AgentCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        agent = await create_agent(db, body.key, body.display_name, body.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return agent


@router.get("/agents", response_model=AgentListResponse)
async def list_agents_endpoint(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    agents, total = await list_agents(db, skip=skip, limit=limit)
    return {"agents": agents, "total": total}


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent_endpoint(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    agent = await get_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent_endpoint(
    agent_id: uuid.UUID,
    body: AgentUpdate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        agent = await update_agent(
            db, agent_id, body.display_name, body.description
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return agent


@router.delete(
    "/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_agent_endpoint(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> None:
    try:
        await delete_agent(db, agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/agents/{agent_id}/status", response_model=AgentResponse)
async def transition_agent_status_endpoint(
    agent_id: uuid.UUID,
    body: StatusTransitionRequest,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        agent = await transition_agent_status(db, agent_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return agent


@router.post(
    "/agents/{agent_id}/copy-to-draft", response_model=AgentResponse
)
async def copy_agent_to_draft_endpoint(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        agent = await copy_agent_to_draft(db, agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return agent


# --- Agent Versions ---


@router.post(
    "/agents/{agent_id}/versions",
    response_model=AgentVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_version_endpoint(
    agent_id: uuid.UUID,
    body: AgentVersionCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        version = await create_agent_version(
            db,
            agent_id=agent_id,
            executable_names=body.executable_names,
            supported_platforms=body.supported_platforms,
            min_version=body.min_version,
            max_version_exclusive=body.max_version_exclusive,
            probe_command=body.probe_command,
            capability_tags=body.capability_tags,
            network_domains=body.network_domains,
            adapter_contract_version=body.adapter_contract_version,
            content_sha256=body.content_sha256,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return version


@router.get(
    "/agents/{agent_id}/versions", response_model=AgentVersionListResponse
)
async def list_agent_versions_endpoint(
    agent_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    versions, total = await list_agent_versions(
        db, agent_id=agent_id, skip=skip, limit=limit
    )
    return {"versions": versions, "total": total}


# --- Models ---


@router.post(
    "/models",
    response_model=ModelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_model_endpoint(
    body: ModelCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        model = await create_model(
            db,
            provider_key=body.provider_key,
            model_key=body.model_key,
            display_name=body.display_name,
            context_window=body.context_window,
            supports_tools=body.supports_tools,
            supports_streaming=body.supports_streaming,
            supports_vision=body.supports_vision,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return model


@router.get("/models", response_model=ModelListResponse)
async def list_models_endpoint(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    models, total = await list_models(db, skip=skip, limit=limit)
    return {"models": models, "total": total}


@router.get("/models/{model_id}", response_model=ModelResponse)
async def get_model_endpoint(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    model = await get_model(db, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.patch("/models/{model_id}", response_model=ModelResponse)
async def update_model_endpoint(
    model_id: uuid.UUID,
    body: ModelUpdate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        model = await update_model(
            db,
            model_id,
            display_name=body.display_name,
            context_window=body.context_window,
            supports_tools=body.supports_tools,
            supports_streaming=body.supports_streaming,
            supports_vision=body.supports_vision,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return model


@router.delete(
    "/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_model_endpoint(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> None:
    try:
        await delete_model(db, model_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/models/{model_id}/status", response_model=ModelResponse)
async def transition_model_status_endpoint(
    model_id: uuid.UUID,
    body: StatusTransitionRequest,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        model = await transition_model_status(db, model_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return model


@router.post(
    "/models/{model_id}/copy-to-draft", response_model=ModelResponse
)
async def copy_model_to_draft_endpoint(
    model_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        model = await copy_model_to_draft(db, model_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return model


# --- Providers ---


@router.post(
    "/providers",
    response_model=ProviderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider_endpoint(
    body: ProviderCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        provider = await create_provider(
            db, body.display_name, body.base_url, body.api_protocol
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return provider


@router.get("/providers", response_model=ProviderListResponse)
async def list_providers_endpoint(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    providers, total = await list_providers(db, skip=skip, limit=limit)
    return {"providers": providers, "total": total}


@router.get("/providers/{provider_id}", response_model=ProviderResponse)
async def get_provider_endpoint(
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    provider = await get_provider(db, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


@router.patch("/providers/{provider_id}", response_model=ProviderResponse)
async def update_provider_endpoint(
    provider_id: uuid.UUID,
    body: ProviderUpdate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        provider = await update_provider(
            db,
            provider_id,
            display_name=body.display_name,
            base_url=body.base_url,
            api_protocol=body.api_protocol,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return provider


@router.delete(
    "/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_provider_endpoint(
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> None:
    try:
        await delete_provider(db, provider_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch(
    "/providers/{provider_id}/status", response_model=ProviderResponse
)
async def transition_provider_status_endpoint(
    provider_id: uuid.UUID,
    body: StatusTransitionRequest,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        provider = await transition_provider_status(
            db, provider_id, body.status
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return provider


@router.post(
    "/providers/{provider_id}/copy-to-draft",
    response_model=ProviderResponse,
)
async def copy_provider_to_draft_endpoint(
    provider_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        provider = await copy_provider_to_draft(db, provider_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return provider


# --- Agent-Model Bindings ---


@router.post(
    "/agent-model-bindings",
    response_model=AgentModelBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_model_binding_endpoint(
    body: AgentModelBindingCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        binding = await create_agent_model_binding(
            db,
            agent_id=uuid.UUID(body.agent_id),
            model_id=uuid.UUID(body.model_id),
            agent_version_range=body.agent_version_range,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return binding


@router.get(
    "/agents/{agent_id}/model-bindings",
    response_model=AgentModelBindingListResponse,
)
async def list_agent_model_bindings_endpoint(
    agent_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    bindings, total = await list_agent_model_bindings(
        db, agent_id=agent_id, skip=skip, limit=limit
    )
    return {"bindings": bindings, "total": total}


# --- Provider-Model Bindings ---


@router.post(
    "/provider-model-bindings",
    response_model=ProviderModelBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider_model_binding_endpoint(
    body: ProviderModelBindingCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    try:
        binding = await create_provider_model_binding(
            db,
            provider_id=uuid.UUID(body.provider_id),
            model_id=uuid.UUID(body.model_id),
            api_protocol=body.api_protocol,
            capabilities=body.capabilities,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return binding


@router.get(
    "/providers/{provider_id}/model-bindings",
    response_model=ProviderModelBindingListResponse,
)
async def list_provider_model_bindings_endpoint(
    provider_id: uuid.UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict:
    bindings, total = await list_provider_model_bindings(
        db, provider_id=provider_id, skip=skip, limit=limit
    )
    return {"bindings": bindings, "total": total}
