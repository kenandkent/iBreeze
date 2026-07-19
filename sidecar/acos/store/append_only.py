"""不可变记录基类：只有 insert，没有 update/delete API。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AppendOnlyModel:
    """不可变记录基类：主键 + created_at/occurred_at。

    只允许插入操作，不暴露 update/delete API。
    """

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
