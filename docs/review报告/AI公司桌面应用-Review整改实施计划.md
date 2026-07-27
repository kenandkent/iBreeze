# iBreeze Review 整改 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 关闭《AI公司桌面应用-文档与代码Review详细报告.md》中的全部 11 个 P0、11 个 P1 和 5 个 P2 问题，使代码、设计方案、原实施计划、部署文档和用户文档形成可验证、可发布的一致交付物。

**Architecture:** 以 JSON Schema/OpenAPI 为跨语言唯一契约源，先修复会产生假阳性的质量门禁，再依次收敛认证与目录信任边界、本地持久化与进程生命周期、任务编排与 Review 状态机、Workspace 副作用、后台管理、备份更新和 UI。每个整改任务必须先提交可复现的失败测试，再实现最小闭环，并以独立 Review 和真实验证证据结束。

**Tech Stack:** React 19、TypeScript 5.7、Vite 6、TanStack Query 5、Zustand 5、Ant Design 5、Tauri 2、Rust 2021、Tokio 1、Python 3.12、Pydantic 2、aiosqlite、LanceDB、ONNX Runtime、FastAPI、SQLAlchemy 2 Async、Alembic、PostgreSQL 16、MinIO、JSON Schema 2020-12、OpenAPI 3.1、JSON-RPC 2.0。

## Global Constraints

- 设计方案 `docs/设计方案/AI公司桌面应用设计方案.md` 是字段、状态机、DDL、RPC、REST、安全边界和发布门禁的唯一事实来源；原实施计划是完整产品的任务基线；本计划只规定当前代码整改顺序和验证闭环。
- 中心后台只保存应用用户、管理员用户和全局 Agent、Model、Provider、Skill、Compatibility、Catalog Release 数据；公司、部门、职员实例、任务、会话、Run、Artifact、Review、知识正文和 Workspace 数据只能保存在桌面本地 Profile。
- WebView、Sidecar、SQLite、日志、Checkpoint、诊断包和测试快照均不得出现 Access Token、Refresh Token、OfflineSessionTicket 或 Provider API Key 明文。
- WebView 只能调用生成的 Tauri/RPC Client；不得手写 Command 名称、RPC 方法名或跨语言 DTO。
- API Model 必须由 Built-in Agent Runtime 执行完整 Agent Loop；Provider 网络和凭据只能经过 Rust Credential/Egress Broker。
- 当前 Run Workspace 内默认可读写；Workspace 外普通文件只读；外部写入只允许单目标、单动作、单次审批和可恢复 receipt。
- 协议和持久化时间使用 RFC 3339 UTC；前端统一按 `Asia/Shanghai` 展示；无时区字符串按北京时间墙钟时间解释。
- 前端数值统一最多保留两位小数且不补零。
- 手写可执行源码必须达到设计方案 K.14 定义的 100% 单元覆盖率；排除项只能来自 `coverage-exclusions.yml`，不得使用 pragma 或降低阈值绕过。
- 每项任务执行 TDD：失败测试必须先红，最小实现后变绿，再运行受影响模块全量测试；禁止删除断言、跳过测试、吞掉失败或伪造证据。
- 每次代码修改同步更新 `README.md` 和 `docs/部署文档.md`；用户可见行为同步更新 `docs/应用用户手册.md` 或 `docs/后管系统用户手册.md`；REST 变化同步更新 `docs/后管系统API文档.md`。
- 只修改当前项目 `/Users/ken/workspace/ibreeze` 内文件；保留用户无关改动；禁止 `git reset --hard`、`git checkout --` 等破坏性回滚。
- 每个任务独立提交，提交格式为 `<type>(<scope>): <result>`；任务接受前由未实现该任务核心代码的 Reviewer 检查 blocker/high 为零。

---

## 1. 整改执行规则

### 1.1 状态与证据

每个任务只允许按以下状态流转：

```text
not_started → test_red → implementing → test_green → reviewing → accepted
                                              └────→ changes_requested → implementing
```

任务证据保存到 `artifacts/remediation/<task-id>/<commit-sha>/`，固定包含：

```text
red.log                 # 失败测试命令、退出码和预期失败原因
green.log               # 局部测试和静态检查
full.log                # 受影响模块全量验证
coverage/               # 原生覆盖率制品
review.md               # Reviewer、问题、处置和结论
traceability.json       # Review ID → 文件 → 测试 → 证据
```

`traceability.json` 使用封闭结构：

```json
{
  "review_ids": ["P0-01"],
  "commit_sha": "40-hex-sha",
  "changed_files": ["relative/path"],
  "tests": [{"command": "exact command", "result": "PASS", "artifact": "green.log"}],
  "review": {"status": "PASS", "blocker": 0, "high": 0}
}
```

### 1.2 依赖与并行边界

```text
R00 可信门禁
 ├─ R01 契约生成
 │   ├─ R02 认证与 Token 边界
 │   ├─ R03 Catalog 不可变发布
 │   ├─ R10 Admin/OpenAPI 对齐
 │   └─ R13 前端路由与状态
 ├─ R04 SQLite/队列/Lifecycle
 │   ├─ R05 原子 Plan 确认
 │   ├─ R07 Review 闭环
 │   ├─ R09 备份与知识
 │   └─ R06 Runtime Gateway
 ├─ R08 外部写入
 └─ R11 后台部署与错误

R02 + R03 + R04 → R06 Credential/Egress 与 CLI Runtime
R05 + R06 + R07 + R08 → R15 端到端闭环
R09 + R10 + R11 + R12 + R13 + R14 + R15 → R16 最终发布审计
```

- R02、R03、R04 可在 R01 接受后并行，但不得同时修改同一 Schema 或迁移序列。
- R11 只能在 Backend OpenAPI 冻结后接入 Admin。
- R14 只能在对应 RPC Client 生成并冻结后接入 Desktop。
- R16 前不得合并包含未关闭 blocker/high 的任务。

### 1.3 固定基线与禁止做法

- 审计基线提交：`79cf450`；开始每个任务前记录实际 `git rev-parse HEAD`。
- 原 Review 报告只作为问题基线，不通过改写或删除原问题来“关闭”问题。
- 不允许用 Mock 替代要求真实进程、PostgreSQL、MinIO、UDS、Keychain、Seatbelt 或恢复语义的发布门禁。
- 不允许把 Stub、`NotSupported`、固定成功值、空 Hash、fallback Catalog 或 `|| echo skipped` 作为完成状态。
- 不允许在计划执行中引入预算、多租户、远程 Agent、普通聊天或后台业务数据同步。

## 2. 文件职责锁定

### 2.1 契约和生成物

| 路径 | 职责 |
|---|---|
| `packages/rpc-schema/methods/` | J.14 每个本地 RPC 的严格 request/response Schema |
| `packages/rpc-schema/ownership.v1.json` | `rust_core/sidecar/supervisor_only` 唯一所有权 |
| `packages/rpc-schema/reverse-methods.v1.json` | Sidecar → Rust reverse RPC allowlist |
| `packages/contracts/events/` | Run/Tool/Approval/Workspace 等标准事件 |
| `packages/contracts/domain-events/` | 本地领域事件与注册表 |
| `packages/contracts/artifacts/` | Plan、ExecutionReport、ReviewReport、Artifact、Backup、Catalog 契约 |
| `apps/desktop/src/generated/` | 生成 TypeScript Tauri/RPC Client 和 DTO |
| `apps/desktop-core/src/generated/` | 生成 Rust Serde DTO 与所有权常量 |
| `sidecar/ibreeze/generated/` | 生成 Pydantic 2 DTO |
| `apps/admin-web/src/generated/openapi/` | 生成 Admin OpenAPI Client |

### 2.2 实现边界

| 组件 | 主要修改文件 | 新建职责文件 |
|---|---|---|
| Desktop | `apps/desktop/src/App.tsx`、现有 pages/hooks/stores | `src/app/routes.tsx`、`src/shared/{tauriClient,rpcClient,queryKeys}.ts`、`src/features/**` |
| Rust Core | `src/commands.rs`、`src/auth/mod.rs`、`src/rpc/**`、`src/security/**`、`src/process/mod.rs` | `src/catalog/**`、`src/profile/**`、`src/update/**`、`src/security/{credential_broker,external_write}.rs` |
| Sidecar | `ibreeze/main.py`、`local_db.py`、`rpc_server.py`、`runtime/**`、`orchestration/**` | `application/app.py`、`persistence/{migrations,write_queue,read_pool}.py`、`workers/**` |
| Backend | `catalog/**`、`releases/**`、`api/errors.py`、Alembic | `releases/canonical_json.py`、`releases/bundle.py`、拆分 migration revisions |
| Admin | `src/App.tsx`、pages/hooks、`utils/apiClient.ts` | `src/app/routes.tsx`、`src/shared/openapiClient.ts` |
| 测试/交付 | `scripts/verify-all.sh`、`.github/workflows/**`、现有 tests | `tests/{faults,performance,release}/**`、`deploy/docker-compose.yml` |

迁移文件只追加不修改：已发布或已执行的 migration 一律保持 SHA；修正必须新增下一 revision。

## 3. R00：建立可信门禁并冻结整改基线

**覆盖问题：** P0-11、P1-11、P2-04、P2-05。

**Files:**

- Modify: `scripts/verify-all.sh`
- Modify: `.github/workflows/{contracts,desktop,desktop-core,sidecar,backend,admin-web,e2e,security}.yml`
- Create: `apps/desktop/eslint.config.js`
- Create: `apps/admin-web/eslint.config.js`
- Modify: `packages/contracts/package.json`
- Modify: `.gitignore`
- Create: `tests/scripts/test_verify_all.py`
- Modify: `tests/contract/test_ci_policy.py`
- Modify: `README.md`
- Modify: `docs/部署文档.md`

**Interfaces:**

- Produces: `scripts/verify-all.sh`，任一必需命令失败或工具缺失时返回该失败的非零退出码。
- Produces: `npm --prefix packages/contracts run lint`，真实校验所有 JSON/registry/$ref，不得使用 `echo`。
- Produces: 清洁 worktree 规则，忽略 `**/tsconfig.tsbuildinfo`、`tests/e2e/test-results/`、本地 coverage 和缓存。

- [ ] **Step 1: 写失败传播测试**

  `tests/scripts/test_verify_all.py` 使用临时 PATH 注入同名假命令，至少覆盖：

  测试函数名固定为
  `test_verify_all_propagates_first_failed_gate`、
  `test_verify_all_rejects_missing_required_tool`、
  `test_verify_all_rejects_no_e2e_tests` 和
  `test_verify_all_runs_every_gate_in_declared_order`。测试辅助器在临时目录建立
  `fake-bin`，为每个必需工具生成记录调用顺序并返回指定退出码的可执行文件；
  断言总脚本退出码等于首个失败码，stderr 含失败门禁名，且失败后的门禁未执行。

  Run:

  ```bash
  python3 -m pytest tests/scripts/test_verify_all.py -v
  ```

  Expected: FAIL，因为当前脚本吞掉失败。

- [ ] **Step 2: 把总脚本改为 fail-closed**

  脚本入口固定为：

  ```bash
  #!/usr/bin/env bash
  set -Eeuo pipefail
  trap 'code=$?; echo "verify-all failed at line ${LINENO} with ${code}" >&2; exit "${code}"' ERR
  ```

  每个门禁直接执行，不使用 `|| true`、`|| echo`、`continue-on-error` 或缺目录跳过。开头逐项验证 `node/npm/uv/cargo/cargo-nextest/cargo-llvm-cov` 和 Playwright 浏览器存在。

- [ ] **Step 3: 启用真实 Lint**

  两个 `eslint.config.js` 使用 ESLint 9 flat config，覆盖 `src/**/*.{ts,tsx}` 和测试，忽略 `dist/coverage/generated`；规则至少启用 TypeScript recommended、React Hooks 和 `no-console`（只允许封装 logger）。

  `packages/contracts` 增加 `scripts/lint-contracts.mjs`，使用 AJV 2020 校验 Schema、唯一 `$id`、全部 `$ref` 和 registry 闭包。

- [ ] **Step 4: 清理生成物策略**

  `.gitignore` 精确加入构建生成物；若 `tsconfig.tsbuildinfo` 已跟踪，使用 `git rm --cached` 从索引移除但保留本地文件。禁止忽略契约生成代码、migration、锁文件和正式测试制品索引。

- [ ] **Step 5: 验证红绿**

  ```bash
  python3 -m pytest tests/scripts/test_verify_all.py tests/contract/test_ci_policy.py -v
  npm --prefix apps/desktop run lint
  npm --prefix apps/admin-web run lint
  npm --prefix packages/contracts run lint
  ```

  Expected: PASS；把任一假命令改为退出 7 时，总脚本必须退出 7。

- [ ] **Step 6: 文档与提交**

  README 只展示 CI badge/制品链接，不手写 passed 数；部署文档列明必需工具和失败语义。

  ```bash
  git add scripts .github apps/desktop/eslint.config.js apps/admin-web/eslint.config.js packages/contracts .gitignore tests README.md docs/部署文档.md
  git commit -m "fix(ci): make delivery gates fail closed"
  ```

**Acceptance:** `verify-all.sh` 不再产生假阳性；缺工具、无 E2E、任一 lint/type/test/coverage 失败均阻断。

**Rollback:** 仅允许回滚整个提交；不得恢复吞错逻辑。若新门禁暴露既有失败，保留门禁并在后续任务修复失败。

## 4. R01：完成 Schema 源、生成 Client 与漂移门禁

**Depends on:** R00。

**覆盖问题：** P0-03、P0-04 的契约前置、P1-05 的 OpenAPI 前置。

**Files:**

- Create/Modify: `packages/rpc-schema/meta.schema.json`
- Create: `packages/rpc-schema/{ownership.v1,reverse-methods.v1}.json`
- Create: `packages/rpc-schema/methods/*.request.schema.json`
- Create: `packages/rpc-schema/methods/*.response.schema.json`
- Create: `packages/contracts/artifacts/{company-plan,execution-report,review-report,artifact-manifest,backup-manifest,catalog-manifest}.v1.schema.json`
- Modify: `packages/contracts/domain-events/registry.v1.json`
- Modify: `scripts/{generate-contracts,check-contract-drift}.sh`
- Modify: `scripts/schema-gen-rust/src/main.rs`
- Create: `apps/desktop/src/generated/`
- Create: `apps/desktop-core/src/generated/`
- Create: `sidecar/ibreeze/generated/`
- Create: `apps/admin-web/src/generated/openapi/`
- Modify: `tests/contract/{test_schema_catalog,test_orchestration,test_local_domain}.py`

**Interfaces:**

- `RpcMeta = {trace_id, ipc_session_id, window_session_id, idempotency_key}`；写方法的 key 只在 meta。
- `ownership.v1.json` 必须把 J.14 方法完整且互斥地分配给 `rust_core`、`sidecar`、`supervisor_only`。
- 所有对象 `additionalProperties:false`；UUID、RFC3339、SHA-256、枚举和版本边界必须进入 Schema。
- Generated Client 的写方法签名固定接受 `operationId`，并用 `createWriteContext(operationId)` 复用 UUID 幂等键。

- [ ] **Step 1: 写完整目录失败测试**

  测试从设计 J.14 的机器可读 fixture 读取方法清单，断言每个方法恰有 request/response、恰有一个 owner，reverse 方法只出现在 reverse registry。

  ```bash
  python3 -m pytest tests/contract/test_schema_catalog.py -v
  ```

  Expected: FAIL，列出全部缺失 Schema 和生成目录。

- [ ] **Step 2: 定义领域顶层契约**

  先实现 `CompanyPlan`、`ExecutionReport`、`ReviewReport`、`ArtifactManifest`、`CatalogManifest`、`BackupManifest`；字段严格复制设计附录 E/H/J。`ReviewReport` 必须包含 `assignment_id/run_id/artifact_id/artifact_sha256/reviewer_employee_id/issues/report_artifact_id`。

- [ ] **Step 3: 定义所有本地 RPC**

  逐项展开 J.14 中斜杠方法；`get/list/update/resolve` 统一约束；`conversation.submitUserMessage` 的响应只允许设计指定字段；Supervisor 的 `system.handshake/health/shutdown` 不生成 WebView 方法。

- [ ] **Step 4: 生成四端代码**

  `scripts/generate-contracts.sh` 先生成到 `mktemp -d`，全部生成成功后原子替换目标。生成顺序固定：

  ```text
  validate source → TypeScript → Pydantic 2 → Rust typify → Backend OpenAPI → Admin Client
  ```

  生成代码顶部包含 source SHA，不允许手工修改。

- [ ] **Step 5: 实现漂移检查**

  `check-contract-drift.sh` 在临时目录重新生成并执行目录级 diff；检测源 Schema、OpenAPI、生成物、owner、reverse allowlist 和事件 registry。

- [ ] **Step 6: 验证确定性与负例**

  ```bash
  bash scripts/generate-contracts.sh
  bash scripts/check-contract-drift.sh
  bash scripts/generate-contracts.sh
  git diff --exit-code -- apps/desktop/src/generated apps/desktop-core/src/generated sidecar/ibreeze/generated apps/admin-web/src/generated
  ```

  删除一个 required 字段或生成文件后，drift 必须非零；恢复后全部 PASS。

- [ ] **Step 7: 提交**

  ```bash
  git add packages scripts apps/desktop/src/generated apps/desktop-core/src/generated sidecar/ibreeze/generated apps/admin-web/src/generated tests README.md docs/部署文档.md
  git commit -m "fix(contracts): establish generated cross-language contracts"
  ```

**Acceptance:** 不存在的方法无法通过 TypeScript/Rust 编译；修改 Schema 未提交生成物时 CI 失败；所有方法 owner 完整互斥。

**Rollback:** Schema 与四端生成物必须作为同一提交回滚；不得只回滚某一语言生成物。

## 5. R02：修复 Desktop 认证流程和凭据边界

**Depends on:** R01。

**覆盖问题：** P0-01、P0-02、P2-01 的认证路由部分。

**Files:**

- Modify: `apps/desktop/src/pages/{LoginPage,RegisterPage}.tsx`
- Modify: `apps/desktop/src/stores/authStore.ts`
- Create: `apps/desktop/src/pages/{ServerPage,ChangePasswordPage,OfflineUnlockPage}.tsx`
- Create: `apps/desktop/src/shared/tauriClient.ts`
- Modify: `apps/desktop/src/App.tsx`
- Modify: `apps/desktop-core/src/auth/mod.rs`
- Modify: `apps/desktop-core/src/keyring.rs`
- Modify: `apps/desktop-core/src/commands.rs`
- Modify: `apps/desktop-core/src/store.rs`
- Modify: `apps/desktop-core/tests/{auth_commands,auth_flow}.rs`
- Create: `apps/desktop/tests/auth-flow.test.tsx`

**Interfaces:**

```ts
type AuthViewState = {
  profileOpened: boolean;
  profileDirectoryId: string | null;
  maskedIdentifier: string | null;
  mode: "online" | "offline" | null;
  catalogReleaseSequence: number | null;
};
```

Store 禁止 `token`、`accessToken`、`refreshToken`、`offlineSessionTicket`。页面只调用生成的：

```ts
validateOrigin(input): Promise<ValidateOriginResult>
register(input): Promise<RegisterResult>
login(input): Promise<LoginResult>
changePassword(input): Promise<LoginResult>
openProfile(input): Promise<OpenProfileResult>
closeProfile(): Promise<CloseProfileResult>
logout(): Promise<LogoutResult>
```

- [ ] **Step 1: 写失败的前端和 Rust 集成测试**

  覆盖 `/auth/server`、注册不自动登录、登录、强制改密、在线开 Profile、离线解锁、关闭、离线退出和损坏 Keychain bundle。

  ```bash
  npm --prefix apps/desktop run test -- auth-flow.test.tsx
  cargo test --manifest-path apps/desktop-core/Cargo.toml --test auth_commands --test auth_flow
  ```

  Expected: FAIL，分别暴露错误 Command 名称、DTO 和 Token Store。

- [ ] **Step 2: 删除 WebView Token**

  替换 `authStore` 为上面的非敏感状态；全仓执行：

  ```bash
  rg -n 'accessToken|refreshToken|access_token|refresh_token|offlineSessionTicket' apps/desktop/src
  ```

  Expected: 只允许生成 DTO 类型中存在后端传输字段，不允许 Store、logger、localStorage 或页面读取。

- [ ] **Step 3: 实现 Rust 登录原子流程**

  `auth_login` 严格执行：

  ```text
  REST login
  → JWT/OfflineSessionTicket validation
  → one Keychain JSON bundle update + read-back
  → Catalog download and verify
  → profile meta atomic write
  → Sidecar start/migrate/local_profile verify
  → first health=healthy
  → profile_opened
  ```

  Access Token 使用 `Zeroizing<String>`；Keychain item 把 refresh token 和 offline ticket 存为单一 JSON bundle。任一步失败关闭 Sidecar并不得返回 opened。

- [ ] **Step 4: 使用生成 wrapper 对齐页面**

  删除所有裸 `invoke("login")`、`invoke("register")`。强制改密只进入 `/auth/change-password`，成功后继续登录后半段；Backend Origin 未验证时禁止进入登录页。

- [ ] **Step 5: 增加敏感信息扫描**

  测试扫描 SQLite、日志、Checkpoint、RPC capture、诊断 ZIP 和前端构建产物；用带唯一 canary 的 token/key 断言零命中。

- [ ] **Step 6: 验证与提交**

  ```bash
  npm --prefix apps/desktop run lint
  npm --prefix apps/desktop run typecheck
  npm --prefix apps/desktop run test:coverage
  cargo fmt --manifest-path apps/desktop-core/Cargo.toml --check
  cargo clippy --manifest-path apps/desktop-core/Cargo.toml --all-targets --all-features -- -D warnings
  cargo test --manifest-path apps/desktop-core/Cargo.toml
  ```

  ```bash
  git add apps/desktop apps/desktop-core tests/security README.md docs/部署文档.md docs/应用用户手册.md
  git commit -m "fix(auth): enforce rust-owned credential boundary"
  ```

**Acceptance:** WebView 无法获取 Token；全部认证路径调用存在且 DTO 一致；登录后半段失败不返回已打开。

**Rollback:** 回滚时同时回滚页面、生成 Client 使用点和 Rust Command；Keychain bundle migration 必须兼容读取旧格式并一次迁移，不得破坏已有有效 session。

## 6. R03：实现不可变 Catalog Release、签名和客户端验签

**Depends on:** R01。

**覆盖问题：** P0-05。

**Files:**

- Modify: `apps/backend-api/src/ibreeze_backend/models/catalog_release.py`
- Modify: `apps/backend-api/src/ibreeze_backend/catalog/{models,service,router,schemas}.py`
- Modify: `apps/backend-api/src/ibreeze_backend/releases/{manifest,router,emergency}.py`
- Create: `apps/backend-api/src/ibreeze_backend/releases/{canonical_json,bundle}.py`
- Create: `apps/backend-api/alembic/versions/002_catalog_release_immutability.py`
- Modify: `apps/backend-api/tests/{test_releases,test_catalog}.py`
- Create: `apps/backend-api/tests/test_release_immutability.py`
- Create: `apps/desktop-core/src/catalog/{mod,manifest,cache}.rs`
- Modify: `apps/desktop-core/src/trust.rs`
- Create: `apps/desktop-core/tests/catalog_trust.rs`

**Interfaces:**

- Manifest 字段严格采用设计 E.2：`release_id/release_sequence/created_at/minimum_client_version/signature_algorithm/resources/signature`。
- `signature_algorithm` 固定 `Ed25519`；排除 `signature` 后使用 RFC 8785 canonical JSON；签名和公钥编码使用 Base64。
- `CatalogReleaseItem` 固化 `resource_type/resource_id/resource_version/object_key/object_sha256/size`。

- [ ] **Step 1: 写不可变与篡改失败测试**

  覆盖发布后修改资源不改变历史 Manifest、RFC8785 key/number canonicalization、签名/对象/SHA/sequence/最低版本篡改、离线使用最近有效 Release。

- [ ] **Step 2: 新增不可变表和约束**

  Migration 创建 ReleaseItem、manifest object key/SHA/signature；published Release 和 ReleaseItem 禁止 UPDATE/DELETE；升级函数只前进，downgrade 明确拒绝。

- [ ] **Step 3: 实现发布事务**

  单事务锁定 draft，冻结资源版本，生成每类 Bundle，上传 MinIO，生成并签名 Manifest，保存全部 key/SHA/signature 后切换 published。任一上传或 DB 步骤失败回滚 DB，并由 reconciliation 清理未引用对象。

- [ ] **Step 4: 公共接口只返回冻结对象**

  `/catalog/manifest/latest` 和历史接口从 `manifest_object_key` 读取并验证 SHA，不得从当前资源表动态重建。

- [ ] **Step 5: Rust 验签与原子切换**

  先验证 Catalog Root/Key 信任链，再验 Manifest 签名、sequence 防回退、最低客户端版本和每个对象 SHA；全部下载到 staging 后原子切换 active。

- [ ] **Step 6: 验证与提交**

  ```bash
  uv run --directory apps/backend-api pytest tests/test_release_immutability.py tests/test_releases.py tests/test_catalog.py -v
  cargo test --manifest-path apps/desktop-core/Cargo.toml --test catalog_trust
  ```

  ```bash
  git add apps/backend-api apps/desktop-core packages/contracts README.md docs/部署文档.md docs/后管系统API文档.md
  git commit -m "fix(catalog): publish immutable signed releases"
  ```

**Acceptance:** 历史 Release 永不随资源变化；任意签名、序列、对象或最低版本异常均 fail-closed；active 只在完整验证后切换。

**Rollback:** Published Release 不做数据回滚；应用回滚只能把服务代码切回兼容版本，客户端仍遵循 sequence 不回退。

## 7. R04：正式迁移、单写队列、固定读池和 Sidecar Lifecycle

**Depends on:** R00、R01。

**覆盖问题：** P0-07、P1-01、P1-02、P1-04。

**Files:**

- Replace responsibilities in: `sidecar/ibreeze/local_db.py`
- Create: `sidecar/ibreeze/persistence/{migrations,write_queue,read_pool}.py`
- Append: `sidecar/migrations/002_*.sql` 至设计要求的顺序 revisions
- Create: `sidecar/ibreeze/application/app.py`
- Modify: `sidecar/ibreeze/main.py`
- Create: `sidecar/ibreeze/workers/{analysis,runtime,projection,knowledge,backup,reconciliation}.py`
- Modify: `apps/desktop-core/src/process/mod.rs`
- Modify: `apps/desktop-core/src/sidecar.rs`
- Create: `sidecar/tests/{test_migrations,test_write_queue,test_application_lifecycle}.py`
- Modify: `apps/desktop-core/tests/supervisor.rs`

**Interfaces:**

```python
class WriteQueue:
    def __init__(self, capacity: int = 32) -> None:
        raise NotImplementedError

    async def execute[T](self, command: Callable[[aiosqlite.Connection], Awaitable[T]]) -> T:
        raise NotImplementedError

class ReadPool:
    def __init__(self, size: int = 8) -> None:
        raise NotImplementedError

    async def acquire(self) -> AsyncIterator[aiosqlite.Connection]:
        raise NotImplementedError

class SidecarApplication:
    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self, grace_seconds: float = 10.0) -> None:
        raise NotImplementedError

    async def health(self) -> HealthSnapshot:
        raise NotImplementedError
```

- [ ] **Step 1: 写迁移和并发失败测试**

  覆盖空库、上一版本、running 中断、历史 SHA drift、SQLite 版本/JSON1/FTS5 不满足、队列第 33 个请求背压、读池不超过 8、PRAGMA 泄漏。

- [ ] **Step 2: 建立 migration ledger**

  固定记录 `version/filename/sha256/status/started_at/completed_at/error_code`。升级前用 SQLite Online Backup；`running/failed`、hash drift、`integrity_check` 或 `foreign_key_check` 失败进入 recovery。

- [ ] **Step 3: 收敛全部数据库访问**

  Command Handler 只能通过 `WriteQueue.execute` 写；Repository 不得自行 commit。读连接池空时等待，不新增第 9 个连接。借出和归还验证 `foreign_keys=1`、`defer_foreign_keys=0`、`query_only=1`。

- [ ] **Step 4: 启动全部 Worker**

  `SidecarApplication.start()` 顺序固定：

  ```text
  runtime asset verify → SQLite capability → migrations → local_profile
  → startup reconciliation → RPC bind → TaskGroup workers → first healthy
  ```

  Workers 使用 durable queue/lease/heartbeat/指数退避/poison 状态；任一必需 Worker 退出使 health degraded/unhealthy。

- [ ] **Step 5: 修复 Rust Supervisor**

  Handshake 后等待首次 healthy 才允许 Profile opened；heartbeat 每 5 秒、超时 3 秒；异常时终止进程组、执行对账、按上限重启；正常启动不计 restart tracker。

- [ ] **Step 6: 崩溃和关闭验证**

  注入进程在 migration、事务提交前后、lease 后、副作用响应前退出；重启必须不丢任务、不重复副作用。关闭顺序为拒绝新写→等待当前写事务≤10秒→释放 lease→停 Worker→关 DB。

- [ ] **Step 7: 验证与提交**

  ```bash
  uv run --directory sidecar pytest tests/test_migrations.py tests/test_write_queue.py tests/test_application_lifecycle.py -v
  cargo test --manifest-path apps/desktop-core/Cargo.toml --test supervisor
  ```

  ```bash
  git add sidecar apps/desktop-core tests/faults README.md docs/部署文档.md
  git commit -m "fix(sidecar): add durable lifecycle and database concurrency"
  ```

**Acceptance:** 主入口真实消费分析、Run、投影、知识和备份；迁移和并发满足固定容量；Worker 故障可被 health/Supervisor 发现。

**Rollback:** migration 只前向；失败恢复升级前 Online Backup。服务代码回滚前必须证明可读取新 Schema。

## 8. R05：原子 Plan 确认、资源快照与调度

**Depends on:** R01、R04、R03。

**覆盖问题：** P0-08。

**Files:**

- Modify: `sidecar/ibreeze/orchestration/{plan_generator,plan_validator,availability_checker,dispatcher}.py`
- Modify: `sidecar/ibreeze/task/service.py`
- Modify: `sidecar/ibreeze/rpc_server.py`
- Modify: `sidecar/ibreeze/schemas.py`
- Create: `sidecar/ibreeze/orchestration/confirm_plan.py`
- Create: `sidecar/tests/test_confirm_plan_transaction.py`
- Modify: `tests/functional/test_plan_advanced.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class ConfirmPlanCommand:
    company_id: UUID
    company_task_id: UUID
    plan_artifact_id: UUID
    plan_sha256: str
    expected_version: int
    workspace_grant_ids: Sequence[UUID]

async def confirm_and_dispatch(
    command: ConfirmPlanCommand,
    tx: CommandTransaction,
) -> ConfirmPlanResult:
    raise NotImplementedError
```

`CompanyPlan` 必须使用生成模型，包含可执行 `department_tasks` DAG，不再持久化私有 `sections` 变体。

- [ ] **Step 1: 写事务注入和并发失败测试**

  在 Plan 固化、grant 解析、snapshot、department task、employee task、runtime queue、event/outbox、状态更新之间逐点抛异常，断言数据库全有或全无。同版本并发确认只允许一次成功。

- [ ] **Step 2: 生成并验证严格 CompanyPlan**

  Plan Generator 输出设计 E.6；PlanValidator 检查部门职责、DAG 无环、任务覆盖、负责人、参与职员、Review/测试阶段和完成条件。

- [ ] **Step 3: 真实可用性探测**

  每个参与职员探测 Agent/Provider/Model/Skill/Workspace；checks 与 `overall_status` 一致；`expires_at > checked_at`，启动 Run 时再次验证未过期。

- [ ] **Step 4: 单事务确认与派发**

  一个 `WriteQueue` Command Transaction 完成 SHA/version、Plan Artifact、Grant、AvailabilitySnapshot、ExecutionSnapshot、任务 DAG、Runtime Queue、DomainEvent、Outbox 和 CompanyTask 状态。禁止 fallback Catalog；无可信 Release 进入 `waiting_resource`。

- [ ] **Step 5: 幂等与恢复**

  `(company_task_id, expected_version)` 和 RPC idempotency result 建唯一约束；重复相同 key 返回原结果，不创建第二个 Run。

- [ ] **Step 6: 验证与提交**

  ```bash
  uv run --directory sidecar pytest tests/test_confirm_plan_transaction.py -v
  python3 -m pytest tests/functional/test_plan_advanced.py -v
  ```

  ```bash
  git add sidecar packages/contracts tests README.md docs/部署文档.md docs/应用用户手册.md
  git commit -m "fix(orchestration): confirm plans in one durable transaction"
  ```

**Acceptance:** 注入失败全有或全无；重复/并发确认不重复派发；过期快照、不可用资源和不可信 Catalog 不创建 Run。

**Rollback:** 事务回滚自动清除未提交行；已提交 Plan 只能用正式 cancel/supersede 状态迁移，不直接删数据。

## 9. R06：Credential/Egress Broker、API Model Loop 与 CLI Adapter

**Depends on:** R02、R03、R04、R05。

**覆盖问题：** P0-06、P1-03。

**Files:**

- Modify: `sidecar/ibreeze/runtime/{run_executor,transport,model_loop,gateway,cli,process_supervisor,permission_gateway}.py`
- Create: `sidecar/ibreeze/runtime/adapters/{codex,claude_code,opencode}.py`
- Modify: `apps/desktop-core/src/security/egress.rs`
- Create: `apps/desktop-core/src/security/credential_broker.rs`
- Modify: `apps/desktop-core/src/rpc/reverse.rs`
- Modify: `apps/desktop-core/src/process/mod.rs`
- Modify: `tests/integration/test_cli_adapter_contract.py`
- Create: `tests/security/{test_credential_boundary,test_ssrf,test_cli_sandbox}.py`

**Interfaces:**

```python
class ModelTransportAdapter(Protocol):
    async def complete(self, request: ModelRequest, credential_ref: str) -> AsyncIterator[ModelEvent]:
        raise NotImplementedError

class AgentAdapter(Protocol):
    def probe(self) -> ProbeResult:
        raise NotImplementedError

    def build_invocation(self, spec: AgentRunSpec, prompt_file: Path) -> Invocation:
        raise NotImplementedError

    def parse_event(self, line: bytes) -> Sequence[RunEvent]:
        raise NotImplementedError

    def checkpoint(self, native_state: NativeState) -> CheckpointRef:
        raise NotImplementedError
```

RunSpec 只允许 `credential_ref`；Sidecar 禁止 Provider 真实出站。

- [ ] **Step 1: 写凭据、SSRF 和 fake CLI 失败测试**

  API Key canary 不得进入 RunSpec/DB/log；禁止 IP literal、私网/loopback/link-local、DNS rebinding、越界 redirect；fake CLI 覆盖版本、argv、stdin/prompt file、事件、取消、超时、恢复。

- [ ] **Step 2: 删除 Sidecar 直连 Provider**

  `transport.py` 只通过 reverse RPC 请求 Rust；移除 `api_key` 参数和 `aiohttp` 直连。Rust 从 Keychain 临时取 key，校验 allowlist、DNS 每个地址、TLS 和每次 redirect。

- [ ] **Step 3: 完成 Built-in Agent Loop**

  从 ExecutionSnapshot 注册 Tool allowlist；标准循环为 model→tool request→permission→tool result→model。`ASK` 创建 HumanApproval、Run 进入 `waiting_approval`，有效 receipt 前无工具副作用。

- [ ] **Step 4: 实现三个固定 CLI Adapter**

  固定支持版本区间；Prompt 走 stdin 或 0600 临时文件，不进入 argv；持久化 native session、PID/PGID/start time/checkpoint；每个任务使用受管 Worktree/快照。

- [ ] **Step 5: Seatbelt 与 Egress**

  每次 Run 生成最小 SBPL；Workspace 内读写，Workspace 外普通文件只读，凭据/Profile/Keychain 路径 deny；CLI 网络只能走 Rust lease/proxy。

- [ ] **Step 6: 验证与提交**

  ```bash
  python3 -m pytest tests/integration/test_cli_adapter_contract.py tests/security/test_credential_boundary.py tests/security/test_ssrf.py tests/security/test_cli_sandbox.py -v
  uv run --directory sidecar pytest tests/test_agent_runtime_gateway.py tests/test_agent_runtime.py -v
  cargo test --manifest-path apps/desktop-core/Cargo.toml
  ```

  ```bash
  git add sidecar apps/desktop-core tests README.md docs/部署文档.md
  git commit -m "fix(runtime): route all agents through secure runtime gateway"
  ```

**Acceptance:** 禁止 Sidecar 出站时 API Model 仍通过 Rust 工作；ASK 批准前零副作用；三 CLI fake 契约全绿，真实冒烟留到 R16。

**Rollback:** Broker 协议和 RunSpec Schema 同提交回滚；不得恢复 Sidecar API Key 或直连作为 fallback。

## 10. R07：Artifact、Review、返修、复测与最终报告状态机

**Depends on:** R01、R04、R05、R06。

**覆盖问题：** P0-09。

**Files:**

- Modify: `sidecar/ibreeze/review/service.py`
- Modify: `sidecar/ibreeze/artifacts/{service,storage,manifest}.py`
- Modify: `sidecar/ibreeze/orchestration/{execution_chain,collaboration,report_generator}.py`
- Modify: `sidecar/ibreeze/state_machine.py`
- Modify: `sidecar/ibreeze/runtime/run_executor.py`
- Create: `sidecar/ibreeze/orchestration/completion_gate.py`
- Create: `sidecar/tests/test_completion_gate.py`
- Modify: `sidecar/tests/test_review_advanced.py`
- Modify: `tests/functional/test_run_advanced.py`

**Interfaces:**

```python
class CompletionGate:
    async def evaluate_employee_task(self, task_id: UUID) -> GateResult:
        raise NotImplementedError

    async def evaluate_department_task(self, task_id: UUID) -> GateResult:
        raise NotImplementedError

    async def evaluate_company_task(self, task_id: UUID) -> GateResult:
        raise NotImplementedError
```

`GateResult` 固定包含 `allowed: bool` 和稳定
`blockers: Sequence[CompletionBlocker]`；Run exit code 只能结束 Run，不能直接完成业务任务。

- [ ] **Step 1: 写每个阻断条件的失败测试**

  覆盖缺 Artifact、缺 assignment、贡献者自审、错误 purpose、旧 SHA Review、blocker/high 未关闭、返修未出新版本、测试部未引用测试用例、缺 DepartmentReport、公司级 Review 未通过。

- [ ] **Step 2: 分离 Run 和业务状态**

  `run_executor` 只写 AgentRun/RunEvent/Artifact candidate；统一状态机服务依据 CompletionGate 转换 EmployeeTask/DepartmentTask/CompanyTask。

- [ ] **Step 3: 严格提交 ReviewReport**

  验证 assignment、reviewer 参与当前任务且不是该 Artifact 贡献者、review Run purpose、Artifact SHA 和 report artifact。新 Artifact version 自动使旧 Review 失效。

- [ ] **Step 4: Issue 关闭证据**

  blocker/high 只能通过 `review.resolveIssue` 关闭，必须绑定 resolution artifact SHA、修复 Run 和复测结果；不得直接改状态字段。

- [ ] **Step 5: 报告门禁**

  DepartmentReport 和 FinalReport 使用生成 Schema；FinalReport 必须引用全部部门报告、Review、测试复测和关闭问题证据。

- [ ] **Step 6: 验证与提交**

  ```bash
  uv run --directory sidecar pytest tests/test_completion_gate.py tests/test_review_advanced.py -v
  python3 -m pytest tests/functional/test_run_advanced.py -v
  ```

  ```bash
  git add sidecar packages/contracts tests README.md docs/部署文档.md docs/应用用户手册.md
  git commit -m "fix(review): enforce evidence-backed completion gates"
  ```

**Acceptance:** 任何缺 Review、严重问题未关闭、SHA 变化或缺复测均不能完成；贡献者不能自审；最终报告可逐项追溯。

**Rollback:** 状态机和 Schema 必须同回滚；已生成报告保留为历史 Artifact，不删除审计证据。

## 11. R08：外部写入、Bookmark、Seatbelt 与一次性 receipt

**Depends on:** R01、R04、R06。

**覆盖问题：** P0-10。

**Files:**

- Modify: `apps/desktop-core/src/commands/external.rs`
- Modify: `apps/desktop-core/src/security/grant_store.rs`
- Create: `apps/desktop-core/src/security/external_write.rs`
- Modify: `apps/desktop-core/src/rpc/reverse.rs`
- Modify: `sidecar/ibreeze/approvals/service.py`
- Modify: `sidecar/ibreeze/runtime/workspace_broker.py`
- Create: `apps/desktop-core/tests/external_write.rs`
- Modify: `tests/functional/test_approval_advanced.py`
- Create: `tests/security/test_external_write_escape.py`

**Interfaces:**

```rust
pub struct ExternalWriteRequest {
    pub approval_id: Uuid,
    pub run_id: Uuid,
    pub operation: ExternalWriteOperation,
    pub target_bookmark_id: Uuid,
    pub expected_target_sha256: Option<String>,
    pub staging_path: PathBuf,
    pub staging_sha256: String,
    pub staging_size: u64,
    pub expires_at: DateTime<Utc>,
}
```

Response 固定包含 `result_state_sha256` 和 `receipt_sha256`。

- [ ] **Step 1: 写攻击和不确定恢复测试**

  覆盖路径逃逸、symlink/hardlink、staging 篡改、目标变化、过期、错误 PID/PGID/父进程/executable、响应丢失后重试。

- [ ] **Step 2: 持久化 Security Scoped Bookmark**

  GrantStore 保存 bookmark 密文和非敏感元数据；重启后恢复授权；未能 resolve 或 stale 时要求用户重新选择，不接受字符串路径代替授权。

- [ ] **Step 3: 实现原子单目标执行**

  校验 session/approval/run/operation/expiry/old state/staging realpath/SHA/size；生成只允许该目标的临时 Seatbelt Profile；create/replace 使用同目录 temp、fsync 文件和目录后 rename。

- [ ] **Step 4: receipt 和幂等恢复**

  receipt 绑定请求 Hash、旧/新状态、执行时间。重试区分：

  ```text
  receipt exists + target=new → return original result
  no receipt + target=old → execute once
  no receipt + target=new → waiting_recovery_approval
  target=third-party state → APPROVAL_TARGET_CHANGED
  ```

- [ ] **Step 5: 验证系统进程通知**

  对 `process.registered/exited` 读取系统进程信息并验证 PID、PGID、parent、executable 和 start time，拒绝仅相信 Sidecar payload。

- [ ] **Step 6: 验证与提交**

  ```bash
  cargo test --manifest-path apps/desktop-core/Cargo.toml --test external_write
  python3 -m pytest tests/functional/test_approval_advanced.py tests/security/test_external_write_escape.py -v
  ```

  ```bash
  git add apps/desktop-core sidecar tests README.md docs/部署文档.md docs/应用用户手册.md
  git commit -m "fix(workspace): execute approved external writes exactly once"
  ```

**Acceptance:** 只能修改批准的唯一目标；篡改和变化 fail-closed；响应丢失重试不产生第二次副作用。

**Rollback:** Bookmark/receipt 数据保留；回滚版本若不认识新 receipt 必须禁用外部写而不是重新执行。

## 12. R09：一致备份恢复与真实知识索引对账

**Depends on:** R04、R07。

**覆盖问题：** P1-06、P1-07。

**Files:**

- Modify: `sidecar/ibreeze/backup/{service,packager,validator,scheduler}.py`
- Modify: `sidecar/ibreeze/knowledge/{service,vector_store,text_search}.py`
- Create: `sidecar/ibreeze/knowledge/generation.py`
- Create: `sidecar/tests/{test_backup_consistency,test_knowledge_reconciliation}.py`
- Create: `tests/security/test_backup_archive.py`
- Create: `tests/faults/test_restore_atomicity.py`

**Interfaces:**

- 备份顺序：暂停新写→等待事务≤10秒→SQLite Online Backup→收集引用 CAS/Catalog/Skill lock→逐文件 SHA manifest→tar.zst→原子移动。
- Knowledge generation 保存 `generation_id/model_id/dimension/source_sequence/status/ids_hash/created_at`。

- [ ] **Step 1: 写一致性、安全和损坏测试**

  覆盖运行中写入、路径穿越、绝对路径、symlink/hardlink、文件数/大小炸弹、SHA 错误、恢复中断、LanceDB 丢行/错 ID/错 hash/维度不符。

- [ ] **Step 2: 替换 SQLite copy**

  删除 `shutil.copy2` 数据库路径；使用 Online Backup API，在 snapshot barrier 内收集外部引用；明确排除 Keychain、API Key、CLI 原生状态、日志和临时 Worktree。

- [ ] **Step 3: 安全解包和原子恢复**

  禁止 `extractall`；逐 entry 校验规范相对路径、普通文件、数量、总大小和 SHA 后写 staging。执行 integrity/migration/foreign key/Artifact 引用验证并重建索引，再原子切换 active。

- [ ] **Step 4: 真实 generation 对账**

  building generation 从一致读快照创建；FTS5 和 LanceDB 全成功后切 active。对账真实读取 LanceDB 的 ID/hash/维数，不用 SQLite count 代替。

- [ ] **Step 5: 验证与提交**

  ```bash
  uv run --directory sidecar pytest tests/test_backup_consistency.py tests/test_knowledge_reconciliation.py -v
  python3 -m pytest tests/security/test_backup_archive.py tests/faults/test_restore_atomicity.py -v
  ```

  ```bash
  git add sidecar tests README.md docs/部署文档.md docs/应用用户手册.md
  git commit -m "fix(recovery): make backup and knowledge generations verifiable"
  ```

**Acceptance:** 备份是事务一致快照；恶意归档不能逃逸；恢复失败保留原 Profile；LanceDB 任意不一致可检测和重建。

**Rollback:** 恢复前总是保留 `restore-before`；失败不切 active；索引 generation 可回到上一完整 generation，不回滚事实 DB。

## 13. R10：Admin Web 与 Backend OpenAPI/Release 语义对齐

**Depends on:** R01、R03。

**覆盖问题：** P1-05。

**Files:**

- Modify: `apps/backend-api/src/ibreeze_backend/releases/router.py`
- Modify: `apps/backend-api/src/ibreeze_backend/releases/emergency.py`
- Modify: `apps/backend-api/src/ibreeze_backend/skills/router.py`
- Modify: `apps/backend-api/scripts/export_openapi.py`
- Delete usage of handwritten DTO in: `apps/admin-web/src/types/index.ts`
- Replace: `apps/admin-web/src/utils/apiClient.ts`
- Modify: `apps/admin-web/src/hooks/{useReleases,useSkills,useAgentCatalog,useModelCatalog,useProviderCatalog}.ts`
- Modify: `apps/admin-web/src/pages/{ReleasePage,SkillPage,AgentCatalogPage,ModelCatalogPage,ProviderCatalogPage}.tsx`
- Create: `apps/admin-web/tests/admin-contract.test.tsx`
- Modify: `apps/backend-api/tests/{test_releases,test_skills_api}.py`

**Interfaces:**

- Admin Client 只能由 OpenAPI 生成；所有写请求自动 `Idempotency-Key`；更新/删除使用 `If-Match`；401 只允许一次 refresh 后重放原逻辑请求。
- Catalog 操作统一 `draft → validated → release publish`，不提供单资源 publish。
- Emergency 指令包含 `resource_type/resource_id/resource_version/action/reason/code/sequence/signature`。
- Skill 版本上传固定 `multipart/form-data`。

- [ ] **Step 1: 写 OpenAPI 与 UI 失败测试**

  覆盖 Release 列表、完整 emergency payload、multipart Skill、幂等、If-Match、一次 refresh、单资源 publish 按钮不存在。

- [ ] **Step 2: 补齐 Backend REST**

  实现管理员 Release cursor 列表；emergency 采用签名完整契约；Skill 上传与 OpenAPI media type 一致。

- [ ] **Step 3: 重新生成 Admin Client**

  导出 OpenAPI 3.1，生成 Client；删除 hooks/pages 中手写 endpoint、response interface 和 envelope 解析。

- [ ] **Step 4: 对齐页面行为**

  Agent/Model/Provider/Skill 只编辑 draft；Release 页面统一验证和发布；Emergency 页面按资源版本签发指令。

- [ ] **Step 5: 验证与提交**

  ```bash
  uv run --directory apps/backend-api pytest tests/test_releases.py tests/test_skills_api.py -v
  npm --prefix apps/admin-web run test -- admin-contract.test.tsx
  bash scripts/check-contract-drift.sh
  ```

  ```bash
  git add apps/backend-api apps/admin-web docs/后管系统API文档.md docs/后管系统用户手册.md README.md docs/部署文档.md
  git commit -m "fix(admin): align catalog ui with generated openapi"
  ```

**Acceptance:** Admin 不再调用不存在/冲突 endpoint；Release、紧急禁用和 Skill 上传在真实 API 集成通过。

**Rollback:** Backend OpenAPI 与 Admin 生成 Client 同步回滚；不得只恢复手写 endpoint。

## 14. R11：Backend 正式迁移、生产部署和安全错误

**Depends on:** R00、R03、R10。

**覆盖问题：** P1-08、P1-10。

**Files:**

- Append: `apps/backend-api/alembic/versions/002_users.py`、`003_catalog.py`、`004_releases.py`
- Modify: `apps/backend-api/src/ibreeze_backend/api/errors.py`
- Modify: `apps/backend-api/src/ibreeze_backend/observability/logging_config.py`
- Modify: `apps/backend-api/Dockerfile`
- Create: `deploy/docker-compose.yml`
- Create: `deploy/nginx.conf`
- Create: `deploy/README.md`
- Create: `apps/backend-api/tests/test_problem_redaction.py`
- Modify: `tests/contract/test_backend_deployment.py`
- Create: `tests/release/test_backend_upgrade.py`

**Interfaces:**

未知异常返回：

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "The request could not be completed.",
    "reference_id": "uuid"
  }
}
```

详细堆栈只进入脱敏日志；路径、SQL、Token、API Key、Prompt 和消息正文不得进入 response。

- [ ] **Step 1: 写迁移、容器和泄露失败测试**

  覆盖空库/上一 head 升级、migration hash、非 root、只读 rootfs、health、固定 image digest、Secret volume、错误 canary 零泄露。

- [ ] **Step 2: 拆分 Alembic revisions**

  保留既有 `001_initial` SHA，不修改历史；新 revisions 负责用户/目录/Release 差异。Migration 独立 Job 执行，API 不在每次启动隐式建表。

- [ ] **Step 3: 实现安全错误映射**

  领域错误使用固定 code/user-safe message；未知异常生成 reference ID；结构化 redactor 递归处理敏感 key 和绝对路径。

- [ ] **Step 4: 完成五服务部署**

  Compose 包含 PostgreSQL 16、MinIO、Backend API、Admin、Nginx 和一次性 migration profile；镜像固定 digest，多阶段、非 root、只读根，`/tmp` tmpfs，Secret 只读 volume；metrics 不发布公网。

- [ ] **Step 5: 验证与提交**

  ```bash
  uv run --directory apps/backend-api pytest tests/test_migrations.py tests/test_problem_redaction.py -v
  python3 -m pytest tests/contract/test_backend_deployment.py tests/release/test_backend_upgrade.py -v
  docker compose -f deploy/docker-compose.yml config
  ```

  ```bash
  git add apps/backend-api deploy tests README.md docs/部署文档.md docs/生产部署文档.md
  git commit -m "fix(backend): add reproducible deployment and safe errors"
  ```

**Acceptance:** 空库和上一版本升级可重现；完整后台可部署；错误响应无内部异常和敏感数据。

**Rollback:** 数据库前向迁移不 downgrade；应用镜像回滚前执行兼容性检查；部署失败保持上一镜像和数据库。

## 15. R12：桌面自动更新、验证和用户驱动回退

**Depends on:** R02、R04、R11。

**覆盖问题：** P1-09。

**Files:**

- Modify: `apps/desktop-core/src/commands/updater.rs`
- Create: `apps/desktop-core/src/update/{mod,manifest,rollback}.rs`
- Modify: `apps/desktop/src/pages/SettingsPage.tsx`
- Create: `apps/desktop/src/pages/RecoveryPage.tsx`
- Create: `apps/desktop-core/tests/updater.rs`
- Create: `tests/release/test_update_rollback.py`

**Interfaces:**

- Update Manifest 包含 version、minimum_current_version、package_url、package_sha256、signature、published_at。
- 安装前缓存当前稳定安装包并执行 Profile Online Backup。
- 新版首次启动必须通过协议、migration 和 Sidecar health；失败进入 Recovery UI，不静默继续。

- [ ] **Step 1: 写篡改、失败启动和回退测试**

  `apps/desktop-core/tests/updater.rs` 固定覆盖：Manifest 签名错误、package SHA
  错误、版本回退、最低当前版本不满足、下载中断、缓存包损坏和有效更新。
  `tests/release/test_update_rollback.py` 用受控假安装器依次模拟协议不匹配、
  migration 失败、Sidecar 首次 health 失败和成功启动；前三项断言进入 Recovery
  UI 且 active Profile 未被替换。

- [ ] **Step 2: 实现 Manifest 和安装包验证**

  Rust 先用 Catalog/Update 独立信任键验证 Ed25519，再校验版本约束、URL
  scheme/host、package size 和 SHA-256。Manifest 或 package 任一失败时删除
  staging 文件、记录稳定错误码，不改变当前安装。

- [ ] **Step 3: 缓存稳定包和升级前备份**

  只有已经完成首次启动验证的版本可标记 stable。安装新版本前确认 stable
  package 的 SHA 和签名仍有效，并调用 R09 Online Backup；缓存和备份均成功后
  才允许关闭当前应用进入安装。

- [ ] **Step 4: 实现首次启动标记与 Recovery UI**

  更新器写入包含 old/new version、backup id、stable package SHA 的原子 pending
  marker。新版依次验证 Desktop-Sidecar 协议、migration、Profile 和首次 health；
  全部通过后删除 marker 并标记 stable。任一失败时 `/recovery` 只提供“重试验证”、
  “恢复稳定版本”和“导出诊断”，不得进入业务路由。

- [ ] **Step 5: 验证回退保持前向迁移数据**

  假安装器恢复缓存 stable package 后，使用新版本留下的 Profile 执行只读
  compatibility probe；若不兼容，Recovery UI 使用升级前备份恢复到新 Profile
  staging 并原子切换，不执行数据库 downgrade。

  ```bash
  cargo test --manifest-path apps/desktop-core/Cargo.toml --test updater
  python3 -m pytest tests/release/test_update_rollback.py -v
  ```

- [ ] **Step 6: 文档与提交**

  ```bash
  git add apps/desktop apps/desktop-core tests README.md docs/部署文档.md docs/应用用户手册.md
  git commit -m "fix(updater): verify updates and provide recovery rollback"
  ```

**Acceptance:** 篡改包拒绝安装；启动失败进入恢复界面；用户可用缓存稳定包恢复应用且原 Profile 可读。

**Rollback:** 更新器代码回滚不删除缓存稳定包和升级前备份。

## 16. R13：Desktop 路由、RPC 幂等、Query 边界和 Bundle

**Depends on:** R01、R02、R05、R07、R08、R09。

**覆盖问题：** P0-04、P2-01、P2-02、P2-03。

**Files:**

- Replace route responsibilities in: `apps/desktop/src/App.tsx`
- Create: `apps/desktop/src/app/{routes,guards}.tsx`
- Create: `apps/desktop/src/shared/{rpcClient,queryKeys}.ts`
- Modify: `apps/desktop/src/hooks/{useTask,useReview,useWorkspace}.ts`
- Modify: all `apps/desktop/src/pages/*.tsx`
- Modify: `apps/desktop/vite.config.ts`
- Create: `apps/desktop/tests/{routes,rpc-client,query-boundary}.test.tsx`
- Modify: `tests/contract/test_desktop_ui.py`

**Interfaces:**

```ts
const queryKeys = {
  company: (ctx, companyId) => [ctx.backendOrigin, ctx.appUserId, ctx.profileId, companyId, "company"] as const,
  resource: (ctx, companyId, type, id) =>
    [ctx.backendOrigin, ctx.appUserId, ctx.profileId, companyId, type, id] as const,
};
```

逻辑写操作创建一次 `operationId` 并在用户显式重试时复用；写请求不自动 retry；GET 只对网络错误重试两次。

- [ ] **Step 1: 写路由、方法清单和幂等失败测试**

  枚举 K.1 所有路由；静态测试禁止裸 `invoke("rpc_request")` 和不存在的 `skill.*`、`workspace.list`、`runtime.run/stop`；Diagnostics 只能用专用 Rust Command。

- [ ] **Step 2: 建立认证/Profile/Company Guards**

  Company ID 进入部门、职员、会话、任务、Review、Workspace 路由；未选择 Company 时禁止公司业务页。

- [ ] **Step 3: 迁移到生成 RPC Client**

  删除所有页面手写方法字符串；修正 `task.confirmPlan` 参数为生成 Command；Rust-owned 和 supervisor-only 使用生成的专用 Tauri wrapper。

- [ ] **Step 4: 收敛状态边界**

  TanStack Query 保存事实数据；Zustand 只保存 Profile/Company 选择、导航、草稿和瞬时 UI。写操作显示 pending，等待事件/查询确认。

- [ ] **Step 5: 路由懒加载和 Bundle 门禁**

  所有页面 `React.lazy`；Ant Design、图表、编辑器拆 chunks；Vite 增加主入口和 lazy chunk size budget，超限构建失败。

- [ ] **Step 6: 验证与提交**

  ```bash
  npm --prefix apps/desktop run lint
  npm --prefix apps/desktop run typecheck
  npm --prefix apps/desktop run test:coverage
  npm --prefix apps/desktop run build
  python3 -m pytest tests/contract/test_desktop_ui.py -v
  ```

  ```bash
  git add apps/desktop tests README.md docs/部署文档.md docs/应用用户手册.md
  git commit -m "fix(desktop): align routes rpc and query state"
  ```

**Acceptance:** 所有写 RPC 有可复用幂等键；不存在/越权方法编译失败；路由作用域一致；Query 无跨用户/Profile/公司串扰；Bundle 达到预算。

**Rollback:** 页面和生成 Client 使用点同回滚；不得恢复裸 RPC 字符串。

## 17. R14：质量债清零和专项测试矩阵

**Depends on:** R00–R13。

**覆盖问题：** P1-11、P2-04、P2-05 的最终关闭。

**Files:**

- Modify: all lint/type errors in `apps/backend-api/src` and `sidecar/ibreeze`
- Modify: Rust files reported by `cargo fmt --check`
- Add tests under: `apps/{desktop,admin-web}/tests`、`sidecar/tests`、`apps/backend-api/tests`、`apps/desktop-core/tests`
- Create: `tests/{e2e,security,faults,performance,release}/`
- Modify: `coverage-exclusions.yml`
- Modify: `scripts/verify-all.sh`
- Modify: `.github/workflows/**`

**Interfaces:**

- 覆盖率绑定 commit SHA；TypeScript 四指标、Python line/branch、Rust line/function/region 均为 100%。
- Sidecar UDS 测试必须在允许 Unix Domain Socket 的 macOS Runner 执行，不允许 skip。
- E2E 至少覆盖认证、公司向导、计划确认、标准研发流程、Review/返修/复测、FinalReport、Catalog 发布同步、备份恢复和更新恢复。

- [ ] **Step 1: 固定现有静态错误清单**

  保存当前 Ruff/mypy/fmt/ESLint 输出，按文件逐个修复，不放宽配置、不使用 blanket ignore。

- [ ] **Step 2: 补齐单元分支**

  从覆盖率 missing lines/branches 逐项新增行为测试；只允许生成 DTO、纯 DDL、无逻辑入口和签名公证包装进入 exclusions。

- [ ] **Step 3: 建立真实集成**

  PostgreSQL 16/MinIO Testcontainer、Rust-Sidecar UDS、fake/真实 CLI、Keychain 测试隔离、Catalog 对象存储和恢复。

- [ ] **Step 4: 建立 Playwright/Tauri E2E**

  `tests/e2e` 至少存在一个 `.spec.ts`；CI 中 `No tests found` 非零；保存 trace/video/screenshot/JUnit。

- [ ] **Step 5: 建立安全、故障、性能、发布测试**

  严格实现 K.15/K.16 fixture、样本数、p95 和 macOS 最低/最高版本 Seatbelt 门禁。

- [ ] **Step 6: 全量验证**

  ```bash
  bash scripts/check-lockfiles.sh
  python3 scripts/check-coverage-exclusions.py
  bash scripts/check-contract-drift.sh
  bash scripts/verify-all.sh
  ```

  Expected: 全部 0；任何单项失败后再次运行总脚本必须非零。

- [ ] **Step 7: 提交**

  按模块拆分测试提交，不把全部质量修复压成一个提交；最终汇总提交只更新追踪矩阵和文档。

**Acceptance:** Ruff/mypy/ESLint/fmt/clippy 零错误零 warning；所有语言 100%；E2E、安全、故障、性能、恢复、发布门禁真实执行。

**Rollback:** 不允许回滚测试来适配实现；若实现回滚，必须同时恢复相应行为测试并保持门禁。

## 18. R15：完整业务闭环 E2E 与可恢复性验收

**Depends on:** R03–R14。

**覆盖问题：** 全部 P0/P1 的跨模块闭环。

**Files:**

- Create: `tests/e2e/standard-software-delivery.spec.ts`
- Create: `tests/e2e/recovery-and-resume.spec.ts`
- Create: `tests/e2e/admin-catalog-release.spec.ts`
- Create: `tests/fixtures/standard-company/`
- Create: `docs/review报告/AI公司桌面应用-整改验证报告.md`

- [ ] **Step 1: 固定测试公司 fixture**

  包含总经理办公室、架构部、开发部、测试部、部门职责、可用职员底座、测试 Skill 和受管 Workspace；所有外部 ID 和版本可重建。

- [ ] **Step 2: 执行标准研发流程**

  用户输入→总经理计划→用户确认→架构文档→开发实现/单测→测试用例→测试 Review→开发返修→测试复测→部门报告→总经理 FinalReport。

- [ ] **Step 3: 验证 Review 负例**

  自审、旧 SHA、未关闭 high、缺测试用例、缺部门报告时 FinalReport 按稳定错误码阻断。

- [ ] **Step 4: 验证崩溃恢复**

  在确认、Run、工具副作用、Review、备份和更新关键边界终止进程；重启后无任务丢失、无重复外部写、无错误完成。

- [ ] **Step 5: 验证后台目录闭环**

  Admin 创建/验证资源→发布不可变 Release→Desktop 验签同步→紧急禁用→新 Run 拒绝禁用资源；后台数据库确认无公司业务表。

- [ ] **Step 6: 生成验证报告**

  报告逐项引用 commit SHA、命令、制品、数据库不变量和截图；不得写“预计通过”。

- [ ] **Step 7: 提交**

  ```bash
  git add tests/e2e tests/fixtures docs/review报告/AI公司桌面应用-整改验证报告.md README.md docs/部署文档.md
  git commit -m "test(e2e): verify complete agent company workflow"
  ```

**Acceptance:** 标准流程和所有负例在真实多进程环境通过；崩溃恢复不破坏事实和 exactly-once 副作用。

## 19. R16：两轮独立全量 Review 与正式发布门禁

**Depends on:** R15。

**Files:**

- Create: `docs/review报告/AI公司桌面应用-整改后全量Review报告.md`
- Create: `docs/review报告/AI公司桌面应用-最终交付追踪矩阵.md`
- Modify: `README.md`
- Modify: `docs/部署文档.md`
- Modify: `docs/应用用户手册.md`
- Modify: `docs/后管系统用户手册.md`
- Modify: `docs/后管系统API文档.md`

- [ ] **Step 1: 第一轮独立 Review**

  Reviewer A 按原 27 个问题、设计不变量、契约、迁移、安全和运行时逐项检查；发现问题进入正式 issue，修复后重新运行受影响门禁。

- [ ] **Step 2: 第二轮独立 Review**

  Reviewer B 不读取第一轮结论，重新从设计、原实施计划、代码和真实测试证据审查；不得只检查 diff。

- [ ] **Step 3: 交叉核对两轮问题**

  合并重复项，逐项记录 `confirmed/false-positive/fixed`；confirmed 必须有修复提交和复验，blocker/high 必须为零。

- [ ] **Step 4: 清洁提交重跑发布门禁**

  新建清洁 worktree，锁文件安装，运行 `scripts/verify-all.sh`、真实 CLI 冒烟、macOS Seatbelt/签名/公证、空库/上一版本迁移、后台部署和灾备演练。

- [ ] **Step 5: 生成最终追踪矩阵**

  每个 P0/P1/P2 和新问题映射到任务、提交、代码、测试、证据和 Reviewer。没有证据的项状态只能是 `open`，不得标记 fixed。

- [ ] **Step 6: 文档一致性检查**

  搜索 `TODO/TBD/暂未/后续/占位/NotSupported/skipped`；区分合法用户文案和未完成实现。检查所有文档链接、命令和文件路径真实存在。

- [ ] **Step 7: 发布结论**

  只有设计 K.17 全部满足才允许 PASS 和 Release；否则报告必须为 NEEDS_CHANGES，并列出阻断证据。

## 20. Review 问题到整改任务追踪矩阵

| Review ID | 主任务 | 必须验证的关闭证据 |
|---|---|---|
| P0-01 | R02 | 认证 Tauri 集成与全部路由 E2E |
| P0-02 | R02、R06 | Token/API Key canary 全介质零命中 |
| P0-03 | R01 | contract drift 和四端生成确定性 |
| P0-04 | R01、R13 | 页面方法清单、幂等复用、真实 Rust-Sidecar 集成 |
| P0-05 | R03 | 历史不可变、签名/sequence/对象篡改负例 |
| P0-06 | R06 | 禁止 Sidecar 出站、SSRF、ASK 零副作用 |
| P0-07 | R04 | 从主入口消费全部队列、Worker health |
| P0-08 | R05 | 注入点全有或全无、并发唯一成功 |
| P0-09 | R07、R15 | Review/返修/复测/FinalReport 负例 |
| P0-10 | R08 | 单目标逃逸测试、响应丢失 exactly-once |
| P0-11 | R00、R14 | 任一门禁失败时总脚本非零 |
| P1-01 | R04 | 空库/上一版/中断/hash drift migration |
| P1-02 | R04 | 写队列容量 32、读池上限 8、PRAGMA |
| P1-03 | R06 | 三 fake CLI 契约、真实 CLI 冒烟、Seatbelt |
| P1-04 | R04 | 首次 health、heartbeat、进程组重启和恢复 |
| P1-05 | R10 | OpenAPI drift、Release/Skill/Emergency E2E |
| P1-06 | R09 | 在线备份、恶意归档、原子恢复 |
| P1-07 | R09 | LanceDB 真实 ID/hash/维度对账与重建 |
| P1-08 | R11 | 五服务 Compose、空库/上一 head 部署 |
| P1-09 | R12 | 签名更新、失败启动、缓存包回退 |
| P1-10 | R11 | 异常 canary 和绝对路径零泄露 |
| P1-11 | R14、R16 | 100% 覆盖和所有专项制品绑定 SHA |
| P2-01 | R02、R13 | K.1/K.7 路由静态与 E2E |
| P2-02 | R13 | Query key 隔离、Zustand 无实体、retry 语义 |
| P2-03 | R13 | 路由 lazy chunks 和 size budget |
| P2-04 | R00、R14、R16 | README 只引用自动质量摘要和有效链接 |
| P2-05 | R00、R16 | 清洁 worktree，无生成物噪声 |

## 21. 固定提交顺序

```text
fix(ci): make delivery gates fail closed
fix(contracts): establish generated cross-language contracts
fix(auth): enforce rust-owned credential boundary
fix(catalog): publish immutable signed releases
fix(sidecar): add durable lifecycle and database concurrency
fix(orchestration): confirm plans in one durable transaction
fix(runtime): route all agents through secure runtime gateway
fix(review): enforce evidence-backed completion gates
fix(workspace): execute approved external writes exactly once
fix(recovery): make backup and knowledge generations verifiable
fix(admin): align catalog ui with generated openapi
fix(backend): add reproducible deployment and safe errors
fix(updater): verify updates and provide recovery rollback
fix(desktop): align routes rpc and query state
test(e2e): verify complete agent company workflow
docs(delivery): publish verified remediation evidence
```

实现团队可以把同一任务拆成更小提交，但不得改变依赖顺序或把不同安全/事务边界混在一个提交。

## 22. 最终完成定义

只有以下条件全部满足，本整改计划才可标记完成：

1. 原 27 个问题及实施中新发现问题全部进入最终追踪矩阵。
2. 所有 confirmed 问题都有代码、测试、提交和复验制品；不存在仅文档声明修复。
3. Schema/OpenAPI/生成代码、设计方案、原实施计划、README、部署和用户文档一致。
4. WebView/Sidecar/SQLite/log/diagnostics 不含 Token/API Key。
5. Catalog、Skill、更新和 emergency 指令签名链真实通过篡改测试。
6. 标准研发流程能完成确认、执行、Review、返修、复测和 FinalReport。
7. Sidecar、Provider、网络和进程崩溃可恢复，无重复副作用。
8. 备份损坏和恢复失败保持原 Profile。
9. 所有语言 100% 单元覆盖，集成/E2E/安全/故障/性能/更新/灾备独立通过。
10. `scripts/verify-all.sh` 在任一失败时非零，只在全部真实门禁通过时返回 0。
11. 两轮独立全量 Review 的 blocker/high 均为零。
12. 最终证据基于同一个清洁 commit SHA，可由第三方按文档命令重现。
