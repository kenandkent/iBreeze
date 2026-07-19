# iBreeze - 本地 AI 组织运行平台

iBreeze 是一个本地 AI 组织运行平台，将 AI 工作流、数据管理和桌面应用集成到一个统一的系统中。所有数据存储在本地，无需联网。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 19 + TypeScript + Vite 6 + Tailwind CSS 3 |
| 状态管理 | Zustand 5 |
| 数据获取 | TanStack Query 5 |
| 流程图 | React Flow 12 |
| 代码编辑器 | Monaco Editor 4 |
| 图标 | Lucide React |
| 桌面壳 | Tauri 2 (Rust) |
| 后端 | Python 3.12+ Sidecar（uv 管理依赖） |
| 存储 | SQLite + LanceDB |

## 快速开始

### 前置条件

- Node.js 18+
- Python 3.12+
- uv（Python 包管理器）
- Rust 工具链（Tauri 编译需要）

### 安装依赖

```bash
# 前端
cd apps/desktop
npm install

# 后端
cd sidecar
uv sync
```

### 启动开发环境

```bash
# 终端 1：启动 Python Sidecar
cd sidecar
uv run python -m acos.app

# 终端 2：启动前端
cd apps/desktop
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
├── apps/desktop/          # Tauri 桌面应用
│   ├── src/
│   │   ├── components/    # React 组件
│   │   │   ├── layout/    # 布局组件 (Sidebar, Header, Layout)
│   │   │   ├── company/   # 公司管理
│   │   │   ├── employee/  # 员工管理
│   │   │   ├── task/      # 任务看板
│   │   │   ├── knowledge/ # 知识库
│   │   │   ├── capability/# 能力/提示词/技能/模板
│   │   │   ├── session/   # 会话（职员安全上下文线程）
│   │   │   ├── provider/  # Provider 与 Backend 管理
│   │   │   ├── grant/     # 授权（员工能力授予）
│   │   │   ├── intervention/ # 人工干预（Backend 恢复等）
│   │   │   ├── audit/     # 审计查询
│   │   │   ├── dashboard/ # Dashboard 概览
│   │   │   ├── settings/  # 设置
│   │   │   └── common/    # 通用组件 (StatusBadge, LoadingSpinner)
│   │   ├── stores/        # Zustand 状态管理
│   │   ├── services/      # RPC 客户端
│   │   ├── types/         # TypeScript 类型定义
│   │   └── styles/        # 全局样式 (Tailwind CSS)
│   ├── tailwind.config.js
│   └── package.json
├── sidecar/               # Python sidecar 服务
│   └── acos/
│       ├── app.py         # RPC 总线接线（所有 Methods 注册入口）
│       ├── rpc/           # 各命名空间 handler（methods_*.py）
│       ├── migrations/    # SQLite 幂等迁移（0028-0058）
│       ├── backends/      # Backend 服务 / Provider 注册 / 凭证代理 / 运行时
│       ├── knowledge/     # 知识库 RAG 模块
│       ├── workflows/     # 工作流引擎
│       └── governance/    # 预算与审批治理
├── packages/
│   ├── rpc-schema/        # JSON-RPC 契约定义
│   └── rpc-types/         # 生成的类型定义
└── docs/                  # 文档
    ├── 部署文档.md
    ├── 设计方案/          # 设计方案、实施计划、Review 记录
    └── 用户手册.md
```

## 架构

系统采用 Sidecar 架构，桌面应用通过 JSON-RPC 2.0 over Unix Domain Socket 与 Python 后端通信。

### RPC 协议

- 使用 NDJSON framing（每行一个 JSON）
- 消息格式: `{type: "request"|"response", id, method, params, result, error}`
- 核心方法: `sys.health` 返回 `{status: "healthy", components: {rpc: "up"}}`

### 治理与审批 RPC（Phase 10）

治理命名空间 `gov.*` 与审批中心 `approval.*` 由 `sidecar/acos/rpc/methods_gov.py`（GovMethods）、
`sidecar/acos/rpc/methods_approval.py`（ApprovalMethods）实现，注册方法如下：

**gov.\***（预算策略 / 预算查询 / 审批类型 / 治理审计）
- `gov.budgetPolicy.get`：`{company_id}` → 当前 active 预算策略（版本化，supersede 旧版切 pointer）
- `gov.budgetPolicy.update`：`{company_id, expected_policy_version, updates{monthly_limit?,per_task_limit?,currency?,on_budget_exceeded?,name?}, idempotency_key}` → CAS 更新，币种 ISO-4217 校验、int64 micros 非负/溢出拒绝
- `gov.budget.get`：`{task_id, company_id}` → `{currency, limit_micros, reserved_micros, settled_micros, remaining_micros, token_limit?}`（跨公司拒绝）
- `gov.budget.reserve`：`{company_id, task_id, run_id, currency, amount_micros, node_id?}` → 调用前预留；触顶且 `require_approval` 时返回 `pending_approval` 并建 budget revision lock；pending 期间同任务同币种新预留返回 `WF-BUDGET-APPROVAL-PENDING`
- `gov.budget.revise`：`{company_id, task_id, currency, requested_delta_micros, run_id?}` → 触发预算修订审批（budget_approval）
- `gov.approvalType.create/list/get/update`：审批类型定义（高风险计划/工具调用/预算超限等）
- `audit.query`：`{company_id, type(budget|approval|approval_type|budget_revision), page}` → 治理审计分页（合并原 `gov.audit.query`）

**approval.\***（审批中心）
- `approval.list`：`{company_id, approval_type?, status?, page}` → 审批分页列表
- `approval.get`：`{approval_id}` → 审批详情（含 budget 绑定字段）
- `approval.resolve`：`{approval_id, decision(approve|reject), comment?, expected_version, idempotency_key}` → 对 pending 做 CAS 决议；过期转 expired；预算审批批准后按 watermark/budget version 改 limit 并释放 revision lock
- `approval.request`：`{company_id, approval_type, target_ref, risk_summary?, task_id?, run_id?, node_id?, generation_id?, expiry?, 预算绑定字段?, idempotency_key}` → 创建审批请求并生成对应 approval（绑定 target_ref/risk_summary/risk_summary）

> 金额一律使用 int64 micros，币种 ISO-4217；写方法需带 `idempotency_key`；审批 `actor`/`approved_by` 由服务端 LocalOwner 注入，不接受客户端传入。

### 知识库与 RAG RPC（Phase 8，`kg.*`）

知识库实现于 `sidecar/acos/knowledge/`，命名空间从旧 `knowledge.*` 迁移/扩展为 `kg.*`
（旧 `knowledge.*` 方法保留于 `methods_knowledge.py` 不破坏）。核心模块：

- `raw_store.py`：第一层原始事件存储读取（复用 `domain_events` / `conversation_events`，不建第二套事件表）+ ingestion watermark
- `extractor.py` + `chunker.py` + `policy_service.py`：提炼流水线（密钥清洗脱敏、ProviderAdapter 驱动、ProcessPoolExecutor 分块、ingestion job 状态机 `pending|running|retryable|succeeded|failed|cancelled`、每次 CAS 发 `notify.knowledgeStatus`）
- `embedding.py`（`LocalEmbedding` / `EmbeddingCapable`）：本地真实确定性向量（环境无法下载 BAAI/bge-m3 ONNX 权重，采用确定性词袋哈希向量，语义相关、可索引、可预过滤，非 mock）
- `vector_store.py`（`LanceVectorStore`）：LanceDB 向量存储，已验证 `prefilter=True` 在 ANN 前应用过滤（pre-filter 验证见 `docs/打包验证记录.md`）
- `retriever.py`（`Retriever`）：混合检索（FTS5 关键词 + LanceDB 向量 + RRF 融合 + ACL 下推 + token 预算 + citation），`query_with_audit` 写 `knowledge_access_logs`
- `reconciler.py`：SQLite / LanceDB 双写一致性对账（缺向量重嵌、孤儿清理）
- `methods_kg.py`（`KgMethods`）：`kg.*` RPC 注册

**kg.\* 注册方法**

| 方法 | 参数 | 说明 |
|------|------|------|
| `kg.document.list` | `company_id, view_as_employee_id, source_category?` | 分页文档列表（ACL 下推） |
| `kg.document.get` | `company_id, view_as_employee_id, knowledge_id` | 文档详情（越权拒绝） |
| `kg.citation.get` | `company_id, view_as_employee_id, citation_id` | 引用详情（回溯来源） |
| `kg.search` | `company_id, view_as_employee_id, query, task_id?, generation_id?, source_categories?` | 混合检索 Context Pack（ACL 下推到 FTS5 + LanceDB 查询条件） |
| `kg.source.delete` | `company_id, source_type, source_id, mode(soft\|hard)` | 级联删除（LocalOwner；不删任务证据与审计） |
| `kg.knowledge.reject` | `company_id, knowledge_id, reason?` | 治理拒绝（status=rejected，移出 FTS） |
| `kg.knowledge.confirm` | `company_id, knowledge_id` | 治理确认（governance_confirmed=1，写审计 operator=LocalOwner） |
| `kg.ingest.retry` | `company_id, job_id` | 对 `retryable`/`failed` job 建新 attempt 重试 |

 > 检索 ACL 红线：范围过滤（company/department/task/employee 四分支）必须下推到 FTS5 SQL WHERE 与 LanceDB `where(prefilter=True)` 查询条件，禁止先查全部再应用层过滤。actor 由服务端注入 LocalOwner，跨公司/越权拒绝。

### Provider 与 Backend RPC（Phase 6，`provider.*` / `backend.*`）

实现于 `sidecar/acos/rpc/methods_provider.py`、`methods_backend.py`，领域逻辑在 `backends/`（registry / pricing / credential_broker / runtime）。

**provider.\***（Provider 注册、价格目录、凭证代理、运行时能力）
- `provider.list` / `provider.get`：`{company_id}` / `{company_id, provider_id}` → Provider 及其版本化价格目录（int64 micros，精确向上取整）
- `provider.import`：幂等从 manifest 导入 Provider 及价格目录（已存在的版本跳过）
- `provider.priceCatalog.get` / `provider.priceCatalog.update`：价格目录读取 / CAS 更新（币种 ISO-4217、未知/过期/跨公司/币种冲突/溢出 fail-closed）
- `provider.credential.set/get/revoke`：凭证存于 OS Keychain，**明文不落 DB**，按 `company_id` 隔离（注：设计原计划 `set` 经 Rust Keychain 代理，当前 sidecar 直连为过渡实现）
- `provider.runtime.getCapabilities`：运行时能力（按 tier 映射，三键 tierMapping）

**backend.\***（Backend 生命周期与调度）
- `backend.list` / `backend.get`：`{company_id}` / `{company_id, backend_id}` → Backend 列表 / 详情
- `backend.create`：创建 Backend（默认唯一，多次创建触发 CAS 冲突）
- `backend.update`：状态机更新（active/disabled/unknown/exhausted），带 `expected_version` CAS
- `backend.archive`：归档（存在有效 lease 时拒绝）
- `backend.probe`：健康探测（手动），更新 last_health 与状态
- `backend.lease`：真实租用机制（acquire/release/renew，带 TTL 与 version CAS）

### 会话 RPC（Phase 7，`session.*`）

实现于 `sidecar/acos/rpc/methods_session.py`，领域逻辑在 `backends/session/`。

- `session.list` / `session.get`：`{company_id, employee_id?}` / `{company_id, session_id}` → 会话线程列表 / 详情
- `session.create`：`{company_id, employee_id, policy_*` 九维安全上下文参数 `}` → 计算 security_context_key（三个策略域前缀 + RFC 8785 canonical JSON + SHA-256），同上下文复用线程
- `session.handoff`：跨员工交接（状态机 + 崩溃对账，恰好一次）
- `session.message.send`：在单线程 active turn 内发送（并发 BUSY 拒绝，READONLY/STALE 防护）

### 设置、系统、治理审计 RPC（Phase 10/12，`settings.*` / `sys.*` / `audit.*`）

- `settings.*`：`settings.policy.get/update`（四类版本化策略：权限/成本/安全/审计）、`settings.cloudConsent.get/update`、`settings.features.get`，均带版本 CAS
- `sys.migration.status`：迁移执行状态查询
- `cap.engine.resolve`：能力引擎 ACL 四分支解析（只收窄不放大）
- `audit.query`：`{company_id, type(budget|approval|approval_type|budget_revision), page}` → 治理审计分页（合并原 `gov.audit.query`）
- `intervention.list`：`{company_id, page}` → 人工干预事项列表（公司隔离 + 分页，如 `backend_recovery`）

### 前端页面（Phase 12）

React 前端通过 `rpcCall` → Tauri `sys_rpc_call` → sidecar 通信。Sidebar 导航共 12 个页面：公司管理、员工管理、任务看板、知识库、能力管理、会话、Provider与Backend、授权、人工干预、审计、Dashboard、设置。时间统一显示北京时间（UTC+8），数值默认 2 位小数不补零。详见 [docs/用户手册.md](docs/用户手册.md)。

## 开发指南

详细部署说明请参阅 [docs/部署文档.md](docs/部署文档.md)。
用户操作手册请参阅 [docs/用户手册.md](docs/用户手册.md)。
