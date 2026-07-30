# iBreeze

iBreeze 是一个以"模拟公司运作方式"组织多个 Agent 协作完成任务的桌面应用。

## 架构概览

```
┌───────────────────────────────────────────────────────────────┐
│ React WebView (Desktop UI, Admin UI)                          │
│ GeneratedRpcClient + TanStack Query + Zustand                 │
└───────────────────────────┬───────────────────────────────────┘
                           │ Tauri Command (JSON-RPC 2.0)
┌──────────────────────────▼───────────────────────────────────┐
│ Rust Trusted Host Kernel                                      │
│ ├─ Duplex UDS Multiplexer (frame/multiplexer/session)         │
│ ├─ Credential HTTP Broker (Keychain → Provider)               │
│ ├─ CONNECT Egress Proxy (per-Run lease + domain policy)       │
│ ├─ Process Supervisor / Seatbelt (sandbox-exec / SBPL)        │
│ ├─ External Write (single-target receipt)                     │
│ └─ IPC Dispatcher (generated method routing)                  │
└───────────────────────────┬───────────────────────────────────┘
                           │ authenticated framed UDS (4B-length + JSON)
┌──────────────────────────▼───────────────────────────────────┐
│ Python Sidecar Domain Kernel                                  │
│ ├─ Application Lifecycle (11-phase startup incl. identity     │
│ │  verification / 9-step shutdown)                            │
│ ├─ Generated RPC Dispatcher / Reverse Client (with            │
│ │  self-connection guard)                                     │
│ ├─ Profile Persistence Kernel                                 │
│ │  ├─ Migration Runner (001_initial.sql)                      │
│ │  ├─ WriteQueue (cap 32) + Unit of Work + Idempotency        │
│ │  └─ ReadPool (8 connections)                                 │
│ ├─ Worker Supervisor (7 workers + heartbeat + backoff +       │
│ │  RuntimeWorker runtime_queue dispatch)                      │
│ ├─ Review/Completion State Machine (Command-driven, opts out  │
│ │  legacy review./completion./rework. handlers)               │
│ ├─ CLI Adapter Protocol (Codex/Claude Code/OpenCode)          │
│ ├─ Built-in Model Runtime (via Credential HTTP Broker,        │
│ │  credential.probe with profile_directory_id)                │
│ └─ Rework Attempt Lifecycle (RequestReworkHandler +           │
│    AdvanceReworkAttemptHandler, optimistic lock)              │
└───────────────────────────┬───────────────────────────────────┘
                           │ single-writer / read pool
┌──────────────────────────▼───────────────────────────────────┐
│ Profile Persistence (SQLite WAL)                              │
│ Domain Event Store / Outbox / CAS / Search Index              │
└───────────────────────────────────────────────────────────────┘

                         signed HTTPS catalog only
Rust Trusted Host Kernel ───────────────────────────────────────►
                         iBreeze Backend API
```

### 信任边界

| 组件 | 可以持有 | 禁止持有 |
|------|---------|---------|
| WebView | Access Token 内存态、非敏感页面数据 | Refresh Token、API Key、CLI 凭据 |
| Rust Core | Keychain 明文的零化对象、代理 Token、进程句柄 | 公司业务状态机、直接修改 SQLite |
| Sidecar | `credential_ref`、目录快照、业务数据、Run 状态 | API Key、Refresh Token、直接公网 socket |
| SQLite | 业务数据、`credential_ref`、非敏感审计 | API Key、代理 Token、CLI 登录 Cookie |

## 技术栈

| 交付物 | 技术基线 |
|---|---|
| 桌面 UI | React 19、TypeScript 5.7、Vite 6、TanStack Query 5、Zustand 5 |
| 桌面壳 | Tauri 2、Rust 2021、Tokio 1 |
| Sidecar | Python 3.12、asyncio、Pydantic 2、aiosqlite、LanceDB、ONNX Runtime |
| 管理后台 API | Python 3.12、FastAPI、SQLAlchemy 2 Async、asyncpg、Alembic |
| 管理后台 UI | React 19、TypeScript 5.7、Vite 6、Ant Design 5、TanStack Query 5 |
| 管理后台数据 | PostgreSQL 16、S3 API（MinIO） |

## 仓库结构

```
ibreeze/
├─ apps/
│  ├─ desktop/          # 桌面 React UI
│  ├─ desktop-core/     # Tauri/Rust Core
│  ├─ admin-web/        # 管理后台 React UI
│  └─ backend-api/      # 管理后台 FastAPI
├─ sidecar/             # Python Sidecar
├─ deploy/              # Docker Compose + Nginx + Dockerfile
├─ packages/
│  ├─ contracts/        # JSON Schema 契约 + Domain Event Registry
│  ├─ rpc-schema/       # Canonical RPC Registry + 方法 Schema + 错误码
│  └─ ui/               # 共享 UI 组件
├─ tests/               # 集成、E2E、安全、性能测试
├─ scripts/             # 构建和验证脚本
└─ docs/                # 文档
```

## 开发环境

### 前置要求

- Node.js >= 20
- Rust >= 1.75
- Python >= 3.12
- uv (Python 包管理器)
- cargo-nextest (Rust 测试运行器)
- cargo-llvm-cov (Rust 覆盖率)
- PostgreSQL 16 (管理后台)

### 快速开始

```bash
# 1. 启动后台服务（PostgreSQL + MinIO + Backend API）
docker compose up -d
docker exec ibreeze-minio-1 mc alias set local http://localhost:9000 minioadmin minioadmin
docker exec ibreeze-minio-1 mc mb local/ibreeze
cd apps/backend-api
IBREEZE_DATABASE_URL="postgresql+asyncpg://ibreeze:ibreeze_password@localhost:51543/ibreeze" \
  uv run alembic upgrade head
cd ../..

# 2. 安装前端依赖
cd apps/admin-web && npm install && cd ../..
cd apps/desktop && npm install && cd ../..

# 3. 运行验证
bash scripts/verify-all.sh

# 4. 桌面开发模式
cd apps/desktop-core && cargo tauri dev
```

## 功能特性

### 桌面客户端
- 多 Agent 协作任务管理
- 对话式交互界面
- 本地知识库管理（SQLite + LanceDB 向量索引，ACL 预授权）
- 工作区配置
- 自动更新与回滚恢复（SQLite Online Backup 一致性快照 + tar.zst 打包）
- 本地离线认证与 Profile 身份校验（`local_profile` 表 `backend_origin`/`app_user_id`/`masked_identifier`/`device_id` 四字段验证）
- Runtime 队列调度（`runtime.dispatch_ready` 将 ready 项标记为 leased）
- Reverse RPC 自连接防护（阻止 Sidecar 误连自身 UDS socket）
- 凭据探测（`credential.probe` 支持 `profile_directory_id` 指定目录）
- 返工尝试生命周期管理（`RequestReworkHandler` + `AdvanceReworkAttemptHandler`，乐观锁）

### 管理后台
- 用户管理（应用用户、管理员）
- 目录管理（Agent、Model、Provider、Skill）
- 安全管理（角色控制、紧急禁用、紧急发布）
- 审计日志
- 目录发布管理（Draft → Validated → Published）

### 测试覆盖率

| 模块 | Statements | Branches | Functions | Lines |
|---|---|---|---|---|
| Sidecar (Python) | 84.72% | - | - | - |
| Admin Web (TypeScript) | 86.33% | 80% | 84.47% | 87.78% |
| Desktop (TypeScript) | 88.95% | 96.49% | 81.81% | 98.56% |
| Desktop Core (Rust) | 100% | - | 100% | 100% |
| Backend API (Python) | 100% | - | - | - |

所有模块覆盖率阈值已配置为 80%，CI 中强制执行。

### 公开目录查询
- Agent 目录查询
- Provider 目录查询
- 技能目录查询
- 紧急禁用规则查询

## 文档

- [设计方案](docs/设计方案/AI公司桌面应用设计方案.md)
- [实施计划](docs/设计方案/AI公司桌面应用-实施计划.md)
- [部署文档](docs/部署文档.md)
- [用户手册](docs/用户手册.md)
- [API 文档](docs/API文档.md)

## 许可证

MIT
