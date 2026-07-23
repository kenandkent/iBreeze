"""Catalog schemas with proper types for Pydantic v2 + SQLAlchemy."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class AgentUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    key: str
    catalog_revision: int
    display_name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentListResponse(BaseModel):
    agents: list[AgentResponse]
    total: int


class AgentVersionCreate(BaseModel):
    executable_names: list[str] | None = None
    supported_platforms: list[str] | None = None
    min_version: str | None = None
    max_version_exclusive: str | None = None
    probe_command: dict | None = None
    capability_tags: list[str] | None = None
    network_domains: list[str] | None = None
    adapter_contract_version: int | None = None
    content_sha256: str | None = None


class AgentVersionResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    executable_names: list[str] | None
    supported_platforms: list[str] | None
    min_version: str | None
    max_version_exclusive: str | None
    probe_command: dict | None
    capability_tags: list[str] | None
    network_domains: list[str] | None
    adapter_contract_version: int | None
    content_sha256: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentVersionListResponse(BaseModel):
    versions: list[AgentVersionResponse]
    total: int


class ModelCreate(BaseModel):
    provider_key: str = Field(..., min_length=1, max_length=128)
    model_key: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=255)
    context_window: int | None = None
    supports_tools: bool = False
    supports_streaming: bool = False
    supports_vision: bool = False


class ModelUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    context_window: int | None = None
    supports_tools: bool | None = None
    supports_streaming: bool | None = None
    supports_vision: bool | None = None


class ModelResponse(BaseModel):
    id: uuid.UUID
    provider_key: str
    model_key: str
    display_name: str
    context_window: int | None
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ModelListResponse(BaseModel):
    models: list[ModelResponse]
    total: int


class ProviderCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=255)
    base_url: str | None = Field(default=None, max_length=512)
    api_protocol: str = Field(..., min_length=1, max_length=32)


class ProviderUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    base_url: str | None = Field(default=None, max_length=512)
    api_protocol: str | None = Field(default=None, min_length=1, max_length=32)


class ProviderResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    base_url: str | None
    api_protocol: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProviderListResponse(BaseModel):
    providers: list[ProviderResponse]
    total: int


class AgentModelBindingCreate(BaseModel):
    agent_id: str
    model_id: str
    agent_version_range: dict | None = None


class AgentModelBindingResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    model_id: uuid.UUID
    agent_version_range: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentModelBindingListResponse(BaseModel):
    bindings: list[AgentModelBindingResponse]
    total: int


class ProviderModelBindingCreate(BaseModel):
    provider_id: str
    model_id: str
    api_protocol: str = Field(..., min_length=1, max_length=32)
    capabilities: dict | None = None


class ProviderModelBindingResponse(BaseModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    model_id: uuid.UUID
    api_protocol: str
    capabilities: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProviderModelBindingListResponse(BaseModel):
    bindings: list[ProviderModelBindingResponse]
    total: int


class StatusTransitionRequest(BaseModel):
    status: str = Field(..., pattern="^(draft|validated|published)$")
