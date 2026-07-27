# AI 公司桌面应用文档与代码 Review 详细报告

## 1. 报告信息

| 项目 | 内容 |
|---|---|
| 设计方案 | `docs/设计方案/AI公司桌面应用设计方案.md` |
| 实施计划 | `docs/设计方案/AI公司桌面应用-实施计划.md` |
| 代码范围 | `apps/desktop`、`apps/desktop-core`、`sidecar`、`apps/backend-api`、`apps/admin-web`、`packages`、`scripts`、`tests`、`.github/workflows` |
| 审查日期 | 2026-07-26 |
| 审查分支 | `main` |
| 审查提交 | `79cf450 fix: 3轮全量review修复 — 契约对齐+测试修复+embedding修复+状态机测试对齐` |
| 工作区状态 | 审查开始时存在两个修改后的 `tsconfig.tsbuildinfo` 和 `tests/e2e/test-results/` 未跟踪目录；测试执行会继续更新这些生成物 |
| 审查方式 | 文档交叉核对、代码静态审查、测试、覆盖率、构建、Lint、类型检查、契约漂移和发布门禁验证 |
| 本次变更范围 | 只生成本报告，不修复业务代码，不修改设计方案和实施计划 |

---

## 2. 审查目标

本次 Review 用于确认：

1. 设计方案与实施计划是否存在功能、架构、接口、数据模型或验收标准冲突。
2. 代码实现是否符合两份文档规定的系统边界和功能范围。
3. Desktop、Rust Core、Sidecar、Backend API、Admin Web 之间的接口是否一致。
4. 用户提交任务后，是否能够真实完成计划生成、用户确认、部门分派、职员执行、Review、返修、复测和最终报告闭环。
5. Agent Runtime、凭据、Catalog、Workspace、备份恢复和更新是否满足安全与恢复要求。
6. 自动化测试和 CI 是否能够提供可信、可复现的交付证据。

---

## 3. 总体结论

### 3.1 两份文档之间

设计方案和实施计划在以下核心方面保持一致：

- 中心后台只保存应用用户、管理员用户以及全局 Agent、Model、Provider、Skill、Catalog Release 等基础目录。
- 公司、部门、职员实例、会话、任务、运行、Artifact、Review 和知识正文只存储在桌面本地。
- Desktop 使用 React WebView，系统与安全能力由 Tauri/Rust Core 提供，本地业务由 Python Sidecar 提供。
- WebView 不直接访问 Keychain、后台 API、CLI、数据库和文件系统。
- API Model 可作为职员模型底座，但由 iBreeze Built-in Agent Runtime 执行完整 Agent Loop。
- Codex CLI、Claude Code、OpenCode 和 API Model 统一进入 Agent Runtime Gateway。
- 用户任务必须先由总经理分析并形成计划，用户确认后才能执行。
- 部门负责人负责拆分任务，参与职员既执行也互相 Review，不设置独立 Review 职员类型。
- Review、问题修复、测试部复测、部门报告和总经理最终报告都有明确闭环条件。
- 文档共同要求 100% 单元测试覆盖率，并把集成、E2E、安全、故障、性能和发布验证设为额外硬门禁。

未发现两份文档之间需要立即修订的高等级直接冲突。

实施计划的任务和最终发布清单仍全部未勾选，因此实施计划本身没有声称当前代码已经完成。该状态与当前代码成熟度一致。

### 3.2 文档与代码之间

当前代码实现了大量数据表、Service、RPC Handler、页面骨架和测试，但仍没有形成文档定义的完整产品。

当前最严重的问题是：

- 桌面登录、注册调用名称和响应结构与 Rust Command 不一致。
- WebView 仍保存 Access Token 和 Refresh Token。
- RPC、OpenAPI 和领域 Schema 生成体系仍未建立。
- 多数 Desktop 写 RPC 没有提供幂等键，运行时会被 Rust 拒绝。
- Catalog Release 仍是可变资源表的实时视图，没有完整不可变 Manifest 和客户端验签。
- API Model 仍由 Sidecar 直接携带 API Key 并访问 Provider 网络。
- Sidecar 主入口没有启动任务分析、Run、知识和备份 Worker。
- `task.confirmPlan` 与调度分两个事务，且没有形成可靠 Snapshot 和资源探测。
- Review、返修和最终报告没有成为不可绕过的状态机门禁。
- Credential Broker、外部写入、自动更新和 Seatbelt 仍是 Stub 或 TODO。
- E2E 为空，覆盖率和静态检查远未通过。
- 总验证脚本会吞掉失败并返回成功。

### 3.3 发布判断

当前版本不满足设计方案 K.17 和实施计划第 21 章的发布要求。

不建议：

- 生成正式版本或发布说明；
- 部署到生产环境；
- 使用真实 API Key 或真实 Workspace 处理业务；
- 将当前代码交付第三方并声明已完整实现；
- 使用 `scripts/verify-all.sh` 的退出码作为验收依据。

---

## 4. 本轮实际验证结果

### 4.1 测试、覆盖率与构建

| 模块 | 验证结果 | 结论 |
|---|---:|---|
| Backend pytest | 117 passed，2 warnings | 功能测试通过 |
| Backend 覆盖率 | 61.32% | 未达到 100% |
| Sidecar pytest | 1021 passed，1 skipped，20 warnings | 已无测试失败 |
| Sidecar 覆盖率 | 79.28% | 未达到 100% |
| Rust 单元与集成测试 | 56 passed | 通过 |
| Rust Clippy | 通过 | 通过 |
| Rust fmt | 多文件格式差异 | 失败 |
| Rust 覆盖率 | `cargo llvm-cov` 未安装/未成功执行 | 未验证 |
| Desktop typecheck | 通过 | 通过 |
| Desktop production build | 通过 | 通过，但有大 Bundle 告警 |
| Desktop Vitest | 16 passed | 仅 formatter 测试 |
| Desktop statements 覆盖率 | 1.75% | 严重不足 |
| Admin Web typecheck | 通过 | 通过 |
| Admin Web production build | 通过 | 通过，但有大 Bundle 告警 |
| Admin Web Vitest | 16 passed | 仅 formatter 测试 |
| Admin Web statements 覆盖率 | 2.86% | 严重不足 |
| Playwright E2E | `No tests found` | 失败 |

Sidecar 当前唯一 skipped 用例是受执行环境 UDS 权限限制的帧测试。该项不能视为通过，必须在允许 Unix Domain Socket 的 macOS Runner 上复验。

### 4.2 静态检查与契约

| 检查项 | 结果 |
|---|---:|
| Backend Ruff | 2 errors |
| Backend mypy | 126 errors，涉及 24 个文件 |
| Sidecar Ruff | 162 errors，其中 105 项可自动修复 |
| Sidecar mypy | 57 errors，涉及 19 个文件 |
| Desktop ESLint | ESLint 9 找不到 `eslint.config.*` |
| Admin Web ESLint | ESLint 9 找不到 `eslint.config.*` |
| RPC contract drift | 生成阶段失败 |
| `packages/contracts` lint | 只执行 `echo 'lint ok'`，不是有效检查 |

### 4.3 验证脚本可信度

`scripts/verify-all.sh` 在以下项目失败时仍会继续：

- Rust fmt；
- Rust nextest/llvm-cov 工具缺失；
- Backend 和 Sidecar lint/typecheck/coverage；
- Desktop 和 Admin lint；
- 根契约/安全/故障测试；
- E2E 无测试。

脚本最终仍退出 0，因此不能作为发布证据。

---

## 5. 问题总表

| ID | 等级 | 问题 | 主要影响 |
|---|---|---|---|
| P0-01 | 阻断 | Desktop 登录注册与 Rust Command 冲突 | 无法完成认证入口 |
| P0-02 | 阻断 | WebView 保存 Token | 凭据边界失效 |
| P0-03 | 阻断 | RPC/OpenAPI/领域 Schema 生成体系缺失 | 多语言契约持续漂移 |
| P0-04 | 阻断 | Desktop 写 RPC 缺少幂等键且存在无效方法 | 多数页面写操作运行时失败 |
| P0-05 | 阻断 | Catalog Release 不可变与签名链未实现 | 目录供应链不可验证 |
| P0-06 | 阻断 | API Model 绕过 Rust Credential/Egress Broker | API Key 泄露和网络策略绕过 |
| P0-07 | 阻断 | Sidecar 后台 Worker 未启动 | 任务、Run、索引和备份不执行 |
| P0-08 | 阻断 | Plan 确认、资源快照和调度不是原子闭环 | 半确认、重复派发和不可恢复状态 |
| P0-09 | 阻断 | Review 与最终报告门禁未落实 | Run 成功被误认为业务完成 |
| P0-10 | 阻断 | 外部写入与审批 receipt 仍是 Stub | 审批副作用不可安全执行 |
| P0-11 | 阻断 | 总验证脚本吞掉失败 | CI/验收产生假阳性 |
| P1-01 | 重要 | SQLite 正式迁移体系缺失 | 升级和中断恢复不可靠 |
| P1-02 | 重要 | 单写队列和固定读连接池未落实 | 并发顺序和背压不可控 |
| P1-03 | 重要 | CLI Adapter 未接入完整 Runtime Gateway | Prompt、沙箱、取消和恢复不安全 |
| P1-04 | 重要 | Rust Supervisor 与 health 不完整 | Sidecar 故障不能可靠恢复 |
| P1-05 | 重要 | Admin Web 与 Backend API 多处冲突 | 目录、发布和紧急禁用不可用 |
| P1-06 | 重要 | 备份恢复不满足一致性和安全要求 | 备份损坏、路径逃逸和恢复覆盖 |
| P1-07 | 重要 | 知识索引 Worker 和 LanceDB 对账不完整 | 索引损坏无法检测 |
| P1-08 | 重要 | Backend 迁移和生产部署不完整 | 无法可复现部署 |
| P1-09 | 重要 | 自动更新和失败回退未实现 | 无法满足更新策略 |
| P1-10 | 重要 | 错误响应可能泄露内部异常 | 路径和 Provider 信息泄露 |
| P1-11 | 重要 | 覆盖率、Lint、类型检查、E2E 和专项测试不足 | 无法证明符合设计 |
| P2-01 | 优化 | Desktop/Admin 路由偏离设计 | 用户流程与作用域混乱 |
| P2-02 | 优化 | React Query 与 Zustand 边界不完整 | 缓存串扰和状态重复 |
| P2-03 | 优化 | 前端 Bundle 过大 | 启动和更新成本偏高 |
| P2-04 | 优化 | README/质量状态容易失真 | 第三方被错误信息误导 |
| P2-05 | 优化 | 工作区包含生成物修改 | 审查和交付不可精确复现 |

---

## 6. P0 阻断问题详细分析与推荐方案

### P0-01：Desktop 登录注册与 Rust Command 冲突

#### 证据

- `apps/desktop/src/pages/LoginPage.tsx` 调用 `invoke('login')`。
- Rust 暴露的是 `auth_login`。
- `apps/desktop/src/pages/RegisterPage.tsx` 调用 `invoke('register')`。
- Rust 暴露的是 `auth_register`。
- Login 页面期待 `access_token`、`refresh_token`、`user_id` 等字段。
- Rust `LoginResult` 返回登录状态、Profile ID、脱敏标识和 Catalog sequence。
- Desktop 路由没有完整 `/auth/server`、`/auth/change-password` 和 `/offline-unlock`。

#### 原因

Tauri Command 名称和 DTO 由各层手写，TypeScript 的 `invoke<T>` 只能约束本地假设，无法证明 Rust 存在对应 Command 或返回相同结构。

#### 影响

- 登录和注册会触发未知 Tauri Command。
- 仅修改 Command 名称仍无法解决响应结构冲突。
- 强制改密错误地跳到设置页。
- Backend Origin 和离线 Profile 流程无法进入。

#### 推荐方案

1. 以设计方案 F.11 的 Rust Command 为唯一清单。
2. 为每个 Command 创建请求/响应 Schema。
3. 生成 TypeScript invoke wrapper，页面禁止手写 Command 字符串。
4. 实现固定流程：
   - 验证 Backend Origin；
   - Backend 登录；
   - Rust 验证 OfflineSessionTicket；
   - Keychain bundle 原子更新；
   - Catalog 获取和验签；
   - Profile meta 原子更新；
   - Sidecar 启动与数据库校验；
   - 首次 health；
   - 返回 `profile_opened`。
5. 强制改密进入独立页面，成功后继续执行登录后半段。

#### 验收标准

- 登录、注册、强制改密、在线/离线开 Profile、关闭和退出均有 Tauri 集成测试。
- 修改 Rust Command 但未更新生成 Client 时契约门禁失败。
- 任一后半段失败不得返回已打开状态。

---

### P0-02：WebView 保存 Token

#### 证据

`apps/desktop/src/stores/authStore.ts` 保存：

- `token`
- `refreshToken`

Login 页面把响应 Token 直接写入 Zustand。

设计方案要求：

- Access Token 只保存在 Rust 零化内存；
- Refresh Token 与 OfflineSessionTicket 作为一个 bundle 保存到 Keychain；
- WebView、SQLite、日志、Checkpoint 和诊断包不得读取明文。

#### 影响

- WebView XSS、调试工具或前端日志可以读取长期凭据。
- Refresh Token 与 OfflineSessionTicket 无法原子轮换。
- 前端状态模型诱导后续代码绕过 Rust 直接请求后台。

#### 推荐方案

1. 删除前端 Store 中全部 Token 字段。
2. Store 只保存 Profile 是否打开、脱敏标识和在线/离线状态。
3. 后台 HTTP 请求全部由 Rust `ApiClient` 发起。
4. Access Token 使用 `Zeroizing<String>`。
5. Refresh Token 和 OfflineSessionTicket 使用单个 Keychain JSON item。
6. 增加数据库、日志、RPC、Checkpoint 和诊断包敏感信息扫描。

#### 验收标准

- WebView 无法通过任何 API 获取 Token 明文。
- Desktop 构建产物不存在 Refresh Token 状态字段。
- 登录、刷新、退出和 Keychain 故障测试证明凭据不进入数据库或日志。

---

### P0-03：RPC、OpenAPI 和领域 Schema 生成体系缺失

#### 证据

- `packages/rpc-schema` 只有 `meta.schema.json`。
- 缺少每个 RPC 方法的 request/response Schema。
- 缺少 `ownership.v1.json` 和 `reverse-methods.v1.json`。
- Desktop、Rust、Sidecar 和 Admin 的 generated 目录不存在。
- `packages/contracts` 只有少量 RunEvent、两个知识事件和 Skill Manifest。
- Plan、Report、Review、Artifact、Approval、Catalog、Backup Schema 不完整。
- `scripts/check-contract-drift.sh` 在生成阶段失败。

#### 影响

- Command/RPC 名称、参数、枚举和响应在不同语言中漂移。
- 方法所有权、Supervisor-only 权限和 reverse allowlist 无法自动校验。
- 事件消费者可能遇到未登记 payload。
- 前端编译通过不能证明运行时调用有效。

#### 推荐方案

1. 按 J.14 建立完整方法 Schema。
2. 每个方法生成严格 request/response，禁止额外字段。
3. 建立 ownership 和 reverse method registries。
4. 补齐 DomainEvent、TaskPlan、ExecutionReport、ReviewReport、Artifact、Approval 和 Catalog Schema。
5. 生成：
   - Desktop TypeScript Client；
   - Rust DTO 与方法所有权表；
   - Sidecar Pydantic DTO；
   - Admin OpenAPI Client。
6. Drift 检查在临时目录生成后与仓库比较。
7. CI 校验未分配、重复分配、悬空引用和未生成代码。

#### 验收标准

- `scripts/check-contract-drift.sh` 返回 0。
- 修改 Schema 但不提交生成物时 CI 失败。
- 不存在的方法无法通过 TypeScript 或 Rust 编译。

---

### P0-04：Desktop 写 RPC 缺幂等键且存在无效方法

#### 证据

Rust `rpc_request` 明确要求写方法提供 `idempotency_key`，但大量页面和 Hook 没有传递，例如：

- `backup.create`
- `department.create`
- `employee.create`
- `workspace.apply`
- `workspace.abandon`
- `task.confirmPlan`
- `task.cancel`
- `knowledge.import`
- `knowledge.remove`

另有方法偏离文档：

- Diagnostics 页面经普通 RPC 调用 Supervisor-only `system.health`。
- Skills 页面调用不存在的 `skill.list/create/archive`。
- Workspace 页面调用未定义的 `workspace.list`。
- Agent 页面调用文档未定义的 `runtime.run/stop`。
- 部分 `task.confirmPlan` 只传 `name`，缺少公司、任务、员工和版本信息。

#### 影响

- 写操作在 Rust 边界直接返回 “write RPC requires idempotency key”。
- Supervisor-only 方法被错误暴露给 WebView。
- 页面出现 `METHOD_NOT_FOUND` 或 `INVALID_PARAMS`。
- 用户可见功能表面存在，但无法完成真实操作。

#### 推荐方案

1. 先完成 P0-03。
2. 生成 Client 自动为每次逻辑写请求产生 UUID 幂等键。
3. 相同用户操作重试必须复用相同幂等键。
4. Rust-owned/Supervisor-only 方法使用专用 Tauri Command。
5. 删除未在 J.14 定义的方法，或先修改并批准文档契约。
6. 对每个页面建立“页面操作 → 方法 → 参数 → 响应”契约测试。

#### 验收标准

- 所有写请求都有有效幂等键。
- WebView 无法调用 Supervisor-only 方法。
- 全部页面操作在真实 Rust-Sidecar 集成环境通过。

---

### P0-05：Catalog Release 不可变与签名链未实现

#### 证据

Backend 当前：

- Manifest 只有 `release_sequence` 和 `resources`；
- 使用普通 `json.dumps(sort_keys=True)`，不是 RFC 8785；
- 签名编码为 hex，不是 Base64；
- Release 创建将 `manifest_object_key` 保存为空；
- 发布只修改数据库状态；
- 公共 Manifest 接口从当前 published 资源表重新构建，而且不返回签名。

Rust `CatalogManifest` 只解析两个字段，缺少：

- `release_id`
- `created_at`
- `minimum_client_version`
- `signature_algorithm`
- `signature`
- 资源下载路径和对象 SHA。

#### 影响

- 历史 Release 会随资源表变化而改变。
- 客户端无法验证目录来源、完整性和 sequence 防回退。
- AgentRun 无法追溯到完整不可变目录。
- Skill 和模型能力的供应链信任不成立。

#### 推荐方案

1. 创建 Release 时冻结全部资源版本。
2. 为每类资源生成不可变 Bundle 并上传 MinIO。
3. 按设计 E.2 生成完整 Manifest。
4. 排除 `signature` 后执行 RFC 8785，再以 Ed25519 签名和 Base64 编码。
5. 数据库保存 Manifest object key、SHA、signature 和不可变 ReleaseItem。
6. 公共接口只返回已存储 Manifest，不得动态重建。
7. Rust 校验 Catalog Key 信任链、Manifest、sequence、最低客户端版本和资源哈希。
8. 全部验证成功后原子切换 active release。

#### 验收标准

- 发布后修改资源不会改变已有 Release。
- 任意 Manifest、签名、对象或 sequence 篡改都会被客户端拒绝。
- 离线模式只使用最近一次完整验证的 Release。

---

### P0-06：API Model 绕过 Rust Credential/Egress Broker

#### 证据

- Sidecar `run_executor.py` 从 RunSpec 读取 `model_binding.api_key`。
- `runtime/transport.py` 使用 `aiohttp` 直接请求 OpenAI/Anthropic。
- `aiohttp` 不在正式依赖中，mypy 也报告模块缺失。
- Rust Credential Broker 返回 `NotSupported`。
- Egress lease 的 `proxy_port` 为 0。
- ModelRuntime 以空工具表运行。
- `ASK` 权限没有暂停流程，只有 `DENY` 被阻止。

#### 影响

- API Key 可进入 SQLite、RunSpec、事件、异常或日志。
- Sidecar 绕过 Rust 域名白名单和网络审计。
- SSRF、DNS 重绑定、IP 直连和重定向越界无法防护。
- API Model 没有真实工具能力。
- ASK 操作可能在用户批准前执行。

#### 推荐方案

1. RunSpec 只保存 `credential_ref`。
2. Sidecar 通过 reverse RPC 请求 Rust 执行 Provider HTTP。
3. Rust 从 Keychain 临时读取凭据，完成域名、DNS、IP、重定向和 TLS 校验。
4. 删除 Sidecar 的真实 Provider 网络实现。
5. 为每个 Run 根据 ExecutionSnapshot 注册 Tool allowlist。
6. `ASK` 创建 HumanApproval 并进入 `waiting_approval`。
7. 只有有效 receipt 到达后恢复执行。

#### 验收标准

- 禁止 Sidecar 出站后 API Model 仍可通过 Rust Broker 工作。
- 数据库和日志扫描不到 API Key。
- SSRF 与网络越界测试全部失败关闭。
- ASK 在批准前无副作用。

---

### P0-07：Sidecar 后台 Worker 未启动

#### 证据

`sidecar/ibreeze/main.py` 只初始化数据库、Profile 和 RPC Server，没有启动：

- 分析 Outbox Consumer；
- Runtime Queue/Run Consumer；
- Projection Worker；
- Knowledge Index Worker；
- Backup Scheduler；
- Recovery/Reconciliation Worker；
- Worker heartbeat。

`run_consumer_loop` 虽然存在，但没有在主入口创建任务。

#### 影响

- 用户输入写入 Outbox 后无人生成 Plan Run。
- 调度产生的 queued Run 无人执行。
- 知识导入后不构建索引。
- 自动备份不运行。
- 重启后非终态任务不自动恢复。

#### 推荐方案

1. 建立 `SidecarApplication` 生命周期。
2. 启动时先完成 migration、Profile identity 和恢复对账。
3. 使用 `asyncio.TaskGroup` 启动全部 Worker。
4. Worker 使用 durable queue、lease、heartbeat、退避和 poison message 策略。
5. Worker 退出必须影响 `system.health`。
6. 关闭时先拒绝新写，再释放 lease，最后关闭数据库。

#### 验收标准

- 从真实 Sidecar 入口运行的集成测试能消费任务、Run、知识和备份任务。
- 强制终止后重启不会丢任务或重复副作用。
- Worker 退出能够被 health 和 Rust Supervisor 发现。

---

### P0-08：Plan 确认、资源快照和调度不是原子闭环

#### 证据

- RPC Handler 先调用 `confirm_plan`，再调用 `dispatch_company_task`。
- 两者分别提交事务。
- Dispatcher 在没有 active Catalog 时创建 fallback active release。
- AvailabilitySnapshot 写入 `overall_status='available'`，但 checks 内容为 pending。
- `expires_at` 与 `checked_at` 相同，Snapshot 立即过期。
- Plan Generator 持久化 `sections` 数组，但返回的 `department_tasks` 为空，不符合设计中的 CompanyPlan。
- Dispatcher 没有强制通过 PlanValidator 和真实职员可用性探测。

#### 影响

- 计划已经确认但调度失败，留下半状态。
- 并发确认可能重复创建任务。
- 没有可信 Catalog 或不可用职员仍可产生 Run。
- ExecutionSnapshot 无法证明资源在启动时真实可用。
- 计划结构无法直接驱动部门任务 DAG。

#### 推荐方案

1. Plan Generator 输出严格 CompanyPlan Schema。
2. 用户确认前执行完整外部可用性探测。
3. 在一个 Command Transaction 中完成：
   - expected version 与 Plan SHA 校验；
   - Plan Artifact 固化；
   - Workspace Grant 解析；
   - AvailabilitySnapshot 与 ExecutionSnapshot；
   - DepartmentTask、EmployeeTask 和依赖；
   - Runtime Queue；
   - DomainEvent、Outbox；
   - CompanyTask 状态更新。
4. 禁止 fallback Catalog；无可信 Release 时进入 `waiting_resource`。
5. Snapshot 使用合理短期有效期，启动 Run 时再次校验未过期。
6. 唯一约束和 idempotency result 防止重复确认。

#### 验收标准

- 每个注入点失败后数据库全有或全无。
- 同一版本并发确认只有一次成功。
- Snapshot 过期、资源不可用或 Catalog 不可信时不创建 Run。

---

### P0-09：Review 与最终报告门禁未落实

#### 证据

Run Executor 根据退出码直接推进 EmployeeTask、DepartmentTask 和 CompanyTask。

当前路径没有强制检查：

- Artifact 是否存在；
- ReviewAssignment 是否完整；
- Reviewer 是否不是 Artifact 贡献者；
- Review Run purpose；
- ReviewReport 是否绑定当前 Artifact SHA；
- blocker/high 是否全部 closed；
- 返修是否生成新 Artifact；
- 测试部是否基于测试用例复测；
- DepartmentReport 是否通过公司级 Review；
- FinalReport 是否满足全部闭环条件。

Report Generator 主要统计任务和 Artifact 数量，没有按 ExecutionReport/ReviewReport Schema 验证证据。

#### 影响

- Agent 进程退出码为 0 就可推动业务状态。
- 没有 Review 或仍存在严重问题时也可能生成报告。
- Artifact 更新后旧 Review 可能被继续引用。
- 总经理最终报告不能证明任务真正闭环。

#### 推荐方案

1. 分离 Run、EmployeeTask、Review 和业务阶段状态。
2. 所有状态转换进入统一状态机服务。
3. ReviewReport 提交时验证 assignment、reviewer、Run、Artifact SHA 和 report artifact。
4. 新 Artifact version 自动使旧 Review 失效。
5. blocker/high 必须关闭并绑定 resolution evidence。
6. 测试部复测必须引用固定测试用例和目标 Artifact。
7. FinalReport 前验证所有部门报告、Review 和问题状态。

#### 验收标准

- 缺少 Review、存在 blocker/high 或 Artifact SHA 改变时不能完成。
- 贡献者不能 Review 自己的 Artifact。
- FinalReport 的每个阻断条件都有自动化测试。

---

### P0-10：外部写入与审批 receipt 仍是 Stub

#### 证据

- Rust `handle_external_write_execute` 返回 `NotSupported`。
- 目标状态哈希固定为空字符串。
- process registered/exited Handler 不验证 PID、PGID、父进程和 executable。
- GrantStore 仅保存在 Rust 内存，没有 Security Scoped Bookmark。

#### 影响

- 工作区外审批允许后仍无法执行。
- 无法覆盖“副作用已完成但响应丢失”的恢复。
- 目标变化和 staging 篡改无法可靠识别。
- 应用重启后 Workspace 授权丢失。

#### 推荐方案

1. 使用 Security Scoped Bookmark 持久化用户授权。
2. Rust 执行前验证 session、approval、run、operation、过期时间、目标旧状态和 staging。
3. create/replace 校验 source realpath、SHA、size 和 symlink。
4. 为单一目标生成临时 Seatbelt Profile。
5. 原子执行并 fsync。
6. 返回 result state SHA 和 receipt SHA。
7. 重试时区分未执行、已达到目标状态和目标被第三方修改。
8. 使用系统进程信息验证通知。

#### 验收标准

- 只能修改审批唯一目标。
- 过期、路径逃逸、staging 篡改和目标变化全部被拒绝。
- 响应丢失后重试不产生第二次副作用。

---

### P0-11：总验证脚本吞掉失败

#### 证据

`scripts/verify-all.sh` 的关键命令都采用：

```bash
command || echo "skipped"
```

因此 lint、typecheck、test、coverage、E2E 和工具缺失都不会导致总脚本失败。

#### 影响

- 失败提交可被误认为全部通过。
- CI 和 README 可能引用错误状态。
- “No tests found” 和缺少覆盖率工具被静默跳过。

#### 推荐方案

1. 删除所有关键门禁后的吞错逻辑。
2. 缺少工具、目录、依赖和测试均直接失败。
3. 每个应用使用独立 CI Job。
4. 保存 JUnit、coverage、SARIF、E2E、性能和灾备制品。
5. 为门禁脚本自身编写失败传播测试。
6. 删除安全 Workflow 的 `continue-on-error: true`。

#### 验收标准

- 任一子门禁失败时总脚本和 CI 返回非零。
- `No tests found` 必须阻断。
- 只有全部 Job 通过才允许生成 Release。

---

## 7. P1 重要问题详细分析与推荐方案

### P1-01：SQLite 正式迁移体系缺失

#### 现状

- `local_db.py` 使用超大 `_CREATE_TABLES_SQL` 每次启动建表。
- 启动时执行 opportunistic `ALTER TABLE`。
- `sidecar/migrations` 没有实施计划规定的十个顺序迁移。
- 没有 migration hash、running/failed 状态、升级前备份和中断恢复。
- 没有严格校验固定 SQLite 版本、JSON1 和 FTS5。

#### 推荐方案

- 建立按时间排序的正式 migration 文件。
- 记录 version、filename、SHA、状态和时间。
- 升级前使用 SQLite Online Backup。
- running 中断、hash drift、foreign key check 失败进入 recovery。
- 固定并探测 SQLite `>=3.45,<3.46`、JSON1 和 FTS5。

#### 验收标准

- 空库和上一版本均可升级。
- 修改历史 migration 后拒绝打开。
- 升级失败保持原 Profile 可恢复。

---

### P1-02：单写队列和固定读池未落实

#### 现状

- Service 可直接使用写连接并 commit。
- 没有容量 32 的统一单写队列。
- Read Pool 为空时会额外创建连接，突破上限 8。
- 连接借出/归还没有完整校验 `defer_foreign_keys=0`。

#### 推荐方案

- 所有 Command 经容量 32 的队列串行写入。
- 读池固定 8，空池阻塞等待。
- 借出、归还和创建时验证 PRAGMA。
- 外键状态泄漏时回滚、关闭连接并降级 health。

---

### P1-03：CLI Adapter 未接入完整 Runtime Gateway

#### 现状

- Prompt 直接放在 argv 中。
- CLI 使用简化命令映射，没有完整 Adapter parser。
- 没有 Task Worktree、Seatbelt 和真实 Egress lease。
- 没有可靠 native session/Checkpoint 恢复。
- Process Supervisor 仍有 Seatbelt TODO。

#### 推荐方案

- 为 Codex CLI、Claude Code、OpenCode 分别实现固定 Adapter。
- Prompt 通过 stdin 或 0600 临时文件传递。
- 每个 Subtask 使用 Worktree 或快照工作区。
- 运行于 Seatbelt 和 Rust Egress Broker 下。
- 持久化 native session、PID/PGID、start time 和 checkpoint。
- 使用 fake CLI 契约测试及真实 CLI 发布冒烟。

---

### P1-04：Rust Supervisor 与 health 不完整

#### 现状

- `check_health` 存在，但登录开 Profile 流程未严格保证首次 healthy 后才返回。
- 正常启动被计入 restart tracker。
- 缺少稳定 5 秒心跳、3 秒超时和完整自动重启流程。
- process notifications 不验证。

#### 推荐方案

- 区分初次启动、手动重开和异常重启。
- Handshake 后必须等待首次 healthy。
- 运行常驻 heartbeat。
- 失败时终止进程组、执行恢复对账后重启。
- 超过重启上限进入 recovery。

---

### P1-05：Admin Web 与 Backend API 多处冲突

#### 证据

- Admin 调用 GET `/catalog/releases`，Backend 没有管理员 Release 列表路由。
- 紧急禁用 UI 发送资源类型、资源 ID、版本、原因和 code，Backend 只接受 `skill_ids`。
- Agent/Provider 页面调用单资源 publish，与 Catalog Release 发布机制冲突。
- Skill UI 和 Backend multipart ZIP 上传契约不一致。
- Admin API Client 没有 Idempotency-Key、If-Match 和一次 refresh 重试。

#### 推荐方案

1. 从 Backend OpenAPI 生成 Admin Client。
2. 删除手写 endpoint 与 DTO。
3. 目录统一采用 draft → validated → Release publish。
4. 实现完整紧急指令 resource/action/version/sequence/signature。
5. Skill 使用 multipart 上传。
6. 写请求自动添加 Idempotency-Key，更新/删除使用 If-Match。

---

### P1-06：备份恢复不满足一致性和安全要求

#### 证据

- 使用 `shutil.copy2` 复制运行中的 SQLite。
- 没有 snapshot barrier 和 Online Backup。
- 没有收集引用 CAS、Catalog 和 Skill lock。
- Validator 使用 `tar.extractall`。
- Restore 切换顺序不能保证失败时原 Profile 不变。

#### 推荐方案

- 暂停新写并等待当前事务。
- 使用 SQLite Online Backup。
- 收集全部被引用外部对象。
- 生成逐文件 SHA Manifest 和 tar.zst。
- 解包前验证路径、链接、大小、数量和哈希。
- staging 完成完整 integrity/migration/foreign-key 校验。
- 原子执行 active → restore-before、staging → active。

---

### P1-07：知识索引 Worker 和 LanceDB 对账不完整

#### 现状

- Embedding 已恢复为 384 维并通过当前测试。
- Knowledge Worker 未从主入口启动。
- 对账仍使用 `lance_count = sqlite_count` 占位。
- 无法检测 LanceDB 丢失、ID/hash 不一致或 generation 损坏。

#### 推荐方案

- generation 保存模型、维度、source sequence 和 ID/hash 集合。
- Worker 从一致读快照创建 building generation。
- LanceDB 与 FTS5 都成功后原子切换 active。
- 对账真实读取 LanceDB，不使用 SQLite 数量代替。
- 覆盖空 generation、构建中断和索引损坏恢复。

---

### P1-08：Backend 迁移和生产部署不完整

#### 现状

- Backend 只有一个 `001_initial.py` Alembic revision。
- 没有完整 `deploy/docker-compose.yml`。
- Backend Dockerfile 没有非 root、只读根文件系统、健康检查和多阶段构建。
- 缺少 PostgreSQL、MinIO、Admin、API 和 Nginx 的完整部署。

#### 推荐方案

- 拆分用户、目录和 Release Alembic revisions。
- 验证空库和上一 head 升级。
- 提供固定 digest 的五服务 Compose。
- 镜像使用多阶段、非 root 和只读根文件系统。
- Secret 以只读 volume 注入。
- Migration 使用独立一次性 Job。
- 提供部署、升级、备份和恢复演练。

---

### P1-09：自动更新和失败回退未实现

#### 证据

- `updater_install` 返回 `NotSupported`。
- 更新检查没有完成签名 Manifest 和安装包验证。
- 没有缓存上一稳定安装包。
- 新版启动失败后没有恢复界面和回退流程。

#### 推荐方案

- 实现签名更新 Manifest、安装包 SHA 和签名验证。
- 安装前缓存当前稳定安装包并备份 Profile 数据库。
- 新版首次启动验证协议、migration 和 health。
- 失败进入恢复界面，由用户使用缓存安装包恢复应用。
- 数据库只采用前向兼容迁移。

---

### P1-10：错误响应可能泄露内部异常

#### 现状

Run Executor 和部分 RPC Handler 会把 `str(exc)` 作为错误 detail 或 code 返回。

#### 推荐方案

- 使用固定 Problem/RPC Error code。
- 未知异常只返回 reference ID 和通用信息。
- 详细异常进入脱敏日志。
- 对路径、SQL、Token、API Key、Prompt 和消息正文执行结构化脱敏。

---

### P1-11：质量证据不足

#### 现状

- Backend 覆盖率 61.32%。
- Sidecar 覆盖率 79.28%。
- Desktop 1.75%，Admin 2.86%。
- Rust 覆盖率未验证。
- 两个前端 ESLint 无法启动。
- Backend mypy 126 errors，Sidecar mypy 57 errors。
- Playwright 没有测试。
- `tests/faults`、`tests/performance`、`tests/release` 等计划交付物缺失。

#### 推荐方案

1. 修复现有 lint、typecheck、fmt 和 warning。
2. 按设计 K.15 追踪矩阵补齐单元测试。
3. 建立 PostgreSQL/MinIO 集成测试。
4. 建立 Rust-Sidecar UDS 集成测试。
5. 建立 Desktop/Admin 组件和主流程 E2E。
6. 补齐真实 CLI、安全、故障、性能、更新和灾备门禁。
7. 覆盖率排除统一进入 `coverage-exclusions.yml`。

#### 验收标准

- 各语言达到文档定义的 100% 单元覆盖率。
- E2E、安全、故障、性能和恢复独立通过。
- 所有报告绑定 commit SHA。

---

## 8. P2 优化问题详细分析与推荐方案

### P2-01：Desktop/Admin 路由偏离设计

Desktop 使用 `/login`、`/register`、`/departments` 等扁平路由，缺少 Backend Origin、强制改密、离线解锁和公司作用域嵌套路由。Admin 使用 `/login` 而不是统一 `/admin/*`。

推荐：

- 按 K.1/K.7 建立固定路由表。
- Company ID 进入部门、职员、会话、任务、Review 和 Workspace 路由。
- 认证、Profile 和 Company 分别使用独立 Guard。
- 未选择 Company 时禁止访问公司业务页面。

---

### P2-02：React Query 与 Zustand 边界不完整

现状：

- Query Key 没有统一包含 backend origin、app user、Profile 和 company。
- 服务端/Sidecar 实体状态与 Zustand 状态有重复。
- 默认 retry 为 1，与文档读取网络错误重试 2 次不一致。

推荐：

- 事实数据只进入 TanStack Query。
- Zustand 只保存 UI 和非敏感本地状态。
- 建立统一 Query Key factory。
- GET 仅对网络错误重试两次，写操作不自动重试。

---

### P2-03：前端 Bundle 过大

本轮构建：

- Desktop 主 Bundle 约 1.40 MB，gzip 约 433 KB。
- Admin 主 Bundle 约 1.36 MB，gzip 约 424 KB。

推荐：

- 路由页面使用 `React.lazy`。
- Ant Design、图表和编辑器按页面拆分。
- 配置 manual chunks 和 Bundle size budget。
- 该优化应在功能与安全问题修复后执行。

---

### P2-04：README 与质量状态容易失真

手写 passed 数量和全绿状态会随测试变化而过期，部分文档链接也可能不存在。

推荐：

- README 使用 CI badge 和制品链接。
- 不手工维护具体通过数量。
- 发布流水线自动生成质量摘要。
- 对所有文档链接增加 CI 检查。

---

### P2-05：工作区包含生成物修改

审查时存在修改后的 `tsconfig.tsbuildinfo` 和 E2E 结果目录。这些文件由本地构建/测试产生，会干扰清洁工作区判断。

推荐：

- 判断这些生成物是否应提交；不应提交则加入 `.gitignore`。
- 正式验收必须在清洁 worktree 运行。
- 报告、测试制品和发布包绑定同一个 commit SHA。

---

## 9. 推荐整改顺序

### 阶段 1：建立可信质量门禁

1. 修复 `verify-all.sh` 假阳性。
2. 修复 Desktop/Admin ESLint 配置。
3. 修复 Ruff、mypy、Rust fmt 和测试 warning。
4. 固定并安装 nextest、llvm-cov 和 Playwright 环境。
5. 缺少工具和测试必须直接失败。

完成标准：后续任何失败都能被 CI 真实阻断。

### 阶段 2：契约优先

1. 完整建立 RPC/OpenAPI/领域 Schema。
2. 生成所有语言 Client 和 DTO。
3. 启用 ownership、reverse method 和 drift 门禁。
4. 删除手写 RPC 方法名和重复 DTO。

完成标准：多语言契约只有一个事实源。

### 阶段 3：认证、Catalog 和凭据边界

1. 修复 Desktop/Rust 认证调用。
2. 删除 WebView Token。
3. 完成 Keychain bundle。
4. 实现不可变 Catalog Release。
5. 完成 Rust Catalog 验签。
6. 完成 Credential/Egress Broker，移除 Sidecar 直连网络。

完成标准：认证与目录供应链满足安全设计。

### 阶段 4：本地基础设施

1. 正式 SQLite migration runner。
2. 容量 32 单写队列和固定读池。
3. Sidecar Application Lifecycle 和 Worker。
4. Supervisor heartbeat 与恢复对账。
5. Workspace Bookmark、Seatbelt、进程监管和外部写 receipt。

完成标准：本地事实和副作用可恢复、可审计。

### 阶段 5：业务闭环

1. 严格 CompanyPlan。
2. 原子 `task.confirmPlan`。
3. Availability/Execution Snapshot。
4. Department/Employee Task DAG。
5. Artifact、Review、返修和复测状态机。
6. DepartmentReport 和 FinalReport。

完成标准：标准研发流程能够从用户输入运行到最终报告。

### 阶段 6：产品界面和后台

1. 对齐 Desktop 路由、RPC 和 Query Key。
2. 对齐 Admin OpenAPI 和页面。
3. 完成 Catalog Release、紧急禁用和 Skill 上传。
4. 完成错误态、空态、权限态和恢复界面。

完成标准：文档中全部页面和用户流程通过 E2E。

### 阶段 7：交付与发布

1. 完成知识 generation 和备份恢复。
2. 完成生产部署。
3. 完成自动更新和失败回退。
4. 达到 100% 单元覆盖率。
5. 补齐集成、E2E、安全、故障、性能和灾备。
6. 在清洁提交上执行独立全量 Review。

完成标准：设计方案 K.17 和实施计划第 21 章全部有可追溯证据。

---

## 10. 最终验收条件

只有同时满足以下条件，才能判定“代码实现与设计方案、实施计划一致”：

1. OpenAPI、RPC、JSON Schema、事件注册表和生成代码无漂移。
2. Desktop、Rust、Sidecar、Backend 和 Admin 不再手写互相冲突的 DTO。
3. Backend 不保存任何公司业务数据。
4. WebView、Sidecar、SQLite、日志和诊断包不出现 Token/API Key。
5. Catalog、Skill、更新包和紧急指令具有完整签名链。
6. 用户任务可以完成计划确认、执行、Review、返修、复测和最终报告闭环。
7. Sidecar 重启、网络中断和 Provider 中断可以安全恢复。
8. Workspace 外部写入只由一次性审批和可信 receipt 执行。
9. 备份损坏或恢复失败不影响原 Profile。
10. 各语言达到文档规定的 100% 单元覆盖率。
11. 集成、E2E、安全、故障、性能、更新和灾备门禁全部通过。
12. 总验证脚本在任一失败时返回非零。
13. 正式验收基于清洁、可复现的 commit。

---

## 11. Review 结论

设计方案和实施计划之间没有发现重大功能冲突，两份文档可以继续作为实施基线。

当前代码已经具备较多模块骨架和局部功能，Sidecar 当前 1021 个测试也已全部通过，但“现有测试通过”不能证明系统已按文档完成。认证入口、凭据边界、契约生成、Catalog 信任链、API Model 网络安全、Sidecar Worker、原子调度、Review 闭环、外部写入和发布门禁仍存在阻断问题。

在全部 P0 问题关闭、P1 问题完成验证且所有发布门禁获得可信证据之前，当前项目不应被认定为可生产部署或可按设计方案完整交付。
