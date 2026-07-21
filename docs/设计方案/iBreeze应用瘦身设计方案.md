# iBreeze 全链路瘦身设计方案

> 本文档定义 iBreeze 从"全功能桌面应用"到"瘦桌面端 + Admin Backend Web 端"的全链路瘦身方案，涵盖桌面端瘦身、Admin Backend 设计、Sidecar 改造、数据库拆分、交互协议和实施计划。

---

## 1. 背景与目标

### 1.1 现状

当前 iBreeze 桌面应用（Tauri + React）承担了**所有功能**：20 个页面、~65 个前端 RPC 调用、~167 个 Sidecar RPC 方法（165 业务 + 2 sys 内置）。包括组织管理、能力管理、知识库、Provider/Backend 配置、治理审批、审计干预等管理功能，全部与用户交互功能（会话、任务）混在一个桌面应用中。

### 1.2 问题

| 问题 | 影响 |
|------|------|
| 桌面端过于臃肿 | 20 个页面全部暴露给用户，管理功能与用户功能混杂 |
| 无法多人协作管理 | 管理操作只能通过单机桌面应用完成，不支持团队管理 |
| 权限控制缺失 | 前端 20 个菜单项对所有用户一视同仁，无 RBAC |
| 部署分发困难 | 管理员和普通用户使用同一个 .app，无法独立升级管理端 |
| 安全风险 | CSP 禁用、管理 API 通过 UDS 暴露在本地 |

### 1.3 目标

- **桌面端瘦身**：从 20 页精简至 9 页，专注用户与 AI 公司的交互
- **Admin Backend**：独立 Web 应用，管理能力/知识/Provider/Backend/治理/审计
- **Sidecar 精简**：RPC 从 ~167 个精简至 ~55 个用户侧方法（含 3 个 sys 内置）
- **数据库拆分**：Admin DB 和 Sidecar DB 完全独立
- **权限隔离**：Admin Backend 独立 JWT + RBAC 认证

---

## 2. 现状分析

### 2.1 桌面应用现状

```
技术栈：React 19 + TypeScript + Vite + Tailwind CSS + Tauri 2 (Rust)
状态管理：Zustand（单 store：appStore）
路由：无 React Router，switch + useState 驱动
页面数：20 个 PageKey
组件数：~40 个 React 组件
```

**20 个页面清单**：

| # | PageKey | 组件 | 类型 | 前端 RPC 数 |
|---|---------|------|------|------------|
| 1 | `companies` | CompanyList + CompanyDetail | 用户侧 | 16 |
| 2 | `employees` | EmployeeList + EmployeeDetail | 用户侧 | 12 |
| 3 | `session` | SessionPage | 用户侧 | 3 |
| 4 | `tasks` | TaskBoard | 用户侧 | 4 |
| 5 | `taskAdvanced` | TaskAdvancedPage + TaskDag | 用户侧 | 7+1 |
| 6 | `dashboard` | DashboardPage | 混合 | 7 |
| 7 | `settings` | SettingsPage | 管理侧 | 11 |
| 8 | `knowledge` | KnowledgeList | 管理侧 | 3 |
| 9 | `knowledgeGov` | KnowledgeGovernancePage | 管理侧 | 10 |
| 10 | `capabilities` | CapabilityList | 管理侧 | 4 |
| 11 | `capengine` | CapabilityEnginePage | 管理侧 | 11 |
| 12 | `skills` | SkillList | 管理侧 | 3 |
| 13 | `prompts` | PromptList | 管理侧 | 3 |
| 14 | `templates` | TemplateList | 管理侧 | 6 |
| 15 | `provider` | ProviderBackendPage | 管理侧 | 12 |
| 16 | `grant` | GrantPage | 管理侧 | 3 |
| 17 | `governance` | GovernancePage | 管理侧 | 8 |
| 18 | `audit` | AuditPage | 管理侧 | 1 |
| 19 | `intervention` | InterventionPage | 管理侧 | 1 |
| 20 | `permission` | PermissionPage | 管理侧 | 3 |

**分类统计**：用户侧 5 页面（含 Dashboard）/ 管理侧 15 页面

### 2.2 Sidecar 现状

```
技术栈：Python 3.12+ / aiosqlite / LanceDB
传输层：NDJSON over Unix Domain Socket (/tmp/acos.sock)
数据库：SQLite (/tmp/acos.db)
注册 RPC：~167 个（含 165 业务方法 + 2 sys 内置；echo 8 个未注册）
```

**RPC 按域分类**：

| 域 | RPC 数 | 管理侧 | 用户侧 | 说明 |
|---|---|---|---|---|
| org.company.* | 8 | 8 | 0 | 公司管理 |
| org.department.* | 10 | 10 | 0 | 部门管理 |
| org.employee.* | 11 | 11 | 0 | 员工管理 |
| org.grant.* | 4 | 4 | 0 | 授权管理 |
| org.template.* | 6 | 6 | 0 | 模板管理 |
| org.graph/permission | 2 | 2 | 0 | 组织图/权限 |
| session.* | 10 | 0 | 10 | 会话交互 |
| task.* | 6 | 0 | 6 | 任务执行 |
| workflow.* | 4 | 0 | 4 | 工作流 |
| cap.skill.* | 11 | 11 | 0 | 技能管理 |
| cap.prompt.* | 11 | 11 | 0 | Prompt 管理 |
| cap.capability.* | 12 | 12 | 0 | 能力管理 |
| cap.snapshot/metrics/engine | 3 | 1 | 2 | 快照/指标/引擎 |
| provider.* | 15 | 12 | 3 | Provider 管理+runtime |
| backend.* | 10 | 10 | 0 | Backend 管理 |
| settings.* | 10 | 10 | 0 | 系统设置 |
| gov.* | 10 | 10 | 0 | 治理策略 |
| approval.* | 4 | 4 | 0 | 审批中心 |
| knowledge.* | 3 | 3 | 0 | 知识文档 CRUD |
| kg.* | 9 | 5 | 4 | 知识图谱 |
| audit.* / intervention.* | 2 | 2 | 0 | 审计/干预 |
| sys.* | 1 | 0 | 1 | 系统健康 |
| echo.* | 8 | 0 | 8 | 测试用 |

**分类**：管理侧 ~105 方法 / 用户侧 ~55 方法 / echo 测试 8 方法（未注册）

### 2.3 配置数据读取路径

Sidecar 中存在三类数据：

| 分类 | 数据类型 | 写入方 | Sidecar 角色 | 需要同步 |
|------|---------|--------|-------------|---------|
| **业务数据** | Company / Department / Employee | Sidecar（Desktop RPC） | 权威源 | 否（Admin 只读镜像用于审计） |
| | Grant | Sidecar（Desktop RPC） | 权威源 | 否 |
| **配置类** | Capability / Skill / PromptAsset | Admin Backend | 只读副本 | 是 |
| | Template | Admin Backend | 只读副本 | 是 |
| | Knowledge/Security/Workspace/Notification Policy | Admin Backend | 只读副本 | 是 |
| | Budget Policy | Admin Backend | 只读副本 | 是 |
| | Backend 注册 | Admin Backend | 只读副本 | 是 |
| | Provider 价格/Tier 映射 | Admin Backend | 只读副本 | 是 |
| **运行时** | Session / Thread | Sidecar | 产生方 | 否 |
| | Task / Checkpoint | Sidecar | 产生方 | 否 |
| | Knowledge Document（runtime） | Sidecar | 产生方 | 否 |
| | Knowledge Document（managed） | Admin Backend | 只读副本 | 是 |
| | Capability Snapshot | Sidecar | 产生方 | 否 |
| | Audit Log | Sidecar | 自动记录 | 否 |
| | Approval | Sidecar | 产生方 | 否 |
| | Provider 可用性 | Sidecar | 自行探测 | 否 |

### 2.4 权限体系现状

- **无独立 roles/permissions 表**：角色由 `employees.employee_type` 隐式表达
- **3 种员工类型**：`company_leader`（最高）/ `department_leader`（中）/ `employee`（最低）
- **权限模型**：部门+任务可见性模型（非传统 RBAC/ABAC）
- **授权机制**：`access_grants` 表支持临时跨部门读授权（`department_read`/`task_read`），有有效期
- **前端无权限过滤**：Sidebar 20 个菜单项对所有用户一视同仁

### 2.5 问题总结

桌面端本质是一个**纯管理后台**包装在 Tauri 壳中，仅 `SessionPage` 是真正的用户交互入口。需要将管理功能剥离到独立 Web 应用，桌面端回归"用户与 AI 公司交互的工作台"定位。

---

## 3. 瘦身目标架构

### 3.1 三端架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                          用户侧（桌面端）                              │
│  ┌────────────────────────┐          ┌────────────────────────────┐  │
│  │  Desktop App (Tauri)    │◄── UDS ──►│  Python Sidecar             │  │
│  │  9 页面                  │ JSON-RPC  │  ~55 个用户侧 RPC            │  │
│  │  React + Zustand        │          │  /tmp/acos.db               │  │
│  └────────────────────────┘          └─────────────┬──────────────┘  │
│                                                     │                 │
│                                              REST Pull (配置同步)     │
│                                                     │                 │
│  ┌──────────────────────────────────────────────────▼──────────────┐  │
│  │                    Admin Backend                                │  │
│  │  ┌──────────────────┐      ┌────────────────────────────────┐  │  │
│  │  │  Admin Frontend    │─────►│  Admin REST API                 │  │  │
│  │  │  @umijs/max        │      │  FastAPI + JWT + RBAC           │  │  │
│  │  │  Ant Design Pro    │      │  :50080                         │  │  │
│  │  │  11 管理页面        │      │  /tmp/ibreeze_admin.db          │  │  │
│  │  │  Web 浏览器访问     │      └────────────────────────────────┘  │  │
│  │  └──────────────────┘                                            │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 职责划分矩阵

| 功能域 | Desktop App | Sidecar | Admin Backend |
|--------|:-----------:|:-------:|:-------------:|
| AI 公司组织管理（公司/部门/员工） | 主界面 | RPC 服务 | — |
| AI 会话交互 | 主界面 | RPC 服务 | — |
| 任务管理与执行 | 主界面 | RPC 服务 | — |
| 能力/技能/Prompt 编排 | — | 配置副本 | 主界面 + API |
| 知识库管理 | — | 配置副本 | 主界面 + API |
| Provider/Backend 管理 | — | 配置副本 | 主界面 + API |
| 系统设置/策略 | — | 配置副本 | 主界面 + API |
| 授权管理 | — | 配置副本 | 主界面 + API |
| 治理审批 | — | 配置副本 | 主界面 + API |
| 审计日志 | — | — | 主界面 + API |
| 人工干预 | — | — | 主界面 + API |

---

## 4. 桌面端瘦身设计

### 4.1 页面精简（20 → 9）

**保留的 9 个页面**（含 Detail 纯展示组件）：

| # | PageKey | 组件 | 理由 |
|---|---------|------|------|
| 1 | `companies` | CompanyList + CompanyDetail | 用户管理 AI 公司的核心功能 |
| 2 | `employees` | EmployeeList + EmployeeDetail | 用户雇佣/管理 AI 员工的核心功能 |
| 3 | `session` | SessionPage | 用户与 AI 交互的核心功能 |
| 4 | `tasks` | TaskBoard | 任务看板，管理 AI 工作 |
| 5 | `taskAdvanced` | TaskAdvancedPage + TaskDag | 高级任务操作（工作流/死信） |
| 6 | `dashboard` | DashboardPage | 轻量概览（仅会话+任务统计） |
| 7 | `settings` | SettingsPage | 客户端连接配置 |
| 8 | — | Sidebar + Layout | 布局组件（重构） |
| 9 | — | common/* | 公共组件（保留） |

**移至 Admin Backend 的 11 个页面**：

| # | 原 PageKey | 原组件 | 移管理理由 |
|---|-----------|--------|-----------|
| 1 | `knowledge` | KnowledgeList | 知识库管理是管理行为 |
| 2 | `knowledgeGov` | KnowledgeGovernancePage | 知识治理是管理行为 |
| 3 | `capabilities` | CapabilityList | 能力资产编排是管理行为 |
| 4 | `capengine` | CapabilityEnginePage | 能力引擎配置是管理行为 |
| 5 | `skills` | SkillList | 技能定义是管理行为 |
| 6 | `prompts` | PromptList | Prompt 资产管理是管理行为 |
| 7 | `templates` | TemplateList | 模板管理是管理行为 |
| 8 | `provider` | ProviderBackendPage | Provider/Backend 配置是管理行为 |
| 9 | `grant` | GrantPage | 授权管理是管理行为 |
| 10 | `governance` | GovernancePage | 审批流/预算策略是管理行为 |
| 11 | `audit` + `intervention` + `permission` | AuditPage / InterventionPage / PermissionPage | 审计/干预/权限可视化是管理行为 |

### 4.2 布局重构

**瘦身后 Sidebar 结构**：

```
┌─────────────────────────────┐
│  iBreeze  ☰                  │
├─────────────────────────────┤
│  🏢 公司管理                  │
│  👥 员工管理                  │
│  💬 会话              ← 默认 │
│  📋 任务看板                  │
│  🔧 任务高级                  │
│  📊 概览                      │
│  ─────────────               │
│  ⚙️ 设置                     │
└─────────────────────────────┘
```

**默认首页**：从 `dashboard` 改为 `session`（AI 会话是核心交互）

### 4.3 路由引入

当前使用 switch + useState 驱动页面切换，瘦身时引入 React Router：

```tsx
// 新增 apps/desktop/src/router.tsx
import { createBrowserRouter } from 'react-router-dom';

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/session" /> },
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
```

**迁移策略**：先引入 React Router，再逐页迁移，最后删除旧 switch 逻辑。

### 4.4 轻量 Dashboard 设计

瘦身后 Dashboard 仅展示与用户交互相关的统计：

| 卡片 | 数据来源 | RPC |
|------|---------|-----|
| 进行中会话 | session_threads WHERE status='active' | `session.list` |
| 进行中任务 | tasks WHERE status='running' | `task.list` |
| 已完成任务 | tasks WHERE status='completed' | `task.list` |
| 最近活动 | 最近 5 条会话/任务 | `session.list` + `task.list` |

**移除**：公司数、员工数、Backend 数、Provider 数、干预列表（管理侧数据）

### 4.5 Tauri 依赖精简

**Cargo.toml 变更**：

| 依赖 | 变更 | 理由 |
|------|------|------|
| `tokio` | `features = "full"` → `features = ["rt-multi-thread", "net", "io-util", "macros"]` | 仅需 TCP/Unix/IO |
| `libc` | 移除 | 改用 `std::process::Command::new("kill")`（macOS/Linux；Windows 需用 `taskkill`） |
| `lazy_static` | 移除 | 改用 `std::sync::OnceLock`（Rust 1.80+ 稳定，需确认项目 MSRV） |
| `tauri-plugin-shell` | 移除 | sidecar 启动改用 `tauri::api::process::Command` 或保留现有 `std::process::Command` |

**package.json 变更**：

| 依赖 | 变更 | 理由 |
|------|------|------|
| `@tauri-apps/plugin-shell` | 移除 | 前端不再需要 shell API |
| `@monaco-editor/react` | 待确认 | 未找到使用处，可能移除 |
| `@xyflow/react` | 保留 | TaskDag 需要 |
| `zustand` | 保留 | 状态管理（store 可精简） |
| `react-router-dom` | **新增** | 路由管理 |

### 4.6 Sidecar RPC 保留清单

**保留 ~55 个用户侧 RPC**（含 3 个 sys 内置）：

```
# 组织管理（28 个）— 用户核心功能
org.company.list / get / create / update / delete / restore / dissolve / activate
org.department.list / get / create / update / delete / get
org.employee.list / get / create / update / delete / setManager / get
org.grant.create / list / revoke / get
org.template.list
org.graph.get
org.permission.resolve

# 知识文档（2 个）— 用户侧 CRUD
knowledge.list / knowledge.create

# 会话（6 个）
session.list / get / sendMessage / cancel / resume / transcript.get

# 任务（8 个）
task.list / get / create / start / complete / cancel / nodes / retrySubtask

# 工作流（4 个）
workflow.plan.validate / checkpoint.list / deadletter.resolve / workflow.task.cancel

# 知识运行时（4 个）
kg.search / kg.document.list / kg.document.get / kg.citation.get

# 系统（3 个内置）
sys.health / sys.shutdown / sys.migration.status
```

**移除 ~105 个管理侧 RPC**（迁移至 Admin Backend REST API）：

```
# 能力管理（36 个）
cap.skill.*（11）/ cap.prompt.*（11）/ cap.capability.*（11）/ cap.snapshot.build / cap.metrics.get / cap.engine.resolve

# Provider 管理（10 个）
provider.create / provider.agent.list / provider.models.fetch /
provider.pricingPolicy.update / provider.budgetFreeze.clear / provider.tierMapping.update /
provider.probe / provider.credential.get / provider.credential.set / provider.credential.revoke

# Backend 管理（10 个）
backend.list / get / create / update / setDefault / enable / drain / archive / probe / checkAvailability

# 设置（10 个）
settings.company.* / settings.knowledgePolicy.* / settings.securityPolicy.*
settings.workspacePolicy.* / settings.notification.*

# 治理（10 个）
gov.budgetPolicy.* / gov.budget.* / gov.approvalType.* / gov.audit.query

# 审计/干预（2 个）
audit.query / intervention.list

# 知识管理（8 个）
knowledge.update / knowledge.delete / knowledge.search（methods_knowledge.py）
kg.source.delete / kg.knowledge.confirm / kg.knowledge.reject / kg.ingest.retry / kg.reindex（methods_kg.py）

# Provider Runtime（3 个）— 保留给 Admin Backend 调用
provider.runtime.start / send / cancel

# 模板管理（4 个）
org.template.create / update / activate / archive

# 审批管理（4 个）
approval.list / get / resolve / request

# Echo 测试（8 个，未注册）
echo.*
```

**注意**：org.* 方法（公司/部门/员工/授权）全部保留为 Sidecar 用户侧方法，因为这些是业务数据，Sidecar 是权威源。Admin Backend 仅提供只读 GET 端点用于审计查询。

**注意**：部分 RPC（如 org.template.*、org.department.setLeader）在桌面端保留查询能力，写操作移至 Admin Backend。桌面端通过 Sidecar 读取配置副本，Admin Backend 通过 REST API 写入后 Sidecar 同步拉取。

---

## 5. Admin Backend 设计

### 5.1 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 前端框架 | @umijs/max | React 全栈框架，约定式路由 |
| UI 组件库 | Ant Design Pro | 企业级管理后台组件 |
| 后端框架 | FastAPI | 异步 Python REST API |
| 数据库 | SQLite | 独立 `/tmp/ibreeze_admin.db` |
| 认证 | JWT | 本地验证，独立用户表 |
| ORM | SQLAlchemy 2.0 | 异步 SQLite |
| 迁移 | Alembic | 数据库版本管理 |

### 5.2 RBAC 认证

**Admin 用户表**（独立于 Sidecar 的 employees）：

```sql
CREATE TABLE admin_users (
    user_id      TEXT PRIMARY KEY,
    username     TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'viewer'
                 CHECK (role IN ('super_admin', 'platform_admin', 'company_admin', 'viewer')),
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'disabled')),
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE admin_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES admin_users(user_id) ON DELETE CASCADE,
    refresh_token_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
```

**角色权限矩阵**：

| 角色 | 能力管理 | 知识管理 | Provider/Backend | 治理审批 | 审计日志 | 系统设置 |
|------|:-------:|:-------:|:----------------:|:-------:|:-------:|:-------:|
| `super_admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `platform_admin` | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| `company_admin` | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `viewer` | 只读 | 只读 | 只读 | 只读 | 只读 | 只读 |

**JWT 认证流程**：

```
POST /api/auth/login
  Request:  { username, password }
  Response: { access_token, refresh_token, user }

GET /api/auth/me
  Header:   Authorization: Bearer <access_token>
  Response: { user_id, username, role }

POST /api/auth/refresh
  Request:  { refresh_token }
  Response: { access_token }
```

### 5.3 页面清单（11 管理页面）

| 分组 | 页面 | 功能 | API 域 |
|------|------|------|--------|
| **能力管理** | CapabilityList | 能力 CRUD + 状态机 | `/api/capabilities/*` |
| | CapabilityEnginePage | 能力引擎 + 版本 + 快照 + 指标 | `/api/capabilities/*` |
| | SkillList | 技能 CRUD + 版本 | `/api/skills/*` |
| | PromptList | Prompt 资产 CRUD + 版本 | `/api/prompts/*` |
| | TemplateList | 员工模板 CRUD + 状态机 | `/api/templates/*` |
| **知识管理** | KnowledgeList | 知识文档 CRUD | `/api/knowledge/*` |
| | KnowledgeGovernancePage | 知识治理（确认/拒绝/重索引） | `/api/knowledge/*` |
| **基础设施** | ProviderBackendPage | Provider + Backend 管理 | `/api/providers/*` `/api/backends/*` |
| **治理** | GovernancePage | 审批流 + 预算策略 | `/api/governance/*` |
| | AuditPage | 审计日志查询 | `/api/audit/*` |
| | InterventionPage | 人工干预列表 | `/api/audit/*` |

### 5.4 REST API 设计

**认证域（4 端点）**：

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/api/auth/login` | 登录获取 JWT | 公开 |
| POST | `/api/auth/refresh` | 刷新 access_token | 公开 |
| GET | `/api/auth/me` | 获取当前用户信息 | 已认证 |
| PUT | `/api/auth/password` | 修改密码 | 已认证 |

**能力管理域（30 端点）**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/capabilities` | 列出能力（分页+过滤） |
| POST | `/api/capabilities` | 创建能力 |
| GET | `/api/capabilities/{id}` | 获取能力详情 |
| PUT | `/api/capabilities/{id}` | 更新能力 |
| POST | `/api/capabilities/{id}/submit-review` | 提交审核 |
| POST | `/api/capabilities/{id}/publish` | 发布 |
| POST | `/api/capabilities/{id}/deprecate` | 弃用 |
| POST | `/api/capabilities/{id}/archive` | 归档 |
| GET | `/api/capabilities/{id}/versions` | 版本列表 |
| POST | `/api/capabilities/{id}/versions` | 新建版本 |
| GET | `/api/capabilities/{id}/bindings` | 获取技能绑定 |

技能/Skill/Prompt 各自对称（list/create/get/update/saveDraft/version.list/createVersion/submitReview/publish/deprecate/archive），共 ~30 端点。

**知识管理域（10 端点）**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/knowledge/documents` | 文档列表（ACL） |
| GET | `/api/knowledge/documents/{id}` | 文档详情 |
| POST | `/api/knowledge/documents` | 创建文档 |
| PUT | `/api/knowledge/documents/{id}` | 更新文档 |
| DELETE | `/api/knowledge/documents/{id}` | 删除文档 |
| POST | `/api/knowledge/documents/{id}/confirm` | 确认知识 |
| POST | `/api/knowledge/documents/{id}/reject` | 拒绝知识 |
| POST | `/api/knowledge/reindex` | 重建索引 |
| POST | `/api/knowledge/sources/{id}/delete` | 删除来源 |
| POST | `/api/knowledge/ingest/{job_id}/retry` | 摄取重试 |

**Provider 域（10 端点）**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/providers` | Provider 列表 |
| POST | `/api/providers` | 创建 Provider |
| GET | `/api/providers/{id}/models` | 模型列表 |
| POST | `/api/providers/{id}/fetch-models` | 实时查模型 |
| PUT | `/api/providers/{id}/credentials` | 设置凭证 |
| DELETE | `/api/providers/{id}/credentials` | 撤销凭证 |
| POST | `/api/providers/{id}/probe` | Provider 探测 |
| PUT | `/api/providers/{id}/pricing` | 更新定价策略 |
| PUT | `/api/providers/{id}/tier-mapping` | 更新 Tier 映射 |

**Backend 域（8 端点）**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/backends` | Backend 列表 |
| POST | `/api/backends` | 创建 Backend |
| PUT | `/api/backends/{id}` | 更新 Backend |
| POST | `/api/backends/{id}/enable` | 启用 |
| POST | `/api/backends/{id}/drain` | 排空 |
| POST | `/api/backends/{id}/archive` | 归档 |
| POST | `/api/backends/{id}/probe` | 健康探测 |
| POST | `/api/backends/{id}/set-default` | 设为默认 |

**治理域（10 端点）**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/governance/approvals` | 审批列表 |
| GET | `/api/governance/approvals/{id}` | 审批详情 |
| POST | `/api/governance/approvals/{id}/resolve` | 决议 |
| POST | `/api/governance/approvals` | 发起审批 |
| GET | `/api/governance/budget-policy` | 预算策略 |
| PUT | `/api/governance/budget-policy` | 更新预算策略 |
| GET | `/api/governance/approval-types` | 审批类型列表 |
| POST | `/api/governance/approval-types` | 创建审批类型 |
| PUT | `/api/governance/approval-types/{id}` | 更新审批类型 |
| GET | `/api/governance/budget/{task_id}` | 任务预算 |

**审计域（2 端点）**：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/audit/logs` | 审计日志查询 |
| GET | `/api/audit/interventions` | 人工干预列表 |

**同步域（1 端点）**：

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/api/sync/config` | Sidecar 配置同步拉取 | 内部调用 |

**总计：~74 个 REST 端点**

### 5.5 Admin DB 数据模型（30 张表）

| # | 表名 | 说明 |
|---|------|------|
| 1 | `admin_users` | 管理员用户 |
| 2 | `admin_sessions` | 登录会话/refresh token |
| 3 | `capabilities` | 能力主表 |
| 4 | `capability_versions` | 能力版本 |
| 5 | `skills` | 技能主表 |
| 6 | `skill_versions` | 技能版本 |
| 7 | `skill_bindings` | 能力→技能绑定 |
| 8 | `prompt_assets` | Prompt 资产主表 |
| 9 | `prompt_asset_versions` | Prompt 版本 |
| 10 | `employee_templates` | 员工模板 |
| 11 | `knowledge_documents` | 知识文档 |
| 12 | `knowledge_sources` | 知识来源 |
| 13 | `knowledge_policies` | 知识策略 |
| 14 | `security_policies` | 安全策略 |
| 15 | `workspace_policies` | 工作区策略 |
| 16 | `notification_policies` | 通知策略 |
| 17 | `budget_policies` | 预算策略 |
| 18 | `providers` | Provider 配置 |
| 19 | `provider_models` | Provider 模型 |
| 20 | `provider_credentials` | Provider 凭证引用 |
| 21 | `provider_pricing_versions` | 定价策略版本 |
| 22 | `provider_tier_mappings` | Tier 映射 |
| 23 | `backends` | Backend 配置 |
| 24 | `company_backend_defaults` | 公司默认 Backend |
| 25 | `companies` | 公司信息 |
| 26 | `departments` | 部门 |
| 27 | `employees` | 员工 |
| 28 | `access_grants` | 授权 |
| 29 | `approval_types` | 审批类型 |
| 30 | `audit_log` | 审计日志 |

---

## 6. Sidecar 改造

### 6.1 RPC 精简

**改造前**：~167 个注册方法（165 业务 + 2 sys 内置；echo 8 个未注册）

**改造后**：~55 个用户侧方法（含 3 个 sys 内置）

**移除策略**：

| 方式 | 适用范围 | 说明 |
|------|---------|------|
| 删除方法类 | EchoMethods | 测试用，生产不注册 |
| 精简方法类 | OrganizationMethods | 保留查询+核心写入，移除管理侧高级操作 |
| 精简方法类 | CapabilityMethods | 保留 `engine.resolve`（运行时需要），移除 CRUD |
| 精简方法类 | ProviderMethods | 保留 `runtime.*`（运行时需要），移除配置管理 |
| 完全移除 | SettingsMethods / GovMethods / ApprovalMethods | 全部迁移到 Admin Backend |
| 完全移除 | BackendMethods | 全部迁移到 Admin Backend |
| 精简方法类 | KnowledgeMethods / KgMethods | 保留 `kg.search`（运行时检索），移除管理操作 |
| 保留 | TaskMethods / WorkflowMethods / SessionMethods | 用户侧核心 |
| 保留 | SysMethods | 系统健康 |

### 6.2 新增配置同步拉取

Sidecar 新增 `ConfigPuller` 模块，从 Admin Backend 拉取配置数据：

```python
# sidecar/acos/sync/puller.py

class ConfigPuller:
    """从 Admin Backend 拉取配置数据，写入本地 Sidecar DB"""
    
    def __init__(self, admin_api_base: str, db_path: str):
        self.admin_api_base = admin_api_base
        self.db_path = db_path
    
    async def pull_full_config(self, company_id: str):
        """全量拉取（启动时）"""
        # GET {admin_api_base}/api/sync/config?company_id={company_id}
        # 返回所有配置数据的 JSON
        # 写入本地 DB（upsert: INSERT OR REPLACE）
        pass
    
    async def pull_incremental(self, company_id: str, since: str):
        """增量拉取（定期）"""
        # GET {admin_api_base}/api/sync/config?company_id={company_id}&since={timestamp}
        # 仅返回 since 之后变更的数据
        pass
    
    async def start_periodic_sync(self, company_id: str, interval_seconds: int = 3600):
        """启动定期同步（每小时）"""
        pass
```

**同步触发时机**：

| 时机 | 模式 | 说明 |
|------|------|------|
| Sidecar 启动 | 全量拉取 | `sys.health` 之后立即执行 |
| 每 1 小时 | 增量拉取 | 后台定时任务 |
| Admin 操作后 | 手动触发 | Admin Backend 调 Sidecar 的 `sys.sync.trigger` RPC |
| 用户手动刷新 | 增量拉取 | 桌面端设置页"同步配置"按钮 |

**同步的表清单**（17 张配置表）：

| 表 | 同步方式 | 说明 |
|---|---------|------|
| capabilities | upsert | 能力主表 |
| capability_versions | upsert | 能力版本 |
| skills | upsert | 技能 |
| skill_versions | upsert | 技能版本 |
| skill_bindings | upsert | 技能绑定 |
| prompt_assets | upsert | Prompt 资产 |
| prompt_asset_versions | upsert | Prompt 版本 |
| employee_templates | upsert | 员工模板 |
| provider_pricing_versions | upsert | 定价策略 |
| provider_tier_mappings | upsert | Tier 映射 |
| knowledge_policies | upsert | 知识策略 |
| security_policies | upsert | 安全策略 |
| workspace_policies | upsert | 工作区策略 |
| notification_policies | upsert | 通知策略 |
| budget_policies | upsert | 预算策略 |
| backends | upsert | Backend 配置 |
| company_backend_defaults | upsert | 默认 Backend |

**注意**：Company / Department / Employee / Grant 由 Sidecar（Desktop RPC）写入，是业务数据权威源。Admin DB 中的对应表为只读镜像，供审计查询和 Admin 前端展示，不参与同步。

---

## 7. 数据库拆分方案

### 7.1 Admin DB（独立）

- **路径**：`/tmp/ibreeze_admin.db`
- **表数量**：30 张
- **写入方**：Admin Backend REST API
- **读取方**：Admin Backend REST API + Sidecar（通过同步 API）
- **特点**：管理侧数据的权威源

### 7.2 Sidecar DB（精简）

- **路径**：`/tmp/acos.db`
- **表数量**：精简至 ~20 张（移除管理侧配置表的写入能力，保留只读副本；业务数据表保持写入）
- **写入方**：Sidecar 运行时 + 配置同步拉取
- **读取方**：Sidecar RPC（用户侧）
- **特点**：业务数据 + 运行时数据的权威源 + 配置数据的只读副本

**移除写入的表**（保留只读副本供运行时消费）：

| 表 | 原写入方 | 瘦身后 |
|---|---------|--------|
| capabilities / capability_versions | CapabilityMethods | 只读（从 Admin 同步） |
| skills / skill_versions | CapabilityMethods | 只读 |
| prompt_assets / prompt_asset_versions | CapabilityMethods | 只读 |
| skill_bindings | CapabilityMethods | 只读 |
| provider_pricing_versions | ProviderMethods | 只读 |
| provider_tier_mappings | ProviderMethods | 只读 |
| backends / company_backend_defaults | BackendMethods | 只读 |
| knowledge_policies / security_policies / workspace_policies / notification_policies | SettingsMethods | 只读 |
| budget_policies | GovMethods | 只读 |

**保留写入的表**（业务数据 + 运行时数据）：

| 表 | 写入方 | 说明 |
|---|--------|------|
| companies / departments / employees | OrganizationMethods | 业务数据权威源（Desktop 管理） |
| access_grants | OrganizationMethods | 授权数据权威源 |
| session_threads / session_messages | SessionMethods | 会话交互 |
| tasks / task_nodes / task_checkpoints | TaskMethods | 任务执行 |
| knowledge_documents | KgMethods | 知识检索（runtime 类型） |
| capability_snapshots | CapEngine | 运行时快照 |
| approvals | ApprovalMethods | 审批流程 |
| audit_log | 各操作自动记录 | 审计 |
| backend_leases | SessionMethods | Backend 租约 |
| local_owner | Principal | 本机身份 |

### 7.3 同步协议

**App Pull 模式**：Sidecar 主动调 Admin REST API 拉取配置数据。

```
┌──────────────┐                    ┌──────────────────┐
│  Sidecar      │                    │  Admin Backend    │
│  (Pull Client)│                    │  (Config Source)  │
└──────┬───────┘                    └────────┬─────────┘
       │                                     │
       │  GET /api/sync/config               │
       │  ?company_id=xxx                     │
       │  &since=2026-07-20T10:00:00Z         │
       │────────────────────────────────────►│
       │                                     │
       │  200 OK                              │
       │  {                                   │
       │    "timestamp": "...",               │
       │    "capabilities": [...],            │
       │    "skills": [...],                  │
       │    "backends": [...],                │
       │    ...                               │
       │  }                                   │
       │◄────────────────────────────────────│
       │                                     │
       │  UPSERT INTO local_db               │
       │  (INSERT OR REPLACE)                │
       │                                     │
```

**同步安全保障**：

| 机制 | 说明 |
|------|------|
| 幂等性 | upsert（INSERT OR REPLACE），重复拉取不产生副作用 |
| 时间戳 | `since` 参数支持增量拉取，减少传输量 |
| 公司隔离 | `company_id` 参数确保只拉取当前公司数据 |
| 错误容忍 | 网络失败时保留上次同步的本地副本，不影响运行时 |
| 冲突解决 | 配置数据以 Admin DB 为权威源，Sidecar 副本始终以 Admin 为准；业务数据以 Sidecar 为权威源 |

---

## 8. 交互协议

### 8.1 Desktop → Sidecar：UDS JSON-RPC

```
协议：JSON-RPC 2.0 over NDJSON
传输：Unix Domain Socket (/tmp/acos.sock)
认证：无（本地进程信任）
消息格式：
  Request:  {"type":"request","id":"uuid","method":"session.sendMessage","params":{...}}
  Response: {"type":"response","id":"uuid","result":{...}} 或 {"error":{"code":...,"message":"..."}}
```

### 8.2 Admin 前端 → Admin Backend：REST + JWT

```
协议：HTTP/REST
传输：TCP localhost:50080
认证：JWT Bearer Token
消息格式：
  Request:  POST /api/capabilities/xxx/publish  {"expected_version": 3}
  Response: {"status": "published", "version": 4}
  Headers:  Authorization: Bearer eyJ...
```

### 8.3 Sidecar ↔ Admin Backend：REST Pull

```
协议：HTTP/REST
传输：TCP localhost:50080
认证：内部 API Key（或 localhost 信任）
方向：Sidecar 主动调 Admin Backend
触发：启动时 + 每 1 小时 + 手动触发
消息格式：
  Request:  GET /api/sync/config?company_id=xxx&since=timestamp
  Response: {"timestamp": "...", "companies": [...], ...}
```

---

## 9. 部署方案

### 9.1 Desktop App 用户

```
组件：
  - Tauri .app (macOS) / .exe (Windows)
  - Python Sidecar (内嵌或独立)

分发：
  - macOS: .dmg 安装包
  - Windows: .msi 安装包

端口：
  - /tmp/acos.sock (UDS，供 Desktop App 调用)
  - 无 TCP 端口暴露

特点：
  - 单机运行，无需联网
  - 数据存储在 /tmp/acos.db
  - 配置数据从 Admin Backend 同步（需网络可达 Admin Backend）
```

### 9.2 Admin 用户

```
组件：
  - Admin Backend (FastAPI + @umijs/max)
  - Admin DB (SQLite)

分发：
  - Docker 容器
  - 或直接运行 Python 进程

端口：
  - :50080 (Admin REST API，供浏览器和 Sidecar 调用)

特点：
  - Web 浏览器访问
  - 支持多用户同时管理
  - 数据存储在 /tmp/ibreeze_admin.db
  - 管理操作实时生效，Sidecar 通过同步获取变更
```

### 9.3 端口分配总表

| 端口 | 协议 | 归属 | 用途 |
|------|------|------|------|
| `/tmp/acos.sock` | UDS | Sidecar | Desktop App ↔ Sidecar 通信 |
| `:50080` | HTTP/REST | Admin Backend | Admin 前端 ↔ Admin Backend 通信 |
| `:50081` | HTTP/REST | Sidecar（内部） | Admin Backend ↔ Sidecar 内部调用 |

---

## 10. 实施计划

### 10.1 Phase 依赖关系

```
Phase 1 ──────► Phase 2 ──────► Phase 3
                   │                │
                   ▼                │
              Phase 4 ─────────────┘
                   │
                   ▼
              Phase 5 ──► Phase 6
```

### 10.2 Phase 详情

| Phase | 内容 | 产出 | 预估工作量 |
|-------|------|------|-----------|
| **Phase 1** | Admin Backend 骨架 | FastAPI 项目 + 30 表 Alembic 迁移 + JWT 认证 + RBAC 中间件 + admin_users 初始数据 | 中 |
| **Phase 2** | Admin Backend REST API | ~74 个端点（能力/知识/Provider/Backend/治理/审计/同步） | 大 |
| **Phase 3** | Admin Frontend | @umijs/max 项目 + 11 管理页面（Ant Design Pro） | 大 |
| **Phase 4** | Sidecar 改造 | RPC 精简（~167→~55）+ ConfigPuller 同步模块 + sys.sync.trigger RPC | 中 |
| **Phase 5** | Desktop App 瘦身 | 页面 20→9 + React Router + Layout 重构 + Tauri 依赖精简 + 默认首页改为 session | 中 |
| **Phase 6** | 集成测试 + 文档 | 全链路测试 + README/部署文档/用户手册更新 | 小 |

### 10.3 Phase 里程碑

| 里程碑 | 完成条件 | 验证方式 |
|--------|---------|---------|
| M1: Admin Backend 可启动 | FastAPI 启动无错 + DB 迁移成功 + JWT 登录可用 | curl 测试 /api/auth/login |
| M2: Admin API 全部可用 | ~74 端点全部注册 + 基本 CRUD 通过 | pytest 测试覆盖 |
| M3: Admin 前端可用 | 11 页面可访问 + CRUD 操作正常 | 浏览器手动验证 |
| M4: Sidecar 瘦身完成 | RPC 精简 + 同步拉取正常 | pytest 测试覆盖 + 同步日志 |
| M5: Desktop 瘦身完成 | 9 页面 + 路由正常 + 构建成功 | npm run tauri build |
| M6: 全链路集成 | Desktop ↔ Sidecar ↔ Admin Backend 协同工作 | 端到端测试 |

### 10.4 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Admin Backend 与 Sidecar DB schema 不一致 | 同步失败 | 统一 schema 定义，共享类型 |
| 同步延迟导致 Sidecar 数据过期 | 运行时使用旧配置 | 增量同步 + 冲突检测 + 手动刷新 |
| 桌面端 RPC 移除后前端报错 | 页面功能异常 | Phase 5 在 Phase 4 之后，确保 Sidecar 已精简 |
| Admin Backend 性能瓶颈 | 管理操作响应慢 | SQLite 本地运行，无网络延迟 |

---

## 附录 A：瘦前后对比总表

| 维度 | 瘦身前 | 瘦身后 |
|------|--------|--------|
| Desktop 页面数 | 20 | 9 |
| Desktop 前端 RPC 依赖 | ~65 | ~30 |
| Sidecar RPC 方法数 | ~167 | ~55 |
| Admin Backend 页面数 | 0 | 11 |
| Admin Backend API 端点 | 0 | ~74 |
| 数据库 | 1 个 (acos.db) | 2 个 (acos.db + ibreeze_admin.db) |
| 认证 | 无 | JWT + RBAC (Admin) |
| 路由 | switch + useState | React Router |
| 默认首页 | Dashboard | SessionPage |
| Tauri 依赖 | 5 个 | 3 个 (移除 plugin-shell/libc/lazy_static) |
| 部署形态 | 单 .app | 桌面 .app + Admin Web |

## 附录 B：关键设计决策记录

| 决策 | 选择 | 替代方案 | 理由 |
|------|------|---------|------|
| Admin 前端框架 | @umijs/max + Ant Design Pro | Next.js / Vite + 自建 | 企业级管理后台最佳实践，约定式路由省配置 |
| 数据库 | SQLite (独立) | PostgreSQL | 本地部署优先，无需额外依赖 |
| 同步方向 | App Pull（Sidecar 拉） | Admin Push（Admin 推） | 多用户场景下 Pull 更简单，无需 Admin 维护连接状态 |
| 默认首页 | SessionPage | Dashboard | AI 会话是核心交互，直接进入 |
| 路由方案 | React Router | 保持 switch | URL 可分享，浏览器前进后退，SEO 友好 |
| Admin 认证 | JWT 本地验证 | OAuth / Session | 本地部署场景，无需第三方依赖 |
