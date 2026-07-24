"""Import the complete central-service model registry for migrations."""

from ibreeze_backend.catalog.models import (
    AgentCatalog,
    AgentModelBinding,
    AgentVersionRange,
    ModelCatalog,
    ProviderCatalog,
    ProviderModelBinding,
)
from ibreeze_backend.compatibility.models import CompatibilityRule
from ibreeze_backend.models.audit_log import AdminAuditLog
from ibreeze_backend.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from ibreeze_backend.models.catalog_release import (
    CatalogRelease,
    CatalogReleaseItem,
)
from ibreeze_backend.models.emergency_disable import EmergencyDisableRelease
from ibreeze_backend.models.idempotency_key import ApiIdempotency
from ibreeze_backend.models.skill import Skill, SkillVersion
from ibreeze_backend.models.token_family import RefreshToken, RefreshTokenFamily
from ibreeze_backend.models.user import User

__all__ = [
    "AdminAuditLog",
    "AgentCatalog",
    "AgentModelBinding",
    "AgentVersionRange",
    "ApiIdempotency",
    "CatalogRelease",
    "CatalogReleaseItem",
    "CompatibilityRule",
    "EmergencyDisableRelease",
    "ModelCatalog",
    "ProviderCatalog",
    "ProviderModelBinding",
    "RefreshToken",
    "RefreshTokenFamily",
    "Skill",
    "SkillVersion",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
]
