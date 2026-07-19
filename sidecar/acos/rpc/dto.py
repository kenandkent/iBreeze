"""RPC 传输对象。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PageRequest:
    """分页请求。"""

    cursor: str = ""
    limit: int = 50

    def validate(self) -> None:
        """校验分页参数。"""
        if self.limit < 1 or self.limit > 200:
            self.limit = 50


@dataclass
class PageResponse:
    """分页响应。"""

    items: list[Any]
    next_cursor: str | None
    has_more: bool
