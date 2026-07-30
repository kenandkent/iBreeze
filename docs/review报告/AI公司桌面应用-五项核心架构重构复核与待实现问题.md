# AI 公司桌面应用五项核心架构重构复核与待实现、待修复问题

## 1. 报告信息

| 项目 | 内容 |
|---|---|
| 复核基线 | Git `e9cb0545b2f67eb952c206ddb4fe0691c17cf093`，分支 `main`，与 `origin/main` 一致 |
| 复核日期 | 2026-07-30 |
| 复核前工作区 | 无未提交变更 |
| 复核对象 | 设计方案、实施计划、五项核心架构设计、字段级实施计划、Rust Core、Python Sidecar、Desktop、Admin、Backend、Updater、部署、测试与 CI |
| 规范依据 | `docs/设计方案/AI公司桌面应用设计方案.md` |
| 核心架构依据 | `docs/设计方案/iBreeze五项核心架构重构设计方案.md` |
| 实施依据 | `docs/superpowers/plans/2026-07-28-ibreeze-five-core-architecture-rewrite.md` |
| 总结论 | **不能确认问题已全部修复；五项核心架构均未达到关闭标准，当前代码不能作为完成目标架构重构的可发布版本** |

本报告只记录当前基线可复现的事实，不沿用提交说明、修复记录或第三方报告中的“已关闭”状态。问题只有同时满足“生产调用链接通、旧旁路删除、目标测试通过、全量门禁通过”四项条件才视为关闭。

## 2. 结论摘要

当前版本相较上一轮已经增加了 `ProductionRpcServer`、后台 reader task、生成方法类型表、Review/Completion Handler、WriteQueue、UnitOfWork、WorkerSupervisor、Broker 组件和更新器安全检查，部分历史缺陷确有进展。但是，新增组件与旧实现仍以双轨方式共存，多个关键组件没有接入同一条生产调用链。

当前存在六个 P0 阻断项：

1. 全新在线 Profile 迁移完成后没有任何代码创建 `local_profile`，Lifecycle 必然以 `PROFILE_NOT_FOUND` 失败，正常首次登录无法打开 Profile。
2. Sidecar 的 API Model transport 被显式禁止连接当前生产 UDS，又没有取得生产连接上的 `IpcSession`；Rust reader 还会先把反向 request 当作 response 反序列化并断开，Reverse RPC 无法工作。
3. Canonical Registry 中 120 个方法全部标为 `owner=sidecar`，代码又用额外 `ownership.v1.json` 修正；生成器、同步脚本、运行时 Dispatcher 和公开方法集合彼此不一致。
4. 生产 Lifecycle 仍实例化根级旧 `rpc_server.py` 作为 legacy bridge；WriteQueue 和 UnitOfWork 在同一连接上分别自行开启事务，不能保证单写顺序和原子性。
5. Rust `process/mod.rs` 仍只有占位说明，CLI 仍由 Python `asyncio.create_subprocess_exec` 启动，Rust Process Supervisor、Seatbelt 和 Egress Lease 没有生产闭环。
6. Review/Completion 新 Handler 的事件和 Outbox 类型与 UnitOfWork 契约不匹配，公开 Review 方法还存在缺口，无法形成权威事务闭环。

因此，提交 `e9cb054` 的“单写者 177 违规清零、契约 drift 修复、Health 改进”说明不能作为验收结论。静态扫描、drift 和 health 的现有实现均存在会产生假绿灯的检查盲区。

## 3. 实际验证结果

### 3.1 全量门禁

执行：

```bash
bash scripts/verify-all.sh --scope all
```

结果为 **退出码 1**。门禁在 Contracts 阶段提前失败：

- 295 个 JSON Schema 语法校验通过；
-生成目录 diff 检查显示无 drift；
- `scripts/sync_contract_registry.py --check` 失败：
  - `Python READ_METHODS is out of sync`；
  - 旧 `RPCServer.self.methods` 缺少 `review.submit`；
  - `Rust sidecar_method_kind is out of sync`。

因为脚本使用 fail-fast，Rust、前端、Sidecar、Backend、E2E、Security 和根级 drift 测试均未在该次全量命令中执行。后续结果来自独立分范围验证。

### 3.2 分范围验证

| 范围 | 命令或检查 | 实际结果 | 判定 |
|---|---|---|---|
| Contracts | `verify-all.sh --scope contracts` | Registry sync 失败 | 不通过 |
| Sidecar lint | `ruff check ibreeze tests` | 61 项错误；生产代码 `workers/runtime.py` 使用未导入的 `Any` | 不通过 |
| Sidecar typecheck | `mypy ibreeze` | 6 项错误，涉及 Worker 构造、返回类型和可空 writer | 不通过 |
| Sidecar test | `pytest tests -q` | 1734 passed、15 failed、1 xfailed、23 warnings | 不通过 |
| Backend | `verify-all.sh --scope backend` | 204 tests passed，但覆盖率 62.89% 小于 100% | 不通过 |
| Rust fmt | `cargo fmt --check` | 多文件格式差异 | 不通过 |
| Rust clippy | `cargo clippy ... -D warnings` | 6 项错误 | 不通过 |
| Rust test | `cargo test --all-features` | 113 passed、1 failed；未知方法判定测试失败 | 不通过 |
| Rust 正式门禁 | `verify-all.sh --scope desktop` | 本机缺少 `cargo-nextest`，按 fail-closed 直接退出 | 环境未满足，不能判定正式门禁通过 |
| Desktop lint | `npm run lint` | `@eslint/js` 未声明/未安装 | 不通过 |
| Desktop typecheck | `npm run typecheck` | 通过 | 通过 |
| Desktop test | `npm run test:coverage` | 147 passed、4 failed；`isReadOperation` 不再导出但测试仍调用 | 不通过 |
| Admin lint | `npm run lint` | `@eslint/js` 未声明/未安装 | 不通过 |
| Admin typecheck | `npm run typecheck` | 通过 | 通过 |
| Admin test | `npm run test:coverage` | 134 passed；86.33% statements、80% branches、84.47% functions、87.78% lines | 测试通过但不满足设计要求的 100% |
| E2E | `verify-all.sh --scope e2e` | 仅 2 个 Backend liveness/readiness 测试 | 不满足四条核心真实链路 |
| Security | `verify-all.sh --scope security` | 27 passed | 该子集通过 |
| 根级 contract/integration/scripts | 显式执行三个根目录 | 168 passed | 测试通过，但 CI Policy 已被放宽为只要求一个 workflow |
| npm audit | Desktop/Admin JSON 审计 | 当前均为 0 vulnerability | 通过 |
| 单写者扫描 | `python3 scripts/check_single_writer.py` | 输出 0 violation | 假绿灯，详见 FIX-P0-04 |

### 3.3 CI 与测试有效性

当前只有 `.github/workflows/ci.yml`，使用 Ubuntu matrix 执行七个 scope。它不能替代目标设计要求的七个职责分离工作流和真实 Apple Silicon macOS 14/macOS 26 发布门禁。

`tests/contract/test_ci_policy.py` 已被改为只要求 `ci.yml`，所以 168 个根级测试通过只证明“测试和当前实现一致”，不证明实现符合设计。

`run_drift()` 的目录判断固定检查 `sidecar/tests/contract`、`sidecar/tests/integration`、`sidecar/tests/scripts`，而实际目录位于仓库根 `tests/`。因此 CI 的 `drift` scope 会输出“no test directories found”并跳过上述 168 个测试。

`tests/e2e` 只有 Backend 的 `/health/live` 和 `/health/ready`，没有以下目标 E2E：

- API Model：Sidecar Agent Loop → 同一 UDS Reverse RPC → Rust Credential Broker → TLS Provider fixture；
- CLI Runtime：Sidecar 调度 → Rust Process Supervisor → Seatbelt → CONNECT Egress → 取消/恢复；
- Review：Artifact → 非贡献者 Review → Issue 修复/复测 → 三级 Completion；
- Updater：签名包 → 安装 → 30 秒真实健康观察 → 恢复旧版本。

## 4. 五项核心架构完成度

| 核心架构 | 当前判定 | 已存在的有效组件 | 未满足的关闭条件 |
|---|---|---|---|
| Credential/HTTP Broker、Reverse RPC、Egress | **部分实现，未完成** | Rust CredentialStore、HttpBroker、DNS Policy、EgressLease、ConnectHandler、后台 UDS reader | 同一连接反向调用不可用；API Model transport 无生产 session；缺 4 个反向 request handler；HTTP 只返回 accepted；CONNECT 无 accept loop且按错误端口查 Lease |
| Canonical RPC、Domain Event、生成契约 | **部分实现，未完成** | 295 个 Schema、120 方法、45 Domain Event、TS/Rust 方法类型生成物 | Registry owner 全错；存在额外 ownership；同步门禁失败；Rust 生成器逻辑错误；生成 DTO 不可编译/未消费；生产 Dispatcher 方法缺失 |
| Persistence Kernel 与 Application Lifecycle | **部分实现，未完成** | `001_initial.sql`、MigrationRunner、8 连接 ReadPool、WriteQueue、UnitOfWork、WorkerSupervisor、ProductionRpcServer | 全新 Profile 无法初始化；旧 RPC 仍在生产；Queue/UoW 双事务入口；扫描器有豁免；双套 Event/Outbox；Health/ready 不可信 |
| CLI Runtime、Workspace、Seatbelt、Egress、取消/恢复 | **未完成** | Python CLI Adapter、Python ProcessSupervisor、静态 sandbox-exec 包装、Rust Egress 数据结构 | Rust Process Supervisor 不存在；Python 仍直接 spawn；runtime.process.* 无 handler；无动态 Workspace/Seatbelt/Egress 绑定；无真实 CLI E2E |
| Review、返工与三级 Completion | **部分实现，未完成** | Review Aggregate、Guard、Repository、Completion Gate、部分 Handler 和测试 | UoW 类型契约错误；RPC meta 幂等键丢失；公开方法缺失；Outbox 不执行内部命令；旧服务/直接 SQL 并存；测试失败 |

五项中没有任何一项满足“已完成”。局部类、Schema 或单元测试存在不能代替生产链路验收。

## 5. 对两项争议问题的最终核实

### 5.1 `FIX-P0-04（rpc_server.py LocalDB 依赖）`

该问题需要拆成两部分判断：

- `sidecar/ibreeze/local_db.py` 已删除，生产代码没有 `LocalDB` 引用。狭义的“LocalDB 依赖”已经消除。
- “`rpc_server.py` 已废弃且只用于测试”不准确。`ApplicationLifecycle.start()` 调用 `register_legacy_handlers()`，后者在生产启动路径中导入并实例化 `ibreeze.rpc_server.RPCServer`，再把旧 `self.methods` 大批包装进新 Dispatcher。

因此不能搁置旧 `rpc_server.py`。它仍是当前绝大多数业务 RPC 的生产实现，也是单写者、契约生成和 Review 路由双轨问题的根源之一。

### 5.2 `FIX-P1-01（CLI Runtime Rust 接管）`

该问题准确且仍未修复：

- `apps/desktop-core/src/process/mod.rs` 只有未来模块说明，没有 ProcessSupervisor 实现；
- `sidecar/ibreeze/runtime/process_supervisor.py` 自身明确写明“Rust 端尚未实现”；
- 生产执行路径 `run_executor.py → get_supervisor() → asyncio.create_subprocess_exec` 仍由 Python 持有 CLI 进程；
- Rust reverse table 未注册 `runtime.process.start/cancel/status`；
- EgressBroker/ConnectHandler 没有进入 AppState 的 CLI Run 生命周期。

这不是局部 `commands.rs` dispatch 调整可以关闭的问题，必须完成 Rust 进程、Seatbelt、管道、Egress 和 Reverse RPC 的整体切换。

## 6. 详细待实现、待修复问题

### FIX-P0-01：全新在线 Profile 无法完成首次启动

**级别：P0 / 登录与本地数据入口阻断**

#### 现状与证据

- `SidecarApplication` 正确把数据库路径改为 `${profile_root}/profile.db`。
- `MigrationRunner` 会创建 `local_profile` 表，但整个代码库没有 `INSERT INTO local_profile`。
- `ApplicationLifecycle._ensure_profile_identity()` 对空表一律返回 `PROFILE_NOT_FOUND`。
- 构造参数 `profile_mode` 被保存，但身份校验没有 online/offline 分支。
- Rust 在线登录在写完 `profile-meta.v1.json` 后启动 Sidecar，未提供另一个初始化 `local_profile` 的入口。
- Lifecycle 把阶段标为 `UDS_HANDSHAKE_ONLY` 时只设置一个全局 socket path，真正的 `ProductionRpcServer` 要等 Lifecycle 完全启动后才创建。

#### 影响

- 用户首次在线登录不能创建本地 Profile。
- `auth.login`、`auth.openProfile`、Migration、Handshake 和后续业务 RPC 无法形成真实 E2E。
- 现有 ApplicationLifecycle 单元测试依赖预置数据库，掩盖了空 Profile 生产失败。

#### 固定修复方案

1. 将 `ProfileOpenContext` 固定为不可缺字段结构：
   - `profile_directory_id`；
   - `backend_origin`；
   - `app_user_id`；
   - `masked_identifier`；
   - `device_id`；
   - `profile_mode=online|offline`；
   - `app_version`；
   - `schema_epoch=1`。
2. Migration 后、业务 Dispatcher 开启前，通过唯一 WriteQueue 执行身份命令：
   - online 且表为空：插入唯一 `local_profile`；
   - offline 且表为空：返回 `PROFILE_NOT_FOUND`；
   - 表非空：逐字段比较，任何不一致返回 `PROFILE_IDENTITY_MISMATCH`；
   - `schema_epoch` 不支持：返回 `PROFILE_SCHEMA_UNSUPPORTED`。
3. 插入和更新 `last_opened_at` 不得直接在 Lifecycle 上调用 writer/commit，必须经过 WriteQueue/UnitOfWork。
4. `launch_id` 和 `app_version` 由 Rust 启动参数传入 Sidecar 并保存；Handshake 必须与启动值逐字比较，不能由客户端请求自行决定。
5. UDS 先绑定为 handshake-only；迁移期间握手请求等待 ready，其他方法返回 `PROFILE_NOT_READY`。
6. 任一步失败按逆序关闭 RPC、Worker、WriteQueue、ReadPool、writer，删除未发布 socket 并释放 Profile lock。

#### 必须新增的测试

- 空目录 online 首次打开后存在且仅存在一条 `local_profile`；
- 空目录 offline 打开失败且不产生伪身份行；
- backend/user/device/masked/schema 任一不一致；
- 第二次打开不重复插入；
- Migration、身份写、Worker、RPC 任一步失败均不返回 ready；
- 真实 Rust Supervisor 启动打包 Sidecar，完成 `handshake → system.health → company.list → shutdown`。

#### 关闭标准

使用全新空 Profile 从真实桌面登录成功，首次 health 为 `healthy`，重启后身份校验成功；测试不得手工预插 `local_profile`。

---

### FIX-P0-02：Duplex UDS、Credential HTTP Broker 和 CONNECT Egress 仍不可用

**级别：P0 / API Model 与 CLI 网络能力阻断**

#### 现状与证据

- Rust `SidecarClient.reader_loop()` 先把每一帧反序列化为 `JsonRpcResponse`。反向 request 含 `method/params/meta`，在 `deny_unknown_fields` 下会直接反序列化失败并断开，后续 `sidecar:` 分支实际不可达。
- Python `ReverseRpcClient` 通过 `asyncio.open_unix_connection()` 新建连接；Lifecycle 又把该地址标记为 Sidecar 自己的 socket，`_ensure_connected()` 会明确抛错拒绝自连接。
- `ProductionRpcServer` 没有创建 `IpcSession`、Multiplexer 或 pending map，也没有把当前连接暴露给 Runtime。
- Rust Registry 固定七个反向 request，但实际只注册 `credential.http.start/cancel/probe`；`host.externalWrite.execute`、`runtime.process.start/cancel/status` 缺失。
- 实际注册了 `runtime.processRegistered`、`runtime.processExited` 两个驼峰 request，名称和方向都不符合 Registry 中的 `runtime.process.registered/exited` notification。
- `credential.http.start` 立即返回 `{request_id,status:"accepted"}`，Python `ReverseRpcTransport.complete()` 却把该响应当最终 `{content,tool_calls,usage}`。
- `EgressBroker` 创建了 TcpListener，但没有 accept loop；`ConnectHandler` 用 CONNECT 目标端口 443 调 `validate_token_by_port()`，而 Lease 保存的是本地随机代理端口，合法连接也无法匹配。

#### 影响

- API Model 职员不能执行真实 Provider 请求。
- Sidecar→Rust 外部写和 CLI 进程控制不可用。
- CLI CONNECT Egress 不可用，现有 Seatbelt 网络策略也没有可连接的代理服务。
- 任意真实反向 request 可能直接导致 Rust reader 断线并让全部 pending RPC 失败。

#### 固定修复方案

1. 每个 Profile 只保留一条认证 UDS，不再创建 reverse 专用自连接。
2. Rust reader 先把帧解析为 `serde_json::Value`，再按字段分类：
   - 有 `method` 且有 `id`：request；
   - 有 `method` 且无 `id`：notification；
   - 无 `method` 且有 `result/error`：response；
   - 其他：协议错误并断开 generation。
3. Rust 和 Python 均使用单 reader task、单 writer queue、pending 上限 256、stream 上限 64；禁止多个任务直接并发写 socket。
4. `ProductionRpcServer` 接受连接后创建真实 `IpcSession`；Dispatcher Handler、Agent Runtime 和 Worker 只取得该 session 的 `call/notify` 接口。
5. 删除 `runtime/transport.py` 中 `UdsConnection` 和全局 socket path；`ReverseRpcTransport` 构造时必须注入当前 session。
6. 从 `reverse-methods.v1.json` 生成 Rust/Python allowlist 和注册表，七个 request 与四个 notification 必须集合精确相等。
7. HTTP Broker 使用明确的两阶段协议：
   - start 返回 `request_id`；
   - Rust 以 `credential.http.event` 推送 delta/tool/usage/completed/failed；
   - Sidecar 按 `request_id` 注册 stream，收到 completed 后组装 ModelTurn；
   - cancel、deadline、断线必须结束 stream 并释放 CredentialLease。
8. 每个 CLI Run 创建 `EgressLease` 后立即启动 accept loop；`ConnectHandler` 直接持有当前 Lease，不得用目标端口查本地 Lease。
9. CONNECT 固定校验本地监听端口、Proxy Token、Run、域名、443、DNS 解析后 IP、DNS rebinding、并发和速率；取消 Run 时关闭 listener 和全部 tunnel。

#### 必须新增的测试

- 同一 UDS 双向同时发请求且响应乱序；
- reverse request 不会被 response parser 拒绝；
- pending/stream 上限、oversize、deadline、generation 切换、断线清理；
- 真实 TLS Provider fixture 的 API Model 文本、Tool Call、usage、取消；
- canary secret 在 Sidecar 内存序列化、日志、SQLite 和 payload 中零命中；
- CLI CONNECT 的正确 Token 成功，错 Token、错 Run、非 443、私网、rebinding 均失败；
- Run 结束后端口不可连接且 Token 已 zeroize。

#### 关闭标准

API Model 和至少一种真实 CLI 均通过同一 UDS 完成端到端任务，Sidecar 不持有 Provider secret，CLI 不能绕过本地 CONNECT Proxy 直接出站。

---

### FIX-P0-03：Canonical Contract 仍有多个事实源，生成代码不可作为运行时契约

**级别：P0 / 跨进程协议与公开接口阻断**

#### 现状与证据

- `registry.v1.json` 的 120 个方法全部标为 `owner=sidecar`，包括 `auth.*` 和 `backend.validateOrigin`。
- `ownership.v1.json` 另行把 8 个方法归 Rust、94 个归 Sidecar、3 个归 supervisor；设计明确禁止独立 ownership 文件。
- `sync_contract_registry.py` 注释和逻辑仍以手写 `rpc_server.py`、`commands.rs`、`rpcClient.ts` 为同步目标，并明确包含 placeholder。
- Contract 门禁当前同步失败。
- `generate-method-kinds.py` 生成的 Rust `method_is_read/write()` 对任何未知方法都返回 `Some(false)`，与自身测试要求的 `None` 冲突；Rust test 已复现失败。
- `check-contract-drift.sh` 声称只读，但会先直接运行无 `--check` 的 `generate-method-kinds.py` 写入工作区，再复制结果进行比较，可能覆盖并掩盖 drift。
- `apps/desktop-core/src/generated/{contracts,rpc}/lib.rs` 生成了同名重复 struct，并把本地 `$ref`/未知引用降级成 `serde_json::Value`；这些 crate 没有被主 Rust crate 编译或消费。
- Rust 同时存在 `src/generated/rpc/method_kinds.rs` 和实际使用的 `src/rpc/generated_method_kinds.rs` 两份生成物。
- 生产 Dispatcher 静态推导缺少公开 `review.listIssues` 和 `review.rerun`，却注册 Registry 外 `review.start/startIssueFix/verifyIssue/closeIssue/rejectIssue` 和 `completion.*`。
- `ProductionRpcServer` 未对 request/response 执行 JSON Schema 校验，也未校验业务请求 `meta.ipc_session_id`，而是传入 `_DummySession`。

#### 固定修复方案

1. `registry.v1.json` 成为唯一事实源，每个公开和 supervisor 方法记录正确 `owner/kind/scope/schema/ttl/errors`。
2. 删除 `ownership.v1.json`、手写 `READ_METHODS`、手写 reverse allowlist和重复 Rust 方法表。
3. 生成器一次生成：
   - Rust owner router、request/response DTO、method metadata、Reverse Dispatcher；
   - Python request/response Model、method metadata、Dispatcher skeleton；
   - Desktop TypeScript Client；
   - Admin OpenAPI 类型。
4. 未识别 `$ref`、重复类型名、无法表示的 union 或 unknown schema 必须让生成器失败，禁止降级成 `Value/Any`。
5. 生成 Rust crate必须加入 workspace 并在 CI 编译；生产 commands/dispatcher 必须直接导入该 crate。
6. drift 脚本只生成到临时目录，禁止写工作区；比较缺失、多余和内容差异后 fail-closed。
7. 生产启动时断言：
   - Rust 路由集合等于 Registry 的 rust/supervisor 集合；
   - Sidecar Dispatcher 集合等于 Registry 的 sidecar 集合；
   - Reverse Handler 集合等于 Reverse Registry；
   - 任一缺失或多余均拒绝 ready。
8. `ProductionRpcServer` 在 Dispatcher 前后分别校验 request/response Schema，并从 `meta` 构造真实 `CommandContext`。

#### 必须新增的测试

- owner 集合互斥且并集等于全部方法；
- 禁止第二 ownership 文件和手写 method set；
- unknown method 在 Rust/Python/TS 三端均为 `METHOD_NOT_ALLOWED`；
- 生成 crate 编译测试；
- 生产 Dispatcher 精确集合测试；
- request/response unknown field、错误 kind、错误 owner、错误 session 全部失败；
- drift 脚本执行后 `git status --short` 必须为空。

#### 关闭标准

删除全部平行契约后，从 Registry 重新生成、编译、运行三端，Contract scope 和生产 Dispatcher 精确集合门禁全部通过。

---

### FIX-P0-04：Persistence 仍不是单一 WriteQueue/UnitOfWork 事务内核

**级别：P0 / 数据一致性阻断**

#### 现状与证据

- `local_db.py` 已删除，但 `handler_registry.py` 在生产 Lifecycle 中实例化旧 `RPCServer` 并桥接绝大多数业务方法。
- 单写者扫描器显式允许 `company.py`、`employee.py` 使用 `BEGIN IMMEDIATE`，排除整个 `rpc_server.py`、`workers/` 和 `application/` 的 commit 检查。
- `WriteQueue` 和 `UnitOfWork` 各自在同一个 writer 上执行 `BEGIN IMMEDIATE/commit/rollback`；现代 Handler 直接调用 UnitOfWork，不经过 WriteQueue，legacy Handler 经过 WriteQueue，二者可能并发撞事务。
- `OutboxWorker` 在 WriteQueue envelope 内再次调用 `conn.commit()`，会提前提交 envelope 的部分工作。
- Lifecycle 身份更新时间直接调用 writer/commit。
- `IdempotencyStore.lookup()` 没有比较已存 `request_sha256`；`claim()` 把任意异常都折叠为 false，无法区分同键同 payload、同键异 payload和基础设施错误。
- DDL 同时存在 `domain_events/outbox_events/projection_offsets` 和 `domain_event_store/outbox/projections`；`DomainEventStore` 还同时写两张事件表，旧服务和新 Worker分别消费不同 Outbox。
- ReadPool 连接没有固定 `PRAGMA query_only=ON`，不能从连接层阻止意外写入。

#### 影响

- 并发 legacy/modern 命令可能出现“cannot start a transaction within a transaction”、提前 commit 或部分回滚。
- 幂等键同键异 payload 不能稳定返回 `IDEMPOTENCY_CONFLICT`。
- Event、Outbox 和 Projection 有两套事实，崩溃恢复后可能重复、遗漏或顺序不一致。
- “单写者检查通过”不能证明没有旁路。

#### 固定修复方案

1. 删除根级旧 `rpc_server.py` 和 `handler_registry.py` 生产桥；所有 Registry 方法迁移为明确 Query/Command Handler。
2. writer 只能由 `WriteQueue` 持有，其他对象不暴露裸 connection。
3. `WriteQueue` 的 envelope 固定包含 `CommandContext`、request hash 和 `execute(UnitOfWork)`；Queue worker 为每个 envelope 创建一个 UoW并独占完整事务。
4. UnitOfWork 不再自行与 Queue 并行开启事务；其唯一职责是在 Queue 已取得的事务中执行幂等、聚合写、Domain Event、Outbox 和响应。
5. Worker、Lifecycle、Migration 后身份写、RPC command、内部 completion command 全部提交到同一 Queue；envelope 内禁止 commit/rollback。
6. 保留 `domain_events/outbox_events/projection_offsets` 作为唯一表组，删除第二套表和双写逻辑。
7. Idempotency 固定语义：
   - 同 key 同 hash completed：返回原结构化响应；
   - 同 key 异 hash：`IDEMPOTENCY_CONFLICT`；
   - processing 未超时：`IDEMPOTENCY_IN_PROGRESS`；
   - 基础设施异常：整体 rollback，不伪装成 claim conflict。
8. ReadPool 以只读 URI 或 `query_only=ON` 打开，任何写语句必须失败。
9. 重写单写者扫描为 AST + SQL token 检查，不允许 legacy allowlist；扫描全部生产 Python。

#### 必须新增的测试

- 32 容量、FIFO、backpressure、barrier、stop drain；
- legacy 代码和直接 commit/BEGIN/裸 writer 的静态门禁；
- 100 个并发 Command 无嵌套事务；
- 在业务写、Event、Outbox、幂等响应每个边界注入失败，结果全有或全无；
- 同键同/异 payload；
- Worker 失败重试不重复 Event/Outbox；
- ReadPool 写入失败；
- 崩溃后 running migration、processing idempotency、processing outbox 的恢复。

#### 关闭标准

代码库只有 Migration 和 WriteQueue 可以开启写事务；生产无 legacy bridge、无双 Event/Outbox 表、无静态扫描豁免，并通过并发与 fault injection。

---

### FIX-P0-05：CLI Runtime 仍由 Python 持有，Rust/Seatbelt/Egress 未接管

**级别：P0 / Codex CLI、Claude Code、OpenCode 基础能力阻断**

#### 现状与证据

- Rust `process/mod.rs` 只有占位说明，没有 registry、signals、stdout/stderr pump 或 ProcessSupervisor。
- Python `ProcessSupervisor.start()` 直接调用 `asyncio.create_subprocess_exec`。
- `run_executor._execute_cli()` 仍直接使用 Python supervisor。
- Python 中的 sandbox profile 是固定字符串，只允许系统目录和临时目录，没有绑定目标 Workspace、只读外部路径、Run 专属 HOME 或 Egress 随机端口。
- Rust Reverse Dispatcher 未注册 `runtime.process.start/cancel/status`。
- Rust EgressBroker 和 ConnectHandler 没有进入 AppState，也没有和 CLI Run 生命周期绑定。
- 没有 Codex CLI、Claude Code、OpenCode 的真实安装探测、执行、取消、恢复和 Seatbelt E2E。

#### 固定修复方案

1. 在 Rust 创建 `process/{supervisor,registry,signals,stdio,seatbelt,environment}.rs`。
2. `runtime.process.start` 请求固定包含：
   - `run_id/employee_id/agent_kind`；
   - 已验签 adapter/version/model；
   - argv，不允许 shell string；
   - Workspace grant ids；
   - network domain policy hash；
   - timeout/deadline；
   - execution snapshot hash。
3. Rust 重新校验当前 IPC session、Catalog、snapshot、Workspace grant 和 policy hash，不信任 Sidecar 传入路径/env。
4. 每个 Run 创建：
   - 独立 process group；
   - Run 专属临时 HOME 与 Agent 配置目录；
   - 动态 SBPL，Workspace 内读写、Workspace 外只读且仅限 grant；
   - 独立 Egress Lease 和本地代理端口；
   - stdout/stderr 两个 Tokio pump。
5. Rust 先登记 Process Registry，再发送 `runtime.process.registered`；output 和 exited 使用 notification。
6. 取消固定执行 process group `SIGTERM → 5s → SIGKILL`，关闭 Egress listener，删除临时 HOME/SBPL并 zeroize Token。
7. Sidecar CLI Adapter只负责生成 Invocation 和解析 RuntimeEvent；删除 Python spawn、signal、sandbox-exec 和 PID 所有权。

#### 必须新增的测试

- 三种真实 CLI probe 与版本不兼容；
- Workspace 内读写、外部只读、外部写拒绝；
- 直接网络/DNS 拒绝，只允许 CONNECT；
- stdout/stderr 大流量不死锁且有序；
- cancel、timeout、Sidecar 断线、Rust 崩溃恢复；
- PID reuse 通过 pid/pgid/start_time 防护；
- 进程树无孤儿，临时目录和 Token 清理。

#### 关闭标准

Sidecar 静态扫描不存在 `create_subprocess_exec/subprocess/os.exec*`；三种 CLI 至少各完成一条真实任务，进程、Seatbelt、Egress 均由 Rust 独占。

---

### FIX-P0-06：Review、返工和三级 Completion 的现代 Handler 无法形成权威事务

**级别：P0 / 任务闭环与交付可信性阻断**

#### 现状与证据

- 新 Review/Completion Handler 已注册，但公开 `review.listIssues`、`review.rerun` 因 legacy prefix 整体跳过而没有生产 Handler。
- 新 Handler注册了 Registry 外的 `review.start/startIssueFix/verifyIssue/closeIssue/rejectIssue` 和 `completion.*`，公开/内部边界不清。
- Handler 生成的 `events` 是普通 dict；`DomainEventStore.append_all()` 要求 `DomainEventRecord` 并访问 `event.company_id` 等属性。
- Handler 生成的 `outbox` 是普通 dict；`OutboxWriter.enqueue_all()` 要求 `OutboxRecord` 并访问 `record.topic/payload_json`。
- `ProductionRpcServer` 丢弃 RPC meta，wrapper 又从 params 读取 `idempotency_key`；设计明确规定幂等键只能在 meta，导致现代写命令实际拿不到幂等上下文。
- `EVENT_COMMAND_MAP` 存在，但 `OutboxWorker` 只把记录标记 delivered，没有执行 `EvaluateEmployeeAcceptance/EvaluateDepartmentReadiness/EvaluateCompanyReadiness`。
- 旧 runtime/task/review service 仍存在大量直接状态 SQL；Run 成功后的 `_feedback_to_tasks()` 仍直接更新 Employee/Department/Company task。
- Sidecar 测试当前有 15 个失败，多数集中在 Review/Completion fixture 外键和 Runtime lease。

#### 固定修复方案

1. 明确公开 RPC 与内部 Command：
   - 公开只保留 Registry 方法；
   - `StartReview/VerifyIssue/Completion Evaluate*` 只进入内部 CommandBus，不注册公开 RPC。
2. 从 RPC meta 构造 `CommandContext`：
   - `trace_id/ipc_session_id/window_session_id/idempotency_key/deadline/company_scope`；
   - params 中出现 idempotency key 必须 Schema 拒绝。
3. Handler 只能返回强类型 `CommandResult[Response]`、`DomainEventRecord`、`OutboxRecord`，禁止 dict 猜字段。
4. Outbox Worker 按 topic 调内部 CommandBus，成功后和 projection offset按规定事务更新；不能先标 delivered。
5. `run_executor` 只结束 AgentRun并写运行事件，不直接完成任何业务任务。
6. Artifact、Verification、Review、Issue、Report、Rework 和 Completion Gate全部读取 current hash/current attempt，使用同一 UoW。
7. Artifact supersede 在同一事务把旧 assignment 置 stale，旧 report 保留审计但退出 Gate。
8. blocker/high 只能 `open→fixing→resolved→verified→closed`；medium/low rejected 必须有理由。

#### 必须新增的测试

- 真实 `review.submit` 通过 ProductionRpcServer、Schema、meta、WriteQueue和UoW；
- contributor 不能自审，reviewer run/employee/artifact hash/report artifact 必须匹配；
- pass 带 issue、needs_changes 无 issue、failed 无 blocker review_execution 均失败；
- Artifact supersede、并发 submit、版本冲突、同键重放；
- Outbox 驱动 Employee→Department→Company completion；
- Run exit_code=0 但无 Review/Verification 时业务任务不能完成；
- blocker/high 未关闭、最新 rework attempt 未完成、department report 未通过均阻断。

#### 关闭标准

从真实任务执行到最终报告只存在一条 Review/Completion 状态路径；删除旧状态写入口后，三级 E2E 和 fault injection 全部通过。

---

### FIX-P1-01：Handshake、Health 和登录 ready 判定会产生假健康

**级别：P1 / 发布与自动恢复可靠性**

#### 现状与证据

- `ProductionRpcServer` 构造时生成一个随机 `launch_id`，Handshake 不校验客户端 `launch_id` 是否等于启动值，也不校验 `app_version`。
- Handshake 只要 Lifecycle 有 writer 就返回 `database_status=ready`，固定返回 `profile_status=ready` 和 `migration_version="1"`。
- `SidecarSupervisor.check_health()` 只判断 `system.health` RPC 是否返回，不检查返回体 `status`；Sidecar 即使返回 `unhealthy` 也会被 Rust判为 healthy。
- `open_online_session/open_offline_session` 在 `supervisor.start()` 后直接返回 opened，没有执行设计要求的首次合成 health。
- Rust `system_health` 只包含平台和 Sidecar running/healthy，不包含 Process Supervisor、Credential Broker、Egress Broker、IPC generation 和 freshness。
- Sidecar Health 不体现 identity、RPC session、reverse broker、write queue worker 存活和观测过期。

#### 固定修复方案

1. Handshake 对启动时固定的 app/protocol/launch/token proof 全量校验。
2. Sidecar Health 使用版本化 Schema，返回 Profile、Migration、Queue、Worker、event-loop lag 和 observed_at。
3. Rust 校验 observed_at freshness并追加 IPC、Process、Credential、Egress 状态，生成唯一合成快照。
4. DB/Migration/IPC/WriteQueue 任一失败为 unhealthy；Broker/Runtime/非关键 Worker失败为 degraded。
5. 登录只有在 Handshake ready且首次合成 health=healthy 后才返回 opened。
6. Health RPC返回 unhealthy 必须让 `check_health()` 返回错误，不能只检查传输成功。

#### 关闭标准

对每个子系统注入 failure/stale/timeout，登录、更新器和监控均得到设计规定的同一状态，不能出现 transport success 被当作 healthy。

---

### FIX-P1-02：CI、覆盖率和 E2E 门禁不满足发布标准

**级别：P1 / 质量门禁**

#### 待修复项

1. 修复当前 Contracts、Sidecar lint/mypy/test、Backend coverage、Rust fmt/clippy/test、Desktop/Admin lint和 Desktop test 的所有失败。
2. Desktop/Admin 补充 `@eslint/js` 的明确 devDependency并锁定 lockfile。
3. TypeScript/Python/Rust 手写可执行代码恢复 100% 指标，不得把配置降为 80%、77%、62%。
4. 删除 xfail/skip；无测试、空测试集和缺关键工具必须失败。
5. 修复 `run_drift` 根目录路径，168 个 contract/integration/script 测试进入主门禁。
6. 建立设计规定的 Contracts、Desktop、Sidecar、Backend、E2E、Security、Release 七个 workflow。
7. Release 在真实 Apple Silicon macOS 14 和 macOS 26执行签名、公证、Seatbelt、CLI、Updater 和 E2E。
8. CI 使用锁定版本安装 uv、cargo-nextest、cargo-llvm-cov、cargo-audit；禁止无版本 `curl | sh` 和无版本 `cargo install`。
9. E2E 增加本报告列出的四条真实链路。
10. 覆盖率门禁必须覆盖生产导入路径，禁止通过不编译/不导入 generated crate规避覆盖。

#### 关闭标准

本地 `verify-all --scope all` 和七个 CI workflow 全绿；报告中无缺工具、skip、xfail、阈值豁免或“仅运行局部测试”。

---

### FIX-P1-03：Updater 与设计规定的 Tauri Updater/恢复流程不一致

**级别：P1 / 更新安全与可恢复性**

#### 现状与证据

- 设计要求固定使用 Tauri Updater，当前实现自行下载并调用系统 `tar`。
- `updater_install()` 把 `state.store.base_path()` 同时当作安装目录和数据目录，解压目标不是签名的 macOS 应用安装位置。
- 安装前没有检查 active AgentRun、待审批和最近备份。
- `check_sidecar_handshake()` 在发送请求前先等待读取，且发送的是未加 4 字节长度前缀的 JSON，和生产 UDS 协议不兼容。
- migration/write queue 检查读取可选 JSON 文件；文件不存在仍视为通过，不是实时 health。
- `trigger_rollback()` 只删除 pending marker，不恢复旧应用包；测试名称声称 rollback，但只断言 marker 被删除。
- `safe_extract()` 有 symlink/hardlink 检查，但无法替代 Tauri 签名、Apple Code Signing 和 Notary 验证。

#### 固定修复方案

1. 使用 Tauri Updater官方安装状态机，Rust 内嵌更新公钥。
2. 安装前逐项校验 active run=0、pending approval=0、最近备份成功。
3. 只接受 HTTPS、Tauri signature、Apple签名和公证均通过的包。
4. 缓存上一稳定的已签名安装包，不把 Profile 数据目录当安装目录。
5. 更新后通过正常 SidecarSupervisor执行真实 Handshake和合成 Health，连续 30 秒健康后标 stable。
6. 失败进入恢复界面，关闭新版后重新安装缓存旧包；数据库只用升级前备份恢复，禁止自动破坏性降级。
7. pending/stable/observation marker使用 fsync + atomic rename并绑定 package hash/version。

#### 关闭标准

从上一稳定安装包完成真实升级；损坏包、错签名、启动失败、Migration失败和Health失败均能保留数据并恢复旧应用版本。

---

### FIX-P1-04：WebView/Tauri Command 安全边界偏离固定七命令契约

**级别：P1 / 本地信任边界**

#### 现状与证据

- `lib.rs` 的 `invoke_handler` 暴露 18 个命令，包括多条 `auth_*`、`system_health` 和两个恢复内部命令。
- 设计只允许 WebView 调用七个自定义 Command：`rpc_request`、`workspace_select`、`readonly_file_select`、`external_open`、`diagnostics_export`、`updater_check`、`updater_install`。
- Frontend 仍直接调用 `auth_change_password` 等命令，没有统一走 owner router。
- `rpc_request` 没有窗口参数，也没有校验 `window_session_id` 和主窗口来源。
- Registry owner 全标 Sidecar，导致 owner router 不能可靠阻止 Rust-owned方法被错误转发。

#### 固定修复方案

1. WebView只暴露固定七命令；认证和 supervisor 方法作为 `rpc_request` 中的 Rust owner handler。
2. App启动时为主窗口建立 window session；每个命令从 Tauri invocation上下文校验窗口 label/session。
3. Capability JSON 显式列出固定 allowlist，禁止 shell/fs/http/process/clipboard-write/updater plugin直通。
4. `rpc_request` 使用生成 owner router，Rust 方法本地执行，Sidecar 方法转发，supervisor 方法仅内部调用。
5. `updater_verify_launch/restore_stable` 只能由 Rust启动/恢复状态机内部调用，不暴露给 WebView。

#### 关闭标准

从 WebView 枚举或调用 Registry 外、非七命令、错误窗口和内部 supervisor 命令均被拒绝并写安全审计。

---

### FIX-P1-05：源码和对外文档仍包含明显迭代痕迹与错误完成声明

**级别：P1 / 第三方交付可执行性**

#### 现状与证据

- `runtime/process_supervisor.py` 直接写有“Rust 端尚未实现”“当前使用 Python”等迁移说明。
- `rpc_server.py`、`handler_registry.py`、Lifecycle 和同步脚本包含 `DEPRECATED`、`legacy`、`placeholder`、`stub mode`。
- `schema-gen-rust` 对本地引用明确返回 placeholder。
- `README.md` 同时声称 Rust/Backend 为 100% 覆盖，又写“所有模块阈值 80%”；实际 Backend为 62.89%。
- `docs/部署文档.md` 声称覆盖率固定 100%、READ_METHODS 已从 Registry 自动生成、单写者违规已清理，但当前对应门禁均失败或存在豁免。
- `docs/review报告/AI公司桌面应用-问题修复记录.md` 将 CUR-P0-04 标记已修复，与本次可复现结果冲突。

#### 固定修复方案

1. 先完成本报告的生产切换，随后删除旧模块、迁移注释、placeholder、stub 和临时兼容说明。
2. README、部署文档和用户手册只写当前可执行行为与实测命令，不写计划状态。
3. 覆盖率、测试数、支持平台和安全门禁由 CI artifact自动生成或引用，不手填易漂移数字。
4. 历史修复记录移入内部归档或改为客观 commit 索引，不作为当前完成状态来源。
5. 发布前执行 `rg` 门禁，禁止生产源码出现 `DEPRECATED/legacy/placeholder/stub mode/尚未实现/未迁移`，业务语义中的 SQL placeholder 除外。

#### 关闭标准

第三方只阅读当前设计、实施、README、部署和用户文档即可得到唯一实现方式；文档陈述与同一提交的门禁报告完全一致。

## 7. 推荐实施顺序

不得继续在 legacy bridge 上做局部补丁。按以下顺序一次性切换：

1. **冻结事实源**：修正 Registry owner，删除额外 ownership，修复生成器并让生成 crate进入编译。
2. **重建 Persistence Kernel**：删除旧 RPC bridge和双 Event/Outbox，形成唯一 WriteQueue→UnitOfWork。
3. **修复 Application Lifecycle**：实现 online 初始化、offline校验、真实 handshake-only和首次 health。
4. **实现同连接 Duplex RPC**：统一 frame classifier、writer queue、pending/stream和 Reverse Dispatcher。
5. **接通 Credential/HTTP Broker**：完成 event stream和真实 API Model E2E。
6. **实现 Rust CLI Runtime**：Process Supervisor、动态 Seatbelt、Egress accept loop、三种 CLI。
7. **重建 Review/Completion**：强类型 Event/Outbox、内部 CommandBus、三级闭环。
8. **修复 Health 与 Updater**：统一合成 health并切换 Tauri Updater。
9. **收紧 WebView 边界**：固定七命令和 window session。
10. **恢复全量门禁**：修复所有 lint/type/test/coverage，建立七个 workflow和四条核心 E2E。
11. **清理迭代痕迹**：删除旧实现、临时兼容、错误修复记录和失真数字。

前一阶段的关闭测试未通过时，不得进入下一阶段并宣称其依赖已完成。

## 8. 总体验收清单

- [ ] 全新 online Profile可初始化，offline空 Profile拒绝。
- [ ] Registry是 owner/kind/schema/ttl/error的唯一事实源。
- [ ] Rust/Python/TypeScript生成代码被生产编译和消费。
- [ ] 同一认证 UDS支持双向 request、notification、stream和取消。
- [ ] API Model真实链路不向 Sidecar暴露 secret。
- [ ] 所有 SQLite业务写只经一个 WriteQueue/UnitOfWork。
- [ ] 生产代码不再导入根级旧 `rpc_server.py`，文件已删除。
- [ ] Rust独占三种 CLI进程、Seatbelt、管道和Egress。
- [ ] Run成功不能绕过 Review/Verification直接完成任务。
- [ ] Review/返工/三级 Completion真实 E2E通过。
- [ ] 登录只在首次合成 health=healthy 后返回 opened。
- [ ] Tauri Updater真实升级和恢复演练通过。
- [ ] WebView只有固定七命令且校验主窗口 session。
- [ ] Contracts、Desktop、Sidecar、Backend、E2E、Security、Release七个 workflow全绿。
- [ ] TypeScript/Python/Rust手写代码目标覆盖指标均为100%。
- [ ] 无 skip、xfail、缺工具回退、空测试集或静态检查豁免。
- [ ] README、部署、用户文档与代码同提交一致。
- [ ] 生产源码和对外文档无 legacy、placeholder、未迁移或错误完成声明。

## 9. 最终判定

截至 Git `e9cb054`：

- 之前的问题**没有全部修复**；
- 五项核心架构**均未完成**；
- 当前至少存在 **6 个 P0** 和 **5 个 P1** 待实现、待修复问题；
- 第三方“18 项全部关闭”和“五项重构完成”的结论缺少生产链路与全量门禁证据，不能采纳；
- 当前版本不满足对外发布、交付第三方继续功能开发或作为完整目标架构基线的条件。

应以本报告第 7 节顺序完成一次性目标架构切换，并在同一干净提交上重新执行全量复核。
