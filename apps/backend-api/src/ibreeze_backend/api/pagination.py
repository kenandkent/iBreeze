"""Cursor-based pagination helpers."""

import base64
import json
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CursorParams(BaseModel):
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


def encode_cursor(created_at: datetime, id: UUID) -> str:
    payload = {
        "created_at": created_at.isoformat(),
        "id": str(id),
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor_str: str) -> tuple[datetime, UUID]:
    try:
        decoded = base64.urlsafe_b64decode(cursor_str.encode())
        payload = json.loads(decoded)
        dt = datetime.fromisoformat(payload["created_at"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt, UUID(payload["id"])
    except Exception:
        raise ValueError("Invalid cursor")
