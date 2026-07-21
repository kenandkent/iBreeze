from pydantic import BaseModel


# --- Capability ---

class CapabilityCreate(BaseModel):
    company_id: str | None = None
    name: str
    description: str | None = None


class CapabilityUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class CapabilityResponse(BaseModel):
    capability_id: str
    company_id: str | None = None
    name: str
    description: str | None = None
    status: str
    current_version: int
    version: int
    created_at: str
    updated_at: str


class CapabilityVersionResponse(BaseModel):
    id: int
    capability_id: str
    version: int
    content: dict
    checksum: str | None = None
    created_at: str


class CapabilityVersionCreate(BaseModel):
    content: dict
    checksum: str | None = None


# --- Skill ---

class SkillCreate(BaseModel):
    company_id: str | None = None
    name: str
    description: str | None = None
    prompt_asset_id: str | None = None


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt_asset_id: str | None = None


class SkillResponse(BaseModel):
    skill_id: str
    company_id: str | None = None
    name: str
    description: str | None = None
    prompt_asset_id: str | None = None
    status: str
    version: int
    created_at: str
    updated_at: str


class SkillVersionResponse(BaseModel):
    id: int
    skill_id: str
    version: int
    content: dict
    checksum: str | None = None
    created_at: str


class SkillVersionCreate(BaseModel):
    content: dict
    checksum: str | None = None


class SkillBindingResponse(BaseModel):
    binding_id: str
    capability_id: str
    skill_id: str
    ordinal: int
    created_at: str


class SkillBindingCreate(BaseModel):
    skill_id: str
    ordinal: int = 0


# --- Prompt Asset ---

class PromptCreate(BaseModel):
    company_id: str | None = None
    name: str
    description: str | None = None
    content: str | None = None


class PromptUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None


class PromptResponse(BaseModel):
    prompt_id: str
    company_id: str | None = None
    name: str
    description: str | None = None
    content: str | None = None
    status: str
    version: int
    created_at: str
    updated_at: str


class PromptVersionResponse(BaseModel):
    id: int
    prompt_id: str
    version: int
    content: dict
    checksum: str | None = None
    created_at: str


class PromptVersionCreate(BaseModel):
    content: dict
    checksum: str | None = None


# --- Template ---

class TemplateCreate(BaseModel):
    company_id: str | None = None
    name: str
    role: str | None = None
    description: str | None = None
    provider_id: str | None = None
    capability_id: str | None = None
    model: str | None = None


class TemplateUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    description: str | None = None
    provider_id: str | None = None
    capability_id: str | None = None
    model: str | None = None


class TemplateResponse(BaseModel):
    template_id: str
    company_id: str | None = None
    name: str
    role: str | None = None
    description: str | None = None
    provider_id: str | None = None
    capability_id: str | None = None
    model: str | None = None
    status: str
    version: str
    created_at: str
    updated_at: str
