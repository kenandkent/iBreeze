# iBreeze 五项核心架构重构设计方案

版本：1.0

文档状态：正式目标架构

适用基线：Git `9a158ff`

目标读者：架构师、Rust 开发、Python 开发、桌面开发、测试、安全与第三方实施团队

关联文档：

- `docs/设计方案/AI公司桌面应用设计方案.md`
- `docs/设计方案/AI公司桌面应用-实施计划.md`
- `docs/superpowers/plans/2026-07-28-ibreeze-five-core-architecture-rewrite.md`
- `docs/review报告/AI公司桌面应用-二次全量复核报告.md`

## 1. 文档效力与实施边界

本文档是《AI公司桌面应用设计方案.md》针对以下五项核心缺口的规范性细化，二者具有同等约束力：

| 编号 | 核心缺口 |
|---|---|
| CUR-P0-01 | API Model Credential Broker、HTTP Broker 与 Egress Proxy 未实现 |
| CUR-P0-02 | RPC Schema、Domain Event、生成代码与运行时校验不完整 |
| CUR-P0-05 | SQLite 初始化、Migration、WriteQueue、Worker 与 Health 生命周期不统一 |
| CUR-P1-01 | CLI Runtime、Workspace、Seatbelt、Egress、取消和恢复未闭环 |
| CUR-P1-02 | Review、返工、任务完成与报告状态机未形成权威事务入口 |

实施团队必须同时满足两份设计文档。本文第 4–19 节是上述五项子系统的字段级、协议级和生命周期级实现规范；主设计负责完整产品边界及其余子系统。两份文档已经按该分工对齐，不提供“任选其一”或“以更严格者为准”的解释空间。未来若发现同一字段、状态边、路径或时序存在不一致，实施必须立即阻断并先修正文档，禁止第三方自行选择。

本次按全新项目实施，固定规则如下：

1. 不迁移任何现有 Profile 数据。
2. 不保留旧 SQLite Schema、旧 RPC、旧 DTO、旧 Adapter、stub、兼容层或 Feature Flag。
3. 删除占位实现后一次性切换到目标架构，主分支不得存在新旧双轨。
4. 新数据库只由新的 `001_initial.sql` 创建。
5. 开发和测试环境中的旧 Profile、CAS、Worktree 与索引数据由一次性清理脚本删除；正式运行时代码不得内置“自动删除未知用户数据”的逻辑。
6. 首个对外发布版本只识别 `schema_epoch=1`。检测到其他 epoch 时返回 `PROFILE_SCHEMA_UNSUPPORTED`，不尝试猜测字段或自动迁移。
7. 文档中的路径、类型、字段、状态、错误码和顺序均为固定要求，不允许第三方替换为“等价方案”。
8. 桌面构建固定 `aarch64-apple-darwin` 与 `MACOSX_DEPLOYMENT_TARGET=14.0`；v1 支持 macOS 14.x、15.x、26.x，发布安全矩阵固定使用真实 Apple Silicon 的 macOS 14 和 macOS 26 runner。

## 2. 目标与非目标

### 2.1 目标

1. API Model 职员可在 Sidecar 永不接触 API Key 的前提下完成含流式输出和 Tool Call 的完整 Agent Loop。
2. Codex CLI、Claude Code、OpenCode 在真实 Workspace、Seatbelt 与每 Run Egress Proxy 下执行、取消和恢复。
3. RPC、反向 RPC、Domain Event、错误码、Rust/Python/TypeScript 类型全部从单一 Registry 生成。
4. Profile 初始化、Migration、读写连接、WriteQueue、Outbox、Worker 和 Health 由一个 Application Lifecycle 管理。
5. 所有业务状态变更通过 Command Bus、Unit of Work 和不可变状态迁移表完成。
6. Run 退出只记录运行结果，不能绕过 Review 与证据门禁直接完成业务任务。
7. 所有核心路径具有正例、负例、故障注入、安全和端到端测试，且进入唯一 fail-closed 质量入口。

### 2.2 非目标

1. 不支持旧 Profile 数据迁移。
2. 不支持 Windows 或 Linux 沙箱；v1 固定 macOS Apple Silicon，最低部署目标 macOS 14.0，支持系列为 14.x、15.x、26.x。
3. 不让 Python Sidecar 读取 Keychain 或直接访问公网模型端点。
4. 不把 Review 状态机移动到 Rust。
5. 不把公司业务数据移动到中心后台。
6. 不提供任意 CLI 命令模板、任意 Provider URL 或任意网络白名单。
7. 不实现分布式数据库、远程 Sidecar、多 Profile 共用 Sidecar 或多写者。

## 3. 总体目标架构

```text
┌──────────────────────────────────────────────────────────────────────┐
│ React WebView                                                        │
│ GeneratedRpcClient + Query Cache + Views                             │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ Tauri Command
┌──────────────────────────────▼───────────────────────────────────────┐
│ Rust Trusted Host Kernel                                             │
│ Profile/Keychain │ Duplex UDS │ Credential HTTP Broker               │
│ CONNECT Egress   │ Process Supervisor │ Seatbelt │ External Write    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ authenticated framed UDS
┌──────────────────────────────▼───────────────────────────────────────┐
│ Python Sidecar Domain Kernel                                         │
│ Generated Dispatcher │ Command Bus │ Unit of Work │ Query Service    │
│ Orchestration │ Built-in Agent Loop │ Review Engine │ Worker Supervisor│
└──────────────────────────────┬───────────────────────────────────────┘
                               │ single-writer / read pool
┌──────────────────────────────▼───────────────────────────────────────┐
│ Profile Persistence Kernel                                           │
│ SQLite WAL │ WriteQueue │ Event Store │ Outbox │ CAS │ Search Index  │
└──────────────────────────────────────────────────────────────────────┘

                     signed HTTPS catalog only
Rust Trusted Host Kernel ───────────────────────────────────────────────►
                     iBreeze Backend API
```

### 3.1 信任边界

| 组件 | 可以持有 | 禁止持有 |
|---|---|---|
| WebView | Access Token 的内存态、非敏感页面数据 | Refresh Token、API Key、CLI 凭据、代理 Token |
| Rust Core | Keychain 明文的短时零化对象、代理 Token、进程句柄 | 公司业务状态机、直接修改业务 SQLite |
| Sidecar | `credential_ref`、目录快照、业务数据、Run 状态 | API Key、Refresh Token、Keychain handle、直接公网 socket |
| SQLite | 业务数据、`credential_ref`、非敏感审计 | API Key、代理 Token、CLI 登录 Cookie |
| 中心后台 | 用户、Agent/Model/Provider/Skill 目录 | 公司、部门、职员实例、任务、会话和 Workspace |

### 3.2 单向依赖

```text
domain ← application ← rpc
domain ← application ← runtime
domain ← application ← workers
contracts-generated ← rpc/runtime
persistence ← application
Rust security kernel ← Rust command/rpc
```

领域模块禁止 import RPC、Tauri、HTTP、Keychain 或具体 CLI Adapter。Repository 禁止决定状态迁移。Adapter 禁止直接修改业务表。

## 4. 代码目录与唯一所有权

### 4.1 Contracts

```text
packages/
├── rpc-schema/
│   ├── registry.v1.json
│   ├── reverse-methods.v1.json
│   ├── error-codes.v1.json
│   ├── meta.schema.json
│   └── methods/<method>.request|response.schema.json
└── contracts/
    ├── domain-events/
    │   ├── registry.v1.json
    │   └── <event-type>.v1.schema.json
    ├── fixtures/
    │   ├── rpc/
    │   ├── reverse-rpc/
    │   └── domain-events/
    └── scripts/
        ├── validate-registry.mjs
        ├── generate-contracts.mjs
        └── verify-generated.mjs
```

RPC 与错误码以 `packages/rpc-schema` 为唯一根；Domain Event 与业务 Artifact Schema 以 `packages/contracts` 为唯一根。禁止再创建第三个契约根或在应用目录手写平行 Registry。

### 4.2 Rust Trusted Host Kernel

```text
apps/desktop-core/src/
├── ipc/
│   ├── connection.rs
│   ├── frame.rs
│   ├── multiplexer.rs
│   ├── dispatcher.rs
│   ├── pending.rs
│   └── session.rs
├── broker/
│   ├── credential.rs
│   ├── http.rs
│   ├── http_stream.rs
│   ├── egress.rs
│   ├── dns_policy.rs
│   └── lease.rs
├── runtime/
│   ├── process_supervisor.rs
│   ├── process_registry.rs
│   ├── seatbelt.rs
│   ├── invocation.rs
│   └── cancellation.rs
├── security/
│   ├── keychain.rs
│   ├── external_write.rs
│   ├── path_policy.rs
│   └── redaction.rs
└── generated/contracts/
```

删除现有 `rpc/reverse.rs`；反向方法的生成路由固定由 `ipc/dispatcher.rs` 实现，Credential、Egress、Process 与 External Write 业务逻辑分别委托给唯一所有权模块。

### 4.3 Python Sidecar Domain Kernel

```text
sidecar/ibreeze/
├── application/
│   ├── app.py
│   ├── lifecycle.py
│   ├── command_bus.py
│   ├── query_bus.py
│   ├── unit_of_work.py
│   └── health.py
├── persistence/
│   ├── database.py
│   ├── migrations.py
│   ├── write_queue.py
│   ├── read_pool.py
│   ├── outbox.py
│   └── migrations/001_initial.sql
├── rpc/
│   ├── server.py
│   ├── dispatcher.py
│   ├── validation.py
│   └── reverse_client.py
├── runtime/
│   ├── gateway.py
│   ├── run_service.py
│   ├── model_loop.py
│   ├── process_client.py
│   ├── event_normalizer.py
│   ├── checkpoint.py
│   └── adapters/
├── review/
│   ├── commands.py
│   ├── policies.py
│   ├── transitions.py
│   ├── completion_gate.py
│   └── projections.py
├── workers/
│   ├── supervisor.py
│   ├── runtime.py
│   ├── analysis.py
│   ├── outbox.py
│   ├── knowledge.py
│   ├── backup.py
│   └── event_compaction.py
└── generated/contracts/
```

根级 `local_db.py` 与 `rpc_server.py` 在迁移完成后删除，禁止继续作为巨型兼容入口。

## 5. Canonical Contract Registry

### 5.1 Registry 是唯一事实来源

`packages/rpc-schema/registry.v1.json` 的每个条目固定包含：

```json
{
  "method": "review.submit",
  "owner": "sidecar",
  "kind": "write",
  "scope": "company",
  "request_schema": "methods/review.submit.request.schema.json",
  "response_schema": "methods/review.submit.response.schema.json",
  "idempotency_ttl_seconds": 2592000,
  "allowed_errors": [
    "VALIDATION_FAILED",
    "RESOURCE_NOT_FOUND",
    "REVIEW_SELF_ASSIGNMENT",
    "STATE_TRANSITION_INVALID",
    "OPTIMISTIC_LOCK_CONFLICT"
  ],
  "empty_request": false
}
```

字段规则：

- `method` 使用 `<domain>.<verb>`，大小写与设计方案 J.14 完全一致。
- `owner` 只允许 `rust`、`sidecar`、`supervisor`。
- `kind` 只允许 `read`、`write`、`stream`。
- `scope` 只允许 `none`、`profile`、`company`。
- `write` 必须配置非零 idempotency TTL。
- `company` scope 的 request 必须包含 required `company_id`。
- `empty_request=true` 时 request schema 必须是 `maxProperties:0` 的封闭对象。
- `allowed_errors` 必须全部存在于 `error-codes.v1.json`。

### 5.2 精确公开方法集合

公开方法集合固定等于《AI公司桌面应用设计方案.md》J.14。以下当前原型方法不得进入公开 Registry：

```text
artifact.create
artifact.get
backup.get
catalog.get
catalog.list
departmentTask.get
departmentTask.list
employee.archive
employee.updateWorkRole
employeeTask.get
employeeTask.list
knowledge.get
report.generateDepartment
report.generateFinal
review.assign
review.get
review.list
task.supersede
planVersion.list
orchestration.list
orchestration.listRuns
orchestration.create
orchestration.run
orchestration.archive
```

上述能力如为内部流程所需，只能实现为 Sidecar Application Command/Query，不得让 WebView 跳过状态机调用。

### 5.3 Schema 完整性

每个 request/response schema 必须：

1. 使用 JSON Schema 2020-12。
2. 根对象设置 `additionalProperties:false`。
3. 明确 `required`、`format`、枚举、长度、数值范围与分页上限。
4. UUID 固定 `format:"uuid"`。
5. UTC 时间固定 `format:"date-time"` 并由自定义检查器要求 `Z`。
6. SHA-256 固定 `pattern:"^[0-9a-f]{64}$"`。
7. Cursor 是 opaque string，禁止前端解释。
8. Response 不得使用无边界 `object`、`array` 或 `additionalProperties:true` 承载领域实体。

当前 76 个空对象必须逐一处理：

- 真正无参数的方法设置 `empty_request=true` 和 `maxProperties:0`；
- 其余方法按 J.14、相关 DDL 与状态机补齐字段；
- 任何 response 不允许为空对象；
- 生成器发现未声明空对象时立即退出非零。

`review.submit.request` 固定为：

```json
{
  "company_id": "uuid",
  "assignment_id": "uuid",
  "reviewer_run_id": "uuid",
  "reviewed_artifact_id": "uuid",
  "reviewed_sha256": "64-char-lower-hex",
  "report_artifact_id": "uuid",
  "verdict": "pass|needs_changes|failed",
  "issues": [],
  "expected_assignment_version": 1
}
```

`issues[]` 固定包含：

```json
{
  "client_issue_id": "uuid",
  "severity": "blocker|high|medium|low",
  "category": "functional|security|performance|reliability|maintainability|documentation|test|contract|review_execution",
  "description": "1..20000",
  "expected": "1..10000",
  "actual": "1..10000",
  "evidence_refs": ["uuid"],
  "suggested_fix": "1..20000",
  "assignee_employee_id": "uuid|null"
}
```

### 5.4 Domain Event Registry

`packages/contracts/domain-events/registry.v1.json` 是事件注册数据，不是 Registry 自身的 schema。每条记录包含：

```json
{
  "event_type": "review.submitted",
  "version": 1,
  "producer": "review.submit",
  "payload_schema": "domain-events/review.submitted.v1.schema.json",
  "requires_company_id": true,
  "consumers": ["review_projection", "completion_projection"]
}
```

v1 event type 集合固定为：

```text
company.created
company.updated
company.archived
department.created
department.updated
department.archived
department.leader_changed
department.responsibility_changed
employee.created
employee.updated
employee.transferred
employee.status_changed
company_task.status_changed
department_task.status_changed
employee_task.status_changed
plan.analyzed
plan.confirmed
plan.rejected
plan.revision_requested
run.queued
run.leased
run.started
run.checkpointed
run.cancelled
run.failed
run.completed
artifact.created
artifact.superseded
artifact.verified
review.assigned
review.submitted
review.staled
review.issue_changed
approval.requested
approval.resolved
approval.consumed
approval.expired
report.generated
report.published
knowledge.imported
knowledge.indexed
knowledge.removed
backup.created
backup.verified
backup.restored
```

状态事件 payload 必须包含 `aggregate_id/from_state/to_state/version`。`run.completed` payload 必须包含 `run_id/status:'succeeded'/evidence_artifact_ids`，该事件不能代表业务 Task 完成。`review.issue_changed` payload 必须包含 `issue_id/from_state/to_state/severity/assignee_employee_id/evidence_refs`，其中 `evidence_refs` 是至少一个 Artifact UUID 的去重数组。

Registry 中每个事件必须存在 payload schema、合法 fixture、非法 fixture、生产者和至少一个消费者。无消费者的审计事件必须显式声明 `consumers:["audit_only"]`。

### 5.5 生成与运行时校验

生成顺序固定为：

```text
validate registry
→ validate every schema
→ validate positive/negative fixtures
→ generate Rust/Python/TypeScript
→ format generated code
→ compile generated code
→ compare method/event/error sets
→ git diff --exit-code
```

生成器遇到未知 `$ref`、循环引用无法展开、未识别 format、重复 `$id`、未登记方法或空 response 时必须失败，禁止退化为 `serde_json::Value`、`Any` 或 `unknown`。

运行时边界固定：

- Rust 收到 WebView 请求后先用生成类型反序列化。
- Sidecar Dispatcher 再按生成 Pydantic 类型校验请求。
- Handler 只能返回生成 response 类型。
- 测试、开发和 Release Candidate 对序列化结果再次执行 JSON Schema 校验。
- 生产环境对认证、安全、审批、Review、Workspace 写、Runtime 方法保留双向 JSON Schema 校验。

## 6. Duplex UDS 架构

### 6.1 单连接双向多路复用

Rust 启动 Sidecar 后只建立一条已认证 UDS。该连接同时承载：

- WebView → Rust → Sidecar 的正向 RPC；
- Sidecar → Rust 的反向 RPC；
- 双向 notification；
- HTTP Broker 流式事件；
- heartbeat 和 shutdown。

禁止为 Credential Broker、Egress 或进程通知另开未认证 socket。

### 6.2 帧格式

固定为 4 字节无符号大端长度加一个 UTF-8 JSON 对象。长度最大 16 MiB；0、超限、非法 UTF-8、顶层非对象或批量 JSON-RPC 立即断开。v1 不压缩帧。

JSON-RPC request：

```json
{
  "jsonrpc": "2.0",
  "id": "core:uuid|sidecar:uuid",
  "method": "credential.http.start",
  "params": {},
  "meta": {
    "trace_id": "uuid",
    "ipc_session_id": "uuid",
    "window_session_id": "uuid|null",
    "idempotency_key": "uuid|null",
    "deadline_at": "RFC3339-Z"
  }
}
```

Rust request id 固定 `core:{uuid}`，Sidecar request id 固定 `sidecar:{uuid}`。Response 必须复用原 id。Notification 省略 id。流式数据使用带 `request_id/sequence` 的 notification，不增加私有帧类型。

### 6.3 Multiplexer 状态

每端维护：

```text
ConnectionGeneration
PendingRequests<id, deadline, response_sender, cancellation_token>
ActiveStreams<request_id, next_sequence, stream_sender>
SessionCancellationToken
```

连接断开时：

1. 原子增加 generation。
2. 取消全部 active stream。
3. 全部 pending request 返回 `IPC_CONNECTION_LOST`。
4. 撤销当前 session 创建的 Credential/Egress lease。
5. 终止当前 session 注册的 CLI 进程组。
6. Rust 按 Sidecar restart policy 决定重启；禁止在新 session 恢复旧代理 Token。

### 6.4 背压与超时

- 每方向 pending request 上限 256。
- 每个 stream 缓冲 64 帧。
- 超限返回 `IPC_BACKPRESSURE`，不得无限排队。
- deadline 由发起方写入；接收方使用 `min(request deadline, method hard timeout)`。
- heartbeat 每 5 秒一次，连续 3 次无响应判定断线。
- 写帧使用单 writer task，禁止多个协程直接写 socket。

### 6.5 反向 Runtime Process Control

Sidecar 负责生成 Agent Adapter Invocation，Rust 负责验证并执行。Sidecar → Rust 固定允许：

```text
runtime.process.start
runtime.process.cancel
runtime.process.status
credential.http.start
credential.http.cancel
credential.probe
host.externalWrite.execute
```

Rust → Sidecar 固定允许：

```text
runtime.process.registered
runtime.process.output
runtime.process.exited
credential.http.event
```

`runtime.process.start` request 固定为：

```json
{
  "run_id": "uuid",
  "execution_snapshot_sha256": "64-char-lower-hex",
  "agent_release_id": "uuid",
  "agent_type": "codex_cli|claude_code|opencode",
  "executable_realpath": "/absolute/path",
  "argv": ["arg0"],
  "cwd_realpath": "/absolute/workspace",
  "stdin_base64": "base64|null",
  "locale": "en_US.UTF-8",
  "purpose": "task_execution|review|repair|verification|merge|company_plan|summary|interactive_turn",
  "workspace_policy_sha256": "64-char-lower-hex",
  "network_policy_sha256": "64-char-lower-hex",
  "deadline_at": "RFC3339-Z"
}
```

约束：

- `argv[0]` 必须等于 `executable_realpath`。
- Rust 必须用已验签 Catalog Release 重新核对 agent type、可执行文件、版本范围和允许参数。
- Sidecar 不传环境变量字典。Rust 根据 `agent_type/profile_directory_id` 固定生成 Agent 原生状态目录变量、受控 `PATH/HOME/locale` 和代理变量。
- `stdin_base64` 解码上限 4 MiB；更大输入必须使用 Profile 内受控临时文件。
- `cwd_realpath`、workspace/network policy hash 必须与 Rust 缓存的 Execution Snapshot 相同。

start response：

```json
{
  "process_id": "uuid",
  "run_id": "uuid",
  "pid": 123,
  "pgid": 123,
  "start_time": "RFC3339-Z",
  "egress_lease_id": "uuid",
  "state": "running"
}
```

`runtime.process.registered` notification 的 payload 与 start response 七个字段逐字相同。Rust 必须先登记 Process Registry，再发送 notification 和完成 start response；两者到达顺序不作为 Sidecar 正确性的前提，Sidecar 以 `process_id/run_id` 幂等合并且字段不一致时立即取消进程并返回 `ADAPTER_RESULT_MISMATCH`。

`runtime.process.output` notification：

```json
{
  "process_id": "uuid",
  "run_id": "uuid",
  "sequence": 1,
  "stream": "stdout|stderr",
  "chunk_base64": "base64",
  "observed_at": "RFC3339-Z"
}
```

Rust 按实际读取顺序为 stdout/stderr 共用一个单调 sequence；单个 `chunk_base64` 解码后最大 256 KiB。Sidecar 按 stream 分别重组行，单行超过 4 MiB 立即取消 Run 并返回 `RUNTIME_OUTPUT_LIMIT_EXCEEDED`。输出不得丢弃；UDS output channel 连续 5 秒无法发送时 Rust 取消进程并返回 `IPC_BACKPRESSURE`，禁止继续执行后只保留截断结果。

`runtime.process.exited` notification：

```json
{
  "process_id": "uuid",
  "run_id": "uuid",
  "exit_code": 0,
  "signal": null,
  "last_sequence": 10,
  "stdout_sha256": "64-char-lower-hex",
  "stderr_sha256": "64-char-lower-hex",
  "ended_at": "RFC3339-Z"
}
```

`runtime.process.cancel` request 固定 `{process_id,run_id,reason}`，`reason` 长度 1..500；调用必须等待进程组回收并返回与 status 相同的终态对象，重复调用返回相同对象。

`runtime.process.status` request 固定 `{process_id,run_id}`，response 固定为：

```json
{
  "process_id": "uuid",
  "run_id": "uuid",
  "state": "running|exited",
  "pid": 123,
  "pgid": 123,
  "start_time": "RFC3339-Z",
  "exit_code": "integer|null",
  "signal": "integer|null",
  "last_sequence": 10,
  "ended_at": "RFC3339-Z|null"
}
```

`state=running` 时 `exit_code/signal/ended_at` 必须全为 null；`state=exited` 时 `ended_at` 必填且 `exit_code/signal` 至少一个非 null。status 只用于断线恢复核对，不允许列出其他 Profile 的进程；未知、其他 session 或其他 Profile 的 process id 统一返回 `RESOURCE_NOT_FOUND`。

## 7. API Model Credential HTTP Broker

### 7.1 固定职责

Sidecar Built-in Agent Runtime 负责：

- 组织 messages/input、tools 与模型参数；
- 执行 Agent Loop；
- 解析标准 Broker Event；
- 调用本地工具；
- 保存 usage、Artifact 和 Checkpoint。

Rust Credential HTTP Broker 负责：

- 从 Keychain 解析 `credential_ref`；
- 构造 Authorization 或协议专属认证字段；
- 校验 Provider Release 和 Model Binding；
- 执行 HTTPS、DNS、SSRF、重定向、超时、重试与取消；
- 把 Provider 响应转换为协议中立流事件；
- 清零凭据和临时请求缓冲。

Sidecar 禁止传入 Authorization、API Key、完整 Provider URL 或任意 Header。

### 7.2 反向 RPC

`credential.http.start` request 固定字段：

```json
{
  "run_id": "uuid",
  "credential_ref": "uuid",
  "provider_release_id": "uuid",
  "model_binding_id": "uuid",
  "protocol": "openai_responses|anthropic_messages|openai_chat_completions",
  "operation": "model_turn",
  "relative_path": "/v1/responses",
  "request": {},
  "deadline_at": "RFC3339-Z"
}
```

`request` 必须通过协议专属 schema。禁止出现 `model` 之外的 URL、Authorization、api_key、token 或代理字段。

初始 response：

```json
{
  "request_id": "uuid",
  "accepted": true,
  "stream": true
}
```

后续 `credential.http.event`：

```json
{
  "request_id": "uuid",
  "sequence": 1,
  "event": "output_text_delta|tool_call_delta|usage|completed|failed",
  "payload": {},
  "received_at": "RFC3339-Z"
}
```

`credential.http.cancel` request 固定 `{request_id,run_id,reason}`，`reason` 长度 1..500；response 固定为：

```json
{
  "request_id": "uuid",
  "run_id": "uuid",
  "state": "cancelled|completed|failed",
  "last_sequence": 10,
  "ended_at": "RFC3339-Z"
}
```

Cancel 幂等；已终止请求返回原终态。

`credential.probe` request 固定为 `{credential_ref,provider_release_id,model_binding_id}`，response 固定为：

```json
{
  "available": true,
  "state": "ready|credential_missing|credential_corrupt|provider_unreachable|provider_rejected|configuration_invalid",
  "checked_at": "RFC3339-Z",
  "error_code": "stable-error-code|null"
}
```

`available` 当且仅当 `state=ready`。probe 必须使用同一 Catalog/Keychain/SSRF/timeout 路径，但不进入 `system.health`；401/403 为 `provider_rejected`，网络失败为 `provider_unreachable`，不得返回 Secret 或 Provider 原始错误正文。

### 7.3 Keychain 与凭据对象

Keychain account 固定为：

```text
{profile_directory_id}/provider/{credential_ref}
```

Keychain value 固定：

```json
{
  "schema_version": 1,
  "provider_id": "uuid",
  "auth_type": "bearer|x_api_key",
  "secret": "opaque",
  "created_at": "RFC3339-Z"
}
```

Rust 使用 `Zeroizing<Vec<u8>>` 读取 value，反序列化后所有 secret 字段继续使用 zeroize 类型。以下内容禁止实现 `Debug` 或 `Clone`：

- API Key；
- Authorization value；
- Egress Token；
- 解密后的 Keychain value。

请求完成、取消、超时或 panic unwind 时必须 Drop 并 zeroize。

### 7.4 Provider 请求构造

Provider 的 `base_url`、relative path、认证位置、固定 Header 和 request defaults 只来自已验签 Catalog Release。请求构造顺序：

1. 读取并验证 Provider Release。
2. 验证 Model Binding 属于该 Provider Release。
3. 规范化 relative path，禁止 scheme、authority、`..` 和 percent-encoded slash。
4. 拼接 base URL。
5. 执行 DNS/IP 策略。
6. 合并允许的 request defaults。
7. 写入服务端选定的 model name。
8. 最后注入认证信息。
9. 发送请求并流式读取。

Sidecar 参数不能覆盖 base URL、model、认证字段、stream、tool schema 安全字段或超时上限。

### 7.5 SSRF 与重定向

每次连接必须：

1. URL 只允许 HTTPS。
2. host 经过 IDNA 和小写规范化。
3. 禁止 userinfo、fragment 和非 Catalog 端口。
4. host 必须等于 Provider allowlist 项或其明确允许的子域。
5. DNS A/AAAA 的每个结果都不得属于 loopback、private、link-local、multicast、documentation、benchmark、reserved 或 unspecified。
6. TCP 必须连接到校验过的 IP，禁止校验域名后由客户端库再次独立解析。
7. TLS SNI 和 Host 仍使用规范域名。
8. 最多跟随 5 次 301/302/303/307/308。
9. 每次重定向重新执行全部 URL、域名、DNS 与 IP 校验。
10. DNS TTL 到期或重试前重新解析。

### 7.6 重试、限流与取消

- 只重试连接中断、408、429、500、502、503、504。
- 最多 3 次，延迟 1 秒、2 秒、4 秒，加 0–250ms CSPRNG 抖动。
- `Retry-After` 小于剩余 deadline 时优先使用；大于 deadline 时直接失败。
- 400/404 返回 `PROVIDER_CONFIGURATION_INVALID`。
- 401/403 返回 `CREDENTIAL_UNAVAILABLE` 并把 credential reference 标记为 unavailable。
- Cancel token 必须同时终止 DNS、连接、上传、响应流和重试等待。

### 7.7 日志与指标

允许记录：

- request id、run id；
- Provider/Model Binding id；
- 规范域名；
- HTTP 状态类别；
- 重试次数、耗时、输入/输出字节数；
- 终态错误码。

禁止记录：

- Header value；
- request/response 原文；
- messages、tool arguments；
- API Key、代理 Token；
- 完整 query string。

## 8. CLI Egress CONNECT Proxy

### 8.1 每 Run 独立 Lease

Rust 为每个 CLI Run 创建一个 `EgressLease`：

```rust
pub struct EgressLease {
    pub lease_id: Uuid,
    pub run_id: Uuid,
    pub listener: TcpListener,
    pub port: u16,
    pub token: Zeroizing<[u8; 32]>,
    pub allowed_domains: BTreeSet<NormalizedDomain>,
    pub created_at: Instant,
    pub expires_at: Instant,
    pub cancel: CancellationToken,
}
```

Listener 必须先成功 bind 并持续持有，再返回端口。禁止先探测空闲端口后释放。

代理环境固定：

```text
HTTP_PROXY=http://ibreeze:<base64url-token>@127.0.0.1:<port>
HTTPS_PROXY=http://ibreeze:<base64url-token>@127.0.0.1:<port>
ALL_PROXY=http://ibreeze:<base64url-token>@127.0.0.1:<port>
NO_PROXY=
```

### 8.2 CONNECT 协议

- 只实现 HTTP/1.1 CONNECT，不实现普通 forward proxy。
- `Proxy-Authorization` 必须为当前 lease token。
- authority 必须是 `host:port`，port 只允许 443。
- Header 总大小上限 16 KiB，单 Header 上限 8 KiB。
- 认证失败返回 407，域名/IP 策略失败返回 403。
- 每 lease 最大 32 个并发 tunnel。
- 单 tunnel idle timeout 120 秒，连接建立 timeout 10 秒。
- 每 Run 新建 tunnel 速率上限 60 次/分钟。
- Run 结束立即 cancel listener 和全部 tunnel。

代理不进行 TLS MITM，不读取 CLI 的 HTTPS 内容。

### 8.3 域名来源

allowlist 是以下集合的并集：

1. Agent Version Range 的认证和模型域名；
2. 当前模型 Provider Release 域名；
3. 当前 Skill 声明且已由 Catalog 校验的域名；
4. 已确认 Plan 中显式声明并通过 PlanValidator 的域名。

禁止用户在任务输入、Prompt、未确认计划、UI 临时字段或环境变量中增加域名。精确域名按 IDNA ASCII lowercase 匹配；`*.example.com` 只匹配一个左侧 label。空 allowlist 表示禁止网络，不表示允许全部。

## 9. CLI Runtime 与 Seatbelt

### 9.1 Execution Snapshot

创建 CLI Run 前冻结：

```json
{
  "run_id": "uuid",
  "company_id": "uuid",
  "purpose": "task_execution|review|repair|verification|merge|company_plan|summary|interactive_turn",
  "workspace_realpath": "/absolute/path",
  "workspace_baseline_sha256": "sha256",
  "agent_release_id": "uuid",
  "agent_executable_realpath": "/absolute/path",
  "agent_version": "semver",
  "model_binding_id": "uuid",
  "skill_release_ids": ["uuid"],
  "tool_policy_sha256": "sha256",
  "network_policy_sha256": "sha256",
  "catalog_release_sequence": 1
}
```

Run 开始后不可修改。Resume 必须复用同一 Snapshot；任一 hash 不匹配返回 `EXECUTION_SNAPSHOT_MISMATCH`。

### 9.2 唯一 Adapter 契约

```python
class CliAgentAdapter(Protocol):
    agent_type: Literal["codex_cli", "claude_code", "opencode"]

    async def probe(self, executable: Path) -> AgentProbe: ...
    def build_invocation(self, snapshot: ExecutionSnapshot, resume: ResumeState | None) -> Invocation: ...
    def parse_stdout(self, line: bytes) -> list[RuntimeEvent]: ...
    def parse_stderr(self, line: bytes) -> list[RuntimeEvent]: ...
    def checkpoint(self, event: RuntimeEvent) -> ResumeState | None: ...
```

删除重复的通用 `CliAdapter` 实现。每种内置 Agent 只能有一个 Adapter 文件。

`Invocation` 固定包含：

```python
@dataclass(frozen=True)
class Invocation:
    argv: tuple[str, ...]
    cwd: Path
    stdin: bytes | None
    env_allowlist: Mapping[str, str]
    stdout_protocol: Literal["jsonl", "text"]
    timeout_seconds: int
```

禁止 Adapter 返回 shell command string。

### 9.3 Prompt 与环境

- Prompt 优先通过 stdin。
- CLI 不支持 stdin 时，写入 `${profile_root}/runtime-input/{run_id}/prompt`，目录 0700、文件 0600。
- 子进程成功打开后立即 unlink；Run 终止后递归清理该 run 目录。
- 环境从空字典构造，只加入 `PATH`、`HOME` 的受控值、locale、代理变量和 Agent 明确要求的非敏感变量。
- 禁止继承宿主 `AWS_*`、`GITHUB_TOKEN`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、SSH Agent 和浏览器代理变量。

Agent 原生状态目录和变量固定为：

```text
CODEX_HOME=${profile_root}/agent-state/codex
CLAUDE_CONFIG_DIR=${profile_root}/agent-state/claude
XDG_CONFIG_HOME=${profile_root}/agent-state/opencode/config
XDG_DATA_HOME=${profile_root}/agent-state/opencode/data
XDG_CACHE_HOME=${profile_root}/agent-state/opencode/cache
```

这些目录权限为 0700，只允许对应 Profile 的 CLI 读写，不进入 Context、Backup、Artifact、诊断导出或日志。`HOME` 使用经 Rust `realpath` 验证的当前用户目录，但 Seatbelt 对主设计 I.8 列出的凭据和隐私子目录保持显式 deny。

### 9.4 Seatbelt Profile

Seatbelt Profile 由 Rust 生成，Python 只传 Snapshot id。固定策略：

- `deny default`；
- 允许读取系统动态库、字体、证书和当前 CLI 可执行文件；
- Workspace realpath 允许读写；
- Workspace 外普通用户文件只读；
- 其他 Profile、Keychain、浏览器数据、SSH/GPG、云凭据、系统隐私目录明确 deny；
- 只允许网络连接到当前 lease 的 `127.0.0.1:port`；
- 禁止直接 DNS、UDP、非代理 TCP；
- `process-exec` 只允许 Catalog 声明的 executable 与固定 helper；
- `interactive_turn/company_plan/review/summary` 对 Workspace 只读；`task_execution/verification/repair/merge` 才允许写。

路径必须先 `realpath`，拒绝 symlink 穿越。SBPL 字符串使用专用转义器，不允许格式化拼接未转义路径。

### 9.5 进程生命周期

Rust Process Supervisor：

1. 验证 Snapshot 和 Seatbelt 能力。
2. 创建 Egress Lease。
3. 构造受控环境。
4. 以新进程组启动 `sandbox-exec -p <profile> -- <argv...>`。
5. 记录 pid、pgid、start_time、run_id 和 session generation。
6. 通过 UDS 发出 `runtime.process.registered`。
7. 分别读取 stdout/stderr，按行大小上限 4 MiB 通过 `runtime.process.output` 传给 Sidecar。
8. 等待退出或 cancel。
9. 清理进程组、lease、prompt 和临时 profile。
10. 发出 `runtime.process.exited`。

取消顺序固定：

```text
SIGINT process group（5 秒）
→ SIGTERM process group（5 秒）
→ SIGKILL process group
→ waitpid 回收
→ 清理资源
```

重复 cancel 返回相同终态。

### 9.6 Resume

Checkpoint 保存：

- native session id；
- 最后持久化 Runtime Event sequence；
- Adapter version；
- Execution Snapshot hash；
- Workspace baseline/current hash；
- 创建时间。

Resume 前验证：

- Agent Release 仍可用；
- Adapter major/minor 与 checkpoint 相同；
- Snapshot hash 相同；
- Workspace 未被未授权修改；
- 上次进程已确认退出。

任一失败返回明确错误，不创建新进程。

## 10. Profile Persistence Kernel

### 10.1 全新 Schema Epoch

全新 Profile metadata 固定包含：

```json
{
  "profile_directory_id": "uuid",
  "schema_epoch": 1,
  "created_by_app_version": "semver",
  "backend_origin": "canonical-origin",
  "app_user_id": "uuid"
}
```

正式应用只接受 `schema_epoch=1`。本次开发切换前执行项目内一次性清理脚本：

```text
scripts/dev-reset-profiles.sh --confirm-delete-all-local-profiles
```

脚本固定执行：

1. 验证当前目录是 iBreeze 项目根。
2. 验证没有运行中的 iBreeze/Sidecar 进程。
3. 列出将删除的开发 Profile 路径。
4. 要求命令行同时包含固定确认参数。
5. 删除开发 Profile、CAS、Worktree、LanceDB 和临时 Runtime 输入。
6. 不接收任意目标路径参数，避免误删。

该脚本只用于开发切换，不随正式应用自动执行。

### 10.2 唯一初始化顺序

```text
acquire profile file lock
→ create profile directory mode 0700
→ bind authenticated UDS transport in handshake-only mode
→ open bootstrap SQLite connection
→ verify SQLite capabilities/version
→ apply fixed PRAGMAs
→ create migration ledger
→ run 001_initial.sql in migration transaction
→ foreign_key_check + integrity_check
→ close bootstrap connection
→ open single write connection
→ open eight read connections
→ start WriteQueue
→ verify local_profile identity
→ start Worker Supervisor
→ enable generated RPC Dispatcher
→ resolve the pending handshake as ready
```

UDS 可以在 Migration 前接受唯一一个 `system.handshake`，但该请求必须等待上述顺序完成；其他方法一律返回 `PROFILE_NOT_READY`。禁止先创建业务表再运行 Migration。禁止在 `LocalDB.initialize()`、测试 fixture 或 Repository 中复制 DDL。

### 10.3 `001_initial.sql`

`001_initial.sql` 是完整 Profile Schema 的唯一创建脚本，包含：

- `local_profile`；Migration Ledger 是 Migration Runner 唯一允许在脚本外创建的 bootstrap 表，不得在初始脚本重复定义；
- company、department、responsibility、employee、profile revision；
- conversation 与 message；
- company/department/employee task、plan、snapshot 与 dependency；
- agent run、runtime queue、event、checkpoint、tool execution；
- workspace、grant、artifact、contributor、version；
- review assignment/report/issue、rework attempt/issue binding；
- approval、verification；
- domain event store、outbox、idempotency；
- knowledge source/chunk/index generation；
- backup record；
- audit record、settings。

所有表、列、组合外键、CHECK、唯一索引和不可变 Trigger 必须与主设计 H 章一致。脚本结束必须执行：

```sql
PRAGMA foreign_key_check;
PRAGMA integrity_check;
```

结果不是空集合/`ok` 时 Migration 失败。

### 10.4 Migration Ledger

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    filename TEXT NOT NULL UNIQUE,
    script_sha256 TEXT NOT NULL CHECK(length(script_sha256)=64),
    status TEXT NOT NULL CHECK(status IN ('running','completed','failed')),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    error_code TEXT,
    error_message TEXT
);
```

未来 Migration 固定三事务：

1. 事务 A 写入 `running` 后提交。
2. 事务 B `BEGIN IMMEDIATE` 执行脚本、校验外键、写 `completed` 后提交。
3. 失败时回滚 B，事务 C 写 `failed/error`。

已完成 Migration 的 hash 变化返回 `MIGRATION_CHECKSUM_MISMATCH`。数据库版本高于客户端返回 `PROFILE_SCHEMA_UNSUPPORTED`。

### 10.5 连接所有权

`ProfileDatabase` 是唯一连接所有者：

```python
class ProfileDatabase:
    _writer: aiosqlite.Connection
    _readers: ReadPool
    _write_queue: WriteQueue

    async def start(self, path: Path) -> None: ...
    async def execute(self, command: WriteCommand[T]) -> T: ...
    async def query(self, query: ReadQuery[T]) -> T: ...
    async def barrier(self) -> None: ...
    async def close(self) -> None: ...
```

禁止业务代码访问 `_writer`、`write_connection` 或 `_readers`。用 AST 架构测试阻断 `persistence` 目录外 import `aiosqlite`。

只保留一个八连接 ReadPool。ReadPool 每连接设置相同 PRAGMA，并提供：

- `query_one`；
- `query_all`；
- `read_transaction`；
- `after_write_token`。

需要 read-after-write 的 Command 响应在同一 write transaction 中构造，不依赖立即从 ReadPool 读取。

### 10.6 WriteQueue

WriteQueue 容量固定 32，元素固定为：

```python
@dataclass
class WriteEnvelope(Generic[T]):
    command_name: str
    trace_id: UUID
    deadline_at: datetime
    execute: Callable[[UnitOfWork], Awaitable[T]]
    future: Future[T]
```

执行规则：

1. `put_nowait` 失败返回 `LOCAL_WRITE_BACKPRESSURE`。
2. 单 worker 顺序消费。
3. 每个 envelope 创建一个 `UnitOfWork`。
4. `BEGIN IMMEDIATE`。
5. Command 执行业务写、Domain Event、Outbox 和幂等结果。
6. 成功 commit 后完成 future。
7. 失败 rollback 后用稳定错误完成 future。
8. deadline 已过期的 command 不进入事务。

禁止使用 `async with db.execute("BEGIN IMMEDIATE")`；必须显式 `BEGIN/COMMIT/ROLLBACK`。

### 10.7 Unit of Work 与幂等

```python
class UnitOfWork:
    connection: aiosqlite.Connection
    repositories: RepositorySet
    events: DomainEventCollector
    outbox: OutboxWriter
    idempotency: IdempotencyWriter
```

写 RPC 顺序：

```text
生成 request_sha256
→ WriteQueue
→ 查询 idempotency
→ 冲突/完成/处理中判定
→ 写 processing
→ 执行 Command
→ 写 Aggregate + EventStore + Outbox
→ 写 completed response
→ commit
```

Command 失败时：

- 业务错误可在同事务保存确定性 failed idempotency 结果后 commit；
- 基础设施错误整体 rollback，不留下 processing；调用方可用相同 key 重试。

禁止在事务外先写 processing。

### 10.8 Backup Barrier

Backup 固定流程：

1. 拒绝新的低优先级后台写。
2. 向 WriteQueue 插入 barrier。
3. 等待 barrier 前全部写完成。
4. 在 writer 上执行 WAL checkpoint。
5. 使用 SQLite Backup API 复制到 staging。
6. 释放 barrier。
7. 校验 staging integrity、manifest 和 CAS 引用。
8. 原子发布 Backup。

Barrier 有 30 秒上限，超时返回 `BACKUP_WRITE_BARRIER_TIMEOUT`，不得复制不一致数据库。

## 11. Worker Supervisor 与 Health

### 11.1 固定 Worker 集合

v1 必须注册：

| Worker | 职责 |
|---|---|
| RuntimeWorker | lease、执行和恢复 AgentRun |
| AnalysisWorker | 公司计划与部门计划分析任务 |
| OutboxWorker | 可靠发布本地 Domain Event |
| KnowledgeWorker | 处理知识索引 generation |
| ReconciliationWorker | 对账 CAS、知识索引、事件投影 |
| BackupWorker | 自动备份与保留策略 |
| EventCompactionWorker | 按 checkpoint 压缩可压缩运行事件 |

Worker 不允许各自创建数据库连接或直接写 writer，所有写入通过 WriteQueue。

### 11.2 Worker 状态

```python
@dataclass
class WorkerHealth:
    name: str
    state: Literal["starting","healthy","degraded","failed","stopped"]
    heartbeat_at: datetime
    last_success_at: datetime | None
    last_error_code: str | None
    queue_lag: int
    restart_count: int
```

每个 Worker 每 5 秒 heartbeat。15 秒无 heartbeat 视为 failed。Supervisor 使用 1、2、4、8、16 秒退避，5 分钟内最多重启 5 次，超过后保持 failed 并使系统 degraded/unhealthy。

### 11.3 Application Lifecycle

启动顺序严格遵循 10.2。关闭顺序：

```text
stop accepting new RPC
→ cancel/finish active streams
→ stop leasing new runtime work
→ drain WriteQueue（最长 10 秒）
→ stop workers
→ checkpoint WAL
→ close read pool
→ close writer
→ release profile lock
```

任一步超时记录错误并继续最安全关闭；不得直接取消 WriteQueue worker 丢失已接收写命令。

### 11.4 健康快照

`system.health` 固定返回：

```json
{
  "status": "healthy|degraded|unhealthy",
  "observed_at": "RFC3339-Z",
  "profile": {
    "schema_epoch": 1,
    "migration_version": 1,
    "database_status": "ready|migrating|failed"
  },
  "ipc": {
    "session_id": "uuid",
    "generation": 1,
    "heartbeat_age_ms": 0
  },
  "queues": {
    "write_depth": 0,
    "runtime_ready": 0,
    "outbox_pending": 0
  },
  "runtime": {
    "active_processes": 0,
    "credential_broker": "ready|degraded|unavailable",
    "egress_broker": "ready|degraded|unavailable"
  },
  "workers": [],
  "event_loop_lag_ms": 0,
  "disk_free_bytes": 0
}
```

总状态：

- DB、Migration、IPC、WriteQueue 任一 failed 为 `unhealthy`。
- Runtime/Credential/Egress 不可用或任一非关键 Worker failed 为 `degraded`。
- 所有必需项 ready 且观测未过期才为 `healthy`。
- 外部 CLI 未安装只影响对应 Agent availability，不影响系统总健康。

Rust `system_health` 必须调用 Sidecar health 并追加 Rust 组件状态，禁止硬编码。

## 12. Review 与任务完成状态机

### 12.1 唯一原则

1. Run 状态与业务 Task 状态完全分离。
2. AgentRun `succeeded` 只表示进程/Agent Loop 成功结束。
3. Artifact、Verification、Review、Issue、Report 是业务完成证据。
4. 只有 Command Handler 能迁移 Aggregate 状态。
5. Worker 和 Event Consumer 只能发 Command，不能直接 UPDATE 业务状态。
6. 所有迁移使用 `expected_version` 和 `UPDATE ... WHERE version=?`。

### 12.2 聚合与状态

#### EmployeeTask

```text
assigned → ready → running → submitted → peer_reviewing → accepted
    │         │         │             └→ changes_requested → ready
    └─────────┴─────────┴→ waiting_resource → resume_state
非终态 → cancelled|failed
```

#### DepartmentTask

```text
draft → checking_resources → ready → executing → reviewing → completed
             │          │        │           └→ fixing → reviewing
             └──────────┴────────┴→ waiting_dependency|waiting_resource|waiting_permission
等待态 → resume_state
非终态 → cancelled|failed
```

#### CompanyTask

```text
draft → analyzing → awaiting_user_confirmation → approved
          │                  ├→ revision_requested → analyzing
          │                  └→ rejected
          └→ waiting_resource
approved → dispatching → checking_resources → executing → reviewing → final_review → completed
                                         │            │           └→ fixing → reviewing
                                         └────────────┴→ waiting_dependency|waiting_resource|waiting_permission|paused
等待态 → resume_state
非终态 → cancelling → cancelled|failed
```

本节只以主设计 H.7 的完整 `ALLOWED_TRANSITIONS` 表为权威来源；上述文本是相同状态边的流程化展示，不得据此省略 H.7 的任一合法失败、取消、等待或恢复边。代码生成测试必须逐项比较 H.7 状态表与 Python 不可变迁移表。

#### ReviewAssignment

```text
assigned → in_review → submitted
assigned|in_review|submitted → stale
assigned|in_review → cancelled
```

#### ReviewIssue

```text
open → fixing → resolved → verified → closed
open → rejected（仅 medium/low，必须 rejection_reason）
resolved|verified → fixing
```

`blocker/high` 禁止 rejected。

### 12.3 Command 集合

固定 Command：

```text
StartEmployeeTask
SubmitEmployeeTask
StartReview
SubmitReview
StartIssueFix
ResolveIssue
VerifyIssue
CloseIssue
RejectIssue
AcceptEmployeeTask
StartDepartmentReview
CompleteDepartmentTask
RequestDepartmentRework
ResumeDepartmentReview
PublishDepartmentReport
StartCompanyReview
RequestCompanyRework
ResumeCompanyReview
GenerateFinalReport
CompleteCompanyTask
```

禁止提供 `setStatus`、`updateStatus` 或接收任意 target state 的通用命令。

### 12.4 `SubmitReview`

事务内固定校验：

1. Assignment 属于 company 和当前任务链。
2. Assignment 状态是 `assigned/in_review`。
3. `expected_assignment_version` 匹配。
4. reviewer run 存在、purpose=`review` 且 employee 与 assignment reviewer 相同。
5. reviewer 不在 Artifact contributors。
6. reviewed artifact id/hash 与 assignment 快照一致。
7. report Artifact 类型为 `review_report` 且由 reviewer run 创建。
8. verdict 为 `pass` 时 issues 必须为空。
9. verdict 为 `needs_changes` 时至少一个 issue。
10. verdict 为 `failed` 时至少一个 blocker 且其 category 为 `review_execution`，表示缺失、损坏或不可执行的证据使本轮无法形成可信结论。
11. 每个 issue 的 severity、category、assignee 和 evidence refs 合法。

成功写入：

- ReviewReport；
- ReviewIssue；
- Assignment `submitted`；
- `review.submitted` Domain Event；
- Outbox；
- 幂等响应。

### 12.5 Artifact 变化与 Review 失效

Artifact 创建新版本的同一事务中：

1. 旧版本 `is_current=false`。
2. 新版本 `is_current=true`。
3. 指向旧 hash 的非终态 ReviewAssignment 变为 `stale`。
4. 旧 ReviewReport 保留审计但不参与 Completion Gate。
5. 旧 Issue 保留并标记 `superseded_by_artifact_id`；未解决问题必须由新 Review 明确重新发现或验证关闭。
6. 发出 `artifact.superseded`、`review.staled`。

### 12.6 Employee Completion Gate

`AcceptEmployeeTask` 必须同时满足：

- 必需 Artifact 当前版本全部存在；
- Artifact contributor 包含该 EmployeeTask 的执行职员；
- 必需 VerificationResult 全部 passed 且指向当前 hash；
- 所有必需 ReviewAssignment submitted；
- Review verdict 全部为 `pass`；
- 当前 Artifact 关联 blocker/high Issue 全部 closed；
- execution report 存在并引用全部证据；
- 没有 running/queued/waiting_approval Run。

满足后从 `peer_reviewing` 迁移到 `accepted`。

### 12.7 Department Completion Gate

`CompleteDepartmentTask` 必须同时满足：

- 所有 required EmployeeTask 为 accepted；
- Merge Task 为 accepted；
- department_report 当前版本存在；
- department_report 的公司级 Review verdict 为 `pass`；
- 当前任务链 blocker/high Issue 全部 closed；
- 测试/验证 Artifact passed；
- 下游所需交付物已发布；
- 无活跃 Run、审批和 Workspace apply 冲突。

### 12.8 Company Completion Gate

`CompleteCompanyTask` 必须同时满足：

- 所有 required DepartmentTask completed；
- 所有 department_report 的公司级 Review verdict 为 `pass`；
- 跨部门一致性 Review verdict 为 `pass`；
- 所有 blocker/high Issue closed；
- final_report 当前版本存在；
- final_report 引用当前计划版本、部门报告 hash、测试结果、Review 与修复证据；
- 总经理完成最终确认 Command；
- 所有代码 Workspace 处于 `ready_to_apply/applied/abandoned` 且没有正在执行 apply；软件任务的 integration Workspace 至少为 `ready_to_apply`，用户可在任务完成后决定应用或放弃；
- 无活跃 Run或未消费审批。

### 12.9 返工

返工使用新 attempt，固定持久化为：

```sql
CREATE TABLE rework_attempts (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_task_id TEXT,
    attempt_no INTEGER NOT NULL CHECK(attempt_no >= 1),
    status TEXT NOT NULL
        CHECK(status IN ('planned','running','completed','cancelled','failed')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version >= 1),
    UNIQUE(id, company_id),
    FOREIGN KEY(company_task_id, company_id)
        REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(department_task_id, company_id)
        REFERENCES department_tasks(id, company_id),
    CHECK(
        (status IN ('completed','cancelled','failed') AND completed_at IS NOT NULL)
        OR
        (status IN ('planned','running') AND completed_at IS NULL)
    )
);
CREATE UNIQUE INDEX ux_rework_attempt_scope_no
ON rework_attempts(
    company_id,
    company_task_id,
    COALESCE(department_task_id, ''),
    attempt_no
);
CREATE UNIQUE INDEX ux_rework_attempt_active_scope
ON rework_attempts(
    company_id,
    company_task_id,
    COALESCE(department_task_id, '')
)
WHERE status IN ('planned','running');

CREATE TABLE rework_attempt_issues (
    company_id TEXT NOT NULL,
    rework_attempt_id TEXT NOT NULL,
    review_issue_id TEXT NOT NULL,
    PRIMARY KEY(rework_attempt_id, review_issue_id),
    FOREIGN KEY(rework_attempt_id, company_id)
        REFERENCES rework_attempts(id, company_id),
    FOREIGN KEY(review_issue_id, company_id)
        REFERENCES review_issues(id, company_id)
);
```

状态只允许 `planned→running/cancelled`、`running→completed/cancelled/failed`，终态无出边。创建新 attempt 时，`attempt_no` 等于同一 company task 与可空 department scope 的历史最大值加 1，且必须绑定至少一个未 closed/rejected 的 ReviewIssue。返工不得重置或覆盖旧证据。新 Artifact 和 Review 必须通过版本链关联旧证据。Completion Gate 读取该 scope 最大 `attempt_no`：其状态必须是 completed，并且只使用该 attempt 的 current Artifact/Review；最大 attempt 为 planned/running/failed 时 Gate 阻断，cancelled attempt 不使更早证据重新生效，必须创建更高 attempt 或显式取消整个任务。

### 12.10 事件驱动推进

Event Consumer 不直接改状态，映射为 Command：

```text
run.completed → EvaluateEmployeeSubmission
review.submitted → EvaluateEmployeeAcceptance
review.issue_changed(to_state=closed) → EvaluateAffectedTask
employee_task.status_changed(to_state=accepted) → EvaluateDepartmentReadiness
department_task.status_changed(to_state=completed) → EvaluateCompanyReadiness
```

`Evaluate*` 是幂等内部 Command，仍通过 WriteQueue 和 Unit of Work。

## 13. 错误模型

五项架构固定新增或保留：

| 错误码 | 场景 |
|---|---|
| `IPC_CONNECTION_LOST` | UDS generation 失效 |
| `IPC_BACKPRESSURE` | pending/stream 队列超限 |
| `IPC_DEADLINE_EXCEEDED` | 请求 deadline 到期 |
| `CREDENTIAL_UNAVAILABLE` | Keychain 凭据不存在、损坏或 401/403 |
| `PROVIDER_CONFIGURATION_INVALID` | Provider/Model/relative path 非法 |
| `EGRESS_DOMAIN_DENIED` | 域名不在 allowlist |
| `EGRESS_ADDRESS_DENIED` | DNS/IP 命中禁止网段 |
| `EGRESS_AUTH_FAILED` | CONNECT Token 错误 |
| `EXECUTION_SNAPSHOT_MISMATCH` | Resume 快照变化 |
| `SEATBELT_UNAVAILABLE` | 真实 Seatbelt 探测失败 |
| `PROCESS_START_FAILED` | 进程启动失败 |
| `PROCESS_CANCEL_TIMEOUT` | TERM/KILL 后仍无法回收 |
| `RUNTIME_OUTPUT_LIMIT_EXCEEDED` | CLI 单行输出超过 4 MiB |
| `PROFILE_NOT_READY` | UDS 已建立但 Profile 初始化尚未完成 |
| `PROFILE_SCHEMA_UNSUPPORTED` | schema epoch 不支持 |
| `MIGRATION_CHECKSUM_MISMATCH` | 已应用脚本 hash 变化 |
| `LOCAL_WRITE_BACKPRESSURE` | WriteQueue 容量已满 |
| `BACKUP_WRITE_BARRIER_TIMEOUT` | 一致性 barrier 超时 |
| `WORKER_FAILED` | Worker 超过重启阈值 |
| `REVIEW_STALE_ARTIFACT` | Review 指向非当前 hash |
| `COMPLETION_GATE_BLOCKED` | 完成证据不满足 |

错误响应必须包含 `code/message/reference_id/retryable/details`。`details` 只包含安全的实体 id、字段路径和 blocker code，不包含 Prompt、凭据或外部文件内容。

## 14. 必须删除的实现

一次性切换完成前删除：

1. `sidecar/ibreeze/runtime/transport.py` 的 stub `ReverseRpcClient`。
2. `apps/desktop-core/src/rpc/reverse.rs` 的固定 Broker unavailable handler。
3. `apps/desktop-core/src/security/egress.rs` 的“探测端口后释放”实现。
4. `sidecar/ibreeze/local_db.py` 的 `_CREATE_TABLES_SQL` 和重复 ReadPool。
5. `sidecar/ibreeze/application/app.py` 中第二套 ReadPool。
6. `sidecar/ibreeze/rpc_server.py` 中绕过 WriteQueue 的 `_idempotent_call`。
7. 所有 Worker 的直接业务 SQL write。
8. 重复 CLI Adapter。
9. Worker/Run 结束后的直接 Task 状态 UPDATE。
10. Rust/TypeScript/Python 手工方法 ownership/kind 列表。
11. Desktop `planVersion.*`、`orchestration.*` 和其他 Registry 外调用。
12. 76 个未声明的空 schema。
13. 只有两个事件的假 Domain Event Registry。
14. 硬编码 `system_health` 和常量健康字段。
15. 包含“后续版本”“TBD”“TODO”“stub mode”的生产路径。

Release Hygiene 脚本必须扫描上述模式；测试 fixture 和明确的负向字符串测试可通过路径 allowlist 排除。

## 15. 测试架构

### 15.1 Contract

- Registry 与 J.14 集合精确相等。
- 每个方法、事件、错误码有生成类型。
- 每个 schema 有合法与非法 fixture。
- 未登记方法、空 response、未知 `$ref`、集合漂移均使生成失败。
- Rust/Python/TypeScript 对 golden payload 编解码一致。

### 15.2 Rust Broker

- 真实双向 UDS 并发、乱序响应、超时、断线、重连。
- Keychain canary 不进入 Sidecar、SQLite、日志和 crash report。
- SSRF、DNS rebinding、重定向、IPv4/IPv6 私网。
- CONNECT 认证、domain allowlist、并发上限、取消。
- 进程组取消、子进程逃逸、Seatbelt 路径与网络逃逸。
- 三个真实 CLI 锁版本首次、恢复和取消。

### 15.3 Persistence

- 空目录只经 `001_initial.sql` 创建。
- Migration 中断、checksum 变化、磁盘满、版本过高。
- 32 容量背压、并发命令顺序、rollback 和幂等。
- Backup barrier 与故障注入。
- Worker crash/restart/failed 和有序关闭。
- 健康状态降级与恢复。

### 15.4 Review

- 每条合法/非法状态边。
- 自审、过期 hash、错误 reviewer run、错误 report Artifact。
- Artifact supersede 后旧 Review 失效。
- blocker/high 不能 rejected。
- 并发 Review 与版本冲突。
- Employee/Department/Company Gate 的每个 blocker。
- 返工多轮和事件重复/乱序。

### 15.5 E2E

必须至少包含：

1. API Model 职员完成含工具调用任务。
2. Codex CLI 在 Workspace 写文件并通过 Review。
3. CLI 直接公网访问失败、代理访问成功。
4. 两名职员交叉 Review，禁止自审。
5. 测试发现 blocker → 开发返工 → 复测 → 关闭 → 最终报告。
6. Worker 崩溃后健康降级并恢复。
7. UDS 断线后 Run 安全终止且不重复副作用。
8. Backup barrier 与恢复。

### 15.6 覆盖率

手写 Rust、Python、TypeScript/TSX 按主实施计划达到 100% 指标。以下行为禁止：

- 降低阈值；
- 把生产目录加入 omit；
- 缺工具时跳过；
- 没有测试文件时返回成功；
- 用仅检查文件存在的测试代替行为测试。

## 16. 安全验收

- Sidecar 进程环境、内存转储测试、日志、SQLite、Event 和 Artifact 中找不到 canary API Key。
- CLI 不能读取 Keychain、其他 Profile、SSH/GPG 和浏览器凭据。
- CLI 不能直接 DNS/TCP/UDP 出站。
- CONNECT Proxy 只接受当前 Run token 和 allowlist。
- `interactive_turn/company_plan/review/summary` Run 对 Workspace 只读；`verification` 只允许执行 ExecutionSnapshot 锁定的验证命令并写测试临时输出，不能获得通用修改源码工具。
- 外部写只通过 Human Approval + Rust receipt。
- 所有路径先 realpath，symlink race 使用目录句柄/openat 风格防护。
- 断线、取消和 panic 都清理 secret、lease、进程组和临时文件。

## 17. 性能与容量

| 指标 | 固定目标 |
|---|---:|
| UDS 普通 RPC p95 | < 50 ms，不含业务执行 |
| UDS pending 上限 | 每方向 256 |
| Stream 缓冲 | 每请求 64 帧 |
| WriteQueue 容量 | 32 |
| ReadPool | 8 |
| CLI tunnel | 每 Run 32 |
| Provider response body | 非流式最大 16 MiB |
| Runtime output notification 解码后 chunk | 最大 256 KiB |
| Runtime stdout/stderr 逻辑行 | 最大 4 MiB |
| Health heartbeat | 5 秒 |
| Worker failed 判定 | 15 秒无 heartbeat |
| Graceful shutdown | 10 秒 |

超限必须返回稳定错误或执行背压，禁止无限增长。

## 18. 一次性切换顺序

```text
1. 清理开发 Profile 和旧生成产物
2. 建立 Canonical Registry 与生成链
3. 建立全新 001_initial.sql 与 Persistence Kernel
4. 建立 Duplex UDS
5. 建立 Credential HTTP Broker 与 CONNECT Egress
6. 建立 CLI Process Supervisor 与 Seatbelt
7. 重建 Sidecar Runtime Gateway
8. 重建 Review/Completion 状态机
9. 重建 Worker Supervisor 与 Health
10. Desktop/Admin 改用生成 Client
11. 删除全部旧入口和占位实现
12. 全量 Contract/Security/Fault/E2E/Coverage 门禁
13. 独立全量 Review
```

步骤 2–9 期间主分支可以暂时不可运行，但不得合入宣称完成的半实现；最终切换提交必须删除旧路径。

## 19. 完成定义

只有同时满足以下条件，五项架构问题才可关闭：

1. 第 14 节全部删除项已不存在。
2. API Model 和三种 CLI 真实锁版本端到端通过。
3. 76 个空 schema 全部完成明确分类，Domain Event Registry 完整。
4. 空 Profile 只通过新 Migration 建立。
5. 所有业务写只经过 WriteQueue/UnitOfWork。
6. 所有 Task 完成只经过 Completion Command。
7. Rust、Sidecar 和 Desktop 健康状态来自实时组件。
8. 安全、故障注入、恢复和 E2E 测试进入 fail-closed 门禁。
9. 覆盖率达到主实施计划的 100% 要求。
10. 独立 Reviewer 未发现 blocker/high。

未满足任一项时，禁止以“框架已完成”“后续补充”或“主要流程可用”关闭问题。
