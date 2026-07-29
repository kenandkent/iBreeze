# AI 公司桌面应用五项核心架构重构复核与待实现问题

## 1. 报告信息

| 项目 | 内容 |
|---|---|
| 复核基线 | Git `bb7bf4c`，分支 `main`，与 `origin/main` 一致 |
| 复核日期 | 2026-07-29 |
| 工作区状态 | 复核开始及测试验证完成后（生成本报告前）均无未提交变更 |
| 复核范围 | 五项核心架构、上一轮 18 项问题、生产调用链、Contracts、Rust Core、Python Sidecar、Desktop、Admin、Backend、Updater、部署、测试与 CI |
| 规范依据 | `docs/设计方案/AI公司桌面应用设计方案.md` |
| 核心重构依据 | `docs/设计方案/iBreeze五项核心架构重构设计方案.md` |
| 实施依据 | `docs/superpowers/plans/2026-07-28-ibreeze-five-core-architecture-rewrite.md` |
| 复核结论 | **不能确认问题全部修复；五项核心架构均未达到关闭标准，当前版本不可作为符合目标架构的可发布版本** |

## 2. 结论摘要

第三方给出的“P0 8/8、P1 8/8、P2 2/2 全部关闭”和“五项核心架构重构完成”结论不成立。当前实现确实增加了大量 Schema、Rust Broker 组件、Persistence 类、Review Handler 和测试，但多数关键组件没有接入同一条生产调用链，仍属于“孤立实现或局部实现”。

当前存在四个直接阻断应用正常闭环的事实：

1. Sidecar 主入口把 `${profile_root}` 目录直接作为 SQLite 文件路径打开，同时没有创建 `RPCServer`、没有监听 UDS，也没有保持服务循环；桌面端最多等待 10 秒后会得到“Sidecar did not create its UDS endpoint”。
2. Rust 的 `SidecarClient` 仍是串行的“写一个请求、读一个响应”客户端，无法接收 Sidecar 主动发起的反向 RPC；Sidecar 又尝试连接自己的 UDS 服务端口，Rust 注册的 `reverse_table` 在生产路径中从未调用。
3. 旧 `LocalDB`、旧巨型 `rpc_server.py`、直接 `BEGIN IMMEDIATE`、直接业务状态 SQL 和新 Persistence/UoW/Command Handler 同时存在；目标架构要求的单写者和单一事务入口没有形成。
4. `verify-all.sh` 通过降低阈值、允许工具缺失、跳过 Rust coverage 和完全跳过 E2E 获得绿灯；当前绿灯不能作为重构完成证据。

按上一轮 18 项问题的原关闭标准复核：

| 状态 | 数量 | 说明 |
|---|---:|---|
| 已关闭 | 2 | `NEW-P0-01`、`NEW-P1-02` |
| 部分修复 | 6 | 有有效实现，但生产闭环或原验收条件未满足 |
| 未关闭 | 10 | 核心路径仍缺失、旁路仍存在或门禁已经回退 |

“部分修复”不能计入关闭。五项核心架构的判定如下：

| 五项核心架构 | 判定 | 已完成部分 | 未完成的决定性条件 |
|---|---|---|---|
| Credential/HTTP Broker、Reverse RPC、Egress | **未完成** | Keychain Store、HTTP/DNS/Lease/CONNECT 类型和局部测试存在 | Sidecar 无可用 RPC；无双工 UDS；Reverse handler 未进入读循环；Egress 无生产 accept loop；真实 API Model E2E 缺失 |
| Canonical RPC、Domain Event 与生成契约 | **部分完成，不能关闭** | 295 个 Schema lint 通过；120 个方法；45 个 Domain Event | Sidecar 生成物不提交也不校验；运行时仍使用手工表和旧 RPC；生成 Dispatcher 未接入；四端仍有平行契约副本 |
| Persistence Kernel 与 Application Lifecycle | **未完成** | `001_initial.sql`、WriteQueue、UoW、ReadPool、WorkerSupervisor 存在 | 主入口数据库路径错误；旧 LocalDB/RPC 仍是业务实现；大量直接写；身份校验/RPC 阶段为 placeholder；Health 计算存在同步阻塞错误 |
| CLI Runtime、Workspace、Seatbelt、Egress、取消/恢复 | **未完成** | Python 本地 ProcessSupervisor 有基础进程组/Seatbelt 代码 | Rust `runtime/` 目标模块不存在；Python 仍直接 spawn；Egress 未接入；无三种真实 CLI、Seatbelt、取消/恢复 E2E |
| Review、返工与三级 Completion | **未完成** | 新 Aggregate、Handler、Gate 和单元测试存在 | `review.submit` 仍路由到旧 Service；三级 Completion Handler 无生产入口；Run 和旧 Service 仍直接改任务状态；SQLite 中仍有 `FOR UPDATE` |

## 3. 实际验证结果

### 3.1 全量门禁

执行：

```bash
bash scripts/verify-all.sh --scope all
```

脚本退出码为 0，但实际结果不能判定为发布通过：

| 域 | 实际结果 | 目标架构要求 | 判定 |
|---|---:|---:|---|
| Contracts | 295 个 Schema lint 通过 | 单一事实源、四端生成、运行时校验、零漂移 | 仅语法与部分生成检查通过 |
| Sidecar | 1342 passed、1 skipped、4 xfailed、2197 warnings；覆盖率 75.61% | 100%，无 skip/xfail，核心路径 E2E | 不通过 |
| Backend | 204 passed；覆盖率 62.89% | 100% | 不通过 |
| Desktop Web | 39 passed；覆盖率约 10.9% | 100% | 不通过 |
| Admin Web | 16 passed；覆盖率约 2.6% | 100% | 不通过 |
| Rust | fmt、clippy、测试通过 | cargo-nextest + cargo-llvm-cov 100% | 本机缺工具时回退并跳过 coverage，不能判定 |
| E2E | 固定输出 `skipped: no e2e test suite configured` | 至少四条真实 E2E | 不通过 |
| CI | 只有 `.github/workflows/ci.yml` | 七个固定 workflow、macOS 14/26 安全 runner | 不通过 |

脚本当前的放宽项：

- `cargo-nextest` 从必需工具降为可选，缺失时回退 `cargo test`。
- `cargo-llvm-cov` 从必需工具降为可选，缺失时完全跳过 Rust coverage。
- Sidecar 和 Backend 在命令行强制使用 `--cov-fail-under=60`，分别覆盖了项目中 77% 和 62% 的现有阈值，更不符合设计的 100%。
- Desktop/Admin 没有 coverage threshold。
- `run_e2e` 不运行任何测试。
- `run_drift` 在找不到测试目录时只打印提示并继续。

### 3.2 针对性门禁测试

执行：

```bash
uv run --directory sidecar pytest \
  ../tests/contract/test_ci_policy.py \
  ../tests/scripts/test_verify_all.py -q
```

结果为 **3 failed、3 passed**：

1. Git 中只有 1 个 workflow，测试要求的 workflow 不存在。
2. `contracts.yml`、`desktop.yml`、`sidecar.yml`、`backend.yml`、`e2e.yml`、`security.yml`、`release.yml` 全部缺失。
3. `verify-all.sh` 的顺序门禁测试失败。

另有规范与测试自身的不一致：核心重构计划要求“七个 workflow”，`test_ci_policy.py` 却把 `ci.yml` 加七个专项 workflow 固定为至少八个。修复时应以设计明确的七个专项 workflow 为准，删除笼统 `ci.yml`，而不是把错误断言继续保留。

### 3.3 其他验证

| 检查 | 结果 |
|---|---|
| Desktop build | 通过；`vendor-antd` 约 1.0 MiB |
| Admin build | 通过；`vendor-antd` 约 1.0 MiB；配置把警告阈值提高到 1100 KiB |
| 生产 Compose 合并 | 配置可解析，但仍发布 PostgreSQL、MinIO、Backend、Admin、Nginx 共 6 个宿主端口 |
| npm audit：Desktop | 15 个漏洞：3 moderate、10 high、2 critical |
| npm audit：Admin | 17 个漏洞：3 moderate、12 high、2 critical |
| E2E 目录 | `tests/e2e` 为空 |
| 生成契约 | 120 个 RPC 方法、241 个方法 Schema、45 个 Domain Event；未发现无约束空对象 Schema |

## 4. 上一轮 18 项问题逐项复核

| 问题编号 | 当前状态 | 复核结论 | 本报告对应问题 |
|---|---|---|---|
| CUR-P0-01 | **未关闭** | Broker 组件存在，但 Reverse RPC 和 Egress 未进入生产调用链，API Model 无法真实执行 | FIX-P0-02 |
| CUR-P0-02 | **部分修复** | Schema 数量和字段已补齐；Sidecar 生成、运行时分派和零手工副本未完成 | FIX-P0-03 |
| CUR-P0-03 | **部分修复** | Registry 外的部分 Desktop 方法已清理；Desktop 仍依赖手工 `READ_OPERATIONS`，没有全量切换生成 Client | FIX-P0-03 |
| CUR-P0-04 | **未关闭** | 全量脚本通过是阈值回退、工具可选和 E2E 跳过产生的假绿灯 | FIX-P0-05 |
| CUR-P0-05 | **未关闭** | 新 Persistence 类存在，但旧 DB/RPC/直接写路径未删除，且 Sidecar 启动路径已断裂 | FIX-P0-01、FIX-P0-04 |
| CUR-P0-06 | **部分修复** | Refresh envelope 已修；device id 只在 localStorage；生成 OpenAPI 未消费；集成测试不在总门禁 | FIX-P1-04 |
| NEW-P0-01 | **已关闭** | 当前 Sidecar Ruff/Mypy 通过 | 无 |
| NEW-P0-02 | **未关闭** | Policy 测试现在能暴露缺失，但测试本身失败，七个固定 workflow 仍未实现 | FIX-P0-05 |
| CUR-P1-01 | **未关闭** | Rust CLI Process Supervisor/Seatbelt/Egress 生产实现不存在，Python 仍直接 spawn | FIX-P1-01 |
| CUR-P1-02 | **未关闭** | 新 Handler 未接入 RPC/Runtime，旧路径仍可直接改变任务状态 | FIX-P1-03 |
| CUR-P1-03 | **部分修复** | backup id 和部分解包校验已修；原子切换、真实健康观察、自动回滚和恶意包限制未完成 | FIX-P1-05 |
| CUR-P1-04 | **部分修复** | MinIO 9001 映射已修；生产端口隔离、Secret 文件和恢复演练未完成 | FIX-P1-06 |
| CUR-P1-05 | **未关闭** | 根级 Policy 测试不在主测试集合；E2E 被删除；总门禁继续容许 skip/xfail/fallback | FIX-P0-05、FIX-P1-08 |
| CUR-P1-06 | **未关闭** | Rust Health 仅看 Sidecar；Sidecar Health 自身计算错误且 Lifecycle 阶段含 placeholder | FIX-P1-02 |
| NEW-P1-01 | **部分修复** | `data.data` 解析已修；缺前端并发 Refresh 测试和真实 Backend E2E | FIX-P1-04 |
| NEW-P1-02 | **已关闭** | 两个 `tsconfig.tsbuildinfo` 已不再跟踪，重复 build 后工作区保持干净 | 无 |
| CUR-P2-01 | **未关闭** | 两端 antd chunk 仍约 1 MiB，Admin 仅提高警告阈值 | FIX-P2-01 |
| CUR-P2-02 | **未关闭** | Rust、Sidecar、Desktop 和 Admin 均仍有手工契约副本 | FIX-P0-03 |

## 5. 待实现、待修复问题

### FIX-P0-01：Sidecar 主入口无法创建可用数据库或 RPC 服务

**级别：P0 / 发布阻断**

**对应：CUR-P0-05；新发现的生产断链**

#### 现状证据

- `sidecar/ibreeze/main.py:29-40` 只构造 `SidecarApplication` 并调用 `await app.start()`。
- `SidecarApplication.start()` 只启动 Lifecycle，既不创建 `RPCServer`，也不等待 `serve_forever()`。
- `ApplicationLifecycle` 接收的是 `profile_root`，随后把该目录直接传给 `aiosqlite.connect()`；设计要求数据库路径为 `${profile_root}/profile.db`。
- 即使把路径改成文件，`verify_sqlite_capabilities()` 仍执行不存在的 `SELECT json1()`；当前锁定环境实测返回 `OperationalError: no such function: json1`，正确能力探针应使用 `json_valid/json`。
- Migration ledger 使用无 `IF NOT EXISTS` 的 `CREATE TABLE schema_migrations`，第二次打开已经初始化的 Profile 会失败。
- `backend_origin/app_user_id/masked_identifier/device_id/profile_mode/startup_token` 传入 `SidecarApplication` 后均被忽略，`local_profile` 不会创建或校验。
- Lifecycle 的 `IDENTITY_VERIFIED` 和 `RPC_DISPATCHER_ENABLED` 只是修改枚举值的 placeholder。
- 生产代码中 `RPCServer(...)` 只在测试出现；主入口不会创建 `${socket_path}`。
- Rust `SidecarSupervisor.wait_for_socket()` 在 100 次、每次 100ms 后失败，因此正常桌面 Profile 打开无法完成。

#### 根因

重构时把旧 `LocalDB + RPCServer.serve_forever()` 主入口替换为新 `SidecarApplication`，但没有把数据库文件解析、Profile 身份初始化、RPC Server 和进程存活职责迁入新 Application Lifecycle。

#### 影响

- 在线和离线 Profile 均无法正常打开。
- Rust/Sidecar handshake、业务 RPC、Health、Reverse RPC 全部不可用。
- 所有下层功能测试只是直接实例化模块，不能证明桌面真实调用链可用。

#### 固定修复方案

1. `SidecarApplication.__init__` 必须显式接收并保存所有启动字段，禁止 `**kwargs` 吞掉必填参数。
2. 固定路径：
   - `profile_root`：Rust 参数传入的 Profile 目录；
   - `database_path = profile_root / "profile.db"`；
   - `socket_path`：Rust 创建的 `${runtime_root}/{launch_id}/sidecar.sock`。
3. Lifecycle 启动顺序固定为：
   - 获取 `${profile_root}/profile.db.lock`；
   - 以 handshake-only 模式绑定 UDS；
   - 打开 `${profile_root}/profile.db` 并执行 `001_initial.sql`；
   - 在线首次打开时插入 `local_profile`，离线首次打开必须返回 `PROFILE_NOT_FOUND`；
   - 后续打开逐字段验证 backend origin、app user、masked identifier、device、schema epoch；
   - 打开唯一 writer、8 个 reader、容量 32 的 WriteQueue；
   - 注册全部生成 Query/Command Handler；
   - 启动 WorkerSupervisor；
   - 在全部就绪后完成 handshake。
   SQLite 能力探针固定执行 `SELECT sqlite_version()`、`SELECT json_valid('{}')` 和 FTS5 临时表正反测试；版本必须满足文档锁定范围。`schema_migrations` ledger 必须幂等创建，并对已应用 migration 的 filename/hash/status 做一致性校验。
4. 把当前根级 `rpc_server.py` 的 UDS 监听能力重写到 `sidecar/ibreeze/rpc/server.py`，由 Application 持有；不得把旧 `RPCServer` 注入新 Lifecycle。
5. `SidecarApplication.run()` 使用 `asyncio.TaskGroup` 同时持有 RPC accept loop、worker supervisor 和 shutdown signal；只有 `system.shutdown`、Rust 断线或不可恢复错误可以退出。
6. 启动任一步失败时按逆序关闭已创建资源、删除未发布的 socket、释放锁并返回稳定错误；不得把 phase 设置为 ready 后再异步失败。
7. `main._run()` 必须使用 `try/finally` 调用 `app.stop()`，进程退出前完成 WriteQueue drain、worker stop、WAL checkpoint 和锁释放。

#### 必须新增的测试

- 真进程测试：Rust Supervisor 启动真实 Sidecar，10 秒内 socket 存在且 handshake 成功。
- 空 Profile 在线初始化、空 Profile 离线拒绝、身份字段不一致、schema epoch 不支持。
- Migration 失败、WriteQueue 启动失败、Worker 启动失败时不得返回 ready。
- `system.shutdown` 后 socket、锁、writer、reader 和 worker 均释放。
- Sidecar 意外退出后 Rust 能检测并按重启阈值处理。

#### 关闭标准

使用打包后的真实 Sidecar 二进制完成 `open profile → handshake → system.health → company.list → system.shutdown`；测试不得直接实例化 `RPCServer` 或使用 fake Sidecar。

---

### FIX-P0-02：Duplex UDS、Credential HTTP Broker 与 CONNECT Egress 未形成生产闭环

**级别：P0 / 发布阻断**

**对应：CUR-P0-01、五项架构第 1 项**

#### 现状证据

- `apps/desktop-core/src/rpc/sidecar.rs:140-200` 在一个 `Mutex<UnixStream>` 内严格执行 write→read，只能处理 Rust 发起的请求及其紧邻响应。
- Rust 注册的 `AppState.reverse_table` 没有传入任何生产读循环；`ipc::handle_frame()` 除单元测试外没有调用者。
- `sidecar/ibreeze/runtime/transport.py:79-81` 使用 `asyncio.open_unix_connection(socket_path)` 新建连接。该 socket 按设计由 Sidecar 自己监听，因此该代码会连接 Sidecar 自己，不会连接 Rust Trusted Host。
- `credential.probe` 仍固定返回“profile_directory_id not yet wired”错误。
- Rust `EgressBroker` 和 `ConnectHandler` 没有在 `AppState` 构造、没有 accept loop、没有绑定 CLI Run 生命周期。
- `ConnectHandler` 用目标端口 443 调用 `validate_token_by_port()`，而 Lease 保存的是本地随机监听端口；即使手动调用也无法正确关联 Lease。
- 没有 API Model 真实 UDS→Keychain→Provider→Tool Call E2E，也没有三种 CLI 的 CONNECT E2E。

#### 根因

Rust/Python 两边分别实现了 Multiplexer、Dispatcher 和 Reverse Client，但仍保留旧串行 SidecarClient；新协议组件没有替换连接所有权。Egress 只实现数据结构和 handler，没有实现受监督的网络服务生命周期。

#### 固定修复方案

1. 每个 Profile 只允许一条已认证 UDS 连接，禁止 Sidecar 为 Reverse RPC 再连接自己的监听地址。
2. Rust 连接成功后立即 `UnixStream::into_split()`：
   - 单一 reader task 读取所有帧；
   - 单一 writer task 消费容量固定的发送队列；
   - pending map 按 `rust:{uuid}` / `sidecar:{uuid}` 区分方向；
   - reader 根据帧类型分发 response、正向 request、反向 request、notification 和 stream event。
3. Rust reader 收到 `sidecar:*` request 时必须调用 `AppState.reverse_table.dispatch()`，再通过同一 writer 返回同 id 的 response。
4. Sidecar 的 `IpcSession` 由 Server accept loop 创建；Runtime 只能取得当前 session 的 `call/notify` 接口，删除 `runtime/transport.py` 自建 `UdsConnection`。
5. generation、pending 256、stream 64、16MiB frame、deadline、cancel 和断线清理必须由同一个 Multiplexer 实现；删除 Rust/Python 平行且未使用的实现。
6. `credential.probe` 请求 Schema 必须包含 `profile_directory_id/credential_ref/provider_release_id/model_binding_id/deadline_at`，Rust 以 profile 绑定读取 Keychain。
7. `EgressBroker` 进入 `AppState`，每个 Run 创建一条 Lease 和一个真实 accept loop；accept loop 必须持有本地监听端口，`ConnectHandler` 直接接收已解析的 Lease，不得用目标端口查 Lease。
8. CONNECT 只允许 443；验证 Proxy-Authorization、Run、Lease、域名规范化、解析后 IP、DNS rebinding 和并发/速率限制；取消/超时/进程退出立即关闭 listener 和所有 tunnel 并 zeroize token。
9. HTTP Broker 和 CONNECT Egress 共用 CredentialStore、DNS Policy、审计和健康探针，但凭据 Lease 与网络 Lease 分开管理。
10. 删除 `rpc/reverse.rs` 中的手工 allowlist，改为从 `reverse-methods.v1.json` 生成 Dispatcher 和方法元数据。

#### 必须新增的测试

- 同一 UDS 上 Rust 与 Sidecar 同时发起请求，响应乱序仍正确关联。
- 256 pending、64 stream、oversize、deadline、断线、generation 切换和 backpressure。
- API Model 真实 TLS fixture：Sidecar 只传 `credential_ref`，Rust 注入 Keychain secret，完成流式文本、Tool Call、取消。
- Sidecar 内存/日志/SQLite/API payload 对 canary API Key 零命中。
- CONNECT 的无 Token、错 Token、错 Run、非 443、域名不在 allowlist、私网/loopback、DNS rebinding 均失败。
- Run cancel 后 listener、tunnel、credential lease、token 和子进程全部消失。

#### 关闭标准

真实桌面进程完成 API Model 工具任务和三种 CLI 网络任务；测试必须经过同一条生产 UDS 与 Broker 路径，禁止直接调用 Handler 代替网络闭环。

---

### FIX-P0-03：Canonical Contract 只完成文件生成，运行时仍有手工契约和双轨分派

**级别：P0 / 发布阻断**

**对应：CUR-P0-02、CUR-P0-03、CUR-P2-02、五项架构第 2 项**

#### 已验证的有效成果

- Contract lint 报告 295 个 Schema 有效。
- Registry 有 120 个 RPC 方法。
- Domain Event Registry 有 45 个事件，45 个 payload Schema 均存在。
- 241 个方法 request/response Schema 中没有未约束的空对象。
- Desktop TypeScript、Rust 和 Admin OpenAPI 的已提交生成目录当前 drift 检查通过。

#### 未完成证据

- `scripts/check-contract-drift.sh:63-67` 明确跳过 Sidecar RPC、Domain Event 和 Skill 生成物。
- `sidecar/ibreeze/generated` 不存在且被 gitignore，干净 clone 无可审查 Python 生成基线。
- 生产仍使用根级 `rpc_server.py` 的手工 `READ_METHODS` 和 `self.methods`。
- Rust `commands.rs` 仍有手工 `sidecar_method_kind`；Reverse RPC 仍有手工 allowlist。
- Desktop `shared/rpcClient.ts` 仍有手工 `READ_OPERATIONS`。
- Admin 的 `generated/openapi/api.ts` 没有被业务代码 import，Login/API Client 继续使用手写 DTO 和 `fetch`。
- Sidecar `rpc/dispatcher.py` 没有注册生产 Handler，也没有进入 Server 调用链。

#### 根因

生成器被当作类型文件生成工具，而不是生产路由、校验和 Client 的唯一来源；为使旧代码继续运行，四端保留了手工表。

#### 固定修复方案

1. `registry.v1.json` 必须生成：
   - Rust `MethodMeta`、正/反向 Dispatcher、request/response 类型；
   - Python Pydantic request/response、MethodMeta、Dispatcher 注册骨架；
   - Desktop `GeneratedRpcClient` 和 Query/Command 方法；
   - Admin OpenAPI Client、envelope 和 Problem Details 类型。
2. Sidecar 生成物必须提交并纳入 drift，或在 CI 中生成到项目内临时工作树并与确定性 manifest/hash 比较；禁止“gitignore 后不比较”。
3. 删除 `READ_METHODS`、`READ_OPERATIONS`、`sidecar_method_kind`、Reverse allowlist 和手工 `self.methods`。读写分类、owner、scope、幂等 TTL 和 allowed errors 全部读取生成元数据。
4. 生成 Dispatcher 只负责校验和路由，业务 Handler 通过显式依赖注入注册；不得在生成文件中写业务 SQL。
5. 运行时对 request、response、error 和 Domain Event payload 都执行生成模型校验；未知字段按 Schema 规则拒绝。
6. Desktop 页面只可 import 共享的 `GeneratedRpcClient`；Admin 只可 import 生成 OpenAPI Client。
7. 增加静态扫描：应用目录出现方法名集合、手工 DTO 或直接 `invoke("rpc_request")` 时失败。

#### 必须新增的测试

- 在 fixture Registry 新增一个读方法和一个写方法，四端生成物、分类、Dispatcher 和 Client 同时变化。
- 删除 Registry 方法后，四端构建对旧调用同时失败。
- 每个公开方法至少一个合法 request/response fixture；每个错误码至少一个公开/内部 redaction fixture。
- 生产 RPC Server 启动后，注册方法集合与 Registry 精确相等。
- Python、Rust、Desktop、Admin 生成目录逐文件 drift 为 0。

#### 关闭标准

静态扫描确认没有平行方法表和手工跨边界 DTO；全量应用只通过生成 Client/Dispatcher 通信。

---

### FIX-P0-04：Persistence Kernel、WriteQueue 和 Unit of Work 仍是新旧双轨

**级别：P0 / 数据一致性阻断**

**对应：CUR-P0-05、五项架构第 3 项**

#### 现状证据

- 根级 `local_db.py` 仍存在，并声明为“向后兼容薄包装”；目标架构明确要求删除。
- 根级 `rpc_server.py` 的构造参数仍是 `LocalDB`。
- 排除测试后，Sidecar 生产源码仍出现 47 处 `BEGIN IMMEDIATE`；Company、Employee、Profile、Task、Review、Approval、Knowledge、Artifact、Conversation、Runtime 等模块均存在直接事务。
- Runtime 和 Task Service 仍直接 `UPDATE employee_tasks/department_tasks/company_tasks`。
- 新 `WriteQueue/UnitOfWork` 只覆盖部分新 Handler，不能约束旧 Service 和 Worker。
- `_NestedTransactionConnection` 通过忽略嵌套 `BEGIN/ROLLBACK/commit` 让旧 Service 塞进新事务，属于兼容层，不是单一事务模型。
- Review Repository 和 Rework Handler 仍使用 SQLite 不支持的 `FOR UPDATE`。
- `001_initial.sql` 是新 DDL，但大量旧 Service 的表名、状态和事务假设继续存在。

#### 根因

实施采用了“在旧系统旁新增 Persistence Kernel”而非设计要求的“一次性切换并删除旧路径”；为了复用旧 Service 又增加了事务适配器。

#### 固定修复方案

1. 先以 `001_initial.sql` 为唯一数据库事实源生成 Schema inventory，逐个登记所有 Repository 和 Command 的表/索引/触发器依赖。
2. 删除 `local_db.py`、根级 `rpc_server.py`、`_NestedTransactionConnection` 和所有 Service 自管事务。
3. Application Lifecycle 只创建：
   - 1 个 bootstrap connection，Migration 后关闭；
   - 1 个 writer；
   - 1 个容量 32 的 WriteQueue；
   - 8 个只读连接。
4. 所有业务写入口统一为 `CommandBus.execute(context, request)`：
   - 从生成 MethodMeta 强制检查 idempotency key；
   - WriteQueue 排队；
   - UoW 执行 `BEGIN IMMEDIATE`；
   - 读取并校验 expected version；
   - Repository 写事实；
   - 同事务写 Domain Event、Outbox、Audit 和 Idempotency response；
   - commit 后返回。
5. Worker 不得拿 writer；Worker 只能向 CommandBus 提交内部 Command。Backup barrier 是唯一可暂停新写并等待队列排空的控制面。
6. Repository 禁止 `commit/rollback/BEGIN`，禁止状态机判断，禁止 `FOR UPDATE`；SQLite 锁由 UoW 的 `BEGIN IMMEDIATE` 和 version compare 提供。
7. QueryBus 只使用 ReadPool；读事务结束时强制 rollback 清理 snapshot。
8. 增加 Semgrep/Ruff 自定义规则：
   - 仅 `unit_of_work.py/write_queue.py/migrator.py` 可出现事务控制；
   - 业务模块禁止 `.commit()`、`.rollback()`、`BEGIN IMMEDIATE`；
   - Worker 禁止 import writer connection。

#### 必须新增的测试

- 32 容量背压、FIFO、公平性、取消前/取消后语义。
- 同一 expected version 并发写只有一个成功。
- 事务中任一 Event/Outbox/Audit 写失败时业务事实回滚。
- Idempotency 同 hash 返回原 response，不同 hash 返回冲突。
- Worker crash/retry 不产生重复状态转换。
- Backup barrier 前后无半事务、WAL 可恢复。
- 静态扫描旧 DB/RPC/事务旁路为 0。

#### 关闭标准

生产代码只有一个 writer 获取点和一个业务事务入口；删除兼容层后全部单元、故障注入和并发测试通过。

---

### FIX-P0-05：验证与 CI 门禁被降级，当前绿灯属于假通过

**级别：P0 / 交付可信度阻断**

**对应：CUR-P0-04、NEW-P0-02、CUR-P1-05**

#### 现状证据

- Rust coverage 工具缺失时只警告并跳过。
- Sidecar/Backend 阈值被命令行降到 60%。
- Desktop/Admin 没有阈值。
- `tests/e2e` 为空，`run_e2e` 固定 skip。
- Sidecar 全量存在 1 skip、4 xfail 和 2197 warnings。
- 根级 CI Policy/verify-all 测试未进入 `run_sidecar`，针对性执行时失败。
- 只有一个 Ubuntu matrix workflow；action 使用 `@v4/@v5/@stable`，未锁定 commit SHA。
- 没有 macOS 14/26 Apple Silicon 安全 runner、release 依赖门禁和签名/Updater 验证。
- npm audit 显示两端均有 critical/high 漏洞，但门禁不失败。

#### 固定修复方案

1. 恢复七个固定 workflow：`contracts.yml`、`desktop.yml`、`sidecar.yml`、`backend.yml`、`e2e.yml`、`security.yml`、`release.yml`；删除笼统 `ci.yml`。
2. 修正 Policy 测试为“集合精确等于七个”，并验证 Git tracking、trigger、permissions、SHA pin、artifact retention、concurrency 和 runner 标签。
3. `verify-all.sh` 的 required tools 固定包含 `node/npm/uv/cargo/cargo-nextest/cargo-llvm-cov`；任何缺失立即失败，禁止 fallback。
4. 五个代码域的 statement/branch/function/line threshold 固定 100%；如确需排除生成物，只能使用版本控制中的 `coverage-exclusions.yml` 且逐项附理由。
5. Sidecar、Backend、根级测试统一使用锁定 `uv` 环境；根级 contract/integration/script 测试必须显式执行，找不到目录或收集 0 项必须失败。
6. skip/xfail/warning 设置固定预算 0；平台专用测试只能在对应 macOS workflow 执行，不能用 skip 代替。
7. 恢复 Playwright，至少实现 API Model、CLI Runtime、Review Rework、Updater/Rollback 四个生产路径 spec。
8. `security.yml` 在真实 Apple Silicon macOS 14 和 26 执行真实 CLI、Seatbelt、CONNECT、Keychain、Updater 和签名测试；runner 离线即失败。
9. `release.yml` 只在六个前置 workflow 对同一 SHA 成功后执行，并重新运行完整门禁。
10. 加入 Rust/Python/npm 依赖审计；critical/high 必须修复或由带到期日的签名豁免清单管理。

#### 关闭标准

干净 clone 在本地和七个 CI workflow 上连续两次通过；缺任一工具、测试文件、runner、Secret、coverage 或 artifact 都必须非零退出。

---

### FIX-P1-01：CLI Runtime 仍由 Python 直接 spawn，Rust Trusted Host 未接管

**级别：P1 / 核心功能未完成**

**对应：CUR-P1-01、五项架构第 4 项**

#### 现状证据

- 目标目录 `apps/desktop-core/src/runtime/` 不存在。
- `sidecar/ibreeze/runtime/process_supervisor.py` 的注释明确写明“当前：Sidecar 使用本地 asyncio.create_subprocess_exec（未迁移）”。
- 排除测试后仍有 4 个 `asyncio.create_subprocess_exec` 生产调用点，分布在 `runtime/cli.py`、`runtime/process_supervisor.py` 和 `workspace/git_ops.py`。
- Seatbelt、PGID、SIGTERM/SIGKILL 逻辑位于 Python，不在 Rust 信任边界。
- Rust Registry/Reverse 类型存在，但没有 `runtime.process.start/writeStdin/cancel/status` 的生产 Handler。
- 无 Codex CLI、Claude Code、OpenCode 锁定真实版本 E2E。

#### 固定修复方案

1. 按设计创建 Rust `runtime/{process_supervisor,process_registry,seatbelt,invocation,cancellation}.rs`。
2. Rust Reverse Dispatcher 实现生成的 `runtime.process.*` 方法；Sidecar 只发送结构化 Invocation，不传任意 shell 字符串。
3. 固定三种 Adapter 的 executable、版本范围、参数白名单、stdin 模式、事件解析器和 resume token 规则。
4. 每个 Run：
   - 解析并 realpath Workspace；
   - 创建 Egress Lease；
   - 生成不可复用的 Seatbelt profile；
   - 创建独立 process group；
   - 注入最小环境和 loopback proxy；
   - spawn 后发 `runtime.processRegistered`；
   - 输出按 sequence 回传；
   - 退出后发 `runtime.processExited`；
   - 释放 proxy、prompt、Seatbelt 和 process registry。
5. 取消固定为 SIGTERM→5 秒→SIGKILL 整个 PGID，随后扫描并确认无子孙进程。
6. 删除 Python 所有 spawn/exec、Seatbelt 和 PGID 代码；Python Adapter 只负责 Invocation 和协议事件规范化。

#### 关闭标准

三种锁定真实 CLI 分别完成 Workspace 写入、流输出、Tool Call、取消和 checkpoint/resume；Workspace 外写、直连公网、Keychain/SSH/GPG/浏览器凭据读取和 fork 逃逸全部失败。

---

### FIX-P1-02：Lifecycle Worker 与 Health 仍有 placeholder、空转和错误计算

**级别：P1 / 运维与自恢复不可信**

**对应：CUR-P1-06、CUR-P0-05**

#### 现状证据

- Lifecycle 的身份验证和 RPC Dispatcher 阶段是 placeholder。
- Knowledge/Reconciliation/Backup/EventCompaction Worker 的 `work()` 只有 `asyncio.sleep()`，没有业务处理。
- `_get_migration_version()` 在同步函数中对当前事件循环调用 `run_coroutine_threadsafe(...).result(timeout=2)`；在同一 loop 调用时会阻塞 loop 并超时，返回 0。
- `_get_loop_lag_ms()` 依赖非公开且通常不存在的 `loop._clock`，大多固定返回 0。
- QueueHealth 的 `runtime_ready/outbox_pending` 从不赋值。
- Rust `system_health` 只汇总 Sidecar 是否 running 和一次 RPC 是否成功，不包含 DB、Queue、Worker、UDS generation、Broker、Egress、磁盘、Backup/Outbox lag。

#### 固定修复方案

1. Health Snapshot 改为 async collector；Migration version、queue depth、outbox lag、disk free 以有界并发查询获取，禁止在 event loop 内同步等待同一 loop。
2. Event loop lag 由独立 heartbeat task 比较计划时间和实际时间计算。
3. 每个 Worker 实现真实单次 `poll_once()`；Supervisor 负责周期、jitter、重启和 5 分钟内 5 次熔断。
4. Worker Health 固定输出 state、heartbeat、last success、last error code、queue lag、restart count。
5. Rust 汇总 Sidecar Snapshot 与 UDS、generation、Credential Broker、Egress、Process Registry、Updater 状态；按设计阈值计算 healthy/degraded/failed。
6. UI 只展示带 `observed_at` 的实时汇总，不得把“RPC 可达”显示成整体 healthy。

#### 关闭标准

对 DB、Migration、WriteQueue、每个 Worker、UDS、Broker、Egress、磁盘、Outbox、Backup 逐项故障注入，状态和恢复时间符合设计；不存在 sleep-only Worker。

---

### FIX-P1-03：Review、返工和三级 Completion Handler 未接入生产入口

**级别：P1 / 业务正确性阻断**

**对应：CUR-P1-02、五项架构第 5 项**

#### 现状证据

- 新 `SubmitReviewHandler`、`AcceptEmployeeTaskHandler`、`CompleteDepartmentTaskHandler`、`CompleteCompanyTaskHandler` 存在并有单元测试。
- 生产 `rpc_server.py` 的 `review.submit` 仍调用旧 `review.service.submit_review_report()`。
- `review.rerun` 和 `review.resolveIssue` 仍直接 SQL 并 commit。
- Registry/RPC Server 没有三级 Completion Command 的公开或内部分派入口。
- `runtime/run_executor.py` 仍直接更新 Employee/Department/Company Task 状态。
- Review Repository/Rework Handler 仍有 SQLite 不支持的 `FOR UPDATE`。
- 旧 Service 与新 Aggregate 的状态、事件和幂等语义并存。

#### 固定修复方案

1. 只保留 `domain/review`、`application/review_handlers.py`、`application/rework_handlers.py`、`application/completion_handlers.py` 这一套实现。
2. 删除旧 `review/service.py` 和 Runtime/Task 中所有直接状态更新。
3. 生成 Dispatcher 注册：
   - Review：Start/Submit/StartIssueFix/Resolve/Verify/Close/Reject；
   - Completion：AcceptEmployeeTask/CompleteDepartmentTask/CompleteCompanyTask；
   - Rework：RequestDepartmentRework/RequestCompanyRework；
   - 内部：EvaluateDepartmentReadiness/EvaluateCompanyReadiness。
4. Run 结束只能写 `agent_runs` 和 Run event，然后通过 Outbox 请求评估，不得写业务 Task 终态。
5. 每个 Handler 在同一 UoW 写 Aggregate、Artifact version/stale、Domain Event、Outbox、Audit 和幂等 response。
6. Artifact 新版本必须使旧 assignment/report/issue evidence stale；旧证据不得满足 Completion Gate。
7. 删除 `FOR UPDATE`，使用 UoW `BEGIN IMMEDIATE + expected_version`。

#### 关闭标准

真实 RPC 路径完成“两名参与职员交叉 Review→blocker→返工→新 Artifact→复测→关闭→Employee accepted→Department completed→Company completed”；任一旧 hash、自审、活跃 Run、未关闭 blocker/high 或缺失报告均阻断。

---

### FIX-P1-04：Admin 认证仍未消费生成 OpenAPI，device id 和前端测试不满足关闭标准

**级别：P1**

**对应：CUR-P0-06、NEW-P1-01**

#### 已修部分

- Login 使用 `identifier/password/device_id`。
- Refresh 使用 HttpOnly Cookie，并按 `data.data.access_token/user` 解析。
- Access Token 只保存在 Zustand 内存。
- 401 Refresh 有基础 single-flight Promise。

#### 未完成证据

- device id 保存在 localStorage，清站点数据或换浏览器上下文即变化；目标方案要求稳定安装标识并与可信设备/session 绑定。
- `generated/openapi/api.ts` 没有业务 import。
- Login 和通用 API Client 继续手写 `fetch`、envelope、Problem Details 和 DTO。
- `tests/functional/test_admin_auth.py` 只测 Backend API，不测 Admin Web 的 Login/401 并发 Refresh；该根级测试也不在当前总门禁。
- Admin Web 只有 formatter 单元测试，覆盖率约 2.6%。

#### 固定修复方案

1. 若 Admin 是普通远程 Web，明确把 device id 定义为浏览器安装实例并使用不可脚本读取的服务端 Device Cookie；若必须与桌面 installation id 一致，则通过 Rust/Tauri 边界提供，禁止 localStorage 自称稳定设备。
2. 以生成 OpenAPI Client 替换 Login/API Client 的路径、DTO、envelope 和 Problem Details。
3. 保留一个 Auth Coordinator：access token 内存态、refresh single-flight、原请求只重试一次、失败统一 logout。
4. 写请求的 idempotency key 在首次请求生成并在 refresh 后重试时复用，不能重新生成。
5. 增加 Vitest + MSW 测试：登录、强制改密、20 个并发 401 只刷新一次、refresh 失败、logout、409、204。
6. 增加真实 Backend 浏览器 E2E，验证 Cookie 属性和 Web Storage/日志中无 Token。

#### 关闭标准

Admin Web 全量使用生成 Client；认证状态机覆盖率 100%；真实登录→并发 401→单次刷新→登出 E2E 通过。

---

### FIX-P1-05：Updater 仍缺安全解包、原子切换、真实 probation 和自动回滚

**级别：P1 / 安全与可恢复性阻断**

**对应：CUR-P1-03**

#### 已修部分

- `cache_current_install()` 已正确返回真实 `backup_id` 和 hash。
- 新增 staging 解包、路径遍历和解包后 symlink/hardlink 检查。
- 新增 pending/stable marker 和 30 秒观察文件。

#### 未完成证据

- `safe_extract()` 先递归删除当前 target，再 rename staging；删除与 rename 之间不是原子切换，失败会留下无安装目录状态。
- 预检使用 `tar -tzf` 普通列表，却用 `" -> "` 判断 symlink；普通列表不可靠提供 entry type/link target。
- 在系统 `tar` 已完成解包后才检查 symlink/hardlink，恶意 entry 已经产生过文件系统副作用。
- 没有 entry 数量、单文件大小、总展开大小、压缩比和磁盘余量限制。
- `verify_pending_update()` 只检查 Sidecar 文件存在、版本一致和经过 30 秒；没有调用真实 Sidecar handshake/DB/Worker/Broker Health。
- 观察期内函数返回 `true`，调用方可能把“仍在观察”误当成稳定。
- `restore_backup()` 直接在现有安装目录解包，不使用 `safe_extract()` 或原子替换。
- `apps/desktop-core/tests/updater.rs` 主要覆盖 Manifest，未覆盖上述解包、切换、probation 和 rollback。

#### 固定修复方案

1. 使用 Rust archive 库逐 entry 解析，解包前拒绝绝对路径、`..`、symlink、hardlink、device、fifo、socket 和未知类型。
2. 固定上限：entry 数、单文件 bytes、总展开 bytes、压缩比、路径长度和层级；解包前检查磁盘余量。
3. 解包到同一文件系统 staging，fsync 文件和目录，校验 bundle 结构、签名、hash、权限和可执行文件。
4. 原子切换固定为 `current → rollback-temp`、`staging → current` 的可恢复 rename 序列；任一步失败自动恢复，禁止先删除 current。
5. pending 状态明确为 `pending/observing/stable/rollback_required`，不能用 bool 混淆。
6. probation 连续 30 秒采集真实 Sidecar handshake、DB migration、WriteQueue、Worker、UDS、Broker Health；任一 failed 立即 rollback。
7. Restore 同样经过安全解包、结构校验和原子切换。
8. 应用崩溃或机器重启后根据 marker 恢复观察或回滚；marker 写入必须 fsync。

#### 关闭标准

正常升级、断电点故障注入、路径穿越、symlink/hardlink、压缩炸弹、磁盘不足、启动崩溃、Health 降级和 rollback 全部自动化通过；任何失败后至少有一个可启动版本。

---

### FIX-P1-06：生产 Compose 仍暴露内部端口，Secret 与备份恢复未实现

**级别：P1**

**对应：CUR-P1-04**

#### 现状证据

合并：

```bash
docker compose \
  -f deploy/docker-compose.yml \
  -f deploy/docker-compose.prod.yml config
```

仍发布：

- PostgreSQL `51543→5432`
- MinIO `51900→9000`
- MinIO Console `51901→9001`
- Backend `51080→51080`
- Admin `51421→80`
- Nginx `8080→80`

原因是 Compose 的序列合并语义没有用 `ports: []` 删除基础文件中的端口。另有：

- 密码和 S3 secret 通过环境变量和连接 URL 注入。
- 生产文件注释声称内部端口不暴露，与实际渲染结果冲突。
- 没有可执行的 PostgreSQL/MinIO 备份、校验、恢复和演练入口。
- 没有自动化验证“仅 Gateway 可从宿主访问”。

#### 固定修复方案

1. 不再用“开发文件 + 生产覆盖”删除端口；创建完整独立的 `docker-compose.dev.yml` 和 `docker-compose.prod.yml`。
2. Prod 只有 Gateway 发布宿主端口；Admin、Backend、PostgreSQL、MinIO 只使用内部 `expose`/network。
3. 数据库密码、JWT、MinIO credential 使用 Docker Secret/read-only file；应用支持 `*_FILE`，禁止 secret 出现在 environment 和 URL。
4. 固定 frontend/backend/data 三个 internal network，只有 Gateway 同时连接 frontend 和外部网络。
5. 提供 `backup`、`verify-backup`、`restore` profile/脚本，记录 manifest/hash/version，并在隔离环境执行恢复演练。
6. CI 对 Prod config 做机器断言：published port 集合精确等于 Gateway；环境中无 secret value；所有 image 使用 digest；资源、health、read-only 和 cap drop 完整。

#### 关闭标准

空库部署五服务健康；宿主只能访问 Gateway；Secret 不出现在 `docker compose config`、容器环境和日志；备份恢复后目录数据和对象 hash 一致。

---

### FIX-P1-07：前端依赖存在 Critical/High 漏洞，安全门禁未处理

**级别：P1 / 新发现**

#### 现状证据

当前 `npm audit`：

- Desktop：15 个漏洞，其中 2 critical、10 high。
- Admin：17 个漏洞，其中 2 critical、12 high。
- 直接依赖涉及 `vitest/@vitest/coverage-v8`、`react-router-dom`、`eslint`；传递依赖涉及 `vite`、`minimatch`、`brace-expansion`、`js-yaml` 等。

#### 影响

测试工具 critical 漏洞可能影响 CI/开发机；Router/Vite 等 high 漏洞可能影响开发服务或运行行为。当前门禁只打印 npm 安装摘要，不阻断发布。

#### 固定修复方案

1. 分别运行 production 和 all dependency audit，区分运行时与开发链风险。
2. 在兼容范围内升级 React Router、Vite、Vitest、Coverage、ESLint/OpenAPI 工具及 lockfile。
3. 不允许使用 `npm audit fix --force` 自动跨大版本；逐项升级并执行 lint/type/test/build/E2E。
4. CI 固定 `npm audit --audit-level=high`；无法立即升级的项必须进入版本控制豁免清单，包含 advisory、影响分析、补偿控制、owner 和不超过 30 天的到期日。

#### 关闭标准

production 依赖 high/critical 为 0；全部依赖 high/critical 为 0，或只剩未到期且经安全 Review 的明确豁免。

---

### FIX-P1-08：测试存在大量 warning、skip/xfail 和孤立测试，不能作为实现证明

**级别：P1**

**对应：CUR-P1-05**

#### 现状证据

- Sidecar 全量产生 2197 warnings，包含未 await AsyncMock 和事件循环关闭后的后台线程异常。
- 1 个 skip、4 个 xfail 仍被门禁接受。
- 新 `rpc` 模块在覆盖报告中接近或等于 0%，与其未进入生产调用链一致。
- 根级 `tests/functional/test_admin_auth.py`、CI Policy 和脚本测试不在 Sidecar 主测试命令中。
- Rust Broker 测试多为直接调用对象，没有真实 UDS、Keychain、Provider、CONNECT accept loop 的进程级测试。

#### 固定修复方案

1. 把测试集合按 contract/unit/integration/e2e/security/fault 明确登记，验证脚本逐集合执行并断言收集数大于 0。
2. warnings 使用 `-W error`；修复未 await mock、未关闭 DB/loop/thread/task，不得全局忽略。
3. skip/xfail 预算固定 0；平台测试移动到真实 macOS workflow。
4. 对每个“新架构模块”增加 production wiring 测试，不允许只直接实例化 Handler。
5. 覆盖率按文件输出，0% 的生产模块直接失败。

#### 关闭标准

全部测试集合被唯一入口执行，0 warning、0 skip、0 xfail、0 空集合；进程级测试覆盖真实入口和退出清理。

---

### FIX-P2-01：Desktop/Admin 初始包体仍超过 500 KiB

**级别：P2**

**对应：CUR-P2-01**

#### 现状证据

- Desktop `vendor-antd` 约 1.0 MiB，超过其 500 KiB 门禁。
- Admin `vendor-antd` 约 1.0 MiB。
- Admin 把 `chunkSizeWarningLimit` 提高到 1100 KiB，仅隐藏警告，不减少包体。

#### 固定修复方案

1. 页面全部改为 route-level lazy import。
2. 禁止整包聚合 import；验证 Ant Design 和 icons 的按需 tree shaking。
3. 对大型表格、图表、编辑器和管理页面按路由拆 chunk。
4. 生成 `rollup-plugin-visualizer` 报告，按模块消除重复依赖。
5. 门禁固定：任一初始 JS chunk 原始大小 `<500 KiB`，不得提高阈值规避。

#### 关闭标准

Desktop/Admin production build 均无 chunk warning，首屏和各路由功能 E2E 通过。

## 6. 实施顺序与依赖

修复必须按以下顺序执行，禁止并行保留旧生产路径：

| 阶段 | 必须完成 | 依赖 | 阶段验收 |
|---|---|---|---|
| A | FIX-P0-03 Contract 唯一事实源 | 无 | 四端生成与 drift，删除手工表 |
| B | FIX-P0-04 Persistence 单写者 | A | 旧 LocalDB/RPC/直接事务扫描为 0 |
| C | FIX-P0-01 Sidecar Lifecycle 与 Server | A、B | 真实进程 handshake/health/shutdown |
| D | FIX-P0-02 Duplex UDS/Broker/Egress | A、C | API Model 真实 Broker E2E |
| E | FIX-P1-01 CLI Runtime | D | 三 CLI + Seatbelt + CONNECT + cancel/resume |
| F | FIX-P1-03 Review/Completion | A、B、C | Review→返工→三级完成 |
| G | FIX-P1-02 Health、FIX-P1-05 Updater | C、D、E、F | 故障注入与自动 rollback |
| H | FIX-P1-04 Admin、FIX-P1-06 部署、FIX-P1-07 依赖、FIX-P2-01 包体 | A | Web E2E、Prod 部署与安全门禁 |
| I | FIX-P0-05、FIX-P1-08 最终门禁 | A–H | 七个 workflow 对同一 SHA 全绿两次 |

每阶段完成后必须删除被替代的旧实现再进入下一阶段。尤其禁止：

- 同时保留根级 `rpc_server.py` 和新 `rpc/server.py`；
- 同时保留 Service 自管事务和 CommandBus/UoW；
- 同时保留 Python ProcessSupervisor 和 Rust ProcessSupervisor；
- 同时保留旧 Review Service 和新 Review Aggregate；
- 用 Feature Flag 在发布构建中选择新旧路径。

## 7. 最终关闭矩阵

只有以下证据全部具备，才可再次声明“五项核心架构重构完成”：

| 架构域 | 必须提供的关闭证据 |
|---|---|
| Broker/RPC/Egress | 真实进程双向 UDS；API Model Tool Loop；Key canary 零泄露；CONNECT 安全负例；cancel 清理 |
| Contract | 120 方法与设计集合一致；全部 Schema/事件 fixture；四端生成物 drift 0；手工方法/DTO 扫描 0 |
| Persistence/Lifecycle | 空 Profile 启动；单 writer；全部写经 UoW；Worker 故障恢复；Backup barrier；旧路径扫描 0 |
| CLI Runtime | 三种锁定真实 CLI；Workspace 权限；Seatbelt；CONNECT；PGID cancel；checkpoint/resume |
| Review/Completion | 真实 RPC 完成 Review→blocker→返工→复测→三级完成；所有 blocker 负例 |
| Updater | 恶意 archive、断电点、probation、自动 rollback |
| Deployment | Prod 只暴露 Gateway；Secret file；空库部署；备份恢复 |
| 质量 | 五域 100% coverage；0 warning/skip/xfail；四条真实 E2E；七个固定 workflow；连续两次全绿 |

## 8. 最终判定

当前代码包含可复用的局部实现，但五项核心架构没有一项满足端到端关闭标准。`FIX-P0-01` 是最直接的发布阻断现象；实际实施仍应按第 6 节先完成 Contract 单轨和 Persistence 单轨，再把可启动的 Sidecar Server 接入该单轨，随后完成 Duplex UDS、CLI 与 Review。

在 `FIX-P0-01` 至 `FIX-P0-05` 全部关闭前，不应继续用当前 `verify-all.sh` 的退出码 0 对外宣称实现完成；在第 7 节全部证据齐备前，不应发布或把“18 项问题全部关闭”写入交付结论。
