"""可变聚合/资源表的基类 mixin，提供通用列定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class BaseModel:
    """可变聚合/资源表的基类 mixin。

    子类只需继承此类即可获得标准审计列和乐观锁支持。
    """

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[str] = None
    delete_reason: Optional[str] = None
