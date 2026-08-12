# iBreeze 五项核心架构重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从空 Profile 和单一目标代码路径实现 Canonical Contract Registry、Profile Persistence Kernel、Duplex UDS、Credential/HTTP/Egress Broker、CLI Runtime/Seatbelt 以及 Review/Completion 状态机，并彻底删除当前占位、旁路和双轨实现。

**Architecture:** React WebView 只调用生成的 RPC Client；Rust Trusted Host Kernel 独占 Keychain、HTTP/CONNECT 出站、Seatbelt、CLI 进程组和 Sidecar 监督；Python Sidecar 独占本地业务状态机、调度、Review 和 SQLite 写事务。所有跨进程类型由 Registry 与 JSON Schema 生成，所有业务写入通过单写队列和 Unit of Work，Run 成功不能直接完成业务任务。

**Tech Stack:** macOS Apple Silicon（`aarch64-apple-darwin`，`MACOSX_DEPLOYMENT_TARGET=14.0`，支持 14.x/15.x/26.x）、Tauri 2、Rust 2021、Tokio 1、React 19、TypeScript 5.7、Python 3.12、Pydantic 2、aiosqlite、SQLite `>=3.45,<3.46`、JSON-RPC 2.0、JSON Schema 2020-12、Vitest、pytest、cargo-nextest、cargo-llvm-cov、Playwright。

## Global Constraints

- 规范来源固定为 `docs/设计方案/AI公司桌面应用设计方案.md` 与 `docs/设计方案/iBreeze五项核心架构重构设计方案.md`；本计划只规定实现顺序，不改变产品语义。
- 本次按全新项目切换，不迁移任何已有 Profile；开发数据只能由 `scripts/dev-reset-profiles.sh --confirm-delete-all-local-profiles` 显式清理。
- 首个正式版本只接受 `schema_epoch=1`；完整业务 Schema 只由 `sidecar/ibreeze/persistence/migrations/001_initial.sql` 创建。
- 不保留旧 RPC、旧 DTO、旧 Adapter、旧 DDL、兼容层、Feature Flag 或可进入生产的假实现。
- Rust Core 是 Credential、HTTP、CONNECT、Seatbelt、CLI Process Supervisor 和外部单次写入的唯一所有者。
- Sidecar 不得调用 `asyncio.create_subprocess_exec`、`subprocess`、`os.exec*`，不得读取 Keychain，不得直接连接公网模型端点。
- SQLite 只有一个写连接和一个容量 32 的 WriteQueue；所有 Command、Worker、Outbox 与 RPC 幂等写入均经过同一个 Unit of Work。
- RPC `meta` 只含 `trace_id/ipc_session_id/window_session_id/idempotency_key/deadline_at`；写方法的幂等键为 UUID，读方法为 null。
- UDS 帧固定为 4 字节无符号大端长度加 UTF-8 JSON 对象，单帧上限 16 MiB；不支持 batch 或压缩。
- Rust 请求 id 使用 `core:{uuid}`，Sidecar 请求 id 使用 `sidecar:{uuid}`。
- CLI 固定支持 Codex CLI `>=0.144.0 <0.145.0`、Claude Code `>=2.1.0 <2.2.0`、OpenCode `>=1.18.0 <1.19.0`。
- 桌面只构建 `aarch64-apple-darwin`，固定 `MACOSX_DEPLOYMENT_TARGET=14.0`；v1 支持 macOS 14.x、15.x、26.x。发布门禁的真实 Apple Silicon runner 标签固定为 `ibreeze-macos-14` 和 `ibreeze-macos-26`，两者均必须在线并执行安全与端到端门禁。
- Workspace 权限固定为：`task_execution/verification/repair/merge` 按快照授予必要读写；`interactive_turn/company_plan/review/summary` 对 Workspace 只读。
- API Model 的完整 Agent Loop 在 Sidecar 执行，但每次模型 HTTP 请求必须经 Rust Credential HTTP Broker。
- 手写 Rust、Python、TypeScript/TSX 的 lines/functions/branches/regions 按适用指标达到 100%；缺工具、无测试或空测试集必须失败。
- 每个任务严格执行红—绿—Review；每个任务一个提交，提交前运行该任务列出的局部门禁。
- 每次代码提交同时更新 `README.md` 和 `docs/部署文档.md`；用户可见变化还要创建或更新 `docs/用户手册.md`。
- 时间在协议和持久层统一为 RFC3339 UTC `Z`，前端统一转换为 `Asia/Shanghai`；数值展示最多两位小数且不补零。

---

## 0. 必读资料、执行顺序与任务边界

实施者在开始任一任务前必须读取：

1. `docs/设计方案/AI公司桌面应用设计方案.md` 的 F、H、I、J、K 章；
2. `docs/设计方案/iBreeze五项核心架构重构设计方案.md` 第 4–19 节；
3. 本计划的 Global Constraints、共享类型账本和当前任务；
4. 当前任务 `Files` 中列出的现有文件和测试。

固定依赖顺序：

```text
Task 1
  └─ Task 2
      └─ Task 3
          └─ Task 4
              ├─ Task 5 ─ Task 6 ─ Task 7 ─ Task 8 ─ Task 9 ─ Task 10 ─ Task 11 ─ Task 12
              │                                   └──────── Task 13
              │                                              │
              │                              Task 6 + Task 13 ─ Task 14 ─ Task 15 ─ Task 16
              └─ Task 17
Task 12 + Task 13 + Task 15 + Task 16 + Task 17 ─ Task 18 ─ Task 19
```

并行限制：

- `001_initial.sql` 只在 Task 5 一次性写完整；后续任务发现字段缺口时必须退回 Task 5 修正文档和初始脚本，禁止创建第二个 Migration。
- Task 9–11 可由不同实施者先写测试，但共享的 `apps/desktop-core/src/broker/` 变更必须按 Task 9→10 顺序合并。
- Task 14–15 只允许通过 Command Bus 修改任务状态，不得并行引入 Repository 状态写接口。
- Task 19 执行删除后，禁止把被删路径恢复为兼容层。

## 1. 共享类型账本

后续任务必须逐字使用以下名称和字段。

### 1.1 RPC 元数据

```rust
pub struct RpcMeta {
    pub trace_id: Uuid,
    pub ipc_session_id: Option<Uuid>,
    pub window_session_id: Option<Uuid>,
    pub idempotency_key: Option<Uuid>,
    pub deadline_at: DateTime<Utc>,
}

pub enum MethodOwner { Rust, Sidecar, Supervisor }
pub enum MethodKind { Read, Write, Stream }
pub enum MethodScope { None, Profile, Company }

pub struct MethodMeta {
    pub method: &'static str,
    pub owner: MethodOwner,
    pub kind: MethodKind,
    pub scope: MethodScope,
    pub request_schema: &'static str,
    pub response_schema: &'static str,
    pub idempotency_ttl_seconds: u64,
    pub allowed_errors: &'static [&'static str],
    pub empty_request: bool,
}
```

### 1.2 Runtime Process RPC

```rust
pub struct RuntimeProcessStartRequest {
    pub run_id: Uuid,
    pub workspace_grant_id: Uuid,
    pub execution_snapshot_sha256: String,
    pub agent_release_id: Uuid,
    pub agent_type: AgentType,
    pub executable_realpath: PathBuf,
    pub argv: Vec<String>,
    pub cwd_realpath: PathBuf,
    pub stdin_base64: Option<String>,
    pub locale: String,
    pub purpose: RunPurpose,
    pub workspace_policy_sha256: String,
    pub network_policy_sha256: String,
    pub deadline_at: DateTime<Utc>,
}

pub struct RuntimeProcessStartResponse {
    pub process_id: Uuid,
    pub run_id: Uuid,
    pub pid: u32,
    pub pgid: i32,
    pub start_time: DateTime<Utc>,
    pub egress_lease_id: Uuid,
    pub state: ProcessState,
}

pub struct RuntimeProcessOutput {
    pub process_id: Uuid,
    pub run_id: Uuid,
    pub sequence: u64,
    pub stream: ProcessStream,
    pub chunk_base64: String,
    pub observed_at: DateTime<Utc>,
}

pub struct RuntimeProcessExited {
    pub process_id: Uuid,
    pub run_id: Uuid,
    pub exit_code: Option<i32>,
    pub signal: Option<i32>,
    pub last_sequence: u64,
    pub stdout_sha256: String,
    pub stderr_sha256: String,
    pub ended_at: DateTime<Utc>,
}

pub struct RuntimeProcessStatus {
    pub process_id: Uuid,
    pub run_id: Uuid,
    pub state: ProcessState,
    pub pid: u32,
    pub pgid: i32,
    pub start_time: DateTime<Utc>,
    pub exit_code: Option<i32>,
    pub signal: Option<i32>,
    pub last_sequence: u64,
    pub ended_at: Option<DateTime<Utc>>,
}
```

`AgentType` 固定为 `codex_cli/claude_code/opencode`；`RunPurpose` 固定为 `task_execution/review/repair/verification/merge/company_plan/summary/interactive_turn`；`ProcessStream` 固定为 `stdout/stderr`；`ProcessState` 固定为 `running/exited`，其中 start response 只允许 `running`。

`runtime.process.registered` notification 的 payload 与 `RuntimeProcessStartResponse` 七个字段完全相同；Sidecar 必须允许 notification 与 start response 任意先后到达，并按 `process_id/run_id` 幂等合并。

### 1.3 Credential HTTP Broker

```rust
pub struct CredentialHttpStartRequest {
    pub run_id: Uuid,
    pub credential_ref: Uuid,
    pub provider_release_id: Uuid,
    pub model_binding_id: Uuid,
    pub protocol: ProviderProtocol,
    pub operation: ModelOperation,
    pub relative_path: String,
    pub request: serde_json::Value,
    pub deadline_at: DateTime<Utc>,
}

pub struct CredentialHttpAccepted {
    pub request_id: Uuid,
    pub accepted: bool,
    pub stream: bool,
}

pub struct CredentialHttpEvent {
    pub request_id: Uuid,
    pub sequence: u64,
    pub event: BrokerEventKind,
    pub payload: serde_json::Value,
    pub received_at: DateTime<Utc>,
}

pub struct CredentialHttpTerminal {
    pub request_id: Uuid,
    pub run_id: Uuid,
    pub state: HttpTerminalState,
    pub last_sequence: u64,
    pub ended_at: DateTime<Utc>,
}

pub struct CredentialProbeResponse {
    pub available: bool,
    pub state: CredentialProbeState,
    pub checked_at: DateTime<Utc>,
    pub error_code: Option<String>,
}
```

`ProviderProtocol` 固定为 `openai_responses/anthropic_messages/openai_chat_completions`；`ModelOperation` 在 v1 只允许 `model_turn`；`BrokerEventKind` 固定为 `output_text_delta/tool_call_delta/usage/completed/failed`；`HttpTerminalState` 固定为 `cancelled/completed/failed`；`CredentialProbeState` 固定为 `ready/credential_missing/credential_corrupt/provider_unreachable/provider_rejected/configuration_invalid`。Accepted response 的 `accepted/stream` 在 v1 必须同时为 true；Probe 的 `available` 当且仅当 state 为 `ready`。

### 1.4 Persistence 与 Command

```python
@dataclass(frozen=True, slots=True)
class CommandContext:
    trace_id: UUID
    ipc_session_id: UUID
    window_session_id: UUID
    idempotency_key: UUID
    deadline_at: datetime
    company_id: UUID | None

@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    aggregate_version: int
    company_id: UUID | None
    payload: BaseModel
    occurred_at: datetime

class UnitOfWork(Protocol):
    async def execute(
        self,
        context: CommandContext,
        request_sha256: str,
        command: Callable[[WriteSession], Awaitable[CommandResult]],
    ) -> CommandResult: ...
```

`UnitOfWork.execute` 在一个写事务内完成：幂等键检查、业务写、Domain Event、Outbox、幂等响应；任一步失败全部回滚。

### 1.5 Review 提交

```python
class ReviewIssueInput(BaseModel):
    client_issue_id: UUID
    severity: Literal["blocker", "high", "medium", "low"]
    category: Literal[
        "functional",
        "security",
        "performance",
        "reliability",
        "maintainability",
        "documentation",
        "test",
        "contract",
        "review_execution",
    ]
    description: Annotated[str, StringConstraints(min_length=1, max_length=20_000)]
    expected: Annotated[str, StringConstraints(min_length=1, max_length=10_000)]
    actual: Annotated[str, StringConstraints(min_length=1, max_length=10_000)]
    evidence_refs: tuple[UUID, ...]
    suggested_fix: Annotated[str, StringConstraints(min_length=1, max_length=20_000)]
    assignee_employee_id: UUID | None

class SubmitReviewRequest(BaseModel):
    company_id: UUID
    assignment_id: UUID
    reviewer_run_id: UUID
    reviewed_artifact_id: UUID
    reviewed_sha256: str
    report_artifact_id: UUID
    verdict: Literal["pass", "needs_changes", "failed"]
    issues: tuple[ReviewIssueInput, ...]
    expected_assignment_version: PositiveInt
```

### 1.6 Health

```python
class HealthSnapshot(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    observed_at: datetime
    profile: ProfileHealth
    ipc: IpcHealth
    queues: QueueHealth
    runtime: RuntimeHealth
    workers: tuple[WorkerHealth, ...]
    event_loop_lag_ms: NonNegativeInt
    disk_free_bytes: NonNegativeInt
```

其 JSON 字段必须逐字符合核心架构设计第 11.4 节；Rust 负责追加 IPC、Process Supervisor、Credential Broker 和 Egress Broker 状态。

---

### Task 1: 建立安全清理入口与锁定开发基线

**Files:**
- Create: `scripts/dev-reset-profiles.sh`
- Create: `tests/scripts/test_dev_reset_profiles.py`
- Modify: `.gitignore`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: 项目根路径、固定确认参数 `--confirm-delete-all-local-profiles`。
- Produces: 只删除 iBreeze 开发 Profile/CAS/Worktree/LanceDB/Runtime 临时目录的无任意路径参数脚本；构建缓存不再被 Git 跟踪。

- [ ] **Step 1: 写缺确认参数和越界路径的失败测试**

```python
def test_reset_requires_exact_confirmation(repo_copy: Path) -> None:
    result = run([repo_copy / "scripts/dev-reset-profiles.sh"], cwd=repo_copy)
    assert result.returncode != 0
    assert "confirm-delete-all-local-profiles" in result.stderr

def test_reset_rejects_non_project_root(repo_copy: Path) -> None:
    result = run(
        [repo_copy / "scripts/dev-reset-profiles.sh", "--confirm-delete-all-local-profiles"],
        cwd=repo_copy.parent,
    )
    assert result.returncode != 0
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
uv run --directory sidecar pytest ../tests/scripts/test_dev_reset_profiles.py -v
```

Expected: FAIL，原因是脚本不存在。

- [ ] **Step 3: 实现固定目标清理脚本**

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
test "${1:-}" = "--confirm-delete-all-local-profiles"
project_root="$(git rev-parse --show-toplevel)"
test "$(pwd -P)" = "$project_root"
test -f "$project_root/apps/desktop-core/Cargo.toml"
test -f "$project_root/sidecar/pyproject.toml"
```

实现必须从应用开发配置中读取固定根目录，逐一 `realpath` 并断言目标位于固定开发数据根下；检测到 iBreeze、Sidecar 或受管 CLI 进程时拒绝执行。脚本不得接受第二个参数、glob 目标、`$HOME`、`~` 或 `/` 作为删除目标。

`.gitignore` 必须包含 `**/tsconfig.tsbuildinfo`；若 Desktop/Admin build info 已被跟踪，使用 `git rm --cached` 从索引删除但保留本地缓存。测试先记录工作区状态，执行两个前端 build，再断言没有新增或修改的 build cache。

- [ ] **Step 4: 验证只删 fixture 内目标**

Run:

```bash
uv run --directory sidecar pytest ../tests/scripts/test_dev_reset_profiles.py -v
bash -n scripts/dev-reset-profiles.sh
```

Expected: 全部 PASS；fixture 外 canary 文件保留。

- [ ] **Step 5: 更新文档并提交**

```bash
git add scripts/dev-reset-profiles.sh tests/scripts/test_dev_reset_profiles.py .gitignore README.md docs/部署文档.md
git commit -m "chore(profile): add guarded development data reset"
```

---

### Task 2: 建立 Canonical RPC Registry 与错误码注册表

**Files:**
- Create: `packages/rpc-schema/registry.v1.json`
- Replace: `packages/rpc-schema/reverse-methods.v1.json`
- Create: `packages/rpc-schema/error-codes.v1.json`
- Modify: `packages/rpc-schema/meta.schema.json`
- Create: `packages/contracts/scripts/validate-registry.mjs`
- Create: `packages/contracts/fixtures/registry/valid-registry.json`
- Create: `packages/contracts/fixtures/registry/invalid-duplicate-owner.json`
- Create: `packages/contracts/fixtures/registry/invalid-unregistered-error.json`
- Modify: `packages/contracts/package.json`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: 主设计 J.14 的完整公开方法集合、核心架构第 5 节和第 13 节。
- Produces: `RegistryEntry[]`、`ReverseMethodEntry[]`、`ErrorCodeEntry[]`；后续生成器不得读取其他 ownership/kind 列表。

- [ ] **Step 1: 写 Registry 结构与集合失败测试**

```javascript
assertUnique(registry.map((entry) => entry.method));
assertEnum(entry.owner, ["rust", "sidecar", "supervisor"]);
assertEnum(entry.kind, ["read", "write", "stream"]);
assertEnum(entry.scope, ["none", "profile", "company"]);
assertFile(entry.request_schema);
assertFile(entry.response_schema);
assertSubset(entry.allowed_errors, errorCodes);
assertEqual(methodSet(registry), methodSetFromJ14Fixture);
```

`methodSetFromJ14Fixture` 固定提交为受 Review 的 golden fixture，集合逐项抄录主设计 J.14；不得在运行时解析 Markdown。

- [ ] **Step 2: 运行 Registry 测试并确认失败**

Run:

```bash
npm --prefix packages/contracts run lint
```

Expected: FAIL，提示 `registry.v1.json`、`reverse-methods.v1.json` 或 `error-codes.v1.json` 缺失。

- [ ] **Step 3: 写入固定 Registry 字段**

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

正向 Registry 必须删除核心架构第 5.2 节列出的原型方法。反向 Registry 固定为七个 Sidecar→Rust request：

```text
credential.http.start
credential.http.cancel
credential.probe
host.externalWrite.execute
runtime.process.start
runtime.process.cancel
runtime.process.status
```

以及四个 Rust→Sidecar notification：

```text
credential.http.event
runtime.process.registered
runtime.process.output
runtime.process.exited
```

- [ ] **Step 4: 验证所有权、Schema 路径和错误码闭包**

Run:

```bash
node packages/contracts/scripts/validate-registry.mjs
npm --prefix packages/contracts run lint
```

Expected: PASS；重复方法、缺 Schema、write TTL 为 0、company request 缺 `company_id`、错误码未登记时均 FAIL。

- [ ] **Step 5: 更新文档并提交**

```bash
git add packages/rpc-schema packages/contracts README.md docs/部署文档.md
git commit -m "feat(contracts): establish canonical rpc registry"
```

---

### Task 3: 补齐 RPC Schema 与完整 Domain Event Registry

**Files:**
- Modify: `packages/rpc-schema/methods/*.request.schema.json`
- Modify: `packages/rpc-schema/methods/*.response.schema.json`
- Create: `packages/contracts/domain-events/*.v1.schema.json`
- Modify: `packages/contracts/domain-events/registry.v1.json`
- Create: `packages/contracts/fixtures/rpc/`
- Create: `packages/contracts/fixtures/domain-events/`
- Modify: `packages/contracts/scripts/lint-contracts.mjs`
- Modify: `scripts/validate-schemas.py`
- Test: `tests/contract/test_schema_catalog.py`
- Test: `tests/contract/test_domain_event_catalog.py`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Task 2 Registry、主设计 J.14 请求/响应、H 章 DDL、核心架构第 5.3–5.4 节。
- Produces: 每个公开/反向方法的封闭 request/response Schema；完整 Domain Event payload Schema 和正反 fixture。

- [ ] **Step 1: 写空 Schema、未知字段和事件悬空失败测试**

```python
def test_every_non_empty_method_declares_properties(registry: Registry) -> None:
    for entry in registry.methods:
        request = load_schema(entry.request_schema)
        if not entry.empty_request:
            assert request["properties"]
            assert request["required"]
        assert request["additionalProperties"] is False
        response = load_schema(entry.response_schema)
        assert response["properties"]
        assert response["additionalProperties"] is False

def test_every_event_has_schema_and_two_fixtures(event_registry: EventRegistry) -> None:
    for event in event_registry.events:
        assert schema_path(event).is_file()
        assert valid_fixture(event).is_file()
        assert invalid_fixture(event).is_file()
```

- [ ] **Step 2: 运行契约测试并确认现有 76 个空根对象失败**

Run:

```bash
uv run --directory sidecar pytest ../tests/contract/test_schema_catalog.py ../tests/contract/test_domain_event_catalog.py -v
```

Expected: FAIL，并列出每个空 request/response 和缺失事件。

- [ ] **Step 3: 固定 Schema 通用规则与 Review 字段**

所有 Schema 使用：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "properties": {},
  "required": []
}
```

真正无参数的方法必须同时满足 Registry `empty_request=true`、Schema `maxProperties=0`。`review.submit.request` 必须逐字包含共享类型账本 1.5 的九个字段；`issues.items` 必须固定九个必填字段，`assignee_employee_id` 使用 `oneOf` 的 UUID/null，`evidence_refs` 至少一个 UUID 且去重，`reviewed_sha256` 使用 `^[0-9a-f]{64}$`。

- [ ] **Step 4: 冻结完整事件名称集合**

`packages/contracts/domain-events/registry.v1.json` 只允许以下 v1 event type：

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

每个状态事件 payload 必须包含 `aggregate_id/from_state/to_state/version`；`run.completed` 必须包含 `run_id/status:"succeeded"/evidence_artifact_ids`，不能把事件名称当作业务 Task 完成；`review.issue_changed` 必须包含 `issue_id/from_state/to_state/severity/assignee_employee_id/evidence_refs`，其中 `evidence_refs` 是至少一个 Artifact UUID 的去重数组。

- [ ] **Step 5: 为每个 Schema 增加正反 fixture**

```json
{
  "event_type": "review.issue_changed",
  "version": 1,
  "producer": "review.resolveIssue",
  "payload_schema": "review.issue_changed.v1.schema.json",
  "requires_company_id": true,
  "consumers": ["review_projection", "completion_projection"]
}
```

非法 fixture 至少分别覆盖缺 required、未知字段、非 `Z` 时间、错误 UUID、错误 hash、越界长度和未登记枚举。

- [ ] **Step 6: 运行完整 Schema 门禁**

Run:

```bash
npm --prefix packages/contracts run lint
uv run --directory sidecar python ../scripts/validate-schemas.py
uv run --directory sidecar pytest ../tests/contract/test_schema_catalog.py ../tests/contract/test_domain_event_catalog.py -v
```

Expected: 全部 PASS，且输出 `empty_unclassified=0`、`missing_event_schema=0`、`orphan_schema=0`。

- [ ] **Step 7: 更新文档并提交**

```bash
git add packages/rpc-schema packages/contracts scripts/validate-schemas.py tests/contract README.md docs/部署文档.md
git commit -m "feat(contracts): complete rpc and event schemas"
```

---

### Task 4: 生成 Rust、Python 与 TypeScript 契约代码

**Files:**
- Create: `packages/contracts/scripts/generate-contracts.mjs`
- Modify: `scripts/schema-gen-rust/src/main.rs`
- Modify: `scripts/generate-contracts.sh`
- Modify: `scripts/check-contract-drift.sh`
- Replace generated: `apps/desktop-core/src/generated/rpc/`
- Replace generated: `sidecar/ibreeze/generated/rpc/`
- Replace generated: `sidecar/ibreeze/generated/domain_events/`
- Replace generated: `apps/desktop/src/generated/rpc/`
- Create: `apps/desktop/src/generated/rpc/client.ts`
- Create: `tests/contract/test_generated_contract_sets.py`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Task 2–3 Registry、Schema、fixture。
- Produces: 三语言同集合类型、生成的 `METHOD_META`、`REVERSE_METHOD_META`、`ERROR_CODES`、`DOMAIN_EVENT_META` 和 TypeScript `GeneratedRpcClient`。

- [ ] **Step 1: 写三语言集合漂移失败测试**

```python
def test_generated_sets_equal_registry() -> None:
    expected = registry_method_set()
    assert rust_generated_method_set() == expected
    assert python_generated_method_set() == expected
    assert typescript_generated_method_set() == expected
```

再增加 golden payload 测试：同一 `review.submit`、`runtime.process.start` 和 `system.health` 在三语言中序列化后必须与 RFC 8785 canonical JSON fixture 相同。

- [ ] **Step 2: 运行生成测试并确认失败**

Run:

```bash
bash scripts/generate-contracts.sh
uv run --directory sidecar pytest ../tests/contract/test_generated_contract_sets.py -v
```

Expected: FAIL，原因是生成器没有输出 Registry metadata 或集合包含已删除方法。

- [ ] **Step 3: 实现单一生成流水线**

```text
validate registry
→ validate schemas and fixtures
→ generate Rust
→ generate Pydantic
→ generate TypeScript
→ generate typed clients and dispatch metadata
→ format generated files
→ compile all generated files
→ compare sets
```

生成器遇到无法表达的 Schema 必须退出非零；禁止生成 `serde_json::Value`、`Any`、`unknown` 作为领域对象。只有 Credential HTTP 的协议专属 `request/payload` 字段允许受 Schema 约束的 JSON 值。

- [ ] **Step 4: 生成强类型 TypeScript Client**

```ts
export interface GeneratedRpcClient {
  call<M extends RpcMethod>(
    method: M,
    params: RpcRequestMap[M],
    options: RpcCallOptions
  ): Promise<RpcResponseMap[M]>;
}

export interface RpcCallOptions {
  idempotencyKey: string | null;
  deadlineAt: string;
}
```

Client 内部把 `idempotencyKey` 映射为 Rust Command 参数 `idempotency_key`，业务 Hook 不允许直接 `invoke("rpc_request", ...)`。

- [ ] **Step 5: 验证生成可重复且工作区无漂移**

Run:

```bash
bash scripts/generate-contracts.sh
bash scripts/check-contract-drift.sh
cargo check --manifest-path apps/desktop-core/Cargo.toml --all-features
uv run --directory sidecar python -m compileall -q ibreeze/generated
uv run --directory sidecar pytest ../tests/contract/test_generated_contract_sets.py -v
npm --prefix apps/desktop run typecheck
git diff --exit-code -- apps/desktop-core/src/generated sidecar/ibreeze/generated apps/desktop/src/generated
```

Expected: 全部 PASS；连续生成两次无差异。

- [ ] **Step 6: 更新文档并提交**

```bash
git add packages scripts apps/desktop-core/src/generated sidecar/ibreeze/generated apps/desktop/src/generated tests/contract README.md docs/部署文档.md
git commit -m "feat(contracts): generate typed cross-runtime clients"
```

---

### Task 5: 重建 `001_initial.sql` 与 Migration Runner

**Files:**
- Replace: `sidecar/ibreeze/persistence/migrations/001_initial.sql`
- Create: `sidecar/ibreeze/persistence/connection.py`
- Create: `sidecar/ibreeze/persistence/migrator.py`
- Create: `sidecar/ibreeze/persistence/profile.py`
- Delete after replacement: `sidecar/ibreeze/persistence/migrations.py`
- Create: `sidecar/tests/persistence/test_connection.py`
- Create: `sidecar/tests/persistence/test_migrator.py`
- Create: `sidecar/tests/persistence/test_profile.py`
- Modify: `tests/contract/test_db_baseline.py`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: 主设计 H 章全部 DDL、核心架构第 12.9 节 Rework DDL、Task 3 Schema Epoch 约束。
- Produces: `ProfileDatabase.prepare(path) -> PreparedProfileDatabase`、单独 bootstrap 的 `schema_migrations`、完整 `001_initial.sql`；身份校验由 Task 7 在 WriteQueue 启动后执行。

- [ ] **Step 1: 写空目录、重复 DDL 和 checksum 失败测试**

```python
async def test_empty_profile_is_created_only_by_initial_migration(tmp_path: Path) -> None:
    db = await ProfileDatabase.prepare(tmp_path / "profile.db")
    assert await db.applied_versions() == [(1, "001_initial.sql")]
    assert await db.foreign_key_check() == []
    assert await db.integrity_check() == "ok"

def test_no_runtime_module_contains_business_ddl() -> None:
    assert find_sql_ddl("sidecar/ibreeze", exclude={"persistence/migrations"}) == []
```

增加 SQLite 版本、JSON1、FTS5、`foreign_keys`、hash drift、running 中断、磁盘满和外键失败用例。

- [ ] **Step 2: 运行持久化测试并确认旧 DDL 旁路失败**

Run:

```bash
uv run --directory sidecar pytest tests/persistence/test_connection.py tests/persistence/test_migrator.py tests/persistence/test_profile.py -v
```

Expected: FAIL，列出 `local_db.py` 的 `_CREATE_TABLES_SQL`、重复读池或缺少 bootstrap ledger。

- [ ] **Step 3: 实现 Migration Ledger**

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

该表由 Migration Runner 在执行 `001_initial.sql` 前创建，初始脚本不得重复创建。迁移固定使用事务 A 写 `running`、事务 B `BEGIN IMMEDIATE` 执行脚本与检查并写 `completed`、失败后事务 C 写 `failed`。

- [ ] **Step 4: 将主设计 H 章 DDL逐表写入初始脚本**

顺序固定：

```text
local_profile/catalog cache
→ company/department/responsibility/employee/profile revision
→ conversation/message
→ company/department/employee task/plan/snapshot/dependency
→ agent run/runtime queue/event/checkpoint/tool execution
→ workspace/grant/artifact/contributor/version
→ review assignment/report/issue/rework attempt
→ approval/verification
→ domain event/outbox/idempotency/projection
→ knowledge/index/access log
→ backup/audit/settings
→ indexes/checks/immutable triggers
```

每个跨公司引用必须使用含 `company_id` 的组合外键；每个可变聚合必须包含 `version`；每个不可变证据表必须有 UPDATE/DELETE 拒绝 Trigger。

- [ ] **Step 5: 实现固定初始化顺序**

```python
async def prepare(path: Path) -> PreparedProfileDatabase:
    lock = await ProfileFileLock.acquire(path)
    bootstrap = await open_bootstrap_connection(path)
    await verify_sqlite_capabilities(bootstrap)
    await MigrationRunner(bootstrap).apply_all()
    await bootstrap.close()
    return PreparedProfileDatabase(path=path, lock=lock)
```

Task 7 使用 PreparedProfileDatabase 打开运行写连接和读池；运行连接必须逐次设置并验证 `journal_mode=WAL`、`foreign_keys=ON`、`busy_timeout=5000`、`synchronous=NORMAL`、`temp_store=MEMORY`、`defer_foreign_keys=OFF`。

- [ ] **Step 6: 验证空库、故障恢复和 Schema 完整性**

Run:

```bash
uv run --directory sidecar pytest tests/persistence -v --cov=ibreeze.persistence --cov-branch --cov-fail-under=100
uv run --directory sidecar pytest ../tests/contract/test_db_baseline.py -v
```

Expected: 全部 PASS；从空目录只产生一个完成的 `001_initial.sql` 记录。

- [ ] **Step 7: 更新文档并提交**

```bash
git add sidecar/ibreeze/persistence sidecar/tests/persistence tests/contract/test_db_baseline.py README.md docs/部署文档.md
git commit -m "feat(persistence): rebuild profile schema and migrator"
```

---

### Task 6: 实现单写连接、WriteQueue、Unit of Work 与幂等

**Files:**
- Replace: `sidecar/ibreeze/persistence/write_queue.py`
- Replace: `sidecar/ibreeze/persistence/read_pool.py`
- Create: `sidecar/ibreeze/persistence/unit_of_work.py`
- Create: `sidecar/ibreeze/persistence/idempotency.py`
- Create: `sidecar/ibreeze/persistence/repositories.py`
- Create: `sidecar/ibreeze/events/store.py`
- Create: `sidecar/ibreeze/events/outbox.py`
- Create: `sidecar/tests/persistence/test_write_queue.py`
- Create: `sidecar/tests/persistence/test_unit_of_work.py`
- Create: `sidecar/tests/persistence/test_idempotency.py`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Task 5 `ProfileDatabase`、Task 3 Domain Event 类型。
- Produces: `WriteQueue.submit(WriteCommand[T]) -> T`、`UnitOfWork.execute(...)`、8 连接 `ReadPool`。

- [ ] **Step 1: 写并发顺序、背压和原子回滚测试**

```python
async def test_write_queue_never_exceeds_capacity(write_queue: WriteQueue) -> None:
    await submit_33_blocked_commands(write_queue)
    assert write_queue.depth == 32
    assert write_queue.waiting_producers == 1

async def test_uow_rolls_back_event_outbox_and_response_on_failure(uow: UnitOfWork) -> None:
    with pytest.raises(InjectedFailure):
        await uow.execute(context(), request_hash(), command_failing_after_event)
    assert await count_business_rows() == 0
    assert await count_domain_events() == 0
    assert await count_outbox_rows() == 0
    assert await count_idempotency_rows() == 0
```

- [ ] **Step 2: 运行测试并确认直接 `BEGIN IMMEDIATE` 路径失败**

Run:

```bash
uv run --directory sidecar pytest tests/persistence/test_write_queue.py tests/persistence/test_unit_of_work.py tests/persistence/test_idempotency.py -v
```

Expected: FAIL，并定位 `rpc_server.py` 或 Worker 绕过队列的写路径。

- [ ] **Step 3: 实现容量 32 的单写队列**

```python
class WriteQueue:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._queue: asyncio.Queue[WriteEnvelope[Any]] = asyncio.Queue(maxsize=32)
        self._connection = connection

    async def submit(self, command: WriteCommand[T]) -> T:
        envelope = WriteEnvelope(command=command)
        await self._queue.put(envelope)
        return await envelope.result
```

只有 queue worker 持有写连接；取消调用方等待不能取消已经开始的事务。关闭时先拒绝新命令，再 drain 10 秒，最后 checkpoint WAL。

- [ ] **Step 4: 实现 8 连接只读池**

```python
class ReadPool:
    def __init__(self, connections: tuple[ReadConnection, ...]) -> None:
        if len(connections) != 8:
            raise ValueError("read pool requires exactly eight connections")
```

借出、归还和重新借出时断言无活动事务且 `PRAGMA defer_foreign_keys=0`；不满足时回滚、丢弃并补建连接。

- [ ] **Step 5: 实现 Unit of Work 与幂等冲突**

```python
async def execute(self, context, request_sha256, command):
    async def transaction(write_session):
        cached = await self._idempotency.lookup(
            write_session, context.idempotency_key, request_sha256
        )
        if cached is not None:
            return cached
        result = await command(write_session)
        await self._events.append_all(write_session, result.events)
        await self._outbox.enqueue_all(write_session, result.outbox)
        await self._idempotency.store(write_session, context, request_sha256, result.response)
        return result.response
    return await self._write_queue.submit(transaction)
```

同键同 hash 返回原响应；同键不同 hash 返回 `IDEMPOTENCY_CONFLICT`；过期清理由 Worker 通过 WriteQueue 执行。

- [ ] **Step 6: 验证并发、取消、磁盘满和 100% 覆盖**

Run:

```bash
uv run --directory sidecar pytest tests/persistence/test_write_queue.py tests/persistence/test_unit_of_work.py tests/persistence/test_idempotency.py -v --cov=ibreeze.persistence --cov-branch --cov-fail-under=100
```

Expected: 全部 PASS；测试进程中同时存在的 SQLite writer 恒为 1。

- [ ] **Step 7: 更新文档并提交**

```bash
git add sidecar/ibreeze/persistence sidecar/ibreeze/events sidecar/tests/persistence README.md docs/部署文档.md
git commit -m "feat(persistence): serialize writes through unit of work"
```

---

### Task 7: 重建 Application Lifecycle、Worker Supervisor、Health 与 Backup Barrier

**Files:**
- Create: `sidecar/ibreeze/application/lifecycle.py`
- Replace: `sidecar/ibreeze/application/app.py`
- Create: `sidecar/ibreeze/workers/supervisor.py`
- Create: `sidecar/ibreeze/workers/spec.py`
- Create: `sidecar/ibreeze/observability/health.py`
- Create: `sidecar/ibreeze/backup/barrier.py`
- Create: `sidecar/tests/application/test_lifecycle.py`
- Create: `sidecar/tests/workers/test_supervisor.py`
- Create: `sidecar/tests/observability/test_health.py`
- Create: `sidecar/tests/backup/test_barrier.py`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Task 5 `ProfileDatabase`、Task 6 WriteQueue/ReadPool/UnitOfWork。
- Produces: `ApplicationLifecycle.start()`, `ApplicationLifecycle.stop()`, `WorkerSupervisor`, Sidecar 部分 `HealthSnapshot`, `BackupBarrier.acquire()`.

- [ ] **Step 1: 写唯一启动顺序和故障清理测试**

```python
async def test_lifecycle_starts_in_fixed_order(recorder: Recorder) -> None:
    await lifecycle(recorder).start()
    assert recorder.events == [
        "profile_lock",
        "uds_handshake_only",
        "bootstrap_db",
        "migration",
        "runtime_writer",
        "read_pool",
        "write_queue",
        "identity_check",
        "worker_supervisor",
        "rpc_dispatcher",
        "handshake_ready",
    ]

async def test_start_failure_closes_every_acquired_resource() -> None:
    app = lifecycle(fail_at="worker_supervisor")
    with pytest.raises(WorkerStartError):
        await app.start()
    assert app.open_resources == ()
```

- [ ] **Step 2: 写 Worker 重启阈值和 Health 状态测试**

```python
async def test_worker_fails_after_five_restarts(fake_clock: FakeClock) -> None:
    supervisor = failing_supervisor(fake_clock)
    await fake_clock.advance(seconds=1 + 2 + 4 + 8 + 16)
    assert supervisor.health("RuntimeWorker").state == "failed"
    assert supervisor.system_status in {"degraded", "unhealthy"}
```

固定 Worker 集合为 `RuntimeWorker/AnalysisWorker/OutboxWorker/KnowledgeWorker/ReconciliationWorker/BackupWorker/EventCompactionWorker`；审批过期、投影对账、CAS 对账和保留策略分别作为 Reconciliation/Backup 的固定 work item，不另建未登记 Worker。每 5 秒 heartbeat，15 秒无 heartbeat 视为 failed，退避为 1/2/4/8/16 秒，5 分钟内最多重启 5 次。

- [ ] **Step 3: 运行测试并确认旧 Application 双读池和双队列失败**

Run:

```bash
uv run --directory sidecar pytest tests/application/test_lifecycle.py tests/workers/test_supervisor.py tests/observability/test_health.py tests/backup/test_barrier.py -v
```

Expected: FAIL，原因包括启动顺序不一致、Worker 集合不足、Health 常量化或第二套 ReadPool。

- [ ] **Step 4: 实现唯一生命周期**

```python
class ApplicationLifecycle:
    async def start(self) -> Application:
        self._transport = await self._transport_factory.bind_handshake_only()
        self._prepared = await ProfileDatabase.prepare(self._path)
        self._writer = await self._prepared.open_writer()
        self._read_pool = await ReadPool.open(self._prepared.path, size=8)
        self._write_queue = await WriteQueue.start(self._writer)
        await self._profile_identity.verify(self._write_queue, self._identity)
        self._workers = await WorkerSupervisor.start(self._worker_specs())
        self._dispatcher = GeneratedDispatcher(self._uow, self._queries)
        await self._transport.mark_ready(self.health_snapshot())
        return Application(...)
```

`app.py` 只能装配依赖，不创建第二套连接、队列、Worker 或 Dispatcher。

- [ ] **Step 5: 实现 Health 合成输入**

```python
def sidecar_health(self) -> SidecarHealth:
    return SidecarHealth(
        profile=self._profile_health.snapshot(),
        queues=self._queue_health(),
        workers=self._workers.health(),
        event_loop_lag_ms=self._lag_monitor.current_ms,
        disk_free_bytes=self._disk_probe.free_bytes,
    )
```

DB、Migration 或 WriteQueue failed 产生 `unhealthy`；非关键 Worker failed 产生 `degraded`；外部 Agent 未安装不改变总状态。Sidecar 不伪造 Rust IPC/Broker/Process 状态。

- [ ] **Step 6: 实现 Backup Barrier**

```python
@asynccontextmanager
async def acquire_backup_barrier(self, timeout: timedelta):
    await self._runtime.pause_new_leases()
    await self._write_queue.barrier(timeout)
    await self._database.checkpoint("TRUNCATE")
    try:
        yield ConsistentSnapshot(...)
    finally:
        self._runtime.resume_new_leases()
```

10 秒未获得 barrier 返回 `BACKUP_WRITE_BARRIER_TIMEOUT`；失败不得留下暂停调度状态。

- [ ] **Step 7: 验证生命周期、故障恢复和覆盖率**

Run:

```bash
uv run --directory sidecar pytest tests/application tests/workers tests/observability/test_health.py tests/backup/test_barrier.py -v --cov=ibreeze.application --cov=ibreeze.workers --cov=ibreeze.observability --cov-branch --cov-fail-under=100
```

Expected: 全部 PASS；关闭顺序为拒绝新 RPC、停止新 lease、停止 Worker、drain 写队列、checkpoint、关闭读池、关闭 writer、释放锁。先停止 Worker 是为了禁止新的写请求进入队列，再由 WriteQueue 完成已接收事务的排空。

- [ ] **Step 8: 更新文档并提交**

```bash
git add sidecar/ibreeze/application sidecar/ibreeze/workers sidecar/ibreeze/observability sidecar/ibreeze/backup sidecar/tests README.md docs/部署文档.md
git commit -m "feat(sidecar): unify lifecycle workers and health"
```

---

### Task 8: 实现 Duplex UDS Multiplexer 与生成 Dispatcher

**Files:**
- Create: `apps/desktop-core/src/ipc/frame.rs`
- Create: `apps/desktop-core/src/ipc/multiplexer.rs`
- Create: `apps/desktop-core/src/ipc/session.rs`
- Create: `apps/desktop-core/src/ipc/dispatcher.rs`
- Modify: `apps/desktop-core/src/ipc/mod.rs`
- Create: `sidecar/ibreeze/rpc/frame.py`
- Create: `sidecar/ibreeze/rpc/multiplexer.py`
- Create: `sidecar/ibreeze/rpc/session.py`
- Create: `sidecar/ibreeze/rpc/dispatcher.py`
- Create: `apps/desktop-core/tests/ipc_duplex.rs`
- Create: `sidecar/tests/rpc/test_duplex.py`
- Create: `tests/integration/test_duplex_uds.py`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Task 4 生成的 MethodMeta 与 request/response 类型、Task 7 handshake-only 生命周期。
- Produces: Rust/Python 双向 `call`, `notify`, `cancel`, `close_generation`；单连接完成正向 RPC、反向 RPC、notification、heartbeat 和 shutdown。

- [ ] **Step 1: 写帧解析和恶意输入失败测试**

```rust
#[test]
fn rejects_zero_oversized_batch_and_top_level_array() {
    assert_eq!(decode_frame(&[0, 0, 0, 0]), Err(FrameError::InvalidLength));
    assert_eq!(decode_frame(&oversized_header()), Err(FrameError::TooLarge));
    assert_eq!(decode_json(br#"[{}]"#), Err(FrameError::TopLevelObjectRequired));
}
```

同时覆盖截断 header/body、非法 UTF-8、16 MiB+1、第二连接、错误 HMAC proof、nonce replay 和旧 session。

- [ ] **Step 2: 写并发乱序、deadline、背压和重连测试**

```python
async def test_out_of_order_responses_match_original_requests(pair: DuplexPair) -> None:
    first = asyncio.create_task(pair.core.call("slow", {}))
    second = asyncio.create_task(pair.core.call("fast", {}))
    assert await second == {"name": "fast"}
    assert await first == {"name": "slow"}

async def test_generation_change_fails_all_pending(pair: DuplexPair) -> None:
    pending = asyncio.create_task(pair.sidecar.call("credential.probe", {}))
    await pair.reconnect()
    with pytest.raises(IpcConnectionLost):
        await pending
```

- [ ] **Step 3: 运行测试并确认单向 RPC 结构失败**

Run:

```bash
cargo nextest run --manifest-path apps/desktop-core/Cargo.toml ipc_duplex
uv run --directory sidecar pytest tests/rpc/test_duplex.py ../tests/integration/test_duplex_uds.py -v
```

Expected: FAIL，原因是现有 `rpc/reverse.rs` 不支持多路复用、流通知和 generation。

- [ ] **Step 4: 实现 4-byte 帧与 pending map**

```rust
pub const MAX_FRAME_BYTES: usize = 16 * 1024 * 1024;
pub const MAX_PENDING_PER_DIRECTION: usize = 256;
pub const MAX_STREAM_BUFFER_FRAMES: usize = 64;

pub struct Multiplexer {
    generation: u64,
    pending: HashMap<RpcId, PendingRequest>,
    streams: HashMap<Uuid, ActiveStream>,
    writer: mpsc::Sender<Frame>,
}
```

pending 达 256 返回 `IPC_BACKPRESSURE`；stream 缓冲达 64 后生产者等待，连续 5 秒无法发送则取消关联请求或进程。

- [ ] **Step 5: 实现严格处理顺序**

```text
frame parse
→ JSON-RPC parse
→ meta/deadline/session
→ method/direction
→ generated request decode
→ handler
→ generated response encode
→ frame write
```

未登记方法返回 `METHOD_NOT_ALLOWED`；`deadline_at` 已过返回 `IPC_DEADLINE_EXCEEDED`；反向 request 必须是 `sidecar:{uuid}`，正向 request 必须是 `core:{uuid}`。

- [ ] **Step 6: 实现握手与合成 Health**

```rust
pub async fn open_profile(&self) -> Result<CompositeHealth, CoreError> {
    let handshake = self.call_supervisor("system.handshake", ...).await?;
    ensure!(handshake.database_status == "ready", CoreError::ProfileNotReady);
    let sidecar = self.call_supervisor("system.health", ...).await?;
    let composite = self.health_composer.compose(sidecar, self.local_health());
    ensure!(composite.status == HealthStatus::Healthy, CoreError::ProfileNotReady);
    Ok(composite)
}
```

Rust 每 5 秒 health、3 秒 timeout、连续 3 次失败判 lost；60 秒最多重启 3 次，第 4 次进入 diagnostics。

- [ ] **Step 7: 运行 Rust、Python 与真实 UDS 集成测试**

Run:

```bash
cargo nextest run --manifest-path apps/desktop-core/Cargo.toml ipc_duplex
uv run --directory sidecar pytest tests/rpc/test_duplex.py ../tests/integration/test_duplex_uds.py -v
```

Expected: 全部 PASS；断线后 pending/stream 全部收到同一 generation 的稳定错误。

- [ ] **Step 8: 更新文档并提交**

```bash
git add apps/desktop-core/src/ipc apps/desktop-core/tests sidecar/ibreeze/rpc sidecar/tests/rpc tests/integration README.md docs/部署文档.md
git commit -m "feat(ipc): add authenticated duplex multiplexer"
```

---

### Task 9: 实现 Rust Credential HTTP Broker

**Files:**
- Create: `apps/desktop-core/src/broker/mod.rs`
- Create: `apps/desktop-core/src/broker/credential.rs`
- Create: `apps/desktop-core/src/broker/http.rs`
- Create: `apps/desktop-core/src/broker/http_stream.rs`
- Create: `apps/desktop-core/src/broker/dns_policy.rs`
- Create: `apps/desktop-core/src/broker/lease.rs`
- Create: `apps/desktop-core/tests/credential_http_broker.rs`
- Create: `apps/desktop-core/tests/credential_canary.rs`
- Create: `apps/desktop-core/tests/ssrf_matrix.rs`
- Modify: `apps/desktop-core/Cargo.toml`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Task 8 反向 `credential.http.start/cancel/probe`、已验签 Catalog、Keychain bundle。
- Produces: `CredentialBroker::start/cancel/probe`、有序 `credential.http.event`。

- [ ] **Step 1: 写凭据边界和构造失败测试**

```rust
#[tokio::test]
async fn api_key_never_crosses_sidecar_boundary() {
    let canary = "ibreeze-canary-secret";
    let event = broker_with_key(canary).execute(valid_request()).await.unwrap();
    assert!(!serialized_uds_frames().contains(canary));
    assert!(!captured_logs().contains(canary));
    assert!(!event.to_string().contains(canary));
}
```

覆盖不存在 credential、损坏 Keychain、Provider/Model binding 不匹配、relative path 越界、请求体含 `authorization/api_key/token/proxy`、401/403 和取消。

- [ ] **Step 2: 写 SSRF 与重定向矩阵**

```rust
#[test_case("127.0.0.1")]
#[test_case("169.254.169.254")]
#[test_case("::1")]
#[test_case("fc00::1")]
fn rejects_forbidden_addresses(address: &str) { ... }
```

覆盖 userinfo、IP literal、非 HTTPS、不同 origin 重定向、超过 3 次重定向、DNS 重绑定、private/link-local/multicast/reserved IPv4/IPv6。

- [ ] **Step 3: 运行 Broker 测试并确认占位 handler 失败**

Run:

```bash
cargo nextest run --manifest-path apps/desktop-core/Cargo.toml credential_http_broker credential_canary ssrf_matrix
```

Expected: FAIL，现有实现返回 `CREDENTIAL_BROKER_NOT_OPERATIONAL` 或固定 false。

- [ ] **Step 4: 实现 Credential 解析和请求构造**

```rust
pub async fn start(
    &self,
    request: CredentialHttpStartRequest,
    session: IpcSession,
) -> Result<CredentialHttpAccepted, BrokerError> {
    self.catalog.validate_binding(&request)?;
    self.schemas.validate_protocol_request(&request)?;
    let secret = self.keychain.load_zeroizing(request.credential_ref)?;
    let outbound = self.request_factory.build(request, secret)?;
    self.streams.spawn(outbound, session).await
}
```

Keychain `auth_type` 只允许 `bearer/x_api_key`；Header 由 Rust 按 Catalog credential schema 构造，Sidecar 不得传入任意 Header 或完整 URL。

- [ ] **Step 5: 实现流式事件、重试和取消**

```rust
enum BrokerEventKind {
    OutputTextDelta,
    ToolCallDelta,
    Usage,
    Completed,
    Failed,
}
```

事件 sequence 从 1 连续递增；非流式正文最大 16 MiB。只对连接前失败、429 和 5xx 按 1/2/4 秒退避重试，最多 3 次；401/403 不重试并返回 `CREDENTIAL_UNAVAILABLE`；cancel 幂等并清零 secret。

- [ ] **Step 6: 验证安全、故障和覆盖率**

Run:

```bash
cargo nextest run --manifest-path apps/desktop-core/Cargo.toml credential_http_broker credential_canary ssrf_matrix
cargo llvm-cov --manifest-path apps/desktop-core/Cargo.toml --all-features --fail-under-lines 100 --fail-under-functions 100 --fail-under-regions 100
```

Expected: 全部 PASS；canary 不出现在 UDS、日志、fixture 输出和崩溃诊断。

- [ ] **Step 7: 更新文档并提交**

```bash
git add apps/desktop-core/src/broker apps/desktop-core/tests apps/desktop-core/Cargo.toml README.md docs/部署文档.md
git commit -m "feat(broker): execute credentialed model requests in rust"
```

---

### Task 10: 实现每 Run CONNECT Egress Proxy

**Files:**
- Create: `apps/desktop-core/src/broker/egress.rs`
- Create: `apps/desktop-core/src/broker/connect.rs`
- Create: `apps/desktop-core/src/broker/domain_policy.rs`
- Create: `apps/desktop-core/tests/egress_connect.rs`
- Create: `apps/desktop-core/tests/egress_dns_rebinding.rs`
- Create: `apps/desktop-core/tests/egress_cleanup.rs`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Task 9 DNS Policy、签名 Catalog 的 Agent/Skill domains、ExecutionSnapshot 的计划显式域名。
- Produces: `EgressBroker::create_lease(run_id, policy) -> EgressLease`、`EgressLease.proxy_url()`、`EgressBroker::revoke(run_id)`。

- [ ] **Step 1: 写 CONNECT 认证和协议拒绝测试**

```rust
#[tokio::test]
async fn only_authenticated_connect_to_443_is_allowed() {
    assert_denied(raw_request("GET https://example.com/ HTTP/1.1"));
    assert_denied(connect("example.com:80", valid_token()));
    assert_denied(connect("127.0.0.1:443", valid_token()));
    assert_denied(connect("example.com:443", "wrong-token"));
    assert_allowed(connect("example.com:443", valid_token()));
}
```

- [ ] **Step 2: 写域名、容量、空闲和清理测试**

```rust
#[test]
fn wildcard_matches_exactly_one_left_label() {
    assert!(matches_domain("api.example.com", "*.example.com"));
    assert!(!matches_domain("a.b.example.com", "*.example.com"));
    assert!(!matches_domain("example.com", "*.example.com"));
}
```

每 Run 最大 32 隧道、建立速率 60/min、连接建立 timeout 10 秒、idle 120 秒；Run 结束、cancel、UDS lost 和 panic 都必须关闭 listener/tunnel 并清零 Token。

- [ ] **Step 3: 运行测试并确认“分配端口后释放”实现失败**

Run:

```bash
cargo nextest run --manifest-path apps/desktop-core/Cargo.toml egress_connect egress_dns_rebinding egress_cleanup
```

Expected: FAIL，原因是当前 Egress 没有持续 listener 和 tunnel。

- [ ] **Step 4: 实现 Lease 与 Basic Auth**

```rust
pub struct EgressLease {
    pub lease_id: Uuid,
    pub run_id: Uuid,
    listener: TcpListener,
    token: Zeroizing<String>,
    policy: DomainPolicy,
    tunnels: JoinSet<()>,
}

pub fn proxy_url(&self) -> SecretString {
    SecretString::new(format!("http://ibreeze:{}@127.0.0.1:{}", self.token, self.port()))
}
```

Token 使用 32 字节 CSPRNG，只通过子进程 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` 传入，不进入数据库或日志。

- [ ] **Step 5: 实现 DNS/IP 和重定向防护**

每次新连接重新解析 DNS，所有解析结果都必须通过禁止网段校验；同一 hostname 在连接前后解析到不同安全类别时拒绝。allowlist 是 AgentVersion、锁定 Skill 和计划显式域名的并集，输入全部来自已验签/已锁定快照。

```rust
async fn authorize_target(&self, host: &str) -> Result<Vec<IpAddr>, EgressError> {
    self.domain_policy.require_allowed(host)?;
    let addresses = self.resolver.resolve(host).await?;
    if addresses.is_empty() || addresses.iter().any(is_forbidden_address) {
        return Err(EgressError::AddressDenied);
    }
    Ok(addresses)
}
```

- [ ] **Step 6: 验证真实 tunnel 和资源清理**

Run:

```bash
cargo nextest run --manifest-path apps/desktop-core/Cargo.toml egress_connect egress_dns_rebinding egress_cleanup
```

Expected: 全部 PASS；测试结束后监听端口不可连接、活动 tunnel 为 0、Token 内存已 zeroize。

- [ ] **Step 7: 更新文档并提交**

```bash
git add apps/desktop-core/src/broker apps/desktop-core/tests README.md docs/部署文档.md
git commit -m "feat(egress): enforce per-run connect leases"
```

---

### Task 11: 实现 Rust Process Supervisor 与 macOS Seatbelt

**Files:**
- Create: `apps/desktop-core/src/runtime/mod.rs`
- Create: `apps/desktop-core/src/runtime/invocation.rs`
- Create: `apps/desktop-core/src/runtime/process_supervisor.rs`
- Create: `apps/desktop-core/src/runtime/process_registry.rs`
- Create: `apps/desktop-core/src/runtime/seatbelt.rs`
- Create: `apps/desktop-core/src/runtime/cancellation.rs`
- Replace: `apps/desktop-core/src/security/external_write.rs`
- Create: `apps/desktop-core/tests/runtime_invocation.rs`
- Create: `apps/desktop-core/tests/process_supervisor.rs`
- Create: `apps/desktop-core/tests/seatbelt.rs`
- Create: `apps/desktop-core/tests/process_cleanup.rs`
- Create: `apps/desktop-core/tests/external_write_receipt.rs`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Task 8 `runtime.process.*`、Task 10 EgressLease、Task 4 生成 Invocation 类型、已验签 Catalog/ExecutionSnapshot。
- Produces: `ProcessSupervisor::start/cancel/status/terminate_session`、`runtime.process.registered/output/exited` 和 `host.externalWrite.execute` 的单次执行 receipt。

- [ ] **Step 1: 写 Invocation 重验证失败测试**

```rust
#[tokio::test]
async fn rejects_snapshot_or_policy_hash_mismatch() {
    assert_error(
        supervisor.start(request_with_bad_snapshot()).await,
        "EXECUTION_SNAPSHOT_MISMATCH",
    );
    assert_no_process_spawned();
    assert_no_egress_lease();
}
```

覆盖 agent release、版本范围、executable realpath、`argv[0]`、cwd、purpose、WorkspacePolicy hash、NetworkPolicy hash、deadline、stdin 4 MiB 上限和非法 locale。

- [ ] **Step 2: 写 Seatbelt 逃逸与 purpose 矩阵**

```rust
#[test_case("review", "/workspace/source.rs", "write", false)]
#[test_case("company_plan", "/workspace/source.rs", "write", false)]
#[test_case("task_execution", "/workspace/source.rs", "write", true)]
#[test_case("task_execution", "/other-profile/secret", "read", false)]
fn enforces_purpose_matrix(purpose: &str, path: &str, op: &str, allowed: bool) { ... }
```

CLI 只允许网络连接当前 Lease 的 loopback 端口；直接 DNS/TCP/UDP、Keychain、其他 Profile、SSH/GPG、浏览器凭据和 Workspace 外写全部拒绝。

- [ ] **Step 3: 写进程输出、取消和 PID 复用测试**

```rust
#[tokio::test]
async fn cancellation_escalates_and_reaps_entire_group() {
    let process = spawn_stubborn_process_group().await;
    supervisor.cancel(process.id, "test").await.unwrap();
    assert_eq!(signals(process.id), [SIGINT, SIGTERM, SIGKILL]);
    assert!(!process_group_exists(process.pgid));
    assert_eq!(active_leases(), 0);
}
```

覆盖 stdout/stderr 共用 sequence、chunk 解码后 256 KiB、逻辑行 4 MiB、5 秒 UDS 背压、双重 fork、session lost 和错误 PID start time。

- [ ] **Step 4: 运行测试并确认 Python Supervisor 所有权冲突**

Run:

```bash
cargo nextest run --manifest-path apps/desktop-core/Cargo.toml runtime_invocation process_supervisor seatbelt process_cleanup
```

Expected: FAIL，原因是 Rust 尚未持有 CLI process group/Seatbelt。

- [ ] **Step 5: 实现固定进程环境**

```rust
pub struct ChildEnvironment {
    pub path: OsString,
    pub home: PathBuf,
    pub locale: String,
    pub http_proxy: SecretString,
    pub https_proxy: SecretString,
    pub all_proxy: SecretString,
    pub codex_home: Option<PathBuf>,
    pub claude_config_dir: Option<PathBuf>,
    pub xdg_config_home: Option<PathBuf>,
    pub xdg_cache_home: Option<PathBuf>,
}
```

Sidecar 不传 env map。Rust 创建 Run 专属 `HOME` 和 Agent 状态目录；`CODEX_HOME/CLAUDE_CONFIG_DIR/XDG_CONFIG_HOME/XDG_CACHE_HOME` 按 Agent 类型设置，路径必须位于 Profile Runtime 临时根。

- [ ] **Step 6: 实现启动、输出和退出**

```text
validate session and deadline
→ load signed catalog/snapshot
→ validate invocation and hashes
→ create egress lease
→ render and probe seatbelt profile
→ create process group
→ spawn CLI
→ notify registered
→ stream ordered output
→ wait/reap
→ close pipes and lease
→ zeroize token and remove temp files
→ notify exited
```

取消固定为 SIGINT 等 5 秒、SIGTERM 等 5 秒、SIGKILL、waitpid；重复 cancel 返回相同终态。

- [ ] **Step 7: 实现外部单目标写入与幂等 receipt**

```rust
pub struct ExternalWriteReceipt {
    pub approval_id: Uuid,
    pub run_id: Uuid,
    pub operation: ExternalWriteOperation,
    pub target_realpath: PathBuf,
    pub result_state_sha256: String,
    pub completed_at: DateTime<Utc>,
    pub receipt_sha256: String,
}
```

请求字段固定为 `approval_id/workspace_grant_id/run_id/operation/target_realpath/expected_old_sha256/source_relative_path/source_sha256/source_size/expires_at`。人工审批 target 固定绑定 `workspace_grant_id/target_realpath/operation/expected_old_sha256/source_sha256` 并保存 canonical JSON hash；Rust 必须重新解析 Workspace Grant、realpath、拒绝 symlink、验证旧状态和 `${profile_root}/external-write-staging/{approval_id}/` 下的 staging source，生成只允许单一目标的临时 Seatbelt Profile；成功后删除 staging 和临时权限。相同 approval 在目标仍为 old state 时只执行一次，在目标已等于 requested result 时只读重建等价 receipt，第三种状态返回 `APPROVAL_TARGET_CHANGED`。

- [ ] **Step 8: 在真实 macOS 执行 Seatbelt 与外部写验收**

Run:

```bash
cargo nextest run --manifest-path apps/desktop-core/Cargo.toml runtime_invocation process_supervisor seatbelt process_cleanup external_write_receipt
```

Expected: 全部 PASS；带 `ibreeze-macos-14` 与 `ibreeze-macos-26` 标签的真实 Apple Silicon runner 都实际拒绝凭据读取、外部写、直连公网和进程组逃逸。

- [ ] **Step 9: 更新文档并提交**

```bash
git add apps/desktop-core/src/runtime apps/desktop-core/src/security/external_write.rs apps/desktop-core/tests README.md docs/部署文档.md
git commit -m "feat(runtime): supervise sandboxed cli processes in rust"
```

---

### Task 12: 重建 Sidecar CLI Runtime、Process Client 与 Adapter

**Files:**
- Create: `sidecar/ibreeze/runtime/process_client.py`
- Create: `sidecar/ibreeze/runtime/invocation.py`
- Create: `sidecar/ibreeze/runtime/workspace_policy.py`
- Replace: `sidecar/ibreeze/runtime/gateway.py`
- Replace: `sidecar/ibreeze/runtime/adapters/codex.py`
- Replace: `sidecar/ibreeze/runtime/adapters/claude_code.py`
- Replace: `sidecar/ibreeze/runtime/adapters/opencode.py`
- Modify: `sidecar/ibreeze/runtime/checkpoint.py`
- Modify: `sidecar/ibreeze/runtime/recovery.py`
- Create: `sidecar/tests/runtime/test_process_client.py`
- Create: `sidecar/tests/runtime/test_invocation.py`
- Create: `sidecar/tests/runtime/test_cli_adapters.py`
- Create: `sidecar/tests/runtime/test_cli_resume.py`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Task 11 `runtime.process.start/cancel/status` 与 process notification、Task 6 UnitOfWork、ExecutionSnapshot。
- Produces: `ProcessClient`, `CliAdapter.build_invocation/consume_event/collect_result`, Runtime Gateway 的 `start/cancel/resume/get_status`。

- [ ] **Step 1: 写 Sidecar 禁止 spawn 和 env 注入的静态测试**

```python
def test_sidecar_has_no_process_spawn_or_exec_calls() -> None:
    forbidden = (
        "asyncio.create_subprocess_exec",
        "subprocess.",
        "os.exec",
        "os.spawn",
    )
    for path in python_files("sidecar/ibreeze"):
        source = path.read_text()
        assert not any(token in source for token in forbidden), path
```

再断言 Invocation 没有 `env/headers/api_key/authorization/full_url/proxy_url` 字段。

- [ ] **Step 2: 写三个 Adapter golden 测试**

```python
@pytest.mark.parametrize(
    ("agent_type", "fixture"),
    [
        ("codex_cli", "codex-invocation.json"),
        ("claude_code", "claude-invocation.json"),
        ("opencode", "opencode-invocation.json"),
    ],
)
def test_adapter_builds_fixed_invocation(agent_type: str, fixture: str) -> None:
    invocation = adapter(agent_type).build_invocation(snapshot_fixture(agent_type))
    assert invocation.model_dump(mode="json") == load_fixture(fixture)
```

每个 fixture 必须固定 executable、argv 顺序、stdin 格式、locale、purpose、cwd 和两个 policy hash；禁止任意 Shell 字符串。

- [ ] **Step 3: 运行测试并确认当前 Python Process Supervisor 失败**

Run:

```bash
uv run --directory sidecar pytest tests/runtime/test_process_client.py tests/runtime/test_invocation.py tests/runtime/test_cli_adapters.py tests/runtime/test_cli_resume.py -v
```

Expected: FAIL，定位 Python spawn、空 reverse handler、Adapter 重复职责或缺 sequence。

- [ ] **Step 4: 实现唯一 Adapter Protocol**

```python
class CliAdapter(Protocol):
    agent_type: Literal["codex_cli", "claude_code", "opencode"]

    def build_invocation(
        self,
        run: AgentRun,
        snapshot: ExecutionSnapshot,
        prompt: RuntimePrompt,
        workspace_policy: WorkspacePolicy,
        network_policy: NetworkPolicy,
    ) -> RuntimeProcessStartRequest: ...

    def consume_event(self, state: AdapterState, event: RuntimeProcessOutput) -> AdapterState: ...

    def collect_result(self, state: AdapterState, exited: RuntimeProcessExited) -> AgentRunResult: ...
```

Adapter 只能做协议参数和输出解析；不得持有进程、网络、Seatbelt、数据库或任务状态机。

- [ ] **Step 5: 实现 Process Client 与有序输出**

```python
class ProcessClient:
    async def start(self, request: RuntimeProcessStartRequest) -> RuntimeProcessRef:
        return await self._rpc.call("runtime.process.start", request)

    async def cancel(self, process_id: UUID, run_id: UUID, reason: str) -> ProcessTerminal:
        return await self._rpc.call(
            "runtime.process.cancel",
            {"process_id": process_id, "run_id": run_id, "reason": reason},
        )
```

`runtime.process.output` 必须按共用 sequence 连续消费；缺口、重复不同 payload 或跨 run/process id 立即取消 Run 并返回 `EVENT_SEQUENCE_INVALID`。Sidecar 按 stream 重组逻辑行，单行超过 4 MiB 返回 `RUNTIME_OUTPUT_LIMIT_EXCEEDED`。

- [ ] **Step 6: 实现 Resume 快照核对**

```python
async def resume(self, run_id: UUID) -> RunHandle:
    run = await self._runs.get(run_id)
    snapshot = await self._snapshots.get(run.execution_snapshot_id)
    await self._resume_guard.verify_unchanged(run, snapshot)
    checkpoint = await self._checkpoints.latest_verified(run_id)
    return await self.start(run.to_resume_spec(checkpoint))
```

Resume 必须重新检查 Catalog release、Agent 版本、Skill hash、Workspace baseline、permission hash、network hash、可用性和原进程已退出；任何变化返回明确错误且不创建进程。

- [ ] **Step 7: 验证三个 CLI 的生成、解析、取消与恢复**

Run:

```bash
uv run --directory sidecar pytest tests/runtime/test_process_client.py tests/runtime/test_invocation.py tests/runtime/test_cli_adapters.py tests/runtime/test_cli_resume.py -v --cov=ibreeze.runtime --cov-branch --cov-fail-under=100
```

Expected: 全部 PASS；Sidecar 静态扫描无 spawn/exec，所有进程动作只经反向 RPC。

- [ ] **Step 8: 更新文档并提交**

```bash
git add sidecar/ibreeze/runtime sidecar/tests/runtime README.md docs/部署文档.md
git commit -m "feat(sidecar-runtime): delegate cli execution to rust"
```

---

### Task 13: 重建 API Model Agent Loop 与 HTTP Broker Transport

**Files:**
- Create: `sidecar/ibreeze/runtime/model_runtime/agent_loop.py`
- Create: `sidecar/ibreeze/runtime/model_runtime/transport.py`
- Create: `sidecar/ibreeze/runtime/model_runtime/protocols/openai_responses.py`
- Create: `sidecar/ibreeze/runtime/model_runtime/protocols/openai_chat_completions.py`
- Create: `sidecar/ibreeze/runtime/model_runtime/protocols/anthropic_messages.py`
- Create: `sidecar/ibreeze/runtime/model_runtime/tool_loop.py`
- Modify: `sidecar/ibreeze/runtime/permission_gateway.py`
- Replace: `sidecar/ibreeze/approvals/service.py`
- Create: `sidecar/tests/model_runtime/test_transport.py`
- Create: `sidecar/tests/model_runtime/test_agent_loop.py`
- Create: `sidecar/tests/model_runtime/test_tool_loop.py`
- Create: `sidecar/tests/model_runtime/test_external_write_receipt.py`
- Create: `sidecar/tests/security/test_api_key_boundary.py`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Task 9 `credential.http.*`、Task 6 UnitOfWork、Task 3 协议 Schema、Runtime Tool Registry。
- Produces: `BrokerModelTransport.turn(ModelTurnRequest) -> AsyncIterator[ModelEvent]`、完整 Built-in Agent Loop。

- [ ] **Step 1: 写 Broker-only 网络边界测试**

```python
def test_model_runtime_cannot_import_http_clients_or_open_sockets() -> None:
    forbidden_imports = {"httpx", "requests", "aiohttp", "urllib3", "socket"}
    assert imported_modules("sidecar/ibreeze/runtime/model_runtime") & forbidden_imports == set()

async def test_transport_uses_reverse_rpc_only(fake_rpc: FakeRpc) -> None:
    await collect(BrokerModelTransport(fake_rpc).turn(valid_turn()))
    assert fake_rpc.calls[0].method == "credential.http.start"
```

- [ ] **Step 2: 写 Agent Loop 多轮工具测试**

```python
async def test_agent_loop_executes_tool_and_returns_verified_result() -> None:
    model = scripted_model([
        tool_call("read_file", {"path": "src/main.rs"}),
        final_answer("implemented"),
    ])
    result = await AgentLoop(model, tools()).run(run_spec())
    assert result.status == "succeeded"
    assert result.tool_executions[0].tool_name == "read_file"
    assert result.final_artifact_ids
```

覆盖多工具、非法工具参数、purpose 禁止工具、工具审批、模型取消、流中断、格式修复最多 2 次和 deadline。

- [ ] **Step 3: 运行测试并确认 stub Transport 失败**

Run:

```bash
uv run --directory sidecar pytest tests/model_runtime tests/security/test_api_key_boundary.py -v
```

Expected: FAIL，当前 `runtime/transport.py` 的真实路径抛出 `NotImplementedError`。

- [ ] **Step 4: 实现 Broker Model Transport**

```python
class BrokerModelTransport:
    async def turn(self, request: ModelTurnRequest) -> AsyncIterator[ModelEvent]:
        accepted = await self._rpc.call(
            "credential.http.start",
            request.to_broker_request(),
        )
        async for event in self._rpc.stream("credential.http.event", accepted.request_id):
            yield self._protocols.decode(request.protocol, event)
```

Transport 只传 `credential_ref/provider_release_id/model_binding_id/protocol/relative_path/request/deadline_at`；不得出现 Secret 或完整 URL。

- [ ] **Step 5: 实现完整 Agent Loop**

```text
load immutable run/snapshot/context
→ build system/user prompt
→ broker model turn
→ parse text/tool calls
→ validate Tool name and JSON Schema
→ enforce purpose permission
→ execute tool or create HumanApproval
→ append immutable RunEvent/ToolExecution
→ continue model turn
→ run Verification Loop
→ write Artifact and execution report
→ mark AgentRun succeeded
```

AgentRun `succeeded` 只写运行结果和证据，不修改 EmployeeTask/DepartmentTask/CompanyTask 状态。

- [ ] **Step 6: 实现 HumanApproval 与外部写 receipt 消费**

```python
async def consume_external_write(
    self,
    context: CommandContext,
    approval_id: UUID,
    receipt: ExternalWriteReceipt,
) -> ApprovalResult:
    async def command(session: WriteSession):
        approval = await self._repo.lock(session, approval_id)
        self._receipt_guard.verify_all_fields(approval, receipt)
        await self._tools.mark_completed(session, approval.tool_execution_id, receipt)
        consumed = await self._repo.transition(session, approval, "consumed")
        return CommandResult(
            response=ApprovalResult.from_entity(consumed),
            events=(approval_consumed_event(consumed),),
            outbox=(resume_agent_run(consumed.run_id),),
        )
    return await self._uow.execute(context, receipt.receipt_sha256, command)
```

`approval.resolve` 只接受 `allow/deny` 和 `expected_version`。allowed 但 receipt 未落库时继续出现在 `approval.listPending` 且 `execution_pending=true`；重复 allow 只重试同一 `host.externalWrite.execute`，不能形成第二次副作用。

- [ ] **Step 7: 验证协议、工具、审批、多轮取消和凭据 canary**

Run:

```bash
uv run --directory sidecar pytest tests/model_runtime tests/security/test_api_key_boundary.py -v --cov=ibreeze.runtime.model_runtime --cov=ibreeze.approvals --cov-branch --cov-fail-under=100
```

Expected: 全部 PASS；API Key canary 不出现在 Sidecar 环境、日志、SQLite、Event、Artifact 或测试快照。

- [ ] **Step 8: 更新文档并提交**

```bash
git add sidecar/ibreeze/runtime/model_runtime sidecar/ibreeze/runtime/permission_gateway.py sidecar/ibreeze/approvals sidecar/tests/model_runtime sidecar/tests/security README.md docs/部署文档.md
git commit -m "feat(model-runtime): drive agent loops through rust broker"
```

---

### Task 14: 实现 Review Aggregate、命令处理与 Artifact 失效

**Files:**
- Create: `sidecar/ibreeze/domain/review/entities.py`
- Create: `sidecar/ibreeze/domain/review/state.py`
- Create: `sidecar/ibreeze/domain/review/commands.py`
- Create: `sidecar/ibreeze/domain/review/repository.py`
- Create: `sidecar/ibreeze/application/review_handlers.py`
- Replace: `sidecar/ibreeze/review/service.py`
- Modify: `sidecar/ibreeze/artifacts/service.py`
- Create: `sidecar/tests/review/test_state.py`
- Create: `sidecar/tests/review/test_submit.py`
- Create: `sidecar/tests/review/test_self_review.py`
- Create: `sidecar/tests/review/test_artifact_stale.py`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Task 3 `review.submit` 类型、Task 6 UnitOfWork、Artifact current hash、AgentRun 与 contributor 证据。
- Produces: `StartReview`, `SubmitReview`, `StartIssueFix`, `ResolveIssue`, `VerifyIssue`, `CloseIssue`, `RejectIssue` Command Handler。

- [ ] **Step 1: 写所有合法和非法状态边测试**

```python
@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("assigned", "in_review"),
        ("assigned", "stale"),
        ("assigned", "cancelled"),
        ("in_review", "submitted"),
        ("in_review", "stale"),
        ("in_review", "cancelled"),
        ("submitted", "stale"),
    ],
)
def test_review_assignment_allowed_edges(source: str, target: str) -> None:
    assert transition_assignment(source, target).state == target

def test_unlisted_edge_is_rejected() -> None:
    with pytest.raises(StateTransitionInvalid):
        transition_assignment("submitted", "in_review")
```

ReviewIssue 边固定为 `open→fixing/rejected`、`fixing→resolved`、`resolved→verified/fixing`、`verified→closed/fixing`；blocker/high 禁止 rejected。

- [ ] **Step 2: 写 `SubmitReview` 十项 guard 失败测试**

```python
async def test_contributor_cannot_review_own_artifact(handler: SubmitReviewHandler) -> None:
    request = request_for_contributor_reviewer()
    with pytest.raises(ReviewSelfAssignment):
        await handler.handle(context(), request)
    assert await count_review_reports() == 0
```

分别覆盖公司/任务链、assignment state/version、reviewer run purpose/employee、contributor 排除、artifact id/hash、report artifact creator/type、verdict/issues 配对、severity/category/assignee/evidence refs。

- [ ] **Step 3: 运行 Review 测试并确认旧 service 直接写失败**

Run:

```bash
uv run --directory sidecar pytest tests/review -v
```

Expected: FAIL，定位直接 SQL 状态更新、缺幂等或过期 Artifact 仍可通过。

- [ ] **Step 4: 实现不可变状态表与 Command Handler**

```python
ASSIGNMENT_TRANSITIONS = MappingProxyType({
    "assigned": frozenset({"in_review", "stale", "cancelled"}),
    "in_review": frozenset({"submitted", "stale", "cancelled"}),
    "submitted": frozenset({"stale"}),
    "stale": frozenset(),
    "cancelled": frozenset(),
})
```

Handler 必须使用 `UPDATE ... WHERE id=? AND version=?`，影响行数不是 1 返回 `OPTIMISTIC_LOCK_CONFLICT`；Repository 不提供 `set_status`。

- [ ] **Step 5: 实现 `SubmitReview` 单事务写入**

```python
async def handle(self, context: CommandContext, request: SubmitReviewRequest):
    async def command(session: WriteSession):
        assignment = await self._repo.lock_assignment(session, request.assignment_id)
        await self._guards.validate(session, assignment, request)
        report = await self._repo.create_report(session, request)
        issues = await self._repo.create_issues(session, request.issues)
        assignment = await self._repo.transition(session, assignment, "submitted")
        return CommandResult(
            response=SubmitReviewResponse.from_entities(assignment, report, issues),
            events=(review_submitted_event(...),),
            outbox=(evaluate_employee_acceptance(...),),
        )
    return await self._uow.execute(context, canonical_hash(request), command)
```

- [ ] **Step 6: 实现 Artifact supersede 同事务失效**

新 Artifact version 提交时必须同时把旧 version `is_current=false`、新 version `is_current=true`、旧 hash 的非终态 Assignment 置 `stale`、发出 `artifact.superseded` 和 `review.staled`。旧 Report 保留审计，旧 Issue 设置 `superseded_by_artifact_id`，不进入 Completion Gate。

```python
async def supersede(session: WriteSession, old: Artifact, new: Artifact) -> CommandResult:
    await artifacts.mark_current(session, old.id, False)
    await artifacts.insert_current(session, new)
    stale = await reviews.stale_assignments_for_hash(session, old.object_sha256)
    await issues.mark_superseded(session, old.id, new.id)
    return CommandResult(
        response=new.to_response(),
        events=(artifact_superseded(old, new), *review_staled_events(stale)),
        outbox=tuple(recheck_review(assignment.id) for assignment in stale),
    )
```

- [ ] **Step 7: 验证 Review 并发、幂等与覆盖率**

Run:

```bash
uv run --directory sidecar pytest tests/review -v --cov=ibreeze.domain.review --cov=ibreeze.application.review_handlers --cov-branch --cov-fail-under=100
```

Expected: 全部 PASS；并发提交只有一个成功，重复同幂等键返回相同响应。

- [ ] **Step 8: 更新文档并提交**

```bash
git add sidecar/ibreeze/domain/review sidecar/ibreeze/application/review_handlers.py sidecar/ibreeze/review sidecar/ibreeze/artifacts sidecar/tests/review README.md docs/部署文档.md
git commit -m "feat(review): enforce evidence-bound review commands"
```

---

### Task 15: 实现三级 Completion Gate、返工与事件推进

**Files:**
- Create: `sidecar/ibreeze/domain/tasks/state.py`
- Create: `sidecar/ibreeze/domain/tasks/commands.py`
- Create: `sidecar/ibreeze/application/completion_handlers.py`
- Create: `sidecar/ibreeze/application/rework_handlers.py`
- Replace: `sidecar/ibreeze/orchestration/completion_gate.py`
- Modify: `sidecar/ibreeze/events/outbox.py`
- Create: `sidecar/tests/completion/test_employee_gate.py`
- Create: `sidecar/tests/completion/test_department_gate.py`
- Create: `sidecar/tests/completion/test_company_gate.py`
- Create: `sidecar/tests/completion/test_rework.py`
- Create: `sidecar/tests/completion/test_event_progression.py`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Task 14 Review/Issue、Artifact/Verification/Report、Task 6 UnitOfWork、Task 3 Domain Events。
- Produces: `AcceptEmployeeTask`, `CompleteDepartmentTask`, `CompleteCompanyTask`, `RequestDepartmentRework`, `RequestCompanyRework` 和幂等 `Evaluate*` 内部 Command。

- [ ] **Step 1: 写 H.7 全量状态边枚举测试**

```python
@pytest.mark.parametrize("aggregate", ["company_task", "department_task", "employee_task"])
def test_transition_table_exactly_matches_design_fixture(aggregate: str) -> None:
    assert implementation_edges(aggregate) == load_h7_golden_edges(aggregate)

def test_repository_exposes_no_generic_status_setter() -> None:
    assert not hasattr(TaskRepository, "set_status")
    assert not hasattr(TaskRepository, "update_status")
```

- [ ] **Step 2: 写 Employee Gate 每个 blocker 的独立测试**

```python
EMPLOYEE_BLOCKERS = (
    "missing_required_artifact",
    "employee_not_contributor",
    "verification_not_passed",
    "review_not_submitted",
    "review_not_passed",
    "blocking_issue_open",
    "execution_report_missing",
    "active_run_or_approval",
)
```

每个 blocker fixture 只违反一项并断言 `COMPLETION_GATE_BLOCKED` 的 `details.blockers` 精确等于该项。

- [ ] **Step 3: 写 Department 与 Company Gate blocker 测试**

Department 固定检查：required EmployeeTask accepted、Merge Task accepted、当前 department_report、公司级 Review verdict 为 `pass`、blocker/high closed、测试/验证 passed、下游交付物发布、无活跃 Run/审批/apply。

Company 固定检查：required DepartmentTask completed、全部 department_report 公司级 Review verdict 为 `pass`、跨部门一致性 Review verdict 为 `pass`、blocker/high closed、当前 final_report 及完整证据引用、总经理确认、Workspace `ready_to_apply/applied/abandoned`、无活跃 Run或未消费审批。

```python
@pytest.mark.parametrize("blocker", DEPARTMENT_BLOCKERS)
async def test_each_department_blocker_is_reported(blocker: str) -> None:
    evidence = valid_department_evidence().with_only_violation(blocker)
    assert await department_gate(evidence) == GateResult(blockers=(blocker,))

@pytest.mark.parametrize("blocker", COMPANY_BLOCKERS)
async def test_each_company_blocker_is_reported(blocker: str) -> None:
    evidence = valid_company_evidence().with_only_violation(blocker)
    assert await company_gate(evidence) == GateResult(blockers=(blocker,))
```

- [ ] **Step 4: 运行 Completion 测试并确认直接 UPDATE 失败**

Run:

```bash
uv run --directory sidecar pytest tests/completion -v
```

Expected: FAIL，定位 Worker/Run 完成函数直接设置 Task 状态的路径。

- [ ] **Step 5: 实现 Command-only 状态迁移**

```python
async def accept_employee_task(self, context, command):
    async def transaction(session):
        task = await self._tasks.lock_employee_task(session, command.task_id)
        blockers = await self._evidence.employee_blockers(session, task)
        if blockers:
            raise CompletionGateBlocked(blockers)
        accepted = await self._tasks.transition(
            session, task, expected="peer_reviewing", target="accepted"
        )
        return CommandResult(
            response=accepted.to_response(),
            events=(employee_task_status_changed(task, accepted),),
            outbox=(evaluate_department_readiness(task.department_task_id),),
        )
    return await self._uow.execute(context, command.hash(), transaction)
```

Department/Company 使用相同模式但各自独立 guard；不得复用一个接收任意 target 的 Handler。

- [ ] **Step 6: 实现返工 attempt 与证据版本链**

```python
@dataclass(frozen=True, slots=True)
class ReworkAttempt:
    id: UUID
    company_id: UUID
    company_task_id: UUID
    department_task_id: UUID | None
    source_review_issue_ids: tuple[UUID, ...]
    attempt_no: int
    status: Literal["planned", "running", "completed", "cancelled", "failed"]
    created_at: datetime
    completed_at: datetime | None
```

同一任务 `attempt_no` 唯一递增；返工不覆盖旧 Artifact/Review/Report；新 Artifact 通过 version chain 和 source issue ids 关联旧证据。

状态只允许 `planned→running/cancelled`、`running→completed/cancelled/failed`。同一 company task 与可空 department scope 最多一个 planned/running attempt；Completion Gate 读取最大 `attempt_no`，要求其状态为 completed，cancelled/failed 不能让更早 attempt 重新成为 current。

- [ ] **Step 7: 实现事件到幂等 Command 的唯一映射**

```python
EVENT_COMMAND_MAP = MappingProxyType({
    "review.submitted": EvaluateEmployeeAcceptance,
    "review.issue_changed": EvaluateAffectedTask,
    "employee_task.status_changed": EvaluateDepartmentReadiness,
    "department_task.status_changed": EvaluateCompanyReadiness,
})
```

只有 `review.issue_changed.to_state=closed`、`employee_task.status_changed.to_state=accepted`、`department_task.status_changed.to_state=completed` 才触发对应 Evaluate；重复或乱序事件由 event id/aggregate version 幂等忽略，不直接改状态。

- [ ] **Step 8: 验证三级闭环、返工多轮和覆盖率**

Run:

```bash
uv run --directory sidecar pytest tests/completion -v --cov=ibreeze.domain.tasks --cov=ibreeze.application.completion_handlers --cov=ibreeze.application.rework_handlers --cov-branch --cov-fail-under=100
```

Expected: 全部 PASS；Run `succeeded` 后 Task 仍保持原业务状态，只有证据齐备的 Completion Command 才推进。

- [ ] **Step 9: 更新文档并提交**

```bash
git add sidecar/ibreeze/domain/tasks sidecar/ibreeze/application sidecar/ibreeze/orchestration/completion_gate.py sidecar/ibreeze/events sidecar/tests/completion README.md docs/部署文档.md
git commit -m "feat(orchestration): gate task completion on review evidence"
```

---

### Task 16: Desktop 全量切换生成 RPC Client

**Files:**
- Replace: `apps/desktop/src/shared/rpcClient.ts`
- Modify: `apps/desktop/src/shared/tauriClient.ts`
- Delete: `apps/desktop/src/hooks/useOrchestration.ts`
- Delete: `apps/desktop/src/hooks/usePlan.ts`
- Modify: `apps/desktop/src/hooks/useReview.ts`
- Modify: `apps/desktop/src/hooks/useTask.ts`
- Modify: `apps/desktop/src/pages/ApprovalListPage.tsx`
- Modify: `apps/desktop/src/pages/TaskDetailPage.tsx`
- Modify: `apps/desktop/src/pages/ReviewPage.tsx`
- Modify: `apps/desktop/src/app/routes.tsx`
- Create: `apps/desktop/src/shared/rpcClient.test.ts`
- Create: `apps/desktop/src/pages/ApprovalListPage.test.tsx`
- Create: `apps/desktop/src/pages/TaskDetailPage.test.tsx`
- Modify: `README.md`
- Modify: `docs/部署文档.md`
- Create or Modify: `docs/用户手册.md`

**Interfaces:**
- Consumes: Task 4 `GeneratedRpcClient`、Task 14–15 Review/Task response。
- Produces: 所有页面只调用 Registry 内方法；审批请求固定使用 `allow/deny` 和 `expected_version`。

- [ ] **Step 1: 写 Registry 外方法和直接 invoke 失败测试**

```ts
it("contains no registry-external rpc method", () => {
  expect(scanRpcMethodLiterals("apps/desktop/src")).toEqual(registryMethods());
  expect(scanDirectInvokeCalls("apps/desktop/src")).toEqual([
    "apps/desktop/src/shared/tauriClient.ts",
  ]);
});
```

显式断言源码不出现 `planVersion.`, `orchestration.`, `READ_OPERATIONS` 或业务页面内 `invoke("rpc_request"`。

- [ ] **Step 2: 写审批字段和错误状态测试**

```tsx
it("sends allow with expected version", async () => {
  render(<ApprovalListPage client={client} />);
  await user.click(screen.getByRole("button", { name: "允许本次" }));
  expect(client.call).toHaveBeenCalledWith(
    "approval.resolve",
    {
      company_id: COMPANY_ID,
      approval_id: APPROVAL_ID,
      decision: "allow",
      expected_version: 3,
    },
    expect.objectContaining({ idempotencyKey: expect.any(String) }),
  );
});
```

覆盖 deny、版本冲突刷新、allowed 但 `execution_pending=true` 的重试和过期提示。

- [ ] **Step 3: 运行 Desktop 测试并确认旧 Hook 失败**

Run:

```bash
npm --prefix apps/desktop run test -- rpcClient ApprovalListPage TaskDetailPage
```

Expected: FAIL，列出 Registry 外方法、`approved/rejected` 决策或缺 `expected_version`。

- [ ] **Step 4: 实现单一 RPC Client 封装**

```ts
export const rpcClient: GeneratedRpcClient = {
  async call(method, params, options) {
    return invoke<RpcResponseMap[typeof method]>("rpc_request", {
      method,
      params,
      idempotency_key: options.idempotencyKey,
      deadline_at: options.deadlineAt,
    });
  },
};
```

写操作每次用户动作生成新 UUID；React Query 自动重试只能复用同一次动作的 key。读操作传 null。

- [ ] **Step 5: 删除无公开契约的页面能力**

删除 `OrchestrationPage` 的 Registry 外创建/运行/归档入口；任务编排结果改从 `task.getGraph/getEvidence`、`run.list/listEvents` 和事件订阅展示。计划历史只展示 `task.get` 返回的当前/历史计划字段，不调用 `planVersion.list`。

```ts
const orchestrationQueries = {
  graph: (companyId: string, taskId: string) =>
    rpcClient.call("task.getGraph", { company_id: companyId, id: taskId }, readOptions()),
  evidence: (companyId: string, taskId: string) =>
    rpcClient.call("task.getEvidence", { company_id: companyId, id: taskId }, readOptions()),
  runs: (companyId: string, taskId: string) =>
    rpcClient.call(
      "run.list",
      { company_id: companyId, filter: { task_id: taskId }, cursor: null, limit: 50 },
      readOptions(),
    ),
};
```

- [ ] **Step 6: 统一时间、数值和错误展示**

```ts
export function formatBeijingTime(value: string): string {
  return parseBackendTime(value).setZone("Asia/Shanghai").toFormat("yyyy-LL-dd HH:mm:ss");
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value);
}
```

所有页面只用共享 formatter；RPC 错误显示稳定 code/reference id，不展示堆栈、路径或凭据。

- [ ] **Step 7: 验证 Desktop 全量门禁**

Run:

```bash
npm --prefix apps/desktop run lint
npm --prefix apps/desktop run typecheck
npm --prefix apps/desktop run test:coverage
npm --prefix apps/desktop run build
```

Expected: 全部 PASS；手写源码四项覆盖率 100%，源码方法集合与 Registry 完全一致。

- [ ] **Step 8: 更新文档并提交**

```bash
git add apps/desktop/src apps/desktop/package.json README.md docs/部署文档.md docs/用户手册.md
git commit -m "feat(desktop): consume generated rpc client exclusively"
```

---

### Task 17: 关闭 Admin、Updater、部署与前端包体问题

**Files:**
- Modify: `apps/admin-web/src/utils/apiClient.ts`
- Modify: `apps/admin-web/src/stores/authStore.ts`
- Create: `apps/admin-web/src/utils/apiClient.test.ts`
- Create: `apps/admin-web/src/utils/deviceId.ts`
- Create: `apps/admin-web/src/utils/deviceId.test.ts`
- Modify: `apps/desktop-core/src/update/manifest.rs`
- Modify: `apps/desktop-core/src/update/rollback.rs`
- Create: `apps/desktop-core/src/update/archive.rs`
- Create: `apps/desktop-core/tests/updater_security.rs`
- Modify: `deploy/docker-compose.yml`
- Create: `deploy/docker-compose.prod.yml`
- Create: `deploy/.env.example`
- Modify: `apps/desktop/vite.config.ts`
- Modify: `apps/admin-web/vite.config.ts`
- Modify: `README.md`
- Modify: `docs/部署文档.md`
- Create or Modify: `docs/用户手册.md`

**Interfaces:**
- Consumes: 后台统一 `{data:{...},meta:{...}}` envelope、主设计 K.10–K.13。
- Produces: 正确 refresh、稳定 device id、安全 updater、dev/prod 分离部署、低于 500 KiB 的前端初始 chunk。

- [ ] **Step 1: 写 Admin refresh envelope 和 device id 测试**

```ts
it("reads refresh result from the common data envelope", async () => {
  mockPost("/admin/api/v1/auth/refresh", {
    data: { access_token: "next", user: USER },
    meta: { request_id: "req-1" },
  });
  await refreshSession();
  expect(authStore.getState().accessToken).toBe("next");
});

it("reuses the same device id across login attempts", () => {
  expect(getOrCreateDeviceId()).toBe(getOrCreateDeviceId());
});
```

- [ ] **Step 2: 写 Updater archive、probation 和 rollback 测试**

```rust
#[test]
fn rejects_archive_traversal_symlink_and_duplicate_paths() {
    assert_rejected("../escape");
    assert_rejected("safe/link-to-outside");
    assert_rejected_duplicate("bin/sidecar");
}
```

覆盖 Tauri 签名、Apple Code Signing、Notary、文件 hash、staging fsync/rename、30 秒 protocol/migration/health probation 和缓存安装包 rollback。

- [ ] **Step 3: 运行相关测试并确认现有回归**

Run:

```bash
npm --prefix apps/admin-web run test -- apiClient deviceId
cargo nextest run --manifest-path apps/desktop-core/Cargo.toml updater_security updater
```

Expected: Admin refresh 因读取错误层级而 FAIL；恶意 archive 或 rollback 缺口导致 Rust 测试 FAIL。

- [ ] **Step 4: 修复 Admin 认证状态**

```ts
type ApiEnvelope<T> = {
  data: T;
  meta: { request_id: string };
};

const { data } = await api.post<ApiEnvelope<RefreshResponse>>(
  "/admin/api/v1/auth/refresh",
  undefined,
  { withCredentials: true },
);
authStore.getState().setSession(data.data.access_token, data.data.user);
```

Refresh Token 只在 HttpOnly Cookie；Access Token 只在 Zustand 内存；device id 是安装级随机 UUID，不以用户名、邮箱或机器硬件 id 派生。

- [ ] **Step 5: 实现 Updater 安全解包和回滚**

```text
download to private staging
→ verify Tauri signature
→ verify Apple signature and notarization
→ parse archive entries without extracting
→ reject absolute/traversal/symlink/hardlink/duplicate/device entries
→ stream extract with per-file and total size limits
→ verify manifest hashes
→ fsync files and directory
→ atomic staging activation
→ 30-second health probation
→ retain or reinstall cached prior signed package on failure
```

更新安装前必须无 active AgentRun、无待审批且最近一次本地备份成功；数据库不得自动降级。

- [ ] **Step 6: 修复 Compose 和 Secret 边界**

MinIO 容器内 console 固定 `:9001`，宿主映射可配置但目标端口必须 9001。生产 Compose 只暴露 Gateway；PostgreSQL、MinIO 和 Backend 不直接暴露公网。Auth/Catalog/TLS Secret 使用只读 volume，私钥 `0400`、公钥/证书 `0444`，配置缺失或权限过宽拒绝启动。

```yaml
services:
  minio:
    command: server /data --console-address ":9001"
    expose: ["9000", "9001"]
  backend:
    expose: ["8000"]
    secrets:
      - auth_private_key
      - catalog_private_key
  gateway:
    ports: ["${IBREEZE_HTTPS_PORT:-443}:443"]
```

- [ ] **Step 7: 拆分前端 chunk**

```ts
manualChunks(id) {
  if (id.includes("antd/es/date-picker")) return "antd-date";
  if (id.includes("antd/es/table")) return "antd-table";
  if (id.includes("antd/es/form")) return "antd-form";
  if (id.includes("node_modules")) return "vendor";
}
```

路由页面使用 `lazy()`；构建测试读取 manifest，断言初始同步 chunk 和任一 vendor chunk gzip 前均小于 500 KiB。

- [ ] **Step 8: 验证 Admin、Updater、部署和构建**

Run:

```bash
npm --prefix apps/admin-web run lint
npm --prefix apps/admin-web run typecheck
npm --prefix apps/admin-web run test:coverage
npm --prefix apps/admin-web run build
cargo nextest run --manifest-path apps/desktop-core/Cargo.toml updater_security updater
docker compose -f deploy/docker-compose.yml config
docker compose -f deploy/docker-compose.prod.yml config
npm --prefix apps/desktop run build
```

Expected: 全部 PASS；Admin 手写源码覆盖率 100%，两个前端构建没有超过 500 KiB 的 chunk 警告。

- [ ] **Step 9: 更新文档并提交**

```bash
git add apps/admin-web apps/desktop-core/src/update apps/desktop-core/tests apps/desktop/vite.config.ts deploy README.md docs/部署文档.md docs/用户手册.md
git commit -m "fix(delivery): close auth updater and deployment gaps"
```

---

### Task 18: 建立唯一 fail-closed 验证入口与真实 E2E

**Files:**
- Replace: `scripts/verify-all.sh`
- Modify: `sidecar/pyproject.toml`
- Modify: `apps/desktop/vite.config.ts`
- Modify: `apps/admin-web/vite.config.ts`
- Create: `.github/workflows/contracts.yml`
- Create: `.github/workflows/desktop.yml`
- Create: `.github/workflows/sidecar.yml`
- Create: `.github/workflows/backend.yml`
- Create: `.github/workflows/e2e.yml`
- Create: `.github/workflows/security.yml`
- Create: `.github/workflows/release.yml`
- Create: `tests/e2e/api-model-agent.spec.ts`
- Create: `tests/e2e/cli-runtime.spec.ts`
- Create: `tests/e2e/review-rework.spec.ts`
- Create: `tests/e2e/fault-recovery.spec.ts`
- Create: `tests/performance/__init__.py`
- Create: `tests/performance/test_runtime_budgets.py`
- Modify: `tests/scripts/test_verify_all.py`
- Replace: `tests/contract/test_ci_policy.py`
- Modify: `coverage-exclusions.yml`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**
- Consumes: Tasks 1–17 所有代码和测试。
- Produces: 本地与 CI 使用同一个 `scripts/verify-all.sh`，工具缺失、测试为空、覆盖不足或 workflow 缺失均失败。

- [ ] **Step 1: 写缺工具、空测试和阈值下降失败测试**

```python
@pytest.mark.parametrize(
    "tool",
    ["node", "npm", "uv", "cargo", "cargo-nextest", "cargo-llvm-cov"],
)
def test_verify_fails_when_required_tool_is_missing(tool: str) -> None:
    result = run_verify_with_path_missing(tool)
    assert result.returncode != 0

def test_all_coverage_thresholds_are_one_hundred() -> None:
    source = Path("scripts/verify-all.sh").read_text()
    assert "--cov-fail-under=100" in source
    assert "--fail-under-lines 100" in source
    assert "--fail-under-functions 100" in source
    assert "--fail-under-regions 100" in source
```

- [ ] **Step 2: 写 CI policy 精确检查**

```python
def test_required_workflows_are_tracked_and_fail_closed() -> None:
    workflows = tracked_workflow_files()
    assert workflows == {
        ".github/workflows/contracts.yml",
        ".github/workflows/desktop.yml",
        ".github/workflows/sidecar.yml",
        ".github/workflows/backend.yml",
        ".github/workflows/e2e.yml",
        ".github/workflows/security.yml",
        ".github/workflows/release.yml",
    }
    for path in workflows:
        assert "scripts/verify-all.sh" in Path(path).read_text()
```

测试不得因目录或文件列表为空而 return。

- [ ] **Step 3: 写四条真实 E2E**

`api-model-agent.spec.ts`：注册/登录→创建公司/部门/职员→API Model 工具调用→Artifact→Review→完成。

`cli-runtime.spec.ts`：锁定三种 CLI 各执行 fixture→Workspace 写入→直连公网失败→CONNECT 成功→取消无残留。

`review-rework.spec.ts`：两名职员交叉 Review→blocker→返工→复测→关闭→部门报告→总经理最终报告。

`fault-recovery.spec.ts`：Worker crash、UDS lost、WriteQueue 背压、Backup barrier 和恢复。

```ts
test("blocker drives rework and final completion", async ({ page }) => {
  await createSoftwareCompanyFixture(page);
  await submitCompanyTask(page, "实现并测试示例功能");
  await approvePlan(page);
  await waitForReviewIssue(page, { severity: "blocker" });
  await triggerAssignedRework(page);
  await waitForIssueState(page, "closed");
  await expectFinalReport(page);
  await expect(page.getByTestId("company-task-status")).toHaveText("completed");
});
```

普通 PR 的 API Model E2E 使用仅在测试二进制中可注入的 TLS Provider fixture：它仍经过真实 UDS、Credential Broker、协议解析和 Tool Loop，但 `BrokerDependencies` 的 resolver/connector 只在 `cfg(test)` 接受本机证书；Release 构建不得包含该注入入口。受保护的 `security.yml/release.yml` 必须提供 `IBREEZE_E2E_PROVIDER_ORIGIN/CREDENTIAL/MODEL` Secret，额外对真实 staging Provider 执行同一用例；Secret 缺失时 workflow 失败而不是跳过。三种 CLI 必须在 macOS workflow 安装锁定版本并执行真实二进制，不用 shell fixture 代替。

- [ ] **Step 4: 写性能和容量硬门禁**

```python
def test_runtime_performance_budgets(benchmark_app: BenchmarkApp) -> None:
    assert benchmark_app.sidecar_cold_start_p95_ms(samples=20) < 3_000
    assert benchmark_app.uds_noop_p95_ms(samples=1_000) < 50
    assert benchmark_app.task_list_50_p95_ms(samples=200) < 50
    assert benchmark_app.event_projection_p95_ms(samples=500) < 100
    assert benchmark_app.reconcile_ten_runs_p95_ms(samples=20) < 10_000
```

同一测试还必须断言 UDS pending=256、stream buffer=64、WriteQueue=32、ReadPool=8、每 Run tunnel=32、Provider 非流式正文=16 MiB、output chunk=256 KiB、逻辑行=4 MiB、heartbeat=5 秒、Worker failed=15 秒、graceful shutdown=10 秒。性能样本预热 3 轮、正式运行 5 轮并取中位轮次的 p95；macOS release runner 超标直接失败。

- [ ] **Step 5: 运行测试并确认当前入口失败**

Run:

```bash
uv run --directory sidecar pytest ../tests/scripts/test_verify_all.py ../tests/contract/test_ci_policy.py -v
uv run --directory sidecar pytest ../tests/performance/test_runtime_budgets.py -v
npm --prefix tests/e2e run test
```

Expected: FAIL，原因包括阈值 62/77、系统 Python、workflow 为空或 E2E 文件不存在。

- [ ] **Step 6: 重写唯一验证脚本**

```bash
required_tools=(node npm uv cargo cargo-nextest cargo-llvm-cov)
```

固定顺序：

```text
lockfile and generated drift
→ contract registry/schema/fixtures
→ Rust fmt/clippy/nextest/llvm-cov 100%
→ Backend ruff/mypy/pytest coverage 100%
→ Sidecar ruff/mypy/pytest coverage 100%
→ Desktop lint/type/test coverage 100%/build
→ Admin lint/type/test coverage 100%/build
→ root tests under locked uv environment
→ performance budgets
→ Playwright E2E
→ release hygiene
→ git diff --check and generated diff
```

脚本只接受 `--scope contracts|desktop|sidecar|backend|e2e|security|release|all`；无参数等于 `all`。每个 scope 执行上述固定顺序中对应且完整的子集，不能降低该代码域覆盖率或跳过依赖契约。禁止工具回退、warning 后继续、空 glob 成功或动态降低阈值。

- [ ] **Step 7: 建立七个固定 CI Workflow**

每个 workflow 只调用同一脚本：

```text
contracts.yml → scripts/verify-all.sh --scope contracts
desktop.yml   → scripts/verify-all.sh --scope desktop
sidecar.yml   → scripts/verify-all.sh --scope sidecar
backend.yml   → scripts/verify-all.sh --scope backend
e2e.yml       → scripts/verify-all.sh --scope e2e
security.yml  → scripts/verify-all.sh --scope security
release.yml   → scripts/verify-all.sh --scope all
```

`security.yml` 使用 `runs-on: [self-hosted, macOS, ARM64, "${{ matrix.runner }}"]`，`matrix.runner` 只能取 `ibreeze-macos-14`、`ibreeze-macos-26`，并执行真实 CLI、Seatbelt、Updater 和签名测试；任一 runner 不在线、标签不匹配或测试未执行均为失败。七个 workflow 必须使用锁定 action SHA、最小 permissions、并发取消和 artifact 保留策略；`release.yml` 依赖其余 workflow 成功且重新执行完整门禁。

- [ ] **Step 8: 验证脚本策略与完整运行**

Run:

```bash
uv run --directory sidecar pytest ../tests/scripts/test_verify_all.py ../tests/contract/test_ci_policy.py -v
bash scripts/verify-all.sh
```

Expected: 全部 PASS，五个代码域覆盖率均达到 100%，Playwright 至少运行四个 spec，工作区无生成差异。

- [ ] **Step 9: 更新文档并提交**

```bash
git add scripts/verify-all.sh sidecar/pyproject.toml apps/desktop apps/admin-web .github tests coverage-exclusions.yml README.md docs/部署文档.md
git commit -m "ci(quality): enforce complete fail-closed verification"
```

---

### Task 19: 删除旧实现并执行一次性切换验收

**Files:**
- Delete: `sidecar/ibreeze/runtime/transport.py`
- Delete: `sidecar/ibreeze/runtime/process_supervisor.py`
- Delete: `sidecar/ibreeze/local_db.py`
- Delete: `apps/desktop-core/src/rpc/reverse.rs`
- Delete: `apps/desktop-core/src/security/credential_broker.rs`
- Delete: `apps/desktop-core/src/security/egress.rs`
- Remove obsolete code from: `sidecar/ibreeze/rpc_server.py`
- Remove obsolete code from: `sidecar/ibreeze/application/app.py`
- Remove obsolete code from: `sidecar/ibreeze/workers/*.py`
- Create: `scripts/check-release-hygiene.py`
- Create: `tests/contract/test_release_hygiene.py`
- Modify: `scripts/verify-all.sh`
- Modify: `README.md`
- Modify: `docs/部署文档.md`
- Modify: `docs/用户手册.md`

**Interfaces:**
- Consumes: Tasks 1–18 的目标实现。
- Produces: 单一生产路径、无旧 Schema/RPC/Adapter/手工方法表的 Release Candidate。

- [ ] **Step 1: 写旧路径和危险模式失败测试**

```python
FORBIDDEN_PATHS = (
    "sidecar/ibreeze/runtime/transport.py",
    "sidecar/ibreeze/runtime/process_supervisor.py",
    "sidecar/ibreeze/local_db.py",
    "apps/desktop-core/src/rpc/reverse.rs",
    "apps/desktop-core/src/security/credential_broker.rs",
    "apps/desktop-core/src/security/egress.rs",
)

FORBIDDEN_PRODUCTION_TOKENS = (
    "_CREATE_TABLES_SQL",
    "CREDENTIAL_BROKER_NOT_OPERATIONAL",
    "NotImplementedError",
    "runtime.processRegistered",
    "runtime.processExited",
    "planVersion.",
    "orchestration.",
)
```

扫描只允许测试 fixture 的明确 allowlist，生产路径出现任一项立即失败。

- [ ] **Step 2: 运行 Hygiene 测试并确认旧文件存在**

Run:

```bash
uv run --directory sidecar pytest ../tests/contract/test_release_hygiene.py -v
```

Expected: FAIL，并逐项列出待删除文件和 token。

- [ ] **Step 3: 删除旧文件和旁路**

删除项必须同时满足：

```text
没有 import
没有 Registry 条目
没有生成类型
没有路由/Hook
没有生产配置
没有测试依赖
没有文档把它描述为当前入口
```

`rpc_server.py` 只保留新的 `sidecar/ibreeze/rpc/dispatcher.py` 入口或直接删除旧模块；Worker 只能发 Command；所有手工 method ownership/kind/read list 全部删除。

- [ ] **Step 4: 执行开发 Profile 清理与空库启动**

Run:

```bash
scripts/dev-reset-profiles.sh --confirm-delete-all-local-profiles
```

Expected: 只删除列出的开发数据。随后启动应用，断言 `schema_epoch=1`、Migration 只有 `001_initial.sql`、首次合成 Health 为 healthy。

- [ ] **Step 5: 执行五项架构关闭矩阵**

```text
CUR-P0-01: API Model 真实工具 E2E + canary secret boundary
CUR-P0-02: Registry/Schema/Event/三语言集合零漂移
CUR-P0-05: 空库 Migration + 单 writer + Worker/Health fault injection
CUR-P1-01: 三 CLI + Seatbelt + CONNECT + cancel/resume
CUR-P1-02: Review→blocker→返工→复测→三级 Completion
```

每一项必须附命令、通过数量、覆盖率、日志 artifact id 和 Reviewer 结论；缺任一证据不得关闭。

- [ ] **Step 6: 运行完整门禁两次**

Run:

```bash
bash scripts/verify-all.sh
bash scripts/verify-all.sh
git status --short
```

Expected: 两次均 PASS；第二次证明生成、Migration fixture 和测试无非确定性；`git status --short` 为空。

- [ ] **Step 7: 执行独立安全与架构 Review**

Reviewer 必须逐项检查：

```text
Secret 边界
SSRF/DNS rebinding
Seatbelt/Workspace/外部写审批
UDS session/generation/deadline/backpressure
SQLite writer/UoW/idempotency
Review self-assignment/Artifact stale/Completion gates
Updater/部署/CI
```

blocker/high 必须为 0；medium/low 必须有明确 owner 和不影响发布的书面依据。

- [ ] **Step 8: 更新最终文档并提交**

```bash
git add -A
git commit -m "refactor(core): switch completely to trusted target architecture"
```

---

## 20. 规范与问题覆盖矩阵

本节是可独立使用的关闭账本。第三方无需回查历史 Review 报告即可知道每个问题的实际缺口、唯一实施方案和关闭标准。

| ID | 实际缺口与影响 | 固定解决方案 | 实现任务 | 必须提供的关闭证据 |
|---|---|---|---|---|
| CUR-P0-01 | Credential Broker、真实 UDS 和 Egress 仍为占位，API Model 无法执行真实 Agent Loop，Sidecar 可能绕过凭据和网络边界。 | Rust 独占 Keychain、Provider HTTP 与 CONNECT；Sidecar 只发送 `credential_ref` 和结构化模型请求；按 Run 签发、撤销网络 lease。 | Task 8–10、13 | API Model 工具 E2E；Sidecar canary secret 零命中；SSRF、DNS rebinding、直连公网负例；取消后连接与凭据全部清理。 |
| CUR-P0-02 | 76 个 request/response Schema 是空对象，Domain Event payload 不完整，三语言方法集合各自维护，编译通过仍可运行时漂移。 | `packages/rpc-schema` 与 `packages/contracts` 成为两个明确职责的唯一契约根；完整封闭 Schema、45 个事件、正反 fixture 和 Rust/Python/TypeScript 生成物均由 Registry 生成。 | Task 2–4 | 空 Schema 数为 0；45 个事件逐项有 Schema/正反 fixture/生产者/消费者；连续生成两次无差异；三语言 golden payload 相同。 |
| CUR-P0-03 | Desktop 调用 Registry 外方法，审批枚举、版本字段和幂等字段命名错误，页面可在运行时失败或把审批写入错误状态。 | 删除 `planVersion.*`、`orchestration.*` 等旁路入口；全部页面只经 `GeneratedRpcClient`；审批固定 `allow/deny + expected_version`；写调用统一 UUID 幂等键。 | Task 16 | Registry 外方法静态扫描为 0；页面方法集合与 J.14 完全一致；审批并发冲突、幂等复用和路由作用域 E2E 通过。 |
| CUR-P0-04 | 总验证脚本会回退或跳过工具，覆盖率远低于 100%，E2E 为空且 CI 缺失，因此可能产生假通过。 | 单一 `scripts/verify-all.sh` fail-closed；固定工具版本；五个代码域 100% 覆盖；四条真实 E2E；七个受跟踪 CI Workflow；缺工具、空测试集、离线安全 runner 均失败。 | Task 18–19 | 完整门禁连续两次 PASS；覆盖率报告绑定提交 SHA；Playwright 至少四个 spec；七个 Workflow 均执行且发布门禁不可绕过。 |
| CUR-P0-05 | DDL、Migration、ReadPool、WriteQueue 和 Worker 存在双轨；幂等、事件和业务写不在同一事务，故障时可产生半写状态。 | 空库只由 bootstrap ledger 与 `001_initial.sql` 创建；单 Writer、容量 32 WriteQueue、容量 8 ReadPool；Command/UoW 同事务写业务、Event、Outbox、幂等结果；Lifecycle 固定启动和关闭顺序。 | Task 5–7 | 空目录启动与 schema hash 测试；第二 writer/第二 pool 静态扫描为 0；故障注入证明全有或全无；七 Worker 健康和恢复测试。 |
| CUR-P0-06 | Admin device id 不稳定、Refresh 读取错误 envelope，且手写 DTO 偏离 Backend OpenAPI，真实登录刷新链会中断。 | 使用稳定 Keychain device id；Admin 只消费生成 OpenAPI Client；统一解析 `data.data`；Access Token 仅内存，Refresh Token 仅 HttpOnly Cookie。 | Task 17 | 登录→刷新→登出集成测试；重启后 device id 不变；Web Storage/日志/文件 canary 零命中；OpenAPI drift 为 0。 |
| CUR-P1-01 | CLI 没有完整 Workspace、Seatbelt、Egress、进程组取消和恢复闭环，任务结果与安全边界不可证明。 | Rust Process Supervisor 负责 spawn、PGID、输出序列、Seatbelt、Egress lease、取消和残留清理；Sidecar Adapter 只处理 Agent 协议和 checkpoint/resume。 | Task 10–12 | Codex/Claude Code/OpenCode fake 契约及真实冒烟；读写权限矩阵；cancel/timeout/crash/resume；凭据读、外部写、直连公网和 fork 逃逸全部失败。 |
| CUR-P1-02 | Run 完成仍可直接更新三级任务；Review、Artifact 失效、返工和 Completion Gate 未经统一 Command/UoW，任务可能提前完成或永久停滞。 | Review Aggregate、Issue、ReworkAttempt 和三级 Completion Engine 只通过 Command Handler 写状态；Run 只记录运行结果；Artifact 新版本使旧 Assignment/Issue 失效并触发重新评估。 | Task 14–15 | 所有允许边与非法边测试；自审/旧 hash/错误 reviewer run 拒绝；blocker→返工→复测→关闭；Employee/Department/Company 每个 Gate blocker 独立测试。 |
| CUR-P1-03 | Updater 缺少安全解包、原子切换、健康观察期和可靠回滚，恶意包或启动失败可破坏安装。 | Rust Updater 在 staging 校验签名、hash、路径与文件类型；同卷原子切换；固定 probation 健康检查；失败回滚到已验证缓存版本。 | Task 17 | 路径穿越、symlink/hardlink、超大 archive 负例；切换中断恢复；probation 失败自动回滚；签名、公证和 Gatekeeper 验证。 |
| CUR-P1-04 | Compose 仍是开发配置且 MinIO 端口错误，Secret、网络暴露、资源限制和恢复演练不满足生产部署。 | 分离 dev/prod Compose；只暴露 Gateway；PostgreSQL/MinIO/Backend 使用 Secret 文件和健康依赖；修正 MinIO 9001；固定 CPU/内存限制、备份与恢复命令。 | Task 17 | 两套 Compose config 校验；五服务健康；外部只能访问 Gateway；Secret 不进入环境/日志；空库部署与备份恢复演练。 |
| CUR-P1-05 | 根级测试环境、Sidecar 环境和 CI 环境不一致，历史测试失败未纳入门禁，测试资产无法作为裁决依据。 | 所有 Python 检查统一从锁定的 `uv` 环境运行；禁止 fallback；根级、Sidecar、Backend、前端、Rust 与 E2E 全部由同一验证入口编排。 | Task 18–19 | 干净 clone 完整执行；任一子命令故障注入时总脚本非零；无 skip/xfail；本地与 CI 命令和锁文件 hash 一致。 |
| CUR-P1-06 | Rust health 硬编码 healthy，DB、Queue、Worker、UDS、Broker、磁盘和恢复状态未实时汇聚，UI 可能显示假健康。 | Lifecycle 持有权威组件句柄；每个组件上报时间戳、延迟、深度、错误和恢复状态；Rust 合并 Sidecar 与受信内核探测，按固定阈值计算 healthy/degraded/failed。 | Task 7–11 | 每个组件故障注入；Worker 15 秒失败阈值；UDS generation 变化；Broker probe；磁盘/Outbox/Backup lag；UI 只显示实时聚合结果。 |
| CUR-P2-01 | Desktop/Admin `vendor-antd` 超过 1 MiB，首屏 chunk 超过 500 KiB，影响冷启动和更新。 | 路由级 lazy import；Ant Design 按需引入；禁止聚合 barrel 重新拉入全包；构建脚本对每个 initial chunk 强制 `<500 KiB`。 | Task 17 | 两个生产构建无 size warning；每个 initial chunk 原始大小小于 500 KiB；登录、公司页和 Admin 目录页按需加载 E2E。 |
| CUR-P2-02 | `READ_OPERATIONS`、Rust 分派、Sidecar 参数和 Admin DTO 仍有手工契约副本，未来修改会再次漂移。 | Registry 生成方法分类、分派表、Pydantic 模型、Rust 类型、TypeScript Client 和 OpenAPI Client；静态检查禁止应用目录维护平行集合。 | Task 2–4、16–17 | 手工方法/DTO 扫描为 0；生成物 hash 可复现；增删 fixture 方法后四端同步变更测试通过。 |
| NEW-P0-01 | Sidecar 存在未使用 import 与 mypy 泛型错误，主门禁在测试前失败。 | 在统一静态检查阶段修复并将 Ruff/Mypy/Pyright 作为不可跳过的前置门禁；禁止用 ignore 压制业务代码。 | Task 18 | Ruff、Mypy、Pyright 全部 PASS；故障 fixture 证明任一静态检查失败会阻断总脚本。 |
| NEW-P0-02 | CI policy 在 Workflow 列表为空时提前 return，本机空目录可假装“CI 存在”，干净 clone 实际没有任何 Workflow。 | 固定且跟踪七个 Workflow；policy 首先断言文件集合精确相等且非空，再检查 action SHA、权限和脚本参数。 | Task 18 | 干净 clone 存在七个 YAML；删除任一文件或清空集合时 policy 测试失败；所有 Workflow 只调用统一验证脚本。 |
| NEW-P1-01 | Admin Refresh 已切换 Cookie 但仍读取错误响应层级，刷新成功也会被前端视为失败。 | 生成 OpenAPI Client 统一 envelope 解码；Login、Refresh、401 单航班重试共享同一认证状态机。 | Task 17 | Mock 与真实 Backend 的 Login/Refresh/401 并发集成测试；一次刷新只发一个请求；失败后清空内存会话并回登录页。 |
| NEW-P1-02 | 前端构建修改被跟踪的 `tsconfig.tsbuildinfo`，导致构建后工作区脏、Review 与发布不可复现。 | 从 Git 移除 build cache，写入 `.gitignore`；验证脚本构建前后检查工作区；生成目录只允许经确定性生成检查变更。 | Task 1、17–19 | 连续两次 Desktop/Admin build 后 `git status --short` 为空；cache 文件未跟踪；生成差异由专用 drift 检查捕获。 |
| ARCH-06/08 | Rust↔Sidecar 既要支持双向请求，又要处理并发、超时、反压和重连，若无统一协议会发生 id 冲突与悬挂请求。 | 单条 Unix Domain Socket 上运行长度前缀 JSON-RPC；请求 id 使用方向前缀；generation 隔离；pending 256、stream 64、16 MiB 帧上限；断线统一取消。 | Task 8 | Rust/Python 同时发起请求、乱序响应、背压、超时、oversize、断线重连和 generation 隔离测试。 |
| ARCH-13/14/18 | 错误模型、旧路径删除和一次性切换若不明确，第三方可能保留兼容层或把内部错误直接暴露给 UI。 | Error Registry 固定公开错误闭包与 redaction；公开跨公司读取统一 `RESOURCE_NOT_FOUND`；Task 19 删除旧 RPC/DTO/DDL/stub，不设 Feature Flag 或双轨。 | Task 2–4、6、8–15、19 | Error 正反 fixture；异常 canary/绝对路径零泄露；删除路径扫描为 0；只从空 Profile 启动目标架构。 |

矩阵中的每一行都必须在 Task 19 的关闭报告中引用具体 commit、测试命令和证据文件；只引用实现代码或口头说明不能关闭问题。

## 21. 阶段出口

### Contract Gate（Task 4 后）

- Registry 方法集合与主设计 J.14 完全一致。
- 所有 request/response/event Schema 封闭且有正反 fixture。
- Rust/Python/TypeScript 集合、字段和 canonical JSON fixture 一致。
- 连续生成两次工作区无差异。

### Persistence Gate（Task 7 后）

- 空目录只由 bootstrap ledger 与 `001_initial.sql` 创建。
- 只有一个 writer、一个 WriteQueue、一个 ReadPool。
- 业务写、Event、Outbox、幂等结果在同一事务。
- Worker/Health/Backup barrier 故障测试通过。

### Trusted Runtime Gate（Task 13 后）

- Sidecar 无 Keychain、直连 HTTP、spawn/exec。
- API Model 和三种 CLI 都完成真实工具任务。
- CLI 直连公网、越界读写和进程逃逸失败。
- cancel、lost、timeout、resume 不残留进程、lease、secret 或临时文件。

### Review Gate（Task 15 后）

- 自审、过期 Artifact、错误 reviewer run 和非法状态边全部拒绝。
- Run succeeded 不能直接完成 Task。
- Employee、Department、Company 的每个 blocker 有独立测试。
- 多轮返工保留全部旧证据并只读取 current attempt。

### Release Gate（Task 19 后）

- 全量门禁连续两次通过。
- 手写代码覆盖率 100%。
- 四条真实 E2E 和 macOS 安全矩阵通过。
- 复核报告全部问题有关闭证据。
- 旧文件、旧方法、占位、兼容层和双轨 Schema 为零。
- 工作区干净，README、部署文档和用户手册与实现一致。

## 22. 交付证据格式

每个任务的 Reviewer 报告固定使用：

```markdown
Task:
Commit:
Design sections:
Files reviewed:
Commands executed:
Tests passed:
Coverage:
Security checks:
Contract/schema changes:
Documentation changes:
Issues:
Decision: PASS | NEEDS_CHANGES
Reviewer:
Reviewed at:
```

`Decision=PASS` 仅在本任务所有 Expected 结果、覆盖率和文档同步均满足时允许。`NEEDS_CHANGES` 必须列出文件、字段/函数、复现命令、实际结果、期望结果和修复建议。
