# iBreeze - 本地 AI 组织运行平台

iBreeze 是一个本地 AI 组织运行平台，将 AI 工作流、数据管理和桌面应用集成到一个统一的系统中。所有数据存储在本地，无需联网。

## 技术栈

| 层 | 技术 |
|----|------|
| 桌面端 | React 19 + TypeScript + Vite 6 + Tailwind CSS 3 |
| Admin 前端 | React 18 + TypeScript + Vite + Ant Design 5 + ProComponents |
| 状态管理 | Zustand 5 |
| 数据获取 | TanStack Query 5 |
| 流程图 | React Flow 12 |
| 桌面壳 | Tauri 2 (Rust) |
| Sidecar | Python 3.12+（uv 管理依赖） |
| Admin Backend | FastAPI + SQLAlchemy + Alembic |
| 存储 | SQLite + LanceDB |

## 快速开始

### 前置条件

- Node.js 18+
- Python 3.12+
- uv（Python 包管理器）
- Rust 工具链（Tauri 编译需要）

### 安装依赖

```bash
# 桌面端
cd apps/desktop
npm install

# Admin 前端
cd apps/admin
npm install

# Sidecar
cd sidecar
uv sync

# Admin Backend
cd admin-backend
uv sync
```

### 启动开发环境

```bash
# 终端 1：Python Sidecar
cd sidecar
uv run python -m acos.app

# 终端 2：桌面端
cd apps/desktop
npm run dev

# 终端 3：Admin Backend（可选，管理功能需要）
cd admin-backend
uv run uvicorn app.main:app --port 50080

# 终端 4：Admin Frontend（可选，管理界面需要）
cd apps/admin
npm run dev
```

### 构建桌面应用

```bash
cd apps/desktop
npm run tauri build
```

## 项目结构

```
ibreeze/
├── apps/desktop/          # Tauri 桌面应用（瘦身后 9 页面）
│   ├── src/
│   │   ├── components/    # React 组件
│   │   │   ├── layout/    # 布局组件 (Sidebar, Header, Layout)
│   │   │   ├── company/   # 公司管理（保留）
│   │   │   ├── employee/  # 员工管理（保留）
│   │   │   ├── task/      # 任务看板 + 任务高级（保留）
│   │   │   ├── session/   # 会话（保留）
│   │   │   ├── dashboard/ # Dashboard 概览（轻量版）
│   │   │   ├── settings/  # 设置（精简版）
│   │   │   └── common/    # 通用组件 (StatusBadge, LoadingSpinner)
│   │   ├── archived/      # 已移除的管理侧组件（13 个）
│   │   ├── stores/        # Zustand 状态管理
│   │   ├── services/      # RPC 客户端
│   │   ├── types/         # TypeScript 类型定义
│   │   └── styles/        # 全局样式 (Tailwind CSS)
│   └── package.json
├── apps/admin/            # Admin Backend 前端（11 管理页面）
│   ├── src/
│   │   ├── pages/         # 管理页面（ProTable）
│   │   ├── layouts/       # ProLayout 侧边栏
│   │   └── services/      # axios 拦截器
│   └── package.json
├── admin-backend/         # Admin Backend API（FastAPI，~90 REST 端点）
│   ├── app/
│   │   ├── api/           # REST 路由（12 个 router）
│   │   ├── models/        # SQLAlchemy 模型（30 张表）
│   │   ├── schemas/       # Pydantic 请求/响应模型
│   │   ├── auth/          # JWT + RBAC
│   │   └── sync/          # 配置同步 API
│   ├── migrations/        # Alembic 迁移
│   └── tests/             # 83 个测试
├── sidecar/               # Python sidecar 服务（瘦身后 ~56 RPC 方法）
│   └── acos/
│       ├── app.py         # RPC 总线接线（8 个活跃 Method class）
│       ├── rpc/           # 各命名空间 handler（methods_*.py）
│       ├── sync/          # ConfigPuller（配置同步拉取）
│       ├── migrations/    # SQLite 幂等迁移
│       ├── backends/      # Backend 服务 / Provider 注册 / 运行时
│       ├── knowledge/     # 知识库 RAG 模块
│       ├── workflows/     # 工作流引擎
│       └── governance/    # 预算与审批治理
├── tests/                 # 全链路集成测试
│   └── integration/       # 端到端契约验证（40 个测试）
├── packages/
│   ├── rpc-schema/        # JSON-RPC 契约定义
│   └── rpc-types/         # 生成的类型定义
└── docs/                  # 文档
    ├── 部署文档.md
    ├── 需求规格说明书.md
    ├── 功能链路测试用例.md
    ├── 设计方案/          # 设计方案、实施计划
    │   ├── iBreeze应用瘦身设计方案.md
    │   └── iBreeze瘦身实施计划.md
    └── 用户手册.md
```

## 架构

系统采用三端架构，详见 [docs/设计方案/iBreeze应用瘦身设计方案.md](docs/设计方案/iBreeze应用瘦身设计方案.md)。

```
Desktop App (Tauri 2, 9 页面) ◄── UDS JSON-RPC ──► Python Sidecar (~56 RPC)
                                                         │
                                                   REST Pull (配置同步)
                                                         │
                                              Admin Backend (FastAPI, ~90 REST 端点)
                                                         │
                                              Admin Frontend (React 18, 11 管理页面)
```

| 端 | 技术栈 | 职责 | 用户 |
|----|--------|------|------|
| Desktop App | React 19 + Tauri 2 | AI 公司交互（公司/员工/会话/任务） | 普通用户 |
| Python Sidecar | aiosqlite + LanceDB | 用户侧 RPC 服务 + 运行时 | — |
| Admin Backend | FastAPI + SQLAlchemy | 管理侧 REST API（能力/知识/Provider/治理/审计） | 管理员 |
| Admin Frontend | React 18 + Ant Design Pro | 管理侧 Web 界面（11 页面 CRUD） | 管理员 |

桌面应用通过 JSON-RPC 2.0 over Unix Domain Socket 与 Python Sidecar 通信。
Sidecar 通过 HTTP REST 从 Admin Backend 拉取配置数据（ConfigPuller）。

### RPC 协议

- 使用 NDJSON framing（每行一个 JSON）
- 消息格式: `{type: "request"|"response", id, method, params, result, error}`
- 核心方法: `sys.health` 返回 `{status: "healthy", components: {rpc: "up"}}`

**瘦身后 Sidecar RPC 方法（~56 个）**：

| 命名空间 | 方法数 | 说明 |
|----------|--------|------|
| `org.*` | ~30 | 公司/部门/员工/授权（业务数据，Sidecar 为权威源） |
| `session.*` | ~6 | 会话生命周期（创建/列表/消息/转录/恢复） |
| `task.*` | ~6 | 任务生命周期（创建/启动/完成/取消/重试/节点） |
| `workflow.*` | ~4 | 工作流引擎（计划/检查点/死信/取消） |
| `kg.*` | ~4 | 知识库检索（搜索/文档列表/详情/引用） |
| `cap.*` | 2 | 能力引擎（运行时解析/快照构建） |
| `provider.*` | ~5 | Provider 运行时（列表/模型/启动/发送/取消） |
| `sys.*` | ~3 | 系统（健康检查/迁移状态/同步触发） |

管理侧方法（能力 CRUD/Skill/Prompt/Provider 管理/Backend 管理/治理/审计/知识写入）已迁移至 Admin Backend REST API。

### 治理与审批 RPC

治理命名空间 `gov.*` 与审批中心 `approval.*` 已迁移至 Admin Backend REST API（`/api/governance/*`）。

### 知识库与 RAG RPC

知识库运行时检索方法保留于 Sidecar（`kg.*`），知识管理（文档 CRUD/确认/拒绝/重索引）已迁移至 Admin Backend REST API（`/api/knowledge/*`）。

**Sidecar `kg.*` 方法**：

| 方法 | 说明 |
|------|------|
| `kg.search` | 混合检索（FTS5 + LanceDB 向量 + RRF 融合 + ACL 下推） |
| `kg.document.list` | 分页文档列表（ACL 下推） |
| `kg.document.get` | 文档详情（越权拒绝） |
| `kg.citation.get` | 引用详情（回溯来源） |

### Provider 与 Backend RPC

Provider/Backend 运行时方法保留于 Sidecar（`provider.*`），管理侧（创建/删除/凭证/探测/定价）已迁移至 Admin Backend REST API（`/api/providers/*` + `/api/backends/*`）。

**Sidecar `provider.*` 方法**：

| 方法 | 说明 |
|------|------|
| `provider.list` | 可用 Provider 列表 |
| `provider.model.list` | Provider 模型列表 |
| `provider.runtime.start` | 启动 Provider 运行时 |
| `provider.runtime.send` | 发送消息 |
| `provider.runtime.cancel` | 取消运行 |

### 会话 RPC

`session.*` 方法保留于 Sidecar，支持会话生命周期管理。

### 设置、系统 RPC

- `sys.migration.status`：迁移执行状态查询
- `sys.sync.trigger`：手动触发配置同步
- `cap.engine.resolve`：能力引擎 ACL 四分支解析（只收窄不放大）

### 前端页面

React 前端通过 `rpcCall` → Tauri `sys_rpc_call` → sidecar 通信。Sidebar 导航共 9 个页面：公司管理、员工管理、会话、任务看板、任务高级、概览、设置。管理侧功能（能力/知识/Provider/治理/审计）已迁移至 Admin Frontend（`apps/admin/`，11 管理页面）。时间统一显示北京时间（UTC+8），数值默认 2 位小数不补零。详见 [docs/用户手册.md](docs/用户手册.md)。

## 开发指南

详细部署说明请参阅 [docs/部署文档.md](docs/部署文档.md)。
用户操作手册请参阅 [docs/用户手册.md](docs/用户手册.md)。
接口契约、数据模型、状态机与业务规则（与代码一一对应，可据以无代码重建项目）请参阅 [docs/需求规格说明书.md](docs/需求规格说明书.md)。

## 测试

```bash
# 全链路集成测试
cd /Users/ken/workspace/ibreeze && python -m pytest tests/integration/ -v

# Admin Backend 单元测试（83 个）
cd admin-backend && uv run pytest tests/ -q

# Desktop 前端测试（193 个）
cd apps/desktop && npx vitest run

# Sidecar RPC 精简测试（4 个）
cd sidecar && uv run pytest tests/test_rpc_slimmed.py -v

# TypeScript 类型检查
cd apps/desktop && npx tsc --noEmit
cd apps/admin && npx tsc --noEmit
```

## 近期变更

- **全链路瘦身完成**（2026-07-21）：桌面端从 20 页精简至 9 页，Sidecar RPC 从 ~167 精简至 ~56，新增 Admin Backend（~90 REST 端点）和 Admin Frontend（11 管理页面）
