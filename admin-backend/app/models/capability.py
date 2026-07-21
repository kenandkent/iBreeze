from sqlalchemy import Column, String, Integer, JSON, func

from app.models.base import Base


class Capability(Base):
    __tablename__ = "capabilities"

    capability_id = Column(String, primary_key=True)
    company_id = Column(String)
    name = Column(String, nullable=False)
    description = Column(String)
    status = Column(String, nullable=False, server_default="draft")
    current_version = Column(Integer, server_default="1")
    version = Column(Integer, nullable=False, server_default="1")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))


class CapabilityVersion(Base):
    __tablename__ = "capability_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    capability_id = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    content = Column(JSON, nullable=False)
    checksum = Column(String)
    created_at = Column(String, server_default=func.datetime("now"))


class Skill(Base):
    __tablename__ = "skills"

    skill_id = Column(String, primary_key=True)
    company_id = Column(String)
    name = Column(String, nullable=False)
    description = Column(String)
    prompt_asset_id = Column(String)
    status = Column(String, nullable=False, server_default="draft")
    version = Column(Integer, nullable=False, server_default="1")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))


class SkillVersion(Base):
    __tablename__ = "skill_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    skill_id = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    content = Column(JSON, nullable=False)
    checksum = Column(String)
    created_at = Column(String, server_default=func.datetime("now"))


class SkillBinding(Base):
    __tablename__ = "skill_bindings"

    binding_id = Column(String, primary_key=True)
    capability_id = Column(String, nullable=False)
    skill_id = Column(String, nullable=False)
    ordinal = Column(Integer, nullable=False, server_default="0")
    created_at = Column(String, server_default=func.datetime("now"))


class PromptAsset(Base):
    __tablename__ = "prompt_assets"

    prompt_id = Column(String, primary_key=True)
    company_id = Column(String)
    name = Column(String, nullable=False)
    description = Column(String)
    content = Column(String)
    status = Column(String, nullable=False, server_default="draft")
    version = Column(Integer, nullable=False, server_default="1")
    created_at = Column(String, server_default=func.datetime("now"))
    updated_at = Column(String, server_default=func.datetime("now"))


class PromptAssetVersion(Base):
    __tablename__ = "prompt_asset_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    prompt_id = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    content = Column(JSON, nullable=False)
    checksum = Column(String)
    created_at = Column(String, server_default=func.datetime("now"))
