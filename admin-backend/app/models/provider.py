from sqlalchemy import Column, String, Integer, JSON, func

from app.models.base import Base


class Provider(Base):
    __tablename__ = "providers"

    provider_id = Column(String, primary_key=True)
    company_id = Column(String)
    name = Column(String, nullable=False)
    provider_type = Column(String, nullable=False)
    config = Column(JSON, server_default="{}")
    status = Column(String, nullable=False, server_default="active")
    version = Column(String, nullable=False, server_default="1")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))


class ProviderModel(Base):
    __tablename__ = "provider_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(String, nullable=False)
    model_id = Column(String, nullable=False)
    display_name = Column(String)
    tier = Column(String, server_default="standard")
    created_at = Column(String, server_default=func.datetime("now"))


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"

    credential_id = Column(String, primary_key=True)
    provider_id = Column(String, nullable=False)
    company_id = Column(String, nullable=False)
    credential_type = Column(String, nullable=False)
    credential_ref = Column(String)
    created_at = Column(String, server_default=func.datetime("now"))


class ProviderPricingVersion(Base):
    __tablename__ = "provider_pricing_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(String, nullable=False)
    company_id = Column(String)
    version = Column(String, nullable=False, server_default="1")
    pricing = Column(JSON, nullable=False, server_default="{}")
    currency = Column(String, server_default="USD")
    created_at = Column(String, server_default=func.datetime("now"))


class ProviderTierMapping(Base):
    __tablename__ = "provider_tier_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String, nullable=False)
    provider_id = Column(String, nullable=False)
    tier = Column(String, nullable=False)
    model_id = Column(String, nullable=False)
    created_at = Column(String, server_default=func.datetime("now"))
