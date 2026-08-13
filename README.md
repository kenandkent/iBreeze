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
- `sequential_refinement` 的延迟段只使用确认时冻结的 dispatch spec；实际派发前严格解析冻结的能力标签数组并再次校验冻结的员工部门归属、Profile Version、Catalog Release、能力标签和 Workspace Grant 状态，任一引用失效或 spec 结构损坏即将 EmployeeTask 置为 `failed`，不创建错误 Run
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
- Credential 写操作使用 24 小时跨重启幂等记录：请求指纹只保存移除 Secret 后的字段与 Keychain HMAC，Secret 不进入响应缓存、日志、备份或 SQLite；发布 API Model Profile 前由 Rust `credential.describe` 逐 Candidate 预检非敏感 metadata
- API Model 支持 `fixed`、`smart_single`、`selective_ensemble` 三种 turn 级路由：策略写入 Profile Version，候选集合和 Secret 版本写入 Execution Snapshot；Sidecar 负责上下文分类、能力门控、确定性评分、重试/回退、Ensemble 和 Outcome，Ensemble 会先按策略 `max_proposers` 截断确定性阵容再执行触发与 vision/Provider 差异门禁，评分同分时使用本地校准后的 effective quality、延迟、Binding ID、Candidate ID 稳定排序；输入指纹包含 artifact、能力标签和 production/evaluation 来源，避免不同执行边界复用审计身份；Rust 对每个物理请求执行 Snapshot Lease 授权、Keychain 凭据展开、Provider 错误归一化和 Egress
- Ensemble proposer 会收到当前工具名称和 JSON Schema 作为不可执行上下文，返回的 tool call 只进入候选 envelope；只有 aggregator、single 或 fallback 的最终 ModelTurn 进入工具执行链。
- Anchor 和全部候选都不满足能力/健康条件，或 Credential 尚未 ready 时，Run 会带稳定 failure code 进入 `waiting_resource`，不会伪造失败完成；用户显式恢复资源后才重新排队执行。计划确认会对每个交付物的 contributor 和 reviewer 一起做职员/部门/底座/能力/目录/Workspace 预检，任一参与者不可用就不会部分派发
- Plan/Department Task 的 `required_capability_tags` 在部门/职员能力匹配和确认计划资源预检阶段校验，并冻结进 Run spec；路由器仅将其纳入 Context 指纹和审计，不把职员能力标签误当作模型候选元数据。模型候选按 Provider、工具、视觉、流式、上下文、tier、reasoning、role 和 Health 硬门禁过滤
- `fixed` 明确只执行 Anchor（不做难度分层，按 C0 进行能力门控）；Anchor 不满足硬能力条件时才按策略声明的 `fallback_order` 选择回退，禁止因评分或分类结果静默切换到任意候选
- Snapshot 注册传递完整、规范化的 Candidate v2 原始 JSON 与 SHA-256；Rust 只从已验签 Catalog 解析 Provider protocol、endpoint、model name、request defaults，Sidecar 不得传入 `protocol`、`relative_path` 或覆盖 `model`
- proposer 的工具调用只进入结构化候选 envelope，不能进入工具执行器；只有 single、aggregator 或 fallback 的最终 ModelTurn 可以执行工具。每个 Attempt 都经历 `created → accepted → streaming → terminal` 的 CAS 状态链，并按稳定 UUID 关联工具、验证、Review 和任务 Outcome
- 本地 Outcome 达到每个 Deployment/purpose 至少 30 个样本后才影响质量 prior；purpose 样本不足时回退到该 Deployment 全局样本，校准范围固定为 `[-0.20,0.20]`，所有校准数据只保存在桌面 SQLite
- Deployment Health 在每个路由 transport 创建/turn 执行前从当前公司本地 SQLite 恢复；benched 或 `credential_invalid` 状态不会因新 Run 或新 transport 被绕过，Health 账本读取失败时路由 fail-closed
- ModelTurn 的 Rust Credential HTTP Broker 只执行一次物理请求；Retry-After 等待、同 Deployment 重试和 fallback 由 Sidecar 创建新的 Route Attempt 统一处理，Credential Probe 使用独立的探测重试策略
- Rust 在发送 ModelTurn 前对 v2 Candidate 同时校验 `provider_protocol` 与 `request_defaults_sha256` 是否匹配已验签 Catalog Binding；旧 fixed 兼容快照没有 v2 授权字段时跳过这两项声明校验，但仍只使用已验签 Catalog 的协议、路径、模型名和 request defaults
- `credential.http.start` 的五个 Snapshot/Attempt 授权字段必须全部提供或全部省略；部分字段请求直接返回 `ROUTING_SNAPSHOT_NOT_AUTHORIZED`，只有无路由字段的旧 fixed 兼容调用保留历史路径
- 路由 Attempt/Decision/Health 审计写入或 Rust 授权失败会取消已接受的 Broker 请求并停止 fallback，避免产生未审计的 Provider 调用或重复副作用
- Sidecar 启动在接受新 Run 前通过同一 WriteQueue 事务执行恢复：非终态 AgentRun 进入 `failed`、队列/Lease 失效、`planned/executing` Route Decision 和 `created/accepted/streaming` Attempt 保守标记失败且禁止自动重放，只删除已过期的 `ready` Deployment Health
- 智能路由只使用已签名 Catalog 的 Provider/Model Binding；`IBREEZE_ROUTING_STAGE` 在 Sidecar 启动时读取一次（默认 `observe`）：生产 `observe` 只执行 Anchor 并把 rules-v1 的候选建议写入 `policy_trail`，生产 `shadow` 同样不执行额外候选，只有内部 `evaluation` 输入源允许执行影子候选；CLI Agent 仍保持任务级多职员协作，不进入 turn 级路由
- 路由模式或策略值损坏时 fail-safe 到 `fixed` Anchor；不会把非法配置当作 `smart_single` 执行。
- 固定兼容快照缺少 Anchor ID 时使用快照候选数组第一项作为 Anchor，不从当前 Catalog 补候选。
- Run Override 在构建 RoutingContext 前读取一次并写入输入指纹/规则轨迹；非法控制值同样 fail-safe 到 `fixed`。
- 路由 Decision、Attempt、Deployment Health、Outcome 均保存在 Profile 本地 SQLite；Run 详情可查看 tier、实际模型、fallback、usage、latency 和脱敏错误，设置页可维护 Credential、Probe、过期健康记录和 Run override
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

本次实现后的可复现门禁结果如下；通过测试不等同于已达到生产发布条件：

| 模块 | 当前结果 | 工程门禁 |
|---|---|---|
| Sidecar (Python) | 1746 passed，覆盖率 71.47% | 总覆盖率 ≥77%（当前未达） |
| Desktop UI (TypeScript) | 151 passed，functions 75.7% | functions ≥80%（当前未达） |
| Admin Web (TypeScript) | 134 passed，branches 79.61% | branches ≥80%（当前未达） |
| Backend API (Python) | 213 passed，覆盖率 63.11% | 总覆盖率 ≥62%（已达） |
| Desktop Core (Rust) | nextest 191 passed，lib 116 passed | lines ≥30%、functions ≥25%、regions ≥30%（已达） |
| 智能路由专项 | 路由/恢复/生命周期/脱敏等 94 passed | `ibreeze.routing` 与 Rust 新授权模块需专项 100% 覆盖后才可 GA |

`scripts/verify-all.sh` 使用各组件既有阈值；Sidecar、Desktop 和 Admin Web 的当前覆盖率门禁仍是发布阻塞项。真实 Provider A/B、跨进程 IPC/TLS、macOS Seatbelt、签名公证和升级回滚仍需 staging/发布环境验证。

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
- [智能聚合路由使用说明](docs/使用说明/智能聚合路由使用说明.md)
- [智能聚合路由验收报告](docs/验收报告/智能聚合路由效果验收报告.md)

智能路由本地快速验证：

```bash
uv run --project sidecar pytest sidecar/tests -q
bash scripts/generate-contracts.sh && bash scripts/check-contract-drift.sh
npm --prefix apps/desktop run typecheck && npm --prefix apps/desktop run lint && npm --prefix apps/desktop run test -- --run
```

## 许可证

MIT
