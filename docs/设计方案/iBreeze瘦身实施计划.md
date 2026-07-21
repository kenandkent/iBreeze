# iBreeze 全链路瘦身实施计划

> 本文档依据《iBreeze全链路瘦身设计方案》（以下简称"设计方案"）编写，是面向**开发团队**的详细实施计划。每个任务给出确切文件路径、需要实现的接口/字段（引用设计方案章节，不重复定义）、测试用例与验收标准（Definition of Done）。
>
> 约定：
> - **任务编号**：`P<阶段号>-T<任务号>`，如 `P1-T2`。任务之间的"依赖"字段指向其他任务编号，必须先完成依赖任务才能开始。
> - **文件路径**：全部位于项目根目录 `/Users/ken/workspace/ibreeze/` 内。
> - **测试优先**：每个任务的"测试"小节列出必须写的测试文件与关键用例。
> - **提交粒度**：一个任务对应一个或多个小提交，提交信息用 `<phase>: <task 简述>`。
> - **验收标准（DoD）**：每个任务的 DoD 明确、可判定。

---

## 0. 总体阶段与时间线

### 0.1 Phase 依赖关系

```
Phase 1 ──────► Phase 2 ──────► Phase 3
                   │                │
                   ▼                │
              Phase 4 ─────────────┘
                   │
                   ▼
              Phase 5 ──► Phase 6
```

### 0.2 Phase 概览

| Phase | 名称 | 依赖 | 任务数 | 预估人周 | 可并行 |
|-------|------|------|--------|---------|--------|
| Phase 1 | Admin Backend 骨架 | 无 | 5 | 2 | — |
| Phase 2 | Admin Backend REST API | P1 | 7 | 4 | — |
| Phase 3 | Admin Frontend | P2 | 5 | 3 | 与 P4 并行 |
| Phase 4 | Sidecar 改造 | P2 | 4 | 2 | 与 P3 并行 |
| Phase 5 | Desktop App 瘦身 | P4 | 5 | 2 | 依赖 P4 |
| Phase 6 | 集成测试 + 文档 | P3, P5 | 3 | 1 | — |
| **合计** | | | **29** | **14** | |

### 0.3 人员分工建议

| 席位 | 主技能 | 主责 Phase | 可备份 |
|------|--------|-----------|--------|
| A | Python / FastAPI | P1, P2 | P4 |
| B | React / TypeScript | P3, P5 | P6 |
| C | Python / Sidecar | P4 | P1, P2 |
| D | 测试 / 集成 | P6 | P3, P5 |

### 0.4 Go/No-Go 检查点

| 检查点 | 完成条件 | 不达标处理 |
|--------|---------|-----------|
| Phase 1 完成 | FastAPI 启动 + JWT 登录可用 + DB 迁移成功 | 停止，排查骨架问题 |
| Phase 2 完成 | ~74 端点全部注册 + pytest 通过 | 停止，补充缺失端点 |
| Phase 4 完成 | Sidecar RPC 精简 + 同步拉取正常 | 回滚 RPC 移除，保留兼容层 |
| Phase 5 完成 | Desktop 构建成功 + 9 页面可用 | 回滚页面移除，保留旧页面 |

---

## Phase 1：Admin Backend 骨架

**目标**：搭建 Admin Backend 项目骨架，实现数据库 Schema、JWT 认证、RBAC 中间件、初始数据。产出一个可启动、可登录的空壳后端。

### P1-T1：项目初始化

**文件**：
- `admin-backend/`（新建目录）
- `admin-backend/pyproject.toml`
- `admin-backend/app/__init__.py`
- `admin-backend/app/main.py`
- `admin-backend/app/config.py`
- `admin-backend/app/database.py`
- `admin-backend/tests/__init__.py`
- `admin-backend/tests/conftest.py`

**实现要点**：
1. 创建 `admin-backend/` 目录结构：
   ```
   admin-backend/
   ├── pyproject.toml          # Python 项目配置（uv 管理）
   ├── app/
   │   ├── __init__.py
   │   ├── main.py             # FastAPI 应用入口
   │   ├── config.py           # 配置（端口、DB 路径、JWT 密钥等）
   │   ├── database.py         # SQLAlchemy async engine + session
   │   ├── models/             # SQLAlchemy 模型（Phase 2 填充）
   │   ├── schemas/            # Pydantic 请求/响应模型（Phase 2 填充）
   │   ├── api/                # 路由（Phase 2 填充）
   │   │   └── __init__.py
   │   ├── auth/               # JWT + RBAC（P1-T3, P1-T4）
   │   │   └── __init__.py
   │   └── sync/               # 同步 API（Phase 2 填充）
   ├── migrations/             # Alembic 迁移
   ├── tests/
   │   ├── __init__.py
   │   └── conftest.py         # 测试 fixtures（测试 DB、TestClient）
   └── alembic.ini
   ```

2. `pyproject.toml` 依赖：
   ```toml
   [project]
   name = "ibreeze-admin-backend"
   version = "0.1.0"
   requires-python = ">=3.12"
   dependencies = [
       "fastapi>=0.115.0",
       "uvicorn[standard]>=0.30.0",
       "sqlalchemy[asyncio]>=2.0.0",
       "aiosqlite>=0.20.0",
       "alembic>=1.13.0",
       "pyjwt>=2.9.0",
       "passlib[bcrypt]>=1.7.4",
       "python-multipart>=0.0.9",
       "httpx>=0.27.0",
   ]
   
   [project.optional-dependencies]
   dev = [
       "pytest>=8.0.0",
       "pytest-asyncio>=0.24.0",
       "httpx>=0.27.0",
   ]
   ```

3. `app/config.py`：
   ```python
   from pydantic_settings import BaseSettings
   
   class Settings(BaseSettings):
       app_name: str = "iBreeze Admin Backend"
       admin_db_path: str = "/tmp/ibreeze_admin.db"
       jwt_secret_key: str = "ibreeze-admin-secret-change-in-production"
       jwt_algorithm: str = "HS256"
       jwt_access_token_expire_minutes: int = 30
       jwt_refresh_token_expire_days: int = 7
       host: str = "127.0.0.1"
       port: int = 50080
   
   settings = Settings()
   ```

4. `app/database.py`：
   ```python
   from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
   from app.config import settings
   
   engine = create_async_engine(f"sqlite+aiosqlite:///{settings.admin_db_path}")
   async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
   
   async def get_db():
       async with async_session() as session:
           yield session
   ```

5. `app/main.py`：
   ```python
   from fastapi import FastAPI
   from fastapi.middleware.cors import CORSMiddleware
   from app.config import settings
   
   app = FastAPI(title=settings.app_name)
   
   # CORS（Admin 前端运行在不同端口，如 8000）
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["http://localhost:8000"],  # Admin 前端端口
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   
   @app.get("/health")
   async def health():
       return {"status": "healthy", "service": "admin-backend"}
   ```

**测试**：
- `tests/conftest.py`：配置测试用 SQLite DB（`:memory:` 或临时文件），提供 `TestClient` fixture。
- `tests/test_health.py`：`GET /health` 返回 `{"status": "healthy"}`。

**DoD**：
- `cd admin-backend && uv sync` 安装依赖成功。
- `cd admin-backend && uvicorn app.main:app --port 50080` 启动无报错。
- `curl http://127.0.0.1:50080/health` 返回 `{"status":"healthy","service":"admin-backend"}`。
- `cd admin-backend && uv run pytest tests/ -q` 通过。

---

### P1-T2：数据库 Schema + Alembic 迁移

**文件**：
- `admin-backend/alembic.ini`
- `admin-backend/migrations/env.py`
- `admin-backend/migrations/script.py.mako`
- `admin-backend/migrations/versions/0001_initial_schema.py`
- `admin-backend/app/models/__init__.py`
- `admin-backend/app/models/admin.py`（admin_users, admin_sessions）
- `admin-backend/app/models/capability.py`（capabilities, capability_versions, skills, skill_versions, skill_bindings, prompt_assets, prompt_asset_versions）
- `admin-backend/app/models/template.py`（employee_templates）
- `admin-backend/app/models/knowledge.py`（knowledge_documents, knowledge_sources, knowledge_policies, security_policies, workspace_policies, notification_policies, budget_policies）
- `admin-backend/app/models/provider.py`（providers, provider_models, provider_credentials, provider_pricing_versions, provider_tier_mappings）
- `admin-backend/app/models/backend.py`（backends, company_backend_defaults）
- `admin-backend/app/models/organization.py`（companies, departments, employees, access_grants）
- `admin-backend/app/models/governance.py`（approval_types, audit_log）

**依赖**：P1-T1

**实现要点**：
1. Alembic 配置异步 SQLite：
   ```ini
   # alembic.ini
   [alembic]
   script_location = migrations
   sqlalchemy.url = sqlite+aiosqlite:////tmp/ibreeze_admin.db
   ```

2. `migrations/env.py` 配置 async engine，导入所有 models 的 `Base.metadata`。

3. 创建 `0001_initial_schema.py` 迁移脚本，包含设计方案 §5.5 定义的全部 30 张表：

   **管理认证表**：
   ```sql
   CREATE TABLE admin_users (
       user_id TEXT PRIMARY KEY,
       username TEXT UNIQUE NOT NULL,
       password_hash TEXT NOT NULL,
       role TEXT NOT NULL DEFAULT 'viewer'
           CHECK (role IN ('super_admin', 'platform_admin', 'company_admin', 'viewer')),
       status TEXT NOT NULL DEFAULT 'active'
           CHECK (status IN ('active', 'disabled')),
       created_at TEXT DEFAULT (datetime('now')),
       updated_at TEXT DEFAULT (datetime('now'))
   );
   
   CREATE TABLE admin_sessions (
       session_id TEXT PRIMARY KEY,
       user_id TEXT NOT NULL REFERENCES admin_users(user_id),
       refresh_token_hash TEXT NOT NULL,
       expires_at TEXT NOT NULL,
       created_at TEXT DEFAULT (datetime('now'))
   );
   ```

   **能力管理表**（从 Sidecar 现有 Schema 迁移，保持字段兼容）：
   ```sql
   CREATE TABLE capabilities (
       capability_id TEXT PRIMARY KEY,
       company_id TEXT,
       name TEXT NOT NULL,
       description TEXT,
       status TEXT NOT NULL DEFAULT 'draft'
           CHECK (status IN ('draft','review','published','deprecated','archived')),
       current_version INTEGER DEFAULT 1,
       version INTEGER NOT NULL DEFAULT 1,
       created_at TEXT DEFAULT (datetime('now')),
       updated_at TEXT DEFAULT (datetime('now'))
   );
   
   CREATE TABLE capability_versions (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       capability_id TEXT NOT NULL,
       version INTEGER NOT NULL,
       content JSON NOT NULL,
       checksum TEXT,
       created_at TEXT DEFAULT (datetime('now')),
       UNIQUE(capability_id, version)
   );
   
   CREATE TABLE skills (
       skill_id TEXT PRIMARY KEY,
       company_id TEXT,
       name TEXT NOT NULL,
       description TEXT,
       prompt_asset_id TEXT,
       status TEXT NOT NULL DEFAULT 'draft',
       version INTEGER NOT NULL DEFAULT 1,
       created_at TEXT DEFAULT (datetime('now')),
       updated_at TEXT DEFAULT (datetime('now'))
   );
   
   CREATE TABLE skill_versions (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       skill_id TEXT NOT NULL,
       version INTEGER NOT NULL,
       content JSON NOT NULL,
       checksum TEXT,
       created_at TEXT DEFAULT (datetime('now')),
       UNIQUE(skill_id, version)
   );
   
   CREATE TABLE skill_bindings (
       binding_id TEXT PRIMARY KEY,
       capability_id TEXT NOT NULL,
       skill_id TEXT NOT NULL,
       ordinal INTEGER NOT NULL DEFAULT 0,
       created_at TEXT DEFAULT (datetime('now'))
   );
   
   CREATE TABLE prompt_assets (
       prompt_id TEXT PRIMARY KEY,
       company_id TEXT,
       name TEXT NOT NULL,
       description TEXT,
       content TEXT,
       status TEXT NOT NULL DEFAULT 'draft',
       version INTEGER NOT NULL DEFAULT 1,
       created_at TEXT DEFAULT (datetime('now')),
       updated_at TEXT DEFAULT (datetime('now'))
   );
   
   CREATE TABLE prompt_asset_versions (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       prompt_id TEXT NOT NULL,
       version INTEGER NOT NULL,
       content JSON NOT NULL,
       checksum TEXT,
       created_at TEXT DEFAULT (datetime('now')),
       UNIQUE(prompt_id, version)
   );
   ```

   **模板表**：
   ```sql
   CREATE TABLE employee_templates (
       template_id TEXT PRIMARY KEY,
       company_id TEXT,
       name TEXT NOT NULL,
       role TEXT,
       description TEXT,
       provider_id TEXT,
       capability_id TEXT,
       model TEXT,
       capability_snapshot JSON DEFAULT '{}',
       template_scope TEXT DEFAULT 'company',
       status TEXT NOT NULL DEFAULT 'draft'
           CHECK (status IN ('draft','active','archived')),
       version INTEGER NOT NULL DEFAULT 1,
       created_at TEXT DEFAULT (datetime('now')),
       updated_at TEXT DEFAULT (datetime('now'))
   );
   ```

   **知识管理表**：
   ```sql
   CREATE TABLE knowledge_documents (
       knowledge_id TEXT PRIMARY KEY,
       company_id TEXT NOT NULL,
       title TEXT NOT NULL,
       content TEXT,
       source_type TEXT,
       source_id TEXT,
       category TEXT,
       status TEXT DEFAULT 'active',
       governance_confirmed INTEGER DEFAULT 0,
       created_at TEXT DEFAULT (datetime('now')),
       updated_at TEXT DEFAULT (datetime('now'))
   );
   
   CREATE TABLE knowledge_sources (
       source_id TEXT PRIMARY KEY,
       company_id TEXT NOT NULL,
       source_type TEXT NOT NULL,
       source_ref TEXT,
       status TEXT DEFAULT 'active',
       created_at TEXT DEFAULT (datetime('now'))
   );
   
   CREATE TABLE knowledge_policies (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       company_id TEXT NOT NULL,
       version INTEGER NOT NULL DEFAULT 1,
       config JSON NOT NULL DEFAULT '{}',
       status TEXT NOT NULL DEFAULT 'active',
       created_at TEXT DEFAULT (datetime('now')),
       UNIQUE(company_id, version)
   );
   
   CREATE TABLE security_policies (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       company_id TEXT NOT NULL,
       version INTEGER NOT NULL DEFAULT 1,
       config JSON NOT NULL DEFAULT '{}',
       status TEXT NOT NULL DEFAULT 'active',
       created_at TEXT DEFAULT (datetime('now')),
       UNIQUE(company_id, version)
   );
   
   CREATE TABLE workspace_policies (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       company_id TEXT NOT NULL,
       version INTEGER NOT NULL DEFAULT 1,
       config JSON NOT NULL DEFAULT '{}',
       status TEXT NOT NULL DEFAULT 'active',
       created_at TEXT DEFAULT (datetime('now')),
       UNIQUE(company_id, version)
   );
   
   CREATE TABLE notification_policies (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       company_id TEXT NOT NULL,
       version INTEGER NOT NULL DEFAULT 1,
       config JSON NOT NULL DEFAULT '{}',
       status TEXT NOT NULL DEFAULT 'active',
       created_at TEXT DEFAULT (datetime('now')),
       UNIQUE(company_id, version)
   );
   
   CREATE TABLE budget_policies (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       company_id TEXT NOT NULL,
       version INTEGER NOT NULL DEFAULT 1,
       config JSON NOT NULL DEFAULT '{}',
       status TEXT NOT NULL DEFAULT 'active',
       created_at TEXT DEFAULT (datetime('now')),
       UNIQUE(company_id, version)
   );
   ```

   **Provider/Backend 表**：
   ```sql
   CREATE TABLE providers (
       provider_id TEXT PRIMARY KEY,
       company_id TEXT,
       name TEXT NOT NULL,
       provider_type TEXT NOT NULL CHECK (provider_type IN ('api','cli')),
       config JSON DEFAULT '{}',
       status TEXT NOT NULL DEFAULT 'active',
       version INTEGER NOT NULL DEFAULT 1,
       created_at TEXT DEFAULT (datetime('now')),
       updated_at TEXT DEFAULT (datetime('now'))
   );
   
   CREATE TABLE provider_models (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       provider_id TEXT NOT NULL,
       model_id TEXT NOT NULL,
       display_name TEXT,
       tier TEXT DEFAULT 'standard',
       created_at TEXT DEFAULT (datetime('now')),
       UNIQUE(provider_id, model_id)
   );
   
   CREATE TABLE provider_credentials (
       credential_id TEXT PRIMARY KEY,
       provider_id TEXT NOT NULL,
       company_id TEXT NOT NULL,
       credential_type TEXT NOT NULL,
       credential_ref TEXT,
       created_at TEXT DEFAULT (datetime('now'))
   );
   
   CREATE TABLE provider_pricing_versions (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       provider_id TEXT NOT NULL,
       company_id TEXT,
       version INTEGER NOT NULL DEFAULT 1,
       pricing JSON NOT NULL DEFAULT '{}',
       currency TEXT DEFAULT 'USD',
       created_at TEXT DEFAULT (datetime('now')),
       UNIQUE(provider_id, company_id, version)
   );
   
   CREATE TABLE provider_tier_mappings (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       company_id TEXT NOT NULL,
       provider_id TEXT NOT NULL,
       tier TEXT NOT NULL,
       model_id TEXT NOT NULL,
       created_at TEXT DEFAULT (datetime('now')),
       UNIQUE(company_id, provider_id, tier)
   );
   
   CREATE TABLE backends (
       backend_id TEXT PRIMARY KEY,
       company_id TEXT NOT NULL,
       name TEXT NOT NULL,
       backend_type TEXT NOT NULL DEFAULT 'local_process',
       provider_id TEXT,
       workspace_root TEXT,
       status TEXT NOT NULL DEFAULT 'disabled'
           CHECK (status IN ('enabled','disabled','draining','archived')),
       concurrency INTEGER DEFAULT 1,
       version INTEGER NOT NULL DEFAULT 1,
       created_at TEXT DEFAULT (datetime('now')),
       updated_at TEXT DEFAULT (datetime('now'))
   );
   
   CREATE TABLE company_backend_defaults (
       company_id TEXT PRIMARY KEY,
       backend_id TEXT NOT NULL,
       version INTEGER NOT NULL DEFAULT 1,
       created_at TEXT DEFAULT (datetime('now'))
   );
   ```

   **组织管理表**：
   ```sql
   CREATE TABLE companies (
       company_id TEXT PRIMARY KEY,
       name TEXT NOT NULL,
       status TEXT NOT NULL DEFAULT 'initializing'
           CHECK (status IN ('initializing','active','dissolving','dissolved')),
       default_provider_policy JSON DEFAULT '{}',
       default_budget_policy JSON DEFAULT '{}',
       root_department_id TEXT,
       leader_employee_id TEXT,
       version INTEGER NOT NULL DEFAULT 1,
       created_at TEXT DEFAULT (datetime('now')),
       updated_at TEXT DEFAULT (datetime('now')),
       deleted_at TEXT,
       dissolved_at TEXT
   );
   
   CREATE TABLE departments (
       department_id TEXT PRIMARY KEY,
       company_id TEXT NOT NULL,
       parent_id TEXT,
       name TEXT NOT NULL,
       description TEXT,
       leader_employee_id TEXT,
       status TEXT NOT NULL DEFAULT 'active'
           CHECK (status IN ('active','frozen','deleted')),
       version INTEGER NOT NULL DEFAULT 1,
       created_at TEXT DEFAULT (datetime('now')),
       updated_at TEXT DEFAULT (datetime('now')),
       deleted_at TEXT
   );
   
   CREATE TABLE employees (
       employee_id TEXT PRIMARY KEY,
       company_id TEXT NOT NULL,
       department_id TEXT,
       name TEXT NOT NULL,
       role_name TEXT,
       employee_type TEXT NOT NULL DEFAULT 'employee'
           CHECK (employee_type IN ('company_leader','department_leader','employee')),
       template_id TEXT,
       capability_snapshot JSON DEFAULT '{}',
       manager_id TEXT,
       status TEXT NOT NULL DEFAULT 'active'
           CHECK (status IN ('active','suspended','archived','deleted')),
       version INTEGER NOT NULL DEFAULT 1,
       created_at TEXT DEFAULT (datetime('now')),
       updated_at TEXT DEFAULT (datetime('now')),
       deleted_at TEXT
   );
   
   CREATE TABLE access_grants (
       grant_id TEXT PRIMARY KEY,
       company_id TEXT NOT NULL,
       employee_id TEXT NOT NULL,
       target_type TEXT NOT NULL CHECK (target_type IN ('department','task')),
       target_id TEXT NOT NULL,
       permission TEXT NOT NULL CHECK (permission IN ('department_read','task_read')),
       status TEXT NOT NULL DEFAULT 'active'
           CHECK (status IN ('active','revoked','expired')),
       expires_at TEXT NOT NULL,
       approved_by TEXT NOT NULL,
       version INTEGER NOT NULL DEFAULT 1,
       created_at TEXT DEFAULT (datetime('now')),
       revoked_at TEXT
   );
   ```

   **治理表**：
   ```sql
   CREATE TABLE approval_types (
       type_id TEXT PRIMARY KEY,
       company_id TEXT NOT NULL,
       name TEXT NOT NULL,
       description TEXT,
       config JSON DEFAULT '{}',
       version INTEGER NOT NULL DEFAULT 1,
       created_at TEXT DEFAULT (datetime('now')),
       updated_at TEXT DEFAULT (datetime('now'))
   );
   
   CREATE TABLE audit_log (
       log_id TEXT PRIMARY KEY,
       company_id TEXT NOT NULL,
       audit_type TEXT NOT NULL,
       actor_id TEXT,
       action TEXT NOT NULL,
       resource_type TEXT,
       resource_id TEXT,
       details JSON DEFAULT '{}',
       trace_id TEXT,
       created_at TEXT DEFAULT (datetime('now'))
   );
    CREATE INDEX idx_audit_log_company ON audit_log(company_id, created_at);
    CREATE INDEX idx_audit_log_type ON audit_log(audit_type, created_at);
    ```

4. 所有表使用 `CREATE TABLE IF NOT EXISTS`（幂等），所有索引使用 `CREATE INDEX IF NOT EXISTS`。

5. 补充业务查询索引：
   ```sql
   CREATE INDEX IF NOT EXISTS idx_companies_status ON companies(status);
   CREATE INDEX IF NOT EXISTS idx_departments_company ON departments(company_id);
   CREATE INDEX IF NOT EXISTS idx_employees_company ON employees(company_id);
   CREATE INDEX IF NOT EXISTS idx_employees_department ON employees(department_id);
   CREATE INDEX IF NOT EXISTS idx_access_grants_company ON access_grants(company_id);
   CREATE INDEX IF NOT EXISTS idx_access_grants_employee ON access_grants(employee_id);
   CREATE INDEX IF NOT EXISTS idx_capabilities_company ON capabilities(company_id);
   CREATE INDEX IF NOT EXISTS idx_skills_company ON skills(company_id);
   CREATE INDEX IF NOT EXISTS idx_prompt_assets_company ON prompt_assets(company_id);
   CREATE INDEX IF NOT EXISTS idx_providers_company ON providers(company_id);
   CREATE INDEX IF NOT EXISTS idx_backends_company ON backends(company_id);
   CREATE INDEX IF NOT EXISTS idx_knowledge_documents_company ON knowledge_documents(company_id);
   CREATE INDEX IF NOT EXISTS idx_knowledge_sources_company ON knowledge_sources(company_id);
   ```

**测试**：
- `tests/test_migration.py`：
  - 执行迁移后检查所有 30 张表存在（使用 conftest 中的内存数据库，而非硬编码 `/tmp/ibreeze_admin.db`）。
  - 重复执行迁移不报错（幂等性）。
  - 检查关键索引存在。

**DoD**：
- `cd admin-backend && uv run alembic upgrade head` 执行成功，30 张表全部创建。
- 重复执行 `alembic upgrade head` 不报错。
- `uv run pytest tests/test_migration.py -q` 通过。

---

### P1-T3：JWT 认证

**文件**：
- `admin-backend/app/auth/__init__.py`
- `admin-backend/app/auth/jwt.py`
- `admin-backend/app/auth/service.py`
- `admin-backend/app/schemas/auth.py`
- `admin-backend/app/api/auth.py`
- `admin-backend/tests/test_auth.py`

**依赖**：P1-T2

**实现要点**：
1. `app/auth/jwt.py` — JWT 工具函数：
   ```python
   import jwt
   from datetime import datetime, timedelta, timezone
   from app.config import settings
   
   def create_access_token(user_id: str, role: str) -> str:
       expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
       payload = {"sub": user_id, "role": role, "exp": expire, "type": "access"}
       return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
   
   def create_refresh_token(user_id: str) -> str:
       expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
       payload = {"sub": user_id, "exp": expire, "type": "refresh"}
       return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
   
   def decode_token(token: str) -> dict:
       return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
   ```

2. `app/auth/service.py` — 认证服务：
   ```python
   from sqlalchemy.ext.asyncio import AsyncSession
   from sqlalchemy import select
   from passlib.hash import bcrypt
   from app.models.admin import AdminUser, AdminSession
   from app.auth.jwt import create_access_token, create_refresh_token, decode_token
   import uuid
   
   class AuthService:
       async def login(self, db: AsyncSession, username: str, password: str) -> dict:
           result = await db.execute(select(AdminUser).where(AdminUser.username == username))
           user = result.scalar_one_or_none()
           if not user or not bcrypt.verify(password, user.password_hash):
               raise ValueError("Invalid credentials")
           if user.status != 'active':
               raise ValueError("Account disabled")
           
           access_token = create_access_token(user.user_id, user.role)
           refresh_token = create_refresh_token(user.user_id)
           
           # 存储 refresh token hash
           session = AdminSession(
               session_id=str(uuid.uuid4()),
               user_id=user.user_id,
               refresh_token_hash=bcrypt.hash(refresh_token),
               expires_at=(datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
           )
           db.add(session)
           await db.commit()
           
           return {
               "access_token": access_token,
               "refresh_token": refresh_token,
               "user": {"user_id": user.user_id, "username": user.username, "role": user.role}
           }
       
        async def refresh(self, db: AsyncSession, refresh_token: str) -> dict:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise ValueError("Invalid token type")
            user_id = payload["sub"]
            
            # 验证 refresh token 在数据库中仍有效（未被撤销）
            from sqlalchemy import select
            from passlib.hash import bcrypt
            result = await db.execute(
                select(AdminSession).where(
                    AdminSession.user_id == user_id,
                    AdminSession.expires_at > datetime.now(timezone.utc).isoformat()
                )
            )
            sessions = result.scalars().all()
            valid_session = any(bcrypt.verify(refresh_token, s.refresh_token_hash) for s in sessions)
            if not valid_session:
                raise ValueError("Refresh token revoked or expired")
            
            # 查询用户获取 role
            result = await db.execute(select(AdminUser).where(AdminUser.user_id == user_id))
            user = result.scalar_one_or_none()
            if not user or user.status != 'active':
                raise ValueError("User disabled or not found")
            
            # 生成新 access_token
            return {"access_token": create_access_token(user_id, user.role)}
   ```

3. `app/api/auth.py` — 路由：
   ```python
   from fastapi import APIRouter, Depends, HTTPException
   from sqlalchemy.ext.asyncio import AsyncSession
   from app.database import get_db
   from app.schemas.auth import LoginRequest, LoginResponse, RefreshRequest
   from app.auth.service import AuthService
   
   router = APIRouter(prefix="/api/auth", tags=["auth"])
   auth_service = AuthService()
   
   @router.post("/login", response_model=LoginResponse)
   async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
       try:
           return await auth_service.login(db, req.username, req.password)
       except ValueError as e:
           raise HTTPException(status_code=401, detail=str(e))
   
   @router.post("/refresh")
   async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
       try:
           return await auth_service.refresh(db, req.refresh_token)
       except ValueError as e:
           raise HTTPException(status_code=401, detail=str(e))
   
   @router.get("/me")
   async def me(current_user = Depends(get_current_user)):
       return current_user
   ```

4. `app/schemas/auth.py`：
   ```python
   from pydantic import BaseModel
   
   class LoginRequest(BaseModel):
       username: str
       password: str
   
   class LoginResponse(BaseModel):
       access_token: str
       refresh_token: str
       user: dict
   
   class RefreshRequest(BaseModel):
       refresh_token: str
   ```

5. `app/main.py` 注册路由：
   ```python
   from app.api.auth import router as auth_router
   app.include_router(auth_router)
   ```

**测试**：
- `tests/test_auth.py`：
  - 创建 admin_user → `POST /api/auth/login` → 返回 access_token + refresh_token。
  - 错误密码 → 401。
  - 不存在的用户 → 401。
  - `GET /api/auth/me` 带有效 token → 返回用户信息。
  - `GET /api/auth/me` 无 token → 401。
  - `GET /api/auth/me` 带过期 token → 401。
  - `POST /api/auth/refresh` 带有效 refresh_token → 返回新 access_token。
  - `POST /api/auth/refresh` 带无效 refresh_token → 401。
  - `PUT /api/auth/password` 带正确旧密码 → 修改成功。
  - `PUT /api/auth/password` 带错误旧密码 → 400。

**DoD**：
- 登录/刷新/获取用户信息/修改密码四个端点可用。
- 错误凭据返回 401。
- 过期 token 返回 401。
- `uv run pytest tests/test_auth.py -q` 全部通过。

---

### P1-T4：RBAC 中间件

**文件**：
- `admin-backend/app/auth/rbac.py`
- `admin-backend/tests/test_rbac.py`

**依赖**：P1-T3

**实现要点**：
1. `app/auth/rbac.py`：
   ```python
   from fastapi import Depends, HTTPException
   from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
   
   security = HTTPBearer()
   
   # 角色权限矩阵
   ROLE_PERMISSIONS = {
       "super_admin": {"capabilities", "knowledge", "providers", "backends", "governance", "audit", "settings"},
       "platform_admin": {"capabilities", "knowledge", "providers", "backends", "governance", "audit"},
       "company_admin": {"capabilities", "knowledge", "providers", "backends"},
       "viewer": set(),  # 只读，不写入
   }
   
   async def get_current_user(
       credentials: HTTPAuthorizationCredentials = Depends(security)
   ) -> dict:
       from app.auth.jwt import decode_token
       try:
           payload = decode_token(credentials.credentials)
           if payload.get("type") != "access":
               raise HTTPException(status_code=401, detail="Invalid token type")
           return {"user_id": payload["sub"], "role": payload["role"]}
       except Exception:
           raise HTTPException(status_code=401, detail="Invalid token")
   
   def require_permission(resource: str):
       """依赖注入：检查当前用户是否有指定资源的写权限"""
       async def checker(current_user: dict = Depends(get_current_user)):
           role = current_user["role"]
           if resource not in ROLE_PERMISSIONS.get(role, set()):
               raise HTTPException(status_code=403, detail="Insufficient permissions")
           return current_user
       return checker
   ```

2. 路由中使用：
   ```python
   from app.auth.rbac import require_permission
   
   @router.post("/capabilities")
   async def create_capability(
       ...,
       current_user: dict = Depends(require_permission("capabilities"))
   ):
       ...
   ```

**注**：`require_permission()` 依赖在 P1-T4 中定义并测试，但需在 Phase 2 的所有业务端点中实际使用，否则 RBAC 不会生效。

**测试**：
- `tests/test_rbac.py`：
  - `super_admin` 可访问所有资源端点。
  - `company_admin` 可访问 capabilities/knowledge/providers/backends，不可访问 governance/audit。
  - `viewer` 对写端点返回 403。
  - 无 token → 401。
  - 过期 token → 401。

**DoD**：
- RBAC 中间件可用，4 种角色按矩阵控制访问。
- `uv run pytest tests/test_rbac.py -q` 全部通过。

---

### P1-T5：初始数据（Seed）

**文件**：
- `admin-backend/app/seed.py`
- `admin-backend/tests/test_seed.py`

**依赖**：P1-T2

**实现要点**：
1. `app/seed.py`：
   ```python
   from sqlalchemy.ext.asyncio import AsyncSession
   from sqlalchemy import select
   from passlib.hash import bcrypt
   from app.models.admin import AdminUser
   import uuid
   
   async def seed_admin_user(db: AsyncSession):
       """创建默认 super_admin 用户（如不存在）"""
       result = await db.execute(select(AdminUser).where(AdminUser.username == "admin"))
       if result.scalar_one_or_none():
           return  # 已存在，跳过
      
       admin = AdminUser(
           user_id=str(uuid.uuid4()),
           username="admin",
           password_hash=bcrypt.hash("admin123"),  # 默认密码，首次登录应修改
           role="super_admin",
           status="active"
       )
       db.add(admin)
       await db.commit()
   ```

2. `app/main.py` 启动时调用：
   ```python
   @app.on_event("startup")
   async def startup():
       from app.seed import seed_admin_user
       from app.database import async_session
       async with async_session() as db:
           await seed_admin_user(db)
   ```

**测试**：
- `tests/test_seed.py`：
  - 启动后 `admin` 用户存在，role=super_admin。
  - 重复调用 `seed_admin_user` 不创建第二个 admin。
  - 用默认密码 `admin123` 可登录。

**DoD**：
- 服务启动后自动创建 `admin/admin123` 超级管理员。
- 重复启动不重复创建。
- `uv run pytest tests/test_seed.py -q` 通过。

---

### Phase 1 验收

| 检查项 | 验证方式 |
|--------|---------|
| FastAPI 启动无错 | `uvicorn app.main:app --port 50080` |
| DB 迁移成功（30 表） | `alembic upgrade head` + 查询表清单 |
| JWT 登录可用 | `curl -X POST http://127.0.0.1:50080/api/auth/login -d '{"username":"admin","password":"admin123"}'` |
| RBAC 中间件生效 | 不同角色访问受限端点返回 403 |
| 初始数据创建 | admin 用户自动创建 |
| 测试通过 | `uv run pytest tests/ -q` 全绿 |

---

## Phase 2：Admin Backend REST API

**目标**：实现设计方案 §5.4 定义的 ~74 个 REST 端点。按功能域分 7 个任务组。

### P2-T1：认证域完善 + 公司管理端点

**文件**：
- `admin-backend/app/api/auth.py`（补充 password 修改端点）
- `admin-backend/app/api/companies.py`（新建）
- `admin-backend/app/schemas/company.py`
- `admin-backend/app/models/organization.py`（补充 Company CRUD service）
- `admin-backend/tests/test_companies_api.py`

**依赖**：P1-T3

**实现要点**：

1. 补充 auth 端点：
   - `PUT /api/auth/password` — 修改密码（需验证旧密码）

2. 公司管理端点（公司/部门/员工为业务数据，Admin 仅提供只读查询用于审计；写入由 Sidecar RPC 完成）：
   ```
   GET    /api/companies                — 公司列表（只读镜像）
   GET    /api/companies/{company_id}   — 公司详情
   ```

3. 部门管理端点（只读）：
   ```
   GET    /api/companies/{company_id}/departments           — 部门列表
   GET    /api/companies/{company_id}/departments/{dept_id} — 部门详情
   ```

4. 员工管理端点（只读）：
   ```
   GET    /api/companies/{company_id}/employees             — 员工列表
   GET    /api/companies/{company_id}/employees/{emp_id}    — 员工详情
   ```

**测试**：
- `tests/test_companies_api.py`：每个端点的正常/异常路径测试。
- 检查公司状态机转换正确性。
- 检查 RBAC 权限控制。

**DoD**：
- 公司/部门/员工 CRUD + 状态机端点全部可用。
- `uv run pytest tests/test_companies_api.py -q` 通过。

---

### P2-T2：能力管理域（Capabilities / Skills / Prompts）

**文件**：
- `admin-backend/app/api/capabilities.py`
- `admin-backend/app/api/skills.py`
- `admin-backend/app/api/prompts.py`
- `admin-backend/app/schemas/capability.py`
- `admin-backend/app/services/capability_service.py`
- `admin-backend/tests/test_capabilities_api.py`

**依赖**：P1-T2, P1-T4

**实现要点**（设计方案 §5.4 能力管理域 30 端点 + 技能 11 端点 + Prompt 11 端点）：

1. 能力端点（11 个）：
   ```
   GET    /api/capabilities                              — 列表（分页+过滤 company_id/status）
   POST   /api/capabilities                              — 创建
   GET    /api/capabilities/{id}                         — 详情
   PUT    /api/capabilities/{id}                         — 更新
   POST   /api/capabilities/{id}/submit-review           — 提交审核
   POST   /api/capabilities/{id}/publish                 — 发布
   POST   /api/capabilities/{id}/deprecate               — 弃用
   POST   /api/capabilities/{id}/archive                 — 归档
   GET    /api/capabilities/{id}/versions                — 版本列表
   POST   /api/capabilities/{id}/versions                — 新建版本
   GET    /api/capabilities/{id}/bindings                — 技能绑定
   ```

2. 技能端点（11 个，对称）：
   ```
   GET    /api/skills
   POST   /api/skills
   GET    /api/skills/{id}
   PUT    /api/skills/{id}
   POST   /api/skills/{id}/save-draft
   GET    /api/skills/{id}/versions
   POST   /api/skills/{id}/versions
   POST   /api/skills/{id}/submit-review
   POST   /api/skills/{id}/publish
   POST   /api/skills/{id}/deprecate
   POST   /api/skills/{id}/archive
   ```

3. Prompt 端点（11 个，对称）：
   ```
   GET    /api/prompts
   POST   /api/prompts
   GET    /api/prompts/{id}
   PUT    /api/prompts/{id}
   POST   /api/prompts/{id}/save-draft
   GET    /api/prompts/{id}/versions
   POST   /api/prompts/{id}/versions
   POST   /api/prompts/{id}/submit-review
   POST   /api/prompts/{id}/publish
   POST   /api/prompts/{id}/deprecate
   POST   /api/prompts/{id}/archive
   ```

4. 模板端点（6 个）：
   ```
   GET    /api/templates
   POST   /api/templates
   GET    /api/templates/{id}
   PUT    /api/templates/{id}
   POST   /api/templates/{id}/activate
   POST   /api/templates/{id}/archive
   ```

5. 状态机校验：`draft → review → published → deprecated → archived`，非法跳转返回 400。

**测试**：
- `tests/test_capabilities_api.py`：
  - 创建→提交审核→发布→弃用→归档 全链路。
  - 非法状态跳转（如 draft→published 直接跳）返回 400。
  - 版本管理：创建版本后 version 递增。
  - 跨公司过滤：company_id 参数生效。

**DoD**：
- 30 + 11 + 11 + 6 = 58 个端点全部可用。
- 状态机校验正确。
- `uv run pytest tests/test_capabilities_api.py -q` 通过。

---

### P2-T3：知识管理域

**文件**：
- `admin-backend/app/api/knowledge.py`
- `admin-backend/app/schemas/knowledge.py`
- `admin-backend/tests/test_knowledge_api.py`

**依赖**：P1-T2, P1-T4

**实现要点**（设计方案 §5.4 知识管理域 10 端点）：
```
GET    /api/knowledge/documents                — 文档列表（ACL 过滤）
GET    /api/knowledge/documents/{id}           — 文档详情
POST   /api/knowledge/documents                — 创建文档
PUT    /api/knowledge/documents/{id}           — 更新文档
DELETE /api/knowledge/documents/{id}           — 删除文档
POST   /api/knowledge/documents/{id}/confirm   — 确认知识
POST   /api/knowledge/documents/{id}/reject    — 拒绝知识
POST   /api/knowledge/reindex                  — 重建索引
POST   /api/knowledge/sources/{id}/delete      — 删除来源
POST   /api/knowledge/ingest/{job_id}/retry    — 摄取重试
```

**测试**：CRUD + 确认/拒绝 + 来源删除 + 跨公司隔离。

**DoD**：10 个端点全部可用，`uv run pytest tests/test_knowledge_api.py -q` 通过。

---

### P2-T4：Provider 与 Backend 管理域

**文件**：
- `admin-backend/app/api/providers.py`
- `admin-backend/app/api/backends.py`
- `admin-backend/app/schemas/provider.py`
- `admin-backend/app/schemas/backend.py`
- `admin-backend/tests/test_providers_api.py`
- `admin-backend/tests/test_backends_api.py`

**依赖**：P1-T2, P1-T4

**实现要点**：

1. Provider 端点（10 个，设计方案 §5.4）：
   ```
   GET    /api/providers
   POST   /api/providers
   GET    /api/providers/{id}/models
   POST   /api/providers/{id}/fetch-models
   PUT    /api/providers/{id}/credentials
   DELETE /api/providers/{id}/credentials
   POST   /api/providers/{id}/probe
   PUT    /api/providers/{id}/pricing
   PUT    /api/providers/{id}/tier-mapping
   ```

2. Backend 端点（8 个，设计方案 §5.4）：
   ```
   GET    /api/backends
   POST   /api/backends
   PUT    /api/backends/{id}
   POST   /api/backends/{id}/enable
   POST   /api/backends/{id}/drain
   POST   /api/backends/{id}/archive
   POST   /api/backends/{id}/probe
   POST   /api/backends/{id}/set-default
   ```

3. Backend 状态机：`disabled → enabled → draining → disabled`，`disabled → archived`。

**测试**：Provider CRUD + 凭证设置/撤销 + Backend 状态机 + 默认 Backend CAS。

**DoD**：18 个端点全部可用，`uv run pytest tests/test_providers_api.py tests/test_backends_api.py -q` 通过。

---

### P2-T5：治理域（审批 + 预算）

**文件**：
- `admin-backend/app/api/governance.py`
- `admin-backend/app/schemas/governance.py`
- `admin-backend/tests/test_governance_api.py`

**依赖**：P1-T2, P1-T4

**实现要点**（设计方案 §5.4 治理域 10 端点）：
```
GET    /api/governance/approvals               — 审批列表
GET    /api/governance/approvals/{id}          — 审批详情
POST   /api/governance/approvals/{id}/resolve  — 决议
POST   /api/governance/approvals               — 发起审批
GET    /api/governance/budget-policy           — 预算策略
PUT    /api/governance/budget-policy           — 更新预算策略
GET    /api/governance/approval-types          — 审批类型列表
POST   /api/governance/approval-types          — 创建审批类型
PUT    /api/governance/approval-types/{id}     — 更新审批类型
GET    /api/governance/budget/{task_id}        — 任务预算
```

**测试**：审批列表/详情/决议 + 预算策略 CAS + 审批类型 CRUD。

**DoD**：10 个端点全部可用，`uv run pytest tests/test_governance_api.py -q` 通过。

---

### P2-T6：审计域

**文件**：
- `admin-backend/app/api/audit.py`
- `admin-backend/tests/test_audit_api.py`

**依赖**：P1-T2, P1-T4

**实现要点**（设计方案 §5.4 审计域 2 端点）：
```
GET    /api/audit/logs                — 审计日志查询（分页+过滤）
GET    /api/audit/interventions       — 人工干预列表
```

**测试**：审计日志分页 + 干预列表过滤。

**DoD**：2 个端点可用，`uv run pytest tests/test_audit_api.py -q` 通过。

---

### P2-T7：配置同步 API

**文件**：
- `admin-backend/app/api/sync.py`
- `admin-backend/app/schemas/sync.py`
- `admin-backend/tests/test_sync_api.py`

**依赖**：P1-T2, P2-T1 ~ P2-T6（需要所有配置表有数据）

**实现要点**（设计方案 §5.4 同步域 1 端点）：

```
GET /api/sync/config?company_id={company_id}&since={timestamp}
```

响应结构：
```json
{
  "timestamp": "2026-07-21T10:00:00Z",
  "capabilities": [...],
  "capability_versions": [...],
  "skills": [...],
  "skill_versions": [...],
  "skill_bindings": [...],
  "prompt_assets": [...],
  "prompt_asset_versions": [...],
  "employee_templates": [...],
  "knowledge_policies": [...],
  "security_policies": [...],
  "workspace_policies": [...],
  "notification_policies": [...],
  "budget_policies": [...],
  "backends": [...],
  "company_backend_defaults": [...],
  "providers": [...],
  "provider_pricing_versions": [...],
  "provider_tier_mappings": [...]
}
```

**注意**：Company / Department / Employee / Grant 不在此同步列表中。这些是业务数据，由 Sidecar（Desktop RPC）写入，是权威源。Admin DB 中的对应表为只读镜像，供审计查询。

实现逻辑：
1. 按 `company_id` 过滤所有配置表。
2. 若提供 `since` 参数，只返回 `updated_at > since` 的记录。
3. 无认证（内部调用，仅 localhost 可达）。
4. 不返回 companies/departments/employees/access_grants（业务数据不在同步范围）。

**测试**：
- `tests/test_sync_api.py`：
  - 创建公司+员工+能力后，调用 `/api/sync/config?company_id=xxx` 返回完整配置。
  - 传 `since` 参数只返回增量变更。
  - 不存在的 company_id 返回空配置。
  - 无 company_id 参数返回 400。

**DoD**：
- 同步端点可用，返回完整的配置数据 JSON。
- 增量拉取正确。
- `uv run pytest tests/test_sync_api.py -q` 通过。

---

### Phase 2 验收

| 检查项 | 验证方式 |
|--------|---------|
| ~74 端点全部注册 | `curl http://127.0.0.1:50080/openapi.json | jq '.paths | keys | length'` |
| 每个域的 CRUD 通过 | `uv run pytest tests/ -q` 全绿 |
| RBAC 控制生效 | 不同角色访问受限端点 |
| 同步端点可用 | `curl http://127.0.0.1:50080/api/sync/config?company_id=test` |

---

## Phase 3：Admin Frontend

**目标**：搭建 @umijs/max + Ant Design Pro 前端项目，实现 11 个管理页面。

### P3-T1：项目初始化 + Layout

**文件**：
- `apps/admin/`（新建目录）
- `apps/admin/package.json`
- `apps/admin/.umirc.ts`
- `apps/admin/src/layouts/index.tsx`（ProLayout）
- `apps/admin/src/pages/login/index.tsx`
- `apps/admin/src/services/api.ts`（axios 封装）
- `apps/admin/src/app.tsx`（运行时配置）

**依赖**：P2-T1（需要登录端点）

**实现要点**：
1. 使用 `npx create-umi` 初始化 @umijs/max 项目。
2. 配置 Ant Design Pro Layout（侧边栏菜单 + 顶栏 + 内容区）。
3. 实现登录页面（`/login`），调用 `/api/auth/login`。
4. 配置 axios 拦截器：自动附加 JWT token、401 时跳转登录。
5. 侧边栏菜单结构（11 个管理页面 + 登录）：
   ```
   能力管理
   ├── 能力列表
   ├── 技能列表
   ├── Prompt 资产
   ├── 员工模板
   └── 能力引擎
   知识管理
   ├── 知识库
   └── 知识治理
   基础设施
   └── Provider 与 Backend
   治理
   └── 治理与审批
   审计
   ├── 审计日志
   └── 人工干预
   ```

**测试**：无自动化测试（脚手架任务），手动验证登录+Layout 渲染。

**DoD**：
- `cd apps/admin && npm install && npm run dev` 启动成功。
- 浏览器访问 `http://localhost:8000` 跳转登录页。
- 用 `admin/admin123` 登录后看到 Layout + 侧边栏菜单。

---

### P3-T2：能力管理 5 页面

**文件**：
- `apps/admin/src/pages/capabilities/index.tsx`（CapabilityList）
- `apps/admin/src/pages/capabilities/[id].tsx`（CapabilityDetail）
- `apps/admin/src/pages/skills/index.tsx`（SkillList）
- `apps/admin/src/pages/prompts/index.tsx`（PromptList）
- `apps/admin/src/pages/templates/index.tsx`（TemplateList）
- `apps/admin/src/pages/capengine/index.tsx`（CapabilityEnginePage）

**依赖**：P2-T2, P3-T1

**实现要点**：
- 每个页面使用 Ant Design Pro 的 `ProTable` 组件。
- 支持分页、过滤、搜索。
- CRUD 操作使用 Modal/Drawer。
- 状态机按钮（提交审核/发布/弃用/归档）根据当前状态动态显示。

**测试**：无前端自动化测试（按项目现有惯例），手动验证 CRUD。

**DoD**：
- 5 个页面可访问，CRUD 操作正常。
- 状态机按钮根据状态正确显示/隐藏。

---

### P3-T3：知识管理 2 页面

**文件**：
- `apps/admin/src/pages/knowledge/index.tsx`（KnowledgeList）
- `apps/admin/src/pages/knowledge/governance.tsx`（KnowledgeGovernancePage）

**依赖**：P2-T3, P3-T1

**DoD**：2 个页面可访问，文档 CRUD + 确认/拒绝操作正常。

---

### P3-T4：基础设施 + 治理 + 审计 4 页面

**文件**：
- `apps/admin/src/pages/providers/index.tsx`（ProviderBackendPage）
- `apps/admin/src/pages/governance/index.tsx`（GovernancePage）
- `apps/admin/src/pages/audit/index.tsx`（AuditPage）
- `apps/admin/src/pages/audit/interventions.tsx`（InterventionPage）

**依赖**：P2-T4, P2-T5, P2-T6, P3-T1

**DoD**：4 个页面可访问，Provider/Backend CRUD + 审批操作 + 审计查询正常。

---

### P3-T5：前端测试 + 构建验证

**文件**：
- `apps/admin/tests/`（新增测试目录）

**依赖**：P3-T2 ~ P3-T4

**实现要点**：
1. 配置 vitest 或 jest。
2. 编写关键页面的冒烟测试（渲染测试）。
3. 验证 `npm run build` 构建成功。

**测试**：
- 每个页面的渲染测试（至少 1 个）。
- `npm run build` 无报错。

**DoD**：
- `cd apps/admin && npm run test` 通过。
- `cd apps/admin && npm run build` 成功。

---

### Phase 3 验收

| 检查项 | 验证方式 |
|--------|---------|
| 11 页面全部可访问 | 浏览器手动验证 |
| CRUD 操作正常 | 每个页面至少完成一次创建→编辑→删除 |
| 构建成功 | `npm run build` |
| 测试通过 | `npm run test` |

---

## Phase 4：Sidecar 改造

**目标**：精简 Sidecar RPC 至 ~55 个用户侧方法，新增配置同步拉取模块。

### P4-T1：RPC 精简 — 移除管理侧方法

**文件**：
- `sidecar/acos/app.py`（修改注册逻辑）
- `sidecar/acos/rpc/methods_capability.py`（精简）
- `sidecar/acos/rpc/methods_provider.py`（精简）
- `sidecar/acos/rpc/methods_backend.py`（移除注册）
- `sidecar/acos/rpc/methods_settings.py`（移除注册）
- `sidecar/acos/rpc/methods_gov.py`（移除注册）
- `sidecar/acos/rpc/methods_approval.py`（移除注册）
- `sidecar/acos/rpc/methods_audit.py`（移除注册）
- `sidecar/acos/rpc/methods_knowledge.py`（移除注册，3 个方法全部移除）
- `sidecar/acos/rpc/methods_kg.py`（精简）
- `sidecar/acos/rpc/methods_org.py`（精简）
- `sidecar/acos/rpc/methods.py`（移除 EchoMethods 注册）

**依赖**：P2-T7（Admin Backend 同步端点就绪，确保 RPC 精简后配置数据可通过同步拉取）

**实现要点**：

1. `app.py` 修改注册逻辑，注释/移除管理侧方法类：
    ```python
    # 保留的用户侧方法
    OrganizationMethods(DB_PATH).register_to(server)  # 精简后
    CapabilityMethods(DB_PATH).register_to(server)    # 仅 engine.resolve
    TaskMethods(DB_PATH).register_to(server)          # 保留
    SessionMethods(DB_PATH).register_to(server)       # 保留
    WorkflowMethods(DB_PATH).register_to(server)      # 保留
    KgMethods(DB_PATH).register_to(server)            # 仅 search + document.list/get + citation.get
    SysMethods(DB_PATH).register_to(server)           # 保留
    
    # 移除的管理侧方法（注释或条件注册）
    # BackendMethods(DB_PATH).register_to(server)     — 移除
    # SettingsMethods(DB_PATH).register_to(server)    — 移除
    # GovMethods(DB_PATH).register_to(server)         — 移除
    # ApprovalMethods(DB_PATH).register_to(server)    — 移除
    # AuditMethods(DB_PATH).register_to(server)       — 移除
    # KnowledgeMethods(DB_PATH).register_to(server)   — 移除（knowledge.update/delete/search）
    # EchoMethods(DB_PATH).register_to(server)        — 移除
    ```

2. `methods_capability.py` 精简：
   - 保留：`cap.engine.resolve`（运行时装配，被 SessionMethods 调用）
   - 保留：`cap.snapshot.build`（运行时快照构建）
   - 移除：`cap.skill.*` CRUD（11 个）
   - 移除：`cap.prompt.*` CRUD（11 个）
   - 移除：`cap.capability.*` CRUD（12 个）
   - 移除：`cap.metrics.get`

3. `methods_provider.py` 精简：
   - 保留：`provider.runtime.start` / `provider.runtime.send` / `provider.runtime.cancel`（运行时调用）
   - 保留：`provider.list` / `provider.model.list`（运行时查询可用 Provider/Model）
   - 移除：`provider.create` / `provider.agent.list` / `provider.models.fetch` / `provider.pricingPolicy.update` / `provider.budgetFreeze.clear` / `provider.tierMapping.update` / `provider.probe` / `provider.credential.*`

4. `methods_org.py` — 全部保留（公司/部门/员工/授权是业务数据，Sidecar 为权威源，不精简）：
   - 保留所有 org.* 方法（包含查询和写入，共 40 个方法）
   - 仅移除：`org.template.create` / `org.template.update` / `org.template.activate` / `org.template.archive`（模板是配置数据，移至管理侧）
   - 注意：`task.create` 在此文件和 methods_task.py 中重复注册，P4-T4 清理时去重保留一份

5. `methods_knowledge.py` — 完全移除注册（3 个方法全部移除）：
   - 移除：`knowledge.update` / `knowledge.delete` / `knowledge.search`

6. `methods_kg.py` 精简：
   - 保留：`kg.search`（运行时检索）
   - 保留：`kg.document.list` / `kg.document.get`（运行时查询）
   - 保留：`kg.citation.get`（运行时引用）
   - 移除：`kg.source.delete` / `kg.knowledge.confirm` / `kg.knowledge.reject` / `kg.ingest.retry` / `kg.reindex`

7. `methods_approval.py` — 完全移除注册（4 个方法全部移除）：
   - 移除：`approval.list` / `approval.get` / `approval.resolve` / `approval.request`

8. `methods.py`（EchoMethods）：完全移除注册。

**测试**：
- `sidecar/tests/test_rpc_slímmed.py`（新建）：
  - 验证保留的 ~55 个方法全部可调用。
  - 验证移除的方法调用返回 method not found。
  - `sys.health` 仍正常返回。
  - 运行现有测试套件确保保留方法无回归：`cd sidecar && uv run pytest tests/ -q`。

**DoD**：
- Sidecar 启动后注册 ~55 个方法（可通过 `sys.health` 的 methods 列表验证）。
- 移除的方法返回 method not found。
- 保留方法的现有测试全部通过。
- `uv run pytest tests/ -q` 全绿（可能需要调整部分测试以适配精简后的 RPC）。

---

### P4-T2：配置同步拉取模块

**文件**：
- `sidecar/acos/sync/__init__.py`（新建）
- `sidecar/acos/sync/puller.py`（ConfigPuller）
- `sidecar/acos/sync/models.py`（同步数据模型）
- `sidecar/tests/sync/__init__.py`
- `sidecar/tests/sync/test_puller.py`

**依赖**：P2-T7（需要 Admin Backend 同步端点就绪）

**实现要点**：

1. `sidecar/acos/sync/puller.py`：
   ```python
   import httpx
   import json
   import logging
   from datetime import datetime, timezone
   
   logger = logging.getLogger(__name__)
   
   class ConfigPuller:
       """从 Admin Backend 拉取配置数据，写入本地 Sidecar DB"""
       
       def __init__(self, admin_api_base: str, db_path: str):
           self.admin_api_base = admin_api_base.rstrip("/")
           self.db_path = db_path
       
       async def pull_full_config(self, company_id: str) -> dict:
           """全量拉取（启动时）"""
           url = f"{self.admin_api_base}/api/sync/config"
           params = {"company_id": company_id}
           
           async with httpx.AsyncClient() as client:
               resp = await client.get(url, params=params)
               if resp.status_code != 200:
                   logger.error(f"Sync failed: {resp.status_code}")
                   return {}
               data = resp.json()
           
           await self._upsert_config(company_id, data)
           return data
       
       async def pull_incremental(self, company_id: str, since: str) -> dict:
           """增量拉取（定期）"""
           url = f"{self.admin_api_base}/api/sync/config"
           params = {"company_id": company_id, "since": since}
           
           async with httpx.AsyncClient() as client:
               resp = await client.get(url, params=params)
               if resp.status_code != 200:
                   logger.error(f"Incremental sync failed: {resp.status_code}")
                   return {}
               data = resp.json()
           
           await self._upsert_config(company_id, data)
           return data
       
       async def _upsert_config(self, company_id: str, data: dict):
           """将拉取的配置数据写入本地 DB（INSERT OR REPLACE）"""
           import aiosqlite
           
           async with aiosqlite.connect(self.db_path) as db:
               # 同步能力/技能/Prompt/模板等配置表（不包含业务数据表）
               # ... 各表 upsert 逻辑
               
               await db.commit()
               logger.info(f"Config synced for company {company_id}: {list(data.keys())}")
   ```

2. `sidecar/acos/app.py` 集成同步：
   ```python
   # 在 run() 函数中，RPC server 启动后触发同步
   async def trigger_initial_sync():
       """启动后全量同步"""
       puller = ConfigPuller(
           admin_api_base="http://127.0.0.1:50080",
           db_path=DB_PATH
       )
       # 获取当前公司 ID（从 local_owner 或配置中读取）
       company_id = await get_current_company_id()
       if company_id:
           await puller.pull_full_config(company_id)
   ```

**测试**：
- `sidecar/tests/sync/test_puller.py`：
  - mock Admin Backend 响应 → 验证本地 DB 被正确写入。
  - 网络失败时保留上次同步数据。
  - 增量拉取只更新变更数据。

**DoD**：
- ConfigPuller 可从 Admin Backend 拉取配置并写入本地 DB。
- 网络失败不影响现有数据。
- `uv run pytest tests/sync/test_puller.py -q` 通过。

---

### P4-T3：手动同步触发 RPC

**文件**：
- `sidecar/acos/rpc/methods_sys.py`（新增 `sys.sync.trigger`）
- `sidecar/tests/test_sync_trigger.py`

**依赖**：P4-T2

**实现要点**：
```python
# methods_sys.py 新增
async def _sync_trigger(self, params: dict) -> dict:
    """手动触发配置同步"""
    company_id = params.get("company_id")
    if not company_id:
        return {"error": {"code": "SYS-VALIDATION", "message": "company_id required"}}
    
    puller = ConfigPuller(
        admin_api_base=self.admin_api_base,
        db_path=self.db_path
    )
    result = await puller.pull_incremental(company_id, since=params.get("since"))
    return {"synced": True, "tables": list(result.keys())}
```

注册为 `sys.sync.trigger`。

**测试**：
- 调用 `sys.sync.trigger` → 触发增量同步 → 返回同步结果。
- 缺少 company_id → 返回验证错误。

**DoD**：
- `sys.sync.trigger` RPC 可用。
- `uv run pytest tests/test_sync_trigger.py -q` 通过。

---

### P4-T4：清理与回归验证

**文件**：
- 同步更新 `sidecar/acos/rpc/server.py`（如有必要）
- 清理未使用的 import

**依赖**：P4-T1, P4-T2, P4-T3

**实现要点**：
1. 运行完整测试套件：`cd sidecar && uv run pytest tests/ -q`。
2. 修复因 RPC 精简导致的测试失败（部分测试可能引用已移除的方法）。
3. 清理未使用的 import。
4. 验证 Sidecar 启动后 RPC 方法数量正确。

**测试**：完整测试套件通过。

**DoD**：
- `uv run pytest tests/ -q` 全绿。
- RPC 方法数量 ~55（含 3 个 sys 内置）。

---

### Phase 4 验收

| 检查项 | 验证方式 |
|--------|---------|
| RPC 精简完成 | 启动 Sidecar，验证方法数量 |
| 同步模块可用 | 调用 `sys.sync.trigger` 验证 |
| 测试通过 | `uv run pytest tests/ -q` 全绿 |
| 保留方法无回归 | 现有测试套件通过 |

---

## Phase 5：Desktop App 瘦身

**目标**：桌面端页面从 20 精简至 9，引入 React Router，重构 Layout，精简 Tauri 依赖。

### P5-T1：移除管理侧页面组件

**文件**：
- 删除以下文件（或移至 `archived/` 目录）：
  - `apps/desktop/src/components/knowledge/KnowledgeList.tsx`
  - `apps/desktop/src/components/knowledge/KnowledgeGovernancePage.tsx`
  - `apps/desktop/src/components/capability/CapabilityList.tsx`
  - `apps/desktop/src/components/capability/CapabilityEnginePage.tsx`
  - `apps/desktop/src/components/capability/SkillList.tsx`
  - `apps/desktop/src/components/capability/PromptList.tsx`
  - `apps/desktop/src/components/capability/TemplateList.tsx`
  - `apps/desktop/src/components/provider/ProviderBackendPage.tsx`
  - `apps/desktop/src/components/grant/GrantPage.tsx`
  - `apps/desktop/src/components/governance/GovernancePage.tsx`
  - `apps/desktop/src/components/audit/AuditPage.tsx`
  - `apps/desktop/src/components/intervention/InterventionPage.tsx`
  - `apps/desktop/src/components/permission/PermissionPage.tsx`
  - 对应的 `.test.tsx` 文件也一并移除

**依赖**：无（可与 P4 并行）

**实现要点**：
1. 将管理侧组件移至 `apps/desktop/src/archived/` 目录（不直接删除，保留参考）。
2. 移除对应的 import 引用。

**测试**：`cd apps/desktop && npx tsc --noEmit` 无报错（移除引用后类型检查通过）。

**DoD**：
- 管理侧组件从 `components/` 移至 `archived/`。
- TypeScript 编译无报错。

---

### P5-T2：引入 React Router

**文件**：
- `apps/desktop/package.json`（新增 `react-router-dom` 依赖）
- `apps/desktop/src/router.tsx`（新建）
- `apps/desktop/src/main.tsx`（修改，接入 RouterProvider）
- `apps/desktop/src/components/layout/Layout.tsx`（修改，使用 `<Outlet />`）

**依赖**：P5-T1

**实现要点**：
1. 安装：`cd apps/desktop && npm install react-router-dom`
2. 创建路由配置：
   ```tsx
   // src/router.tsx
   import { createBrowserRouter, Navigate } from 'react-router-dom';
   import Layout from './components/layout/Layout';
   import SessionPage from './components/session/SessionPage';
   import CompanyList from './components/company/CompanyList';
   import CompanyDetail from './components/company/CompanyDetail';
   import EmployeeList from './components/employee/EmployeeList';
   import EmployeeDetail from './components/employee/EmployeeDetail';
   import TaskBoard from './components/task/TaskBoard';
   import TaskAdvancedPage from './components/task/TaskAdvancedPage';
   import DashboardPage from './components/dashboard/DashboardPage';
   import SettingsPage from './components/settings/SettingsPage';
   
   const router = createBrowserRouter([
     {
       path: '/',
       element: <Layout />,
       children: [
         { index: true, element: <Navigate to="/session" replace /> },
         { path: 'companies', element: <CompanyList /> },
         { path: 'companies/:companyId', element: <CompanyDetail /> },
         { path: 'employees', element: <EmployeeList /> },
         { path: 'employees/:employeeId', element: <EmployeeDetail /> },
         { path: 'session', element: <SessionPage /> },
         { path: 'tasks', element: <TaskBoard /> },
         { path: 'tasks/advanced', element: <TaskAdvancedPage /> },
         { path: 'dashboard', element: <DashboardPage /> },
         { path: 'settings', element: <SettingsPage /> },
       ],
     },
   ]);
   
   export default router;
   ```
3. `main.tsx` 修改：
   ```tsx
   import { RouterProvider } from 'react-router-dom';
   import router from './router';
   
   function App() {
     return <RouterProvider router={router} />;
   }
   ```
4. `Layout.tsx` 修改：移除 switch 逻辑，使用 `<Outlet />` 渲染子路由。

**测试**：`npx vitest run` + `npx tsc --noEmit`。

**DoD**：
- 浏览器地址栏显示 `/session`（默认首页）。
- 点击侧边栏菜单项 URL 正确变化。
- 浏览器前进/后退按钮正常工作。
- TypeScript 编译通过。

---

### P5-T3：重构 Sidebar + 轻量 Dashboard

**文件**：
- `apps/desktop/src/components/layout/Sidebar.tsx`（重构）
- `apps/desktop/src/components/dashboard/DashboardPage.tsx`（精简）
- `apps/desktop/src/types/index.ts`（精简 PageKey）

**依赖**：P5-T2

**实现要点**：

1. `types/index.ts` — 精简 PageKey：
   ```typescript
   export type PageKey =
     | 'companies'
     | 'employees'
     | 'session'
     | 'tasks'
     | 'taskAdvanced'
     | 'dashboard'
     | 'settings';
   ```

2. `Sidebar.tsx` — 重构为 7 个菜单项：
   ```tsx
   import { useNavigate, useLocation } from 'react-router-dom';
   
   const menuItems = [
     { key: '/companies', label: '公司管理', icon: Building2 },
     { key: '/employees', label: '员工管理', icon: Users },
     { key: '/session', label: '会话', icon: MessageSquare },
     { key: '/tasks', label: '任务看板', icon: ClipboardList },
     { key: '/tasks/advanced', label: '任务高级', icon: GitBranch },
     { key: '/dashboard', label: '概览', icon: LayoutDashboard },
     { key: '/settings', label: '设置', icon: Settings },
   ];
   ```
   - 默认高亮 `/session`。
   - 使用 `useLocation().pathname` 匹配当前路由。

3. `DashboardPage.tsx` — 精简为轻量版：
   - 移除：公司数、员工数、Backend 数、Provider 数、干预列表。
   - 保留：进行中会话数（`session.list`）、进行中任务数（`task.list`）、已完成任务数（`task.list`）。
   - 最近活动：最近 5 条会话/任务。

**测试**：`npx vitest run` + `npx tsc --noEmit`。

**DoD**：
- Sidebar 显示 7 个菜单项。
- 默认高亮"会话"。
- Dashboard 仅显示会话+任务统计。
- 测试通过。

---

### P5-T4：精简 Tauri 依赖

**文件**：
- `apps/desktop/src-tauri/Cargo.toml`
- `apps/desktop/src-tauri/src/lib.rs`（移除 libc/lazy_static 引用）
- `apps/desktop/package.json`（移除 @tauri-apps/plugin-shell）

**依赖**：P5-T2

**实现要点**：

1. `Cargo.toml`：
   ```toml
   [dependencies]
   tauri = "2"
   # tauri-plugin-shell = "2"  # 移除
   serde = { version = "1", features = ["derive"] }
   serde_json = "1"
   tokio = { version = "1", features = ["rt-multi-thread", "net", "io-util", "macros"] }  # 精简
   # libc = "0.2"  # 移除
   # lazy_static = "1"  # 移除
   ```

2. `lib.rs`：
   - 将 `libc::kill(pid, libc::SIGKILL)` 替换为 `std::process::Command::new("kill").arg("-9").arg(pid.to_string()).spawn()`。
   - 将 `lazy_static! { static ref SIDECAR_CHILD: ... }` 替换为 `std::sync::OnceLock`。
   - 移除 `tauri_plugin_shell` 相关代码。

3. `package.json`：
   - 移除 `@tauri-apps/plugin-shell` 依赖。
   - 移除 `@monaco-editor/react`（确认未使用后）。

**测试**：`cd apps/desktop && npx tauri build` 构建成功。

**DoD**：
- Tauri 构建成功，产物大小减小。
- Sidecar 启动/停止功能正常（使用新实现）。

---

### P5-T5：完整回归验证

**文件**：无新文件

**依赖**：P5-T1 ~ P5-T4

**实现要点**：
1. 运行前端测试：`cd apps/desktop && npx vitest run`。
2. TypeScript 检查：`npx tsc --noEmit`。
3. Tauri 构建：`npx tauri build`。
4. 安装验证：安装到 `/Applications`，启动，验证 9 个页面可用。
5. 核心链路验证：
   - 创建公司 → 激活 → 创建部门 → 雇佣员工
   - 发起会话 → 发送消息 → 查看转录
   - 创建任务 → 启动 → 完成

**测试**：完整测试套件通过 + 手动链路验证。

**DoD**：
- `npx vitest run` 全绿。
- `npx tsc --noEmit` 无报错。
- `npx tauri build` 成功。
- 安装后 9 个页面可用。

---

### Phase 5 验收

| 检查项 | 验证方式 |
|--------|---------|
| 页面精简至 9 | 侧边栏菜单 7 项 + 默认跳转 session |
| React Router 工作 | URL 变化 + 前进后退 |
| 轻量 Dashboard | 仅显示会话+任务统计 |
| Tauri 依赖精简 | Cargo.toml 依赖减少 |
| 构建成功 | `npx tauri build` |
| 测试通过 | `npx vitest run` + `npx tsc --noEmit` |

---

## Phase 6：集成测试 + 文档

**目标**：全链路集成验证，文档同步更新。

### P6-T1：全链路集成测试

**文件**：
- `tests/integration/test_full_chain.py`（新建）

**依赖**：P3, P5

**实现要点**：
1. 启动 Admin Backend（端口 50080）。
2. 启动 Sidecar（`/tmp/acos.sock`）。
3. 验证 Sidecar 同步拉取：`sys.sync.trigger` → 确认配置数据写入 Sidecar DB。
4. 模拟 Desktop 操作（通过 RPC）：
   - `org.company.create` → `org.company.activate`
   - `org.department.create`
   - `org.employee.create`
   - `session.sendMessage`
   - `task.create` → `task.start` → `task.complete`
5. 验证 Admin Backend 查询：`GET /api/companies` 返回同步的公司数据。
6. 验证审计日志：`GET /api/audit/logs` 记录了所有操作。

**测试**：集成测试脚本。

**DoD**：
- 全链路测试通过。
- 三端数据一致。

---

### P6-T2：文档同步

**文件**：
- `README.md`（更新）
- `docs/部署文档.md`（更新）
- `docs/用户手册.md`（更新）

**依赖**：P6-T1

**实现要点**：

1. `README.md`：
   - 更新"快速开始"节：新增 Admin Backend 启动命令。
   - 更新"项目结构"节：新增 `admin-backend/` 和 `apps/admin/`。
   - 更新架构图：三端架构。

2. `docs/部署文档.md`：
   - 新增 Admin Backend 部署说明（Docker / 直接运行）。
   - 新增端口分配表。
   - 新增同步配置说明。

3. `docs/用户手册.md`：
   - 更新桌面端操作手册（仅 9 页面）。
   - 新增 Admin Backend 操作手册（11 管理页面）。

**DoD**：
- 三份文档更新完成。
- 文档内容与代码一致。

---

### P6-T3：最终验证

**文件**：无新文件

**依赖**：P6-T1, P6-T2

**实现要点**：
1. 全量测试：`cd sidecar && uv run pytest tests/ -q` + `cd apps/desktop && npx vitest run`。
2. 构建验证：`cd apps/desktop && npx tauri build`。
3. 安装验证：安装到 `/Applications`，启动，验证所有功能。
4. Admin Backend 验证：`cd admin-backend && uv run pytest tests/ -q`。
5. 文档检查：README/部署文档/用户手册内容与代码一致。

**DoD**：
- 所有测试通过。
- 构建成功。
- 安装验证通过。
- 文档一致。

---

### Phase 6 验收

| 检查项 | 验证方式 |
|--------|---------|
| 全链路集成测试通过 | 集成测试脚本 |
| Sidecar 同步正常 | `sys.sync.trigger` 验证 |
| Desktop 9 页面可用 | 安装后手动验证 |
| Admin Backend 11 页面可用 | 浏览器手动验证 |
| 文档同步 | README/部署文档/用户手册更新 |
| 所有测试通过 | 各项目 pytest/vitest |

---

## 附录：任务依赖关系图

```
Phase 1:
  P1-T1 ──► P1-T2 ──► P1-T3 ──► P1-T4
                │
                └────────────► P1-T5

Phase 2:
  P1-T3 ──► P2-T1 (公司管理)
  P1-T2 + P1-T4 ──► P2-T2 (能力管理)
  P1-T2 + P1-T4 ──► P2-T3 (知识管理)
  P1-T2 + P1-T4 ──► P2-T4 (Provider/Backend)
  P1-T2 + P1-T4 ──► P2-T5 (治理)
  P1-T2 + P1-T4 ──► P2-T6 (审计)
  P2-T1~T6 ──► P2-T7 (同步 API)

Phase 3（依赖 Phase 2 完成）:
  P2-T1 + P3-T1 ──► P3-T2 (能力 5 页面)
  P2-T3 + P3-T1 ──► P3-T3 (知识 2 页面)
  P2-T4~T6 + P3-T1 ──► P3-T4 (基础设施+治理+审计 4 页面)
  P3-T2~T4 ──► P3-T5 (测试+构建)

Phase 4（依赖 Phase 2 完成，与 Phase 3 并行）:
  P2-T7 ──► P4-T1 (RPC 精简)
  P2-T7 ──► P4-T2 (同步模块)
  P4-T2 ──► P4-T3 (手动同步 RPC)
  P4-T1 + P4-T2 + P4-T3 ──► P4-T4 (清理)

Phase 5:
  P5-T1 ──► P5-T2 (React Router)
  P5-T2 ──► P5-T3 (Sidebar + Dashboard)
  P5-T2 ──► P5-T4 (Tauri 依赖)
  P5-T1~T4 ──► P5-T5 (回归验证)

Phase 6:
  P3 + P5 ──► P6-T1 (集成测试)
  P6-T1 ──► P6-T2 (文档)
  P6-T1 + P6-T2 ──► P6-T3 (最终验证)
```
