"""Pydantic V2 schemas for all Sidecar domain services."""
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator


# ── 枚举定义 ──────────────────────────────────────────────────────────────

class MessageRole(str, Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ReferenceType(str, Enum):
    """引用类型枚举"""
    RESOURCE = "resource"
    SKILL = "skill"
    POLICY = "policy"


class ConversationStatus(str, Enum):
    """对话状态枚举"""
    ACTIVE = "active"
    ARCHIVED = "archived"


class KnowledgeType(str, Enum):
    """知识条目类型枚举"""
    FAQ = "FAQ"
    DOC = "DOC"
    URL = "URL"


class KnowledgeStatus(str, Enum):
    """知识条目状态枚举"""
    ACTIVE = "active"
    ARCHIVED = "archived"


class WorkspaceMemberRole(str, Enum):
    """工作区成员角色枚举"""
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class OrchestrationStatus(str, Enum):
    """编排状态枚举"""
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class OrchestrationNodeType(str, Enum):
    """编排节点类型枚举"""
    AGENT = "agent"
    TOOL = "tool"
    GATEWAY = "gateway"
    TRANSFORM = "transform"
    INPUT = "input"
    OUTPUT = "output"


class OrchestrationRunStatus(str, Enum):
    """编排运行状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EmployeeStatus(str, Enum):
    """员工状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"


class AuditOutcome(str, Enum):
    """审计结果枚举"""
    SUCCESS = "success"
    DENIED = "denied"
    FAILED = "failed"


# ── E.164 手机号正则 ──────────────────────────────────────────────────────

_E164_RE = re.compile(r"^\+[1-9]\d{10,14}$")
# 18 位统一信用代码（字母+数字）
_CREDIT_CODE_RE = re.compile(r"^[A-Z0-9]{18}$")
# 18 位身份证号码
_ID_CARD_RE = re.compile(r"^\d{17}[\dXx]$")


# ── 工作区配置 ────────────────────────────────────────────────────────────

class StrictModel(BaseModel):
    """所有 schema 的基类，禁止额外字段"""
    model_config = ConfigDict(extra="forbid")


# ── Company schemas ───────────────────────────────────────────────────────

class CompanyCreate(StrictModel):
    """创建企业请求"""
    name: Annotated[str, Field(min_length=1, max_length=128, description="企业名称")]
    email: Annotated[EmailStr, Field(description="企业邮箱 (RFC5322)")]
    phone: Annotated[str, Field(description="手机号 (E.164 格式，如 +8613800138000)")]
    unified_credit_code: Annotated[str, Field(description="统一社会信用代码 (18位字母+数字)")]
    business_license_url: Annotated[str, Field(description="营业执照 URL (必填)")]
    legal_rep_id_card: Annotated[str, Field(description="法人身份证号码 (18位)")]
    industry: Annotated[str | None, Field(default=None, max_length=128, description="所属行业")]

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not _E164_RE.match(v):
            raise ValueError("手机号必须为 E.164 格式，如 +8613800138000")
        return v

    @field_validator("unified_credit_code")
    @classmethod
    def validate_credit_code(cls, v: str) -> str:
        if not _CREDIT_CODE_RE.match(v.upper()):
            raise ValueError("统一社会信用代码必须为 18 位字母+数字")
        return v.upper()

    @field_validator("legal_rep_id_card")
    @classmethod
    def validate_id_card(cls, v: str) -> str:
        if not _ID_CARD_RE.match(v):
            raise ValueError("法人身份证号码必须为 18 位")
        return v

    @field_validator("business_license_url")
    @classmethod
    def validate_license_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("营业执照 URL 不能为空")
        if not v.startswith(("http://", "https://")):
            raise ValueError("营业执照 URL 必须以 http:// 或 https:// 开头")
        return v.strip()


class CompanyUpdate(StrictModel):
    """更新企业请求（部分更新）"""
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128, description="企业名称")]
    email: Annotated[EmailStr | None, Field(default=None, description="企业邮箱")]
    phone: Annotated[str | None, Field(default=None, description="手机号 (E.164)")]
    unified_credit_code: Annotated[str | None, Field(default=None, description="统一社会信用代码")]
    business_license_url: Annotated[str | None, Field(default=None, description="营业执照 URL")]
    legal_rep_id_card: Annotated[str | None, Field(default=None, description="法人身份证号码")]
    industry: Annotated[str | None, Field(default=None, max_length=128, description="所属行业")]

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is not None and not _E164_RE.match(v):
            raise ValueError("手机号必须为 E.164 格式")
        return v

    @field_validator("unified_credit_code")
    @classmethod
    def validate_credit_code(cls, v: str | None) -> str | None:
        if v is not None and not _CREDIT_CODE_RE.match(v.upper()):
            raise ValueError("统一社会信用代码必须为 18 位字母+数字")
        return v.upper() if v is not None else None

    @field_validator("legal_rep_id_card")
    @classmethod
    def validate_id_card(cls, v: str | None) -> str | None:
        if v is not None and not _ID_CARD_RE.match(v):
            raise ValueError("法人身份证号码必须为 18 位")
        return v

    @field_validator("business_license_url")
    @classmethod
    def validate_license_url(cls, v: str | None) -> str | None:
        if v is not None:
            if not v.strip():
                raise ValueError("营业执照 URL 不能为空")
            if not v.startswith(("http://", "https://")):
                raise ValueError("营业执照 URL 必须以 http:// 或 https:// 开头")
            return v.strip()
        return None


class CompanyResponse(StrictModel):
    """企业详情响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="企业 ID")]
    name: Annotated[str, Field(description="企业名称")]
    email: Annotated[str, Field(description="企业邮箱")]
    phone: Annotated[str, Field(description="手机号")]
    unified_credit_code: Annotated[str, Field(description="统一社会信用代码")]
    business_license_url: Annotated[str, Field(description="营业执照 URL")]
    legal_rep_id_card: Annotated[str, Field(description="法人身份证号码")]
    industry: Annotated[str | None, Field(description="所属行业")]
    is_deleted: Annotated[bool, Field(default=False, description="是否已软删除")]
    created_at: Annotated[datetime, Field(description="创建时间")]
    updated_at: Annotated[datetime, Field(description="更新时间")]


# ── Conversation schemas ──────────────────────────────────────────────────

class ConversationCreate(StrictModel):
    """创建对话请求"""
    title: Annotated[str | None, Field(default=None, max_length=256, description="对话标题")]
    company_id: Annotated[str, Field(description="所属企业 ID")]


class ConversationUpdate(StrictModel):
    """更新对话请求"""
    title: Annotated[str | None, Field(default=None, max_length=256, description="对话标题")]
    status: Annotated[ConversationStatus | None, Field(default=None, description="对话状态")]


class ConversationResponse(StrictModel):
    """对话详情响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="对话 ID")]
    company_id: Annotated[str, Field(description="所属企业 ID")]
    title: Annotated[str | None, Field(description="对话标题")]
    status: Annotated[ConversationStatus, Field(description="对话状态")]
    is_deleted: Annotated[bool, Field(default=False, description="是否已软删除")]
    created_at: Annotated[datetime, Field(description="创建时间")]
    updated_at: Annotated[datetime, Field(description="更新时间")]


# ── Reference & Message schemas ───────────────────────────────────────────

class MessageReference(StrictModel):
    """消息引用"""
    type: Annotated[ReferenceType, Field(description="引用类型")]
    id: Annotated[str, Field(description="引用资源 ID")]
    name: Annotated[str | None, Field(default=None, max_length=256, description="引用名称")]


class MessageCreate(StrictModel):
    """添加消息请求"""
    role: Annotated[MessageRole, Field(description="消息角色")]
    content: Annotated[str, Field(min_length=1, description="消息内容")]
    references: Annotated[list[MessageReference] | None, Field(default=None, description="引用列表")]


class MessageResponse(StrictModel):
    """消息详情响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="消息 ID")]
    conversation_id: Annotated[str, Field(description="所属对话 ID")]
    role: Annotated[MessageRole, Field(description="消息角色")]
    content: Annotated[str, Field(description="消息内容")]
    references: Annotated[list[MessageReference], Field(default_factory=list, description="引用列表")]
    is_deleted: Annotated[bool, Field(default=False, description="是否已软删除")]
    created_at: Annotated[datetime, Field(description="创建时间")]


# ── Knowledge schemas ─────────────────────────────────────────────────────

class KnowledgeEntryCreate(StrictModel):
    """创建知识条目请求"""
    title: Annotated[str, Field(min_length=1, max_length=256, description="条目标题")]
    content: Annotated[str, Field(min_length=1, description="条目内容")]
    type: Annotated[KnowledgeType, Field(description="条目类型")]
    tags: Annotated[list[str] | None, Field(default=None, description="标签列表")]


class KnowledgeEntryUpdate(StrictModel):
    """更新知识条目请求"""
    title: Annotated[str | None, Field(default=None, min_length=1, max_length=256, description="条目标题")]
    content: Annotated[str | None, Field(default=None, min_length=1, description="条目内容")]
    type: Annotated[KnowledgeType | None, Field(default=None, description="条目类型")]
    tags: Annotated[list[str] | None, Field(default=None, description="标签列表")]


class KnowledgeEntryResponse(StrictModel):
    """知识条目详情响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="条目 ID")]
    title: Annotated[str, Field(description="条目标题")]
    content: Annotated[str, Field(description="条目内容")]
    type: Annotated[KnowledgeType, Field(description="条目类型")]
    status: Annotated[KnowledgeStatus, Field(description="条目状态")]
    content_sha256: Annotated[str, Field(description="内容 SHA-256 哈希")]
    tags: Annotated[list[str], Field(default_factory=list, description="标签列表")]
    version: Annotated[int, Field(description="版本号")]
    is_deleted: Annotated[bool, Field(default=False, description="是否已软删除")]
    created_at: Annotated[datetime, Field(description="创建时间")]
    updated_at: Annotated[datetime, Field(description="更新时间")]


class KnowledgeStatsResponse(StrictModel):
    """知识库统计响应"""
    total: Annotated[int, Field(description="总条目数")]
    active: Annotated[int, Field(description="活跃条目数")]
    archived: Annotated[int, Field(description="归档条目数")]
    by_type: Annotated[dict[str, int], Field(description="按类型统计")]
    by_tag: Annotated[dict[str, int], Field(description="按标签统计")]


# ── Workspace schemas ─────────────────────────────────────────────────────

class WorkspaceCreate(StrictModel):
    """创建工作区请求"""
    name: Annotated[str, Field(min_length=1, max_length=128, description="工作区名称")]
    description: Annotated[str | None, Field(default=None, max_length=512, description="工作区描述")]
    company_id: Annotated[str, Field(description="所属企业 ID")]


class WorkspaceUpdate(StrictModel):
    """更新工作区请求"""
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128, description="工作区名称")]
    description: Annotated[str | None, Field(default=None, max_length=512, description="工作区描述")]


class WorkspaceResponse(StrictModel):
    """工作区详情响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="工作区 ID")]
    company_id: Annotated[str, Field(description="所属企业 ID")]
    name: Annotated[str, Field(description="工作区名称")]
    description: Annotated[str | None, Field(description="工作区描述")]
    is_deleted: Annotated[bool, Field(default=False, description="是否已软删除")]
    created_at: Annotated[datetime, Field(description="创建时间")]
    updated_at: Annotated[datetime, Field(description="更新时间")]


class WorkspaceMemberAdd(StrictModel):
    """添加工作区成员请求"""
    user_id: Annotated[str, Field(description="用户 ID")]
    role: Annotated[WorkspaceMemberRole, Field(description="成员角色")]


class WorkspaceMemberRemove(StrictModel):
    """移除工作区成员请求"""
    user_id: Annotated[str, Field(description="用户 ID")]


class WorkspaceMemberResponse(StrictModel):
    """工作区成员响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="成员记录 ID")]
    workspace_id: Annotated[str, Field(description="工作区 ID")]
    user_id: Annotated[str, Field(description="用户 ID")]
    role: Annotated[WorkspaceMemberRole, Field(description="成员角色")]
    created_at: Annotated[datetime, Field(description="加入时间")]


class WorkspaceConfigUpdate(StrictModel):
    """工作区配置更新请求"""
    key: Annotated[str, Field(min_length=1, max_length=128, description="配置键")]
    value: Annotated[str, Field(description="配置值")]


class WorkspaceConfigResponse(StrictModel):
    """工作区配置响应"""
    key: Annotated[str, Field(description="配置键")]
    value: Annotated[str, Field(description="配置值")]
    updated_at: Annotated[datetime, Field(description="更新时间")]


# ── Orchestration schemas ─────────────────────────────────────────────────

class OrchestrationNodeCreate(StrictModel):
    """编排节点创建请求"""
    name: Annotated[str, Field(min_length=1, max_length=128, description="节点名称")]
    node_type: Annotated[OrchestrationNodeType, Field(description="节点类型")]
    config: Annotated[dict | None, Field(default=None, description="节点配置")]


class OrchestrationNodeResponse(StrictModel):
    """编排节点响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="节点 ID")]
    orchestration_id: Annotated[str, Field(description="所属编排 ID")]
    name: Annotated[str, Field(description="节点名称")]
    node_type: Annotated[OrchestrationNodeType, Field(description="节点类型")]
    config: Annotated[dict | None, Field(description="节点配置")]
    created_at: Annotated[datetime, Field(description="创建时间")]


class OrchestrationEdgeCreate(StrictModel):
    """编排边创建请求"""
    source_node_id: Annotated[str, Field(description="源节点 ID")]
    target_node_id: Annotated[str, Field(description="目标节点 ID")]


class OrchestrationEdgeResponse(StrictModel):
    """编排边响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="边 ID")]
    orchestration_id: Annotated[str, Field(description="所属编排 ID")]
    source_node_id: Annotated[str, Field(description="源节点 ID")]
    target_node_id: Annotated[str, Field(description="目标节点 ID")]
    created_at: Annotated[datetime, Field(description="创建时间")]


class OrchestrationCreate(StrictModel):
    """创建编排请求"""
    name: Annotated[str, Field(min_length=1, max_length=128, description="编排名称")]
    description: Annotated[str | None, Field(default=None, max_length=512, description="编排描述")]
    company_id: Annotated[str, Field(description="所属企业 ID")]
    nodes: Annotated[list[OrchestrationNodeCreate] | None, Field(default=None, description="初始节点列表")]
    edges: Annotated[list[OrchestrationEdgeCreate] | None, Field(default=None, description="初始边列表")]


class OrchestrationUpdate(StrictModel):
    """更新编排请求"""
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128, description="编排名称")]
    description: Annotated[str | None, Field(default=None, max_length=512, description="编排描述")]


class OrchestrationResponse(StrictModel):
    """编排详情响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="编排 ID")]
    company_id: Annotated[str, Field(description="所属企业 ID")]
    name: Annotated[str, Field(description="编排名称")]
    description: Annotated[str | None, Field(description="编排描述")]
    status: Annotated[OrchestrationStatus, Field(description="编排状态")]
    version: Annotated[int, Field(description="版本号")]
    is_deleted: Annotated[bool, Field(default=False, description="是否已软删除")]
    nodes: Annotated[list[OrchestrationNodeResponse], Field(default_factory=list, description="节点列表")]
    edges: Annotated[list[OrchestrationEdgeResponse], Field(default_factory=list, description="边列表")]
    created_at: Annotated[datetime, Field(description="创建时间")]
    updated_at: Annotated[datetime, Field(description="更新时间")]


class OrchestrationRunResponse(StrictModel):
    """编排运行记录响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="运行记录 ID")]
    orchestration_id: Annotated[str, Field(description="所属编排 ID")]
    orchestration_version: Annotated[int, Field(description="编排版本")]
    status: Annotated[OrchestrationRunStatus, Field(description="运行状态")]
    started_at: Annotated[datetime, Field(description="开始时间")]
    completed_at: Annotated[datetime | None, Field(description="完成时间")]
    result: Annotated[dict | None, Field(default=None, description="运行结果")]
    error: Annotated[str | None, Field(default=None, description="错误信息")]


# ── Employee schemas ──────────────────────────────────────────────────────

class EmployeeCreate(StrictModel):
    """创建员工请求"""
    name: Annotated[str, Field(min_length=1, max_length=100, description="员工姓名")]
    department_id: Annotated[str | None, Field(default=None, description="所属部门 ID")]
    role: Annotated[str, Field(default="member", max_length=64, description="角色")]
    email: Annotated[EmailStr | None, Field(default=None, description="员工邮箱")]
    company_id: Annotated[str, Field(description="所属企业 ID")]


class EmployeeUpdate(StrictModel):
    """更新员工请求"""
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=100, description="员工姓名")]
    department_id: Annotated[str | None, Field(default=None, description="所属部门 ID")]
    role: Annotated[str | None, Field(default=None, max_length=64, description="角色")]
    email: Annotated[EmailStr | None, Field(default=None, description="员工邮箱")]


class EmployeeResponse(StrictModel):
    """员工详情响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="员工 ID")]
    company_id: Annotated[str, Field(description="所属企业 ID")]
    name: Annotated[str, Field(description="员工姓名")]
    department_id: Annotated[str | None, Field(description="所属部门 ID")]
    role: Annotated[str, Field(description="角色")]
    email: Annotated[str | None, Field(description="员工邮箱")]
    status: Annotated[EmployeeStatus, Field(description="员工状态")]
    is_deleted: Annotated[bool, Field(default=False, description="是否已软删除")]
    created_at: Annotated[datetime, Field(description="创建时间")]
    updated_at: Annotated[datetime, Field(description="更新时间")]


# ── Department schemas ────────────────────────────────────────────────────

class DepartmentCreate(StrictModel):
    """创建部门请求"""
    name: Annotated[str, Field(min_length=1, max_length=100, description="部门名称")]
    parent_id: Annotated[str | None, Field(default=None, description="上级部门 ID")]
    company_id: Annotated[str, Field(description="所属企业 ID")]


class DepartmentResponse(StrictModel):
    """部门详情响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="部门 ID")]
    company_id: Annotated[str, Field(description="所属企业 ID")]
    name: Annotated[str, Field(description="部门名称")]
    parent_id: Annotated[str | None, Field(description="上级部门 ID")]
    is_deleted: Annotated[bool, Field(default=False, description="是否已软删除")]
    created_at: Annotated[datetime, Field(description="创建时间")]
    updated_at: Annotated[datetime, Field(description="更新时间")]


# ── Domain schemas ────────────────────────────────────────────────────────

class DomainRegister(StrictModel):
    """域名注册请求"""
    domain: Annotated[str, Field(min_length=1, max_length=253, description="域名")]
    company_id: Annotated[str, Field(description="所属企业 ID")]


class DomainResponse(StrictModel):
    """域名详情响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="域名记录 ID")]
    domain: Annotated[str, Field(description="域名")]
    company_id: Annotated[str, Field(description="所属企业 ID")]
    dns_status: Annotated[str, Field(description="DNS 解析状态")]
    ssl_status: Annotated[str, Field(description="SSL 证书状态")]
    created_at: Annotated[datetime, Field(description="创建时间")]
    updated_at: Annotated[datetime, Field(description="更新时间")]


# ── Audit schemas ─────────────────────────────────────────────────────────

class AuditEventCreate(StrictModel):
    """审计事件创建请求"""
    event_type: Annotated[str, Field(min_length=1, max_length=128, description="事件类型")]
    actor_type: Annotated[str, Field(description="操作者类型 (user/employee/system)")]
    actor_id: Annotated[str | None, Field(default=None, description="操作者 ID")]
    resource_type: Annotated[str, Field(min_length=1, max_length=128, description="资源类型")]
    resource_id: Annotated[str | None, Field(default=None, description="资源 ID")]
    outcome: Annotated[AuditOutcome, Field(description="操作结果")]
    detail: Annotated[dict | None, Field(default=None, description="事件详情")]
    company_id: Annotated[str | None, Field(default=None, description="所属企业 ID")]


class AuditEventResponse(StrictModel):
    """审计事件响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="事件 ID")]
    row_sequence: Annotated[int, Field(description="序列号")]
    company_id: Annotated[str | None, Field(description="所属企业 ID")]
    actor_type: Annotated[str, Field(description="操作者类型")]
    actor_id: Annotated[str | None, Field(description="操作者 ID")]
    action: Annotated[str, Field(description="事件类型")]
    resource_type: Annotated[str, Field(description="资源类型")]
    resource_id: Annotated[str | None, Field(description="资源 ID")]
    outcome: Annotated[AuditOutcome, Field(description="操作结果")]
    detail: Annotated[dict, Field(description="事件详情")]
    created_at: Annotated[datetime, Field(description="创建时间")]


# ── Agent Runtime schemas ─────────────────────────────────────────────────

class AgentRunRequest(StrictModel):
    """Agent 运行请求"""
    agent_id: Annotated[str, Field(description="Agent ID")]
    user_id: Annotated[str, Field(description="用户 ID")]
    message: Annotated[str, Field(min_length=1, description="用户消息")]


class AgentResponse(StrictModel):
    """Agent 响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="Agent ID")]
    name: Annotated[str, Field(description="Agent 名称")]
    status: Annotated[str, Field(description="Agent 状态")]
    model: Annotated[str, Field(description="使用的模型")]
    created_at: Annotated[datetime, Field(description="创建时间")]
    updated_at: Annotated[datetime, Field(description="更新时间")]


class AgentRunResponse(StrictModel):
    """Agent 运行响应"""
    model_config = ConfigDict(from_attributes=True)

    id: Annotated[str, Field(description="运行 ID")]
    agent_id: Annotated[str, Field(description="Agent ID")]
    user_id: Annotated[str, Field(description="用户 ID")]
    status: Annotated[str, Field(description="运行状态")]
    response: Annotated[str | None, Field(default=None, description="Agent 响应内容")]
    started_at: Annotated[datetime, Field(description="开始时间")]
    completed_at: Annotated[datetime | None, Field(default=None, description="完成时间")]


# ── 分页 ──────────────────────────────────────────────────────────────────

class PaginationParams(StrictModel):
    """分页参数"""
    offset: Annotated[int, Field(default=0, ge=0, description="偏移量")]
    limit: Annotated[int, Field(default=20, ge=1, le=100, description="每页数量")]


class PaginatedResponse(StrictModel):
    """分页响应基类"""
    total: Annotated[int, Field(description="总数")]
    offset: Annotated[int, Field(description="偏移量")]
    limit: Annotated[int, Field(description="每页数量")]
