"""企业身份管理领域服务。

提供企业 CRUD、字段校验（email RFC5322, 手机 E.164, 统一信用代码 18 位,
营业执照 URL 必填, 法人身份证 18 位）和软删除能力。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ibreeze.schemas import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
)


# ── 内存存储（迁移到 SQLite 前的临时方案）──────────────────────────────

_companies: dict[str, dict[str, Any]] = {}


def _now_utc() -> datetime:
    """返回当前 UTC 时间"""
    return datetime.now(timezone.utc)


# ── 公开接口 ──────────────────────────────────────────────────────────────

def create_company(data: CompanyCreate) -> CompanyResponse:
    """创建企业。

    校验所有字段（在 CompanyCreate Pydantic 模型中自动完成），
    生成 ID，设置时间戳，存入内存。
    """
    import uuid

    company_id = str(uuid.uuid4())
    now = _now_utc()

    record: dict[str, Any] = {
        "id": company_id,
        "name": data.name,
        "email": data.email,
        "phone": data.phone,
        "unified_credit_code": data.unified_credit_code,
        "business_license_url": data.business_license_url,
        "legal_rep_id_card": data.legal_rep_id_card,
        "industry": data.industry,
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
    }
    _companies[company_id] = record
    return CompanyResponse(**record)


def list_companies(offset: int = 0, limit: int = 20) -> list[CompanyResponse]:
    """分页列出未删除的企业。"""
    active = [c for c in _companies.values() if not c["is_deleted"]]
    return [CompanyResponse(**c) for c in active[offset : offset + limit]]


def get_company(company_id: str) -> CompanyResponse:
    """获取单个企业详情。"""
    record = _companies.get(company_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"企业不存在: {company_id}")
    return CompanyResponse(**record)


def update_company(company_id: str, data: CompanyUpdate) -> CompanyResponse:
    """部分更新企业信息。

    只更新请求中非 None 的字段。
    """
    record = _companies.get(company_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"企业不存在: {company_id}")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        record[key] = value
    record["updated_at"] = _now_utc()

    return CompanyResponse(**record)


def delete_company(company_id: str) -> None:
    """软删除企业。"""
    record = _companies.get(company_id)
    if record is None or record["is_deleted"]:
        raise KeyError(f"企业不存在: {company_id}")
    record["is_deleted"] = True
    record["updated_at"] = _now_utc()
