from pydantic import BaseModel


class SyncConfigResponse(BaseModel):
    timestamp: str
    capabilities: list[dict]
    capability_versions: list[dict]
    skills: list[dict]
    skill_versions: list[dict]
    skill_bindings: list[dict]
    prompt_assets: list[dict]
    prompt_asset_versions: list[dict]
    employee_templates: list[dict]
    knowledge_policies: list[dict]
    security_policies: list[dict]
    workspace_policies: list[dict]
    notification_policies: list[dict]
    budget_policies: list[dict]
    backends: list[dict]
    company_backend_defaults: list[dict]
    providers: list[dict]
    provider_pricing_versions: list[dict]
    provider_tier_mappings: list[dict]
