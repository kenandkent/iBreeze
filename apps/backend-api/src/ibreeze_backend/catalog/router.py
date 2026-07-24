"""Canonical v1 management routes for Agent, Model and Provider catalogs."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ibreeze_backend.catalog.schemas import (
    AgentCreate,
    AgentModelBindingCreate,
    AgentModelBindingResponse,
    AgentResponse,
    AgentUpdate,
    AgentVersionCreate,
    AgentVersionResponse,
    ModelCreate,
    ModelResponse,
    ModelUpdate,
    ProviderCreate,
    ProviderModelBindingCreate,
    ProviderModelBindingResponse,
    ProviderResponse,
    ProviderUpdate,
)
from ibreeze_backend.catalog.service import (
    clone_agent_revision,
    clone_model_revision,
    clone_provider_revision,
    create_agent,
    create_agent_model_binding,
    create_agent_version,
    create_model,
    create_provider,
    create_provider_model_binding,
    delete_agent,
    delete_agent_model_binding,
    delete_agent_version,
    delete_model,
    delete_provider,
    delete_provider_model_binding,
    get_agent,
    get_model,
    get_provider,
    list_agent_model_bindings,
    list_agent_versions,
    list_agents,
    list_models,
    list_provider_model_bindings,
    list_providers,
    update_agent,
    update_model,
    update_provider,
    validate_agent,
    validate_model,
    validate_provider,
)
from ibreeze_backend.db.session import get_db_session
from ibreeze_backend.dependencies import get_current_user
from ibreeze_backend.models.user import User

router = APIRouter(prefix="/admin/api/v1", tags=["catalog"])
def _if_match(value: str | None) -> int:
    if value is None:
        raise HTTPException(status_code=428, detail="IF_MATCH_REQUIRED")
    try:
        parsed = int(value.strip('"'))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="IF_MATCH_INVALID") from exc
    if parsed < 1:
        raise HTTPException(status_code=400, detail="IF_MATCH_INVALID")
    return parsed


async def _call(operation: Callable[[], Awaitable[Any]]) -> Any:
    try:
        return await operation()
    except ValueError as exc:
        code = str(exc)
        if code == "CATALOG_RESOURCE_NOT_FOUND":
            http_status = 404
        elif code in {
            "CATALOG_REVISION_IMMUTABLE",
            "OPTIMISTIC_LOCK_CONFLICT",
            "CATALOG_LOGICAL_KEY_EXISTS",
        }:
            http_status = 409
        else:
            http_status = 422
        raise HTTPException(status_code=http_status, detail=code) from exc


def _page[ResponseModel: BaseModel](
    items: list[Any],
    schema: type[ResponseModel],
) -> dict[str, object]:
    return {
        "items": [schema.model_validate(item) for item in items],
        "next_cursor": None,
    }


@router.post("/agents", status_code=status.HTTP_201_CREATED, response_model=AgentResponse)
async def create_agent_endpoint(
    body: AgentCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> AgentResponse:
    return AgentResponse.model_validate(await _call(lambda: create_agent(db, body)))


@router.get("/agents")
async def list_agents_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    return _page(await list_agents(db, limit), AgentResponse)


@router.get("/agents/{resource_id}", response_model=AgentResponse)
async def get_agent_endpoint(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> AgentResponse:
    item = await get_agent(db, resource_id)
    if item is None:
        raise HTTPException(status_code=404, detail="CATALOG_RESOURCE_NOT_FOUND")
    return AgentResponse.model_validate(item)


@router.patch("/agents/{resource_id}", response_model=AgentResponse)
async def update_agent_endpoint(
    resource_id: uuid.UUID,
    body: AgentUpdate,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> AgentResponse:
    item = await _call(lambda: update_agent(db, resource_id, body, _if_match(if_match)))
    return AgentResponse.model_validate(item)


@router.delete("/agents/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_endpoint(
    resource_id: uuid.UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> Response:
    await _call(lambda: delete_agent(db, resource_id, _if_match(if_match)))
    return Response(status_code=204)


@router.post("/agents/{resource_id}/validate", response_model=AgentResponse)
async def validate_agent_endpoint(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> AgentResponse:
    return AgentResponse.model_validate(await _call(lambda: validate_agent(db, resource_id)))


@router.post(
    "/agents/{resource_id}/revisions",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentResponse,
)
async def clone_agent_endpoint(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> AgentResponse:
    return AgentResponse.model_validate(
        await _call(lambda: clone_agent_revision(db, resource_id))
    )


@router.post(
    "/agents/{resource_id}/versions",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentVersionResponse,
)
async def create_agent_version_endpoint(
    resource_id: uuid.UUID,
    body: AgentVersionCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> AgentVersionResponse:
    return AgentVersionResponse.model_validate(
        await _call(lambda: create_agent_version(db, resource_id, body))
    )


@router.get("/agents/{resource_id}/versions")
async def list_agent_versions_endpoint(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    return _page(await list_agent_versions(db, resource_id), AgentVersionResponse)


@router.delete(
    "/agents/{resource_id}/versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_agent_version_endpoint(
    resource_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> Response:
    await _call(lambda: delete_agent_version(db, resource_id, version_id))
    return Response(status_code=204)


@router.post(
    "/agents/{resource_id}/model-bindings",
    status_code=status.HTTP_201_CREATED,
    response_model=AgentModelBindingResponse,
)
async def create_agent_binding_endpoint(
    resource_id: uuid.UUID,
    body: AgentModelBindingCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> AgentModelBindingResponse:
    return AgentModelBindingResponse.model_validate(
        await _call(lambda: create_agent_model_binding(db, resource_id, body))
    )


@router.get("/agents/{resource_id}/model-bindings")
async def list_agent_bindings_endpoint(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    return _page(
        await list_agent_model_bindings(db, resource_id),
        AgentModelBindingResponse,
    )


@router.delete(
    "/agents/{resource_id}/model-bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_agent_binding_endpoint(
    resource_id: uuid.UUID,
    binding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> Response:
    await _call(lambda: delete_agent_model_binding(db, resource_id, binding_id))
    return Response(status_code=204)


@router.post("/models", status_code=status.HTTP_201_CREATED, response_model=ModelResponse)
async def create_model_endpoint(
    body: ModelCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> ModelResponse:
    return ModelResponse.model_validate(await _call(lambda: create_model(db, body)))


@router.get("/models")
async def list_models_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    return _page(await list_models(db, limit), ModelResponse)


@router.get("/models/{resource_id}", response_model=ModelResponse)
async def get_model_endpoint(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> ModelResponse:
    item = await get_model(db, resource_id)
    if item is None:
        raise HTTPException(status_code=404, detail="CATALOG_RESOURCE_NOT_FOUND")
    return ModelResponse.model_validate(item)


@router.patch("/models/{resource_id}", response_model=ModelResponse)
async def update_model_endpoint(
    resource_id: uuid.UUID,
    body: ModelUpdate,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> ModelResponse:
    return ModelResponse.model_validate(
        await _call(lambda: update_model(db, resource_id, body, _if_match(if_match)))
    )


@router.delete("/models/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model_endpoint(
    resource_id: uuid.UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> Response:
    await _call(lambda: delete_model(db, resource_id, _if_match(if_match)))
    return Response(status_code=204)


@router.post("/models/{resource_id}/validate", response_model=ModelResponse)
async def validate_model_endpoint(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> ModelResponse:
    return ModelResponse.model_validate(await _call(lambda: validate_model(db, resource_id)))


@router.post(
    "/models/{resource_id}/revisions",
    status_code=status.HTTP_201_CREATED,
    response_model=ModelResponse,
)
async def clone_model_endpoint(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> ModelResponse:
    return ModelResponse.model_validate(
        await _call(lambda: clone_model_revision(db, resource_id))
    )


@router.post(
    "/providers",
    status_code=status.HTTP_201_CREATED,
    response_model=ProviderResponse,
)
async def create_provider_endpoint(
    body: ProviderCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> ProviderResponse:
    return ProviderResponse.model_validate(await _call(lambda: create_provider(db, body)))


@router.get("/providers")
async def list_providers_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    return _page(await list_providers(db, limit), ProviderResponse)


@router.get("/providers/{resource_id}", response_model=ProviderResponse)
async def get_provider_endpoint(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> ProviderResponse:
    item = await get_provider(db, resource_id)
    if item is None:
        raise HTTPException(status_code=404, detail="CATALOG_RESOURCE_NOT_FOUND")
    return ProviderResponse.model_validate(item)


@router.patch("/providers/{resource_id}", response_model=ProviderResponse)
async def update_provider_endpoint(
    resource_id: uuid.UUID,
    body: ProviderUpdate,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> ProviderResponse:
    return ProviderResponse.model_validate(
        await _call(
            lambda: update_provider(db, resource_id, body, _if_match(if_match))
        )
    )


@router.delete("/providers/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_endpoint(
    resource_id: uuid.UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> Response:
    await _call(lambda: delete_provider(db, resource_id, _if_match(if_match)))
    return Response(status_code=204)


@router.post("/providers/{resource_id}/validate", response_model=ProviderResponse)
async def validate_provider_endpoint(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> ProviderResponse:
    return ProviderResponse.model_validate(
        await _call(lambda: validate_provider(db, resource_id))
    )


@router.post(
    "/providers/{resource_id}/revisions",
    status_code=status.HTTP_201_CREATED,
    response_model=ProviderResponse,
)
async def clone_provider_endpoint(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> ProviderResponse:
    return ProviderResponse.model_validate(
        await _call(lambda: clone_provider_revision(db, resource_id))
    )


@router.post(
    "/providers/{resource_id}/model-bindings",
    status_code=status.HTTP_201_CREATED,
    response_model=ProviderModelBindingResponse,
)
async def create_provider_binding_endpoint(
    resource_id: uuid.UUID,
    body: ProviderModelBindingCreate,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> ProviderModelBindingResponse:
    return ProviderModelBindingResponse.model_validate(
        await _call(lambda: create_provider_model_binding(db, resource_id, body))
    )


@router.get("/providers/{resource_id}/model-bindings")
async def list_provider_bindings_endpoint(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    return _page(
        await list_provider_model_bindings(db, resource_id),
        ProviderModelBindingResponse,
    )


@router.delete(
    "/providers/{resource_id}/model-bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_provider_binding_endpoint(
    resource_id: uuid.UUID,
    binding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    _user: User = Depends(get_current_user),
) -> Response:
    await _call(lambda: delete_provider_model_binding(db, resource_id, binding_id))
    return Response(status_code=204)
