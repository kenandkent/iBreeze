from pydantic import BaseModel


class ProviderCreate(BaseModel):
    company_id: str | None = None
    name: str
    provider_type: str
    config: dict | None = None


class ProviderUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None


class ProviderResponse(BaseModel):
    provider_id: str
    company_id: str | None = None
    name: str
    provider_type: str
    config: dict
    status: str
    version: str
    created_at: str
    updated_at: str


class ProviderModelResponse(BaseModel):
    id: int
    provider_id: str
    model_id: str
    display_name: str | None = None
    tier: str
    created_at: str


class ProviderCredentialSet(BaseModel):
    credential_type: str
    credential_ref: str | None = None


class ProviderCredentialResponse(BaseModel):
    credential_id: str
    provider_id: str
    company_id: str
    credential_type: str
    credential_ref: str | None = None
    created_at: str


class ProviderPricingUpdate(BaseModel):
    pricing: dict
    currency: str = "USD"


class ProviderPricingResponse(BaseModel):
    id: int
    provider_id: str
    company_id: str | None = None
    version: str
    pricing: dict
    currency: str
    created_at: str


class ProviderTierMappingUpdate(BaseModel):
    tier: str
    model_id: str


class ProviderTierMappingResponse(BaseModel):
    id: int
    company_id: str
    provider_id: str
    tier: str
    model_id: str
    created_at: str


# --- Backend ---

class BackendCreate(BaseModel):
    company_id: str
    name: str
    backend_type: str = "local_process"
    provider_id: str | None = None
    workspace_root: str | None = None
    concurrency: int = 1


class BackendUpdate(BaseModel):
    name: str | None = None
    provider_id: str | None = None
    workspace_root: str | None = None
    concurrency: int | None = None


class BackendResponse(BaseModel):
    backend_id: str
    company_id: str
    name: str
    backend_type: str
    provider_id: str | None = None
    workspace_root: str | None = None
    status: str
    concurrency: int
    version: str
    created_at: str
    updated_at: str


class CompanyBackendDefaultResponse(BaseModel):
    company_id: str
    backend_id: str
    version: str
    created_at: str
