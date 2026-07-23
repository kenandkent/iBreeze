# iBreeze

iBreeze 是一个以"模拟公司运作方式"组织多个 Agent 协作完成任务的桌面应用。

## 架构概览

```
┌──────────────────── iBreeze 桌面客户端 ────────────────────┐
│ React + TypeScript                                          │
│        │ Tauri Command / Event                              │
│ Rust Desktop Core                                           │
│ ├─ Window / Keychain / File Grant                           │
│ └─ Python Sidecar Supervisor                                │
│        │ authenticated local IPC                            │
│ Python Sidecar（单进程）                                    │
│ ├─ Local Application Service                                │
│ ├─ Agent Orchestration Platform                             │
│ └─ Agent Runtime Gateway                                    │
│    ├─ Built-in Agent Runtime                                │
│    ├─ Codex / Claude Code / OpenCode Adapter                │
│    └─ Tool / Permission / Workspace / Checkpoint            │
└─────────────────────────────────────────────────────────────┘
                         │ HTTPS
                         ▼
┌────────────── iBreeze 管理后台服务 ─────────────────────────┐
│ Admin Web                                                   │
│ Backend API                                                 │
│ PostgreSQL + S3-Compatible Object Storage                   │
└─────────────────────────────────────────────────────────────┘
```

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
├─ packages/
│  ├─ contracts/        # JSON Schema 契约
│  ├─ rpc-schema/       # 本地 RPC Schema
│  └─ ui/               # 共享 UI 组件
├─ tests/               # 集成、E2E、安全、性能测试
├─ deploy/              # Docker Compose 部署
├─ scripts/             # 构建和验证脚本
└─ docs/                # 文档
```

## 开发环境

### 前置要求

- Node.js >= 20
- Rust >= 1.75
- Python >= 3.12
- uv (Python 包管理器)
- PostgreSQL 16 (管理后台)

### 快速开始

```bash
# 安装依赖
cd apps/desktop && npm install
cd ../admin-web && npm install
cd ../desktop-core && cargo check
cd ../../sidecar && uv sync
cd ../apps/backend-api && uv sync
cd ../../tests/e2e && npm install

# 运行验证
bash scripts/verify-all.sh
```

## 功能特性

### 桌面客户端
- 多 Agent 协作任务管理
- 对话式交互界面
- 本地知识库管理
- 工作区配置

### 管理后台
- 用户管理（应用用户、管理员）
- 目录管理（Agent、Model、Provider、Skill）
- 安全管理（角色控制、紧急禁用）
- 审计日志

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
