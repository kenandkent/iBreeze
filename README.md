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
│ ├─ Generated RPC Dispatcher / authenticated reverse calls     │
│ │  (same handshake session; no second UDS connection)        │
│ ├─ Profile Persistence Kernel                                 │
│ │  ├─ Migration Runner (001_initial.sql)                      │
│ │  ├─ WriteQueue (cap 32) + Unit of Work + Idempotency        │
│ │  └─ ReadPool (8 connections)                                 │
│ ├─ Worker Supervisor (7 workers + heartbeat + backoff +       │
│ │  RuntimeWorker runtime_queue dispatch)                      │
│ ├─ Review/Completion State Machine + internal Command Bus      │
│ ├─ CLI Adapter Protocol (Rust ProcessSupervisor reverse RPC)   │
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
│  ├─ rpc-schema/       # Canonical RPC Registry（包含 ownership，唯一事实源）+ 方法 Schema + 错误码
│  └─ ui/               # 共享 UI 组件
├─ tests/               # 集成、E2E、安全、性能测试
├─ scripts/             # 构建和验证脚本
└─ docs/                # 文档
```

RPC 方法的 ownership、kind、scope 与 Schema 引用只以
`packages/rpc-schema/registry.v1.json` 为事实源。运行
`scripts/generate-contracts.sh` 生成三端契约，运行
`scripts/generate-method-kinds.py --check` 与
`scripts/check-contract-drift.sh` 做只读漂移检查；项目不维护可改写生产源码的第二套同步脚本。

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
- Runtime 队列调度（RuntimeWorker 按公司公平性与优先级领取 ready Run，创建 5 分钟 lease，调用 Rust ProcessSupervisor/ModelRuntime 执行，并通过 WriteQueue 原子落库状态、事件和 Outbox；心跳每 30 秒续租）
- 计划确认与分发只有 `task.confirmPlan` 一个入口：在同一 WriteQueue 事务校验 plan hash/version、active Catalog、Workspace Grant、部门和每个参与职员的状态/发布 Profile/运行绑定，创建不可变 Availability/Execution Snapshot、Task、Run 与队列项，并按 `approved → dispatching → checking_resources → executing` 逐边记录状态事件；任一资源不可用时返回 `waiting_resource` 且不留下部分任务图，Catalog 不可用时不创建本地占位目录
- 低层 `runtime.run` 只接受已持久化且未过期的 Availability Snapshot、Execution Snapshot、CompanyTask、Conversation、职员和适配器契约，创建带 `run.queued` 事件的队列项；生产 RPC 委托 `ibreeze.runtime.gateway.start` 唯一实现，除 `task.confirmPlan` 原子创建完整任务图和该 Gateway 外，其他模块不得自行插入 `agent_runs`；客户端不能用任务 ID 直接启动未快照的 Run，任务执行入口仍是计划确认后的 RuntimeWorker
- Review 状态机的 `StartReview`、`StartIssueFix`、`VerifyIssue`、`CloseIssue` 和 `RejectIssue` 只注册到内部 Command Bus；Outbox 在当前 WriteQueue 事务中直接调用它们，公共 RPC 只能提交带完整产物/运行/复测证据的 `review.resolveIssue`，不能绕过状态迁移
- Review Issue 进入 `verified` 必须持久化同公司且仍为 active 的 `verifier_employee_id`；进入 `rejected` 必须持久化 1–2000 个字符的 `rejection_reason`，blocker/high 问题不可驳回
- Workspace Git 由固定 argv 的受控执行器负责，所有 cwd 来自已确认的 TaskWorkspace；apply 前重新校验用户工作树干净、分支和 baseline 未漂移，受管 Worktree 清理不使用 `--force`
- Reverse RPC 会话复用（所有反向调用复用已认证 IPC Session）
- RPC 公共边界严格校验 `meta`：写方法必须携带 UUID `idempotency_key`，读方法必须省略该字段；`deadline_at` 必须带时区且不能已过期，未知 meta 字段直接拒绝
- Rust 进程监管（独立进程组、超时 SIGINT→SIGTERM→SIGKILL、输出摘要与 macOS Seatbelt）；启动前按已验签 Catalog 的 adapter contract、平台、可执行文件和版本范围运行 `probe_argv` 校验
- CLI 启动仅接受固定 Execution Snapshot（真实可执行路径、策略哈希、截止时间与 Agent 类型）；Sidecar 不得注入任意环境变量，关闭顺序为 Workers → WriteQueue drain → 数据库/IPC
- CLI 输出按单行 4 MiB、单流 16 MiB 上限执行，超限立即终止进程组并以 `RUNTIME_OUTPUT_LIMIT_EXCEEDED` 失败；Rust status 明确区分 `cancelled` 与 `timed_out`
- Rust stdout/stderr 读取器共享一个发送锁，序号分配与 IPC 通知原子化，Sidecar 始终按连续序号接收；Agent 版本探测在失败或超时路径等待输出读取任务结束，禁止遗留后台任务
- API Model 由内置 Agent Loop 驱动，固定只读工具为 `read_file`、`list_files`、`search_text`；模型、Credential、Provider、Workspace 和 ToolPolicy 均来自不可变 Execution Snapshot，取消通过 `credential.http.cancel` 传播到 Rust
- API Model 通过 Rust Credential HTTP Broker + CONNECT Egress Proxy 执行完整请求闭环；Provider 事件通过同一认证 IPC Session 的反向通知返回 Sidecar
- 外部写入同时绑定人工 `approval_id` 与 Rust `workspace_grant_id`；staging 文件必须在 Profile 内、校验 source hash/size、目标状态 hash 和 receipt，不能把审批 ID 当作 Workspace 授权
- 不确定恢复审批只允许固定 `retry_once` 目标（run/tool execution/input hash/prior started time/TTL），外部写入和恢复审批均使用版本化 JSON Schema 与 canonical hash，消费前逐字段校验并保证幂等
- 凭据探测（`credential.probe` 支持 `profile_directory_id` 指定目录）
- 返工尝试生命周期管理（`RequestReworkHandler` + `AdvanceReworkAttemptHandler`，乐观锁）

### 管理后台
- 用户管理（应用用户、管理员）
- 目录管理（Agent、Model、Provider、Skill）；Agent 发布版本固定携带 SemVer 范围、可执行文件、支持平台、探测参数和网络域名
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
