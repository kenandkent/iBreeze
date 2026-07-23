"""本地 SQLite 数据库，WAL 模式，100MB 限制，自动 compact。"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite

DEFAULT_DB_PATH = Path.home() / ".ibreeze" / "sidecar.db"
MAX_DB_SIZE_BYTES = 100 * 1024 * 1024  # 100MB

# 各表的 TEXT 型字段列表，用于 list_all 中 LIKE 搜索
_TABLE_SEARCH_FIELDS: dict[str, list[str]] = {
    "companies": ["name", "email", "phone", "industry", "address"],
    "conversations": ["title"],
    "messages": ["content"],
    "knowledge_entries": ["title", "content"],
    "workspaces": ["name", "description"],
    "orchestrations": ["name", "description"],
    "employees": ["name", "email", "phone"],
    "departments": ["name"],
    "agent_states": ["agent_id", "user_id"],
    "audit_log": ["event_type", "actor_id", "resource_type", "resource_id"],
}

# 所有表的建表 DDL
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    email TEXT,
    phone TEXT,
    unified_credit_code TEXT,
    business_license_url TEXT,
    legal_rep_id_card TEXT,
    industry TEXT,
    address TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'inactive', 'deleted')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'archived', 'deleted')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    metadata TEXT,
    deleted_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS knowledge_entries (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('FAQ', 'DOC', 'URL')),
    content_hash TEXT NOT NULL CHECK(length(content_hash) = 64),
    tags TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'archived')),
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_active_hash
    ON knowledge_entries(content_hash) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    owner_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'inactive', 'deleted')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspace_members (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('owner', 'admin', 'member')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

CREATE TABLE IF NOT EXISTS orchestrations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'active', 'archived', 'deleted')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orchestration_nodes (
    id TEXT PRIMARY KEY,
    orchestration_id TEXT NOT NULL,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    config TEXT,
    position_x REAL DEFAULT 0.0,
    position_y REAL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (orchestration_id) REFERENCES orchestrations(id)
);

CREATE TABLE IF NOT EXISTS orchestration_edges (
    id TEXT PRIMARY KEY,
    orchestration_id TEXT NOT NULL,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    source_port TEXT,
    target_port TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (orchestration_id) REFERENCES orchestrations(id)
);

CREATE TABLE IF NOT EXISTS orchestration_runs (
    id TEXT PRIMARY KEY,
    orchestration_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running' CHECK(status IN ('running', 'success', 'failed')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_message TEXT,
    result TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (orchestration_id) REFERENCES orchestrations(id)
);

CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    department_id TEXT,
    role TEXT,
    email TEXT,
    phone TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'inactive')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (department_id) REFERENCES departments(id)
);

CREATE TABLE IF NOT EXISTS departments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    parent_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES departments(id)
);

CREATE TABLE IF NOT EXISTS agent_states (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'stopped' CHECK(status IN ('running', 'stopped', 'error')),
    config TEXT,
    last_heartbeat TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
"""


class LocalDB:
    """异步 SQLite 数据库，WAL 模式，自动 compact。"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = str(db_path or DEFAULT_DB_PATH)
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """打开连接、设置 PRAGMA、创建所有表。"""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode = WAL")
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.execute("PRAGMA busy_timeout = 5000")
        await self._db.execute("PRAGMA synchronous = NORMAL")
        await self._db.execute("PRAGMA temp_store = MEMORY")
        await self._db.executescript(_CREATE_TABLES_SQL)
        await self._db.commit()

    async def compact(self) -> None:
        """VACUUM 并检查 100MB 限制。"""
        assert self._db is not None, "数据库未初始化"
        await self._db.execute("VACUUM")
        await self._db.commit()
        size = os.path.getsize(self._db_path)
        if size > MAX_DB_SIZE_BYTES:
            raise RuntimeError(
                f"数据库大小 {size} 超过 100MB 限制，请清理数据后重试"
            )

    async def close(self) -> None:
        """关闭连接。"""
        if self._db is not None:
            await self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            await self._db.close()
            self._db = None

    # ---- 通用 CRUD ----

    async def insert(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        """插入一条记录，返回插入的完整数据。"""
        assert self._db is not None, "数据库未初始化"
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        values = list(data.values())
        await self._db.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
            values,
        )
        await self._db.commit()
        return data

    async def get_by_id(self, table: str, id: str) -> dict[str, Any] | None:
        """按 ID 获取单条记录。"""
        assert self._db is not None, "数据库未初始化"
        cursor = await self._db.execute(f"SELECT * FROM {table} WHERE id = ?", (id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    async def update_by_id(
        self, table: str, id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """按 ID 更新记录，返回更新后的记录。"""
        assert self._db is not None, "数据库未初始化"
        if not data:
            return await self.get_by_id(table, id)
        set_clause = ", ".join(f"{k} = ?" for k in data.keys())
        values = list(data.values()) + [id]
        await self._db.execute(
            f"UPDATE {table} SET {set_clause} WHERE id = ?",
            values,
        )
        await self._db.commit()
        return await self.get_by_id(table, id)

    async def delete_by_id(self, table: str, id: str) -> bool:
        """按 ID 删除记录，返回是否删除成功。"""
        assert self._db is not None, "数据库未初始化"
        cursor = await self._db.execute(f"DELETE FROM {table} WHERE id = ?", (id,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_all(
        self,
        table: str,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """列出记录，支持简单等值过滤。"""
        assert self._db is not None, "数据库未初始化"
        where_parts: list[str] = []
        values: list[Any] = []
        if filters:
            for k, v in filters.items():
                where_parts.append(f"{k} = ?")
                values.append(v)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        cursor = await self._db.execute(
            f"SELECT * FROM {table} {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            values + [limit, offset],
        )
        rows = await cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    async def count(self, table: str, filters: dict[str, Any] | None = None) -> int:
        """统计记录数。"""
        assert self._db is not None, "数据库未初始化"
        where_parts: list[str] = []
        values: list[Any] = []
        if filters:
            for k, v in filters.items():
                where_parts.append(f"{k} = ?")
                values.append(v)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        cursor = await self._db.execute(
            f"SELECT COUNT(*) FROM {table} {where_sql}", values
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def search(
        self, table: str, query: str, fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """在指定字段上做 LIKE 模糊搜索。"""
        assert self._db is not None, "数据库未初始化"
        if fields is None:
            fields = _TABLE_SEARCH_FIELDS.get(table, [])
        if not fields:
            return []
        like_parts = [f"{f} LIKE ?" for f in fields]
        like_sql = " OR ".join(like_parts)
        pattern = f"%{query}%"
        cursor = await self._db.execute(
            f"SELECT * FROM {table} WHERE {like_sql} ORDER BY created_at DESC LIMIT 100",
            [pattern] * len(fields),
        )
        rows = await cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
