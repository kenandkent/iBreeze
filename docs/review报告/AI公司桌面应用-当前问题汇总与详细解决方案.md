# AI 公司桌面应用当前问题汇总与详细解决方案

## 1. 报告信息

| 项目 | 内容 |
|---|---|
| 项目 | iBreeze AI 公司桌面应用 |
| 复核基线 | Git 提交 `f14425c` |
| 复核日期 | 2026-07-27 |
| 复核对象 | 设计方案、实施计划、桌面端、Rust Core、Sidecar、中心后台、管理后台、契约、测试、部署配置 |
| 设计方案 | `docs/设计方案/AI公司桌面应用设计方案.md` |
| 实施计划 | `docs/设计方案/AI公司桌面应用-实施计划.md` |
| 报告性质 | 当前代码与文档差距的整改输入，不是完成证明 |

本报告只记录在当前基线仍可复现或需要进一步裁决的问题。已经确认修复的事项单独列出，不把旧 Review 报告中的历史问题原样复制为当前问题。

## 2. 结论摘要

当前版本尚不能判定为“完全符合设计方案并可交付生产部署”。主要原因不是普通页面缺陷，而是若干基础闭环仍未建立：

1. API Model 的 Credential Broker、CONNECT Egress Proxy 和反向 RPC 仍是占位实现，API Model 职员无法完成真实 Agent Loop。
2. RPC 契约虽然具备生成框架，但方法集合、字段语义、事件目录和运行时校验仍不完整，当前“契约检查通过”只能证明 JSON Schema 语法合法。
3. 桌面端仍调用契约中不存在的方法，且路由、审批参数、备份公司上下文等与设计方案冲突。
4. 全量验证脚本会跳过缺失的覆盖率工具和空 E2E 套件；仓库又没有 CI 工作流，无法提供设计方案要求的 100% 覆盖率与 fail-closed 质量证明。
5. 数据库迁移、写队列、后台 Worker 和实时健康检查没有形成统一生命周期，存在并发写入、升级和故障可观测性风险。
6. CLI Runtime 的真实工作区、Seatbelt 和 Egress 闭环未落地。

按优先级统计：

| 优先级 | 数量 | 含义 |
|---|---:|---|
| P0 | 6 | 阻断核心功能、契约可信度或交付证明，必须先修复 |
| P1 | 6 | 影响安全、业务闭环、生产运维或跨端一致性 |
| P2 | 2 | 不阻断基本功能，但影响性能和长期可维护性 |
| 合计 | 14 | 当前需要处理或正式裁决的问题 |

## 3. 本轮复核证据

### 3.1 已通过的检查

| 检查 | 结果 |
|---|---|
| 266 个 JSON Schema 语法检查 | 通过 |
| Rust `fmt`、`clippy` | 通过 |
| Rust 测试 | 94 项通过 |
| 中心后台 lint、类型检查 | 通过 |
| 中心后台主测试集 | 204 项通过 |
| Sidecar lint、类型检查 | 通过 |
| Sidecar 主测试集 | 1113 项通过、1 项跳过 |
| 管理后台 lint、类型检查、测试 | 通过，16 项测试 |
| 契约漂移检查 | 通过 |
| Desktop 与 Admin 生产构建 | 通过 |
| 锁文件与覆盖率排除规则检查 | 通过 |
| Docker Compose 配置解析 | 使用占位环境变量时通过 |

### 3.2 未通过或无法形成交付证明的检查

| 检查 | 结果 | 说明 |
|---|---|---|
| `scripts/verify-all.sh` | 失败 | Desktop 路由测试 1 项失败，验证提前终止 |
| Desktop 测试 | 38 通过、1 失败 | 实际路由为 `/company/:companyId/...`，测试和设计要求 `/companies/:companyId/...` |
| 根级契约/集成/故障测试 | 171 通过、1 失败 | 测试要求 `.github/workflows`，但当前提交已删除该目录 |
| Playwright E2E | 失败 | `No tests found` |
| Rust 覆盖率 | 未生成 | 缺少 `cargo-llvm-cov` 时脚本仅告警并跳过 |
| 中心后台覆盖率 | 62.91% | 低于设计方案要求的 100% |
| Sidecar 覆盖率 | 77.21% | 低于设计方案要求的 100% |
| Desktop 覆盖率抽样 | 4.36% statements | 未配置 100% 门槛 |
| Admin 覆盖率 | 2.61% statements | 未配置覆盖率门槛 |
| Sidecar 旧功能测试集 | 90 通过、17 失败 | 未纳入主门禁，需逐项区分测试漂移和产品缺陷 |
| 中心后台旧功能测试集 | 118 通过、60 失败 | 未纳入主门禁，需逐项区分测试漂移和产品缺陷 |

旧功能测试集的失败不能直接全部判定为代码缺陷，因为其中存在构造器、接口和数据模型已经变更的测试。正确处理方式是先为每个失败用例建立“设计条款—当前接口—测试断言”映射，再决定修复代码还是删除/重写已失效测试。

## 4. 已确认修复的事项

以下事项在当前基线已有代码或测试证据，不再列为待修复问题：

1. Desktop 调用 Rust Command 的主要参数已从 camelCase 调整为 snake_case。
2. Desktop WebView 不再持久化 Access Token。
3. Sidecar 方法所有权登记与 Sidecar 注册的方法数量已经达到 94/94 对齐。
4. Review Service 已增加任务分配、Artifact SHA、自审限制和 superseding 关系校验。
5. `CompletionGate` 已接入部分运行完成处理。
6. `RuntimeWorker` 已启动真实消费循环，不再只是空壳构造。
7. Rust 单测、主 Python/TypeScript lint 和类型检查当前通过。
8. 契约生成结果漂移检查当前通过。
9. 两份核心设计文档中未发现遗留的 `Review 问题汇总`、`review 结论`或显式迭代批注章节。

上述“已修复”仅代表对应局部问题已关闭，不代表其所在的完整业务链已经闭环。

## 5. 当前问题总表

| 编号 | 优先级 | 问题 | 主要影响 | 建议责任域 |
|---|---|---|---|---|
| CUR-P0-01 | P0 | API Model Runtime Broker 与 Egress 为占位实现 | API Model 职员无法执行真实任务 | Rust Core + Sidecar Runtime |
| CUR-P0-02 | P0 | RPC 与 Domain Event 契约不完整且缺少强校验 | 跨端可编译但运行时失配 | Contracts + Rust + Sidecar |
| CUR-P0-03 | P0 | Desktop 路由和 RPC 调用偏离公开契约 | 页面失败、审批或备份写错范围 | Desktop |
| CUR-P0-04 | P0 | 全量验证、覆盖率和 CI 不是 fail-closed | 无法证明质量与 100% 覆盖率 | QA/Build |
| CUR-P0-05 | P0 | 迁移、写队列、Worker 与健康检查未形成统一闭环 | 升级、并发写和故障恢复不可靠 | Sidecar Persistence |
| CUR-P0-06 | P0 | Admin 登录与刷新协议偏离后端契约 | 管理后台认证在真实环境失败 | Admin + Backend Auth |
| CUR-P1-01 | P1 | CLI Runtime 未绑定真实工作区与完整 Seatbelt/Egress | CLI 职员安全边界和任务结果不可信 | Runtime Gateway |
| CUR-P1-02 | P1 | Review、部门完成和公司完成的权威状态转换仍不完整 | 任务可能提前完成或永久停滞 | Orchestration |
| CUR-P1-03 | P1 | 自动更新解包、切换与回滚不具备生产安全性 | 路径穿越、半更新、无法可靠回滚 | Rust Updater |
| CUR-P1-04 | P1 | 部署配置仍是开发级别且 MinIO 端口错误 | 服务不可用或不满足生产安全要求 | Deployment |
| CUR-P1-05 | P1 | 旧功能测试大面积失败但未纳入门禁 | 回归风险被隐藏，测试资产失真 | QA + 各模块 |
| CUR-P1-06 | P1 | 真实健康状态没有从进程、队列和 Worker 汇聚 | UI 和运维可能收到假健康 | Rust + Sidecar |
| CUR-P2-01 | P2 | Desktop/Admin 首屏产物过大 | 冷启动和更新体验下降 | Frontend |
| CUR-P2-02 | P2 | 契约、客户端和方法分类仍有多处手工维护 | 后续修改容易再次漂移 | Contracts/Tooling |

## 6. P0 问题与详细解决方案

### CUR-P0-01：API Model Runtime Broker 与 Egress 为占位实现

#### 现象与证据

- `sidecar/ibreeze/runtime/transport.py` 中 `ReverseRpcClient` 默认以 `socket_path=None` 启动。
- 同一文件明确记录真实 Unix Domain Socket 传输尚未实现，并在非 stub 路径抛出 `NotImplementedError`。
- `RuntimeTransport` 直接构造 stub 模式的 `ReverseRpcClient`。
- `apps/desktop-core/src/rpc/reverse.rs` 对 Credential Broker 返回 `CREDENTIAL_BROKER_NOT_OPERATIONAL`，探测结果固定为不可用。
- `apps/desktop-core/src/security/egress.rs` 只分配空闲端口，源码注释说明实际 TCP 代理留待后续实现。
- API Model 执行路径依赖上述 transport 获取 Credential 并发起模型调用，因此真实执行必然在凭据或网络阶段失败。

#### 根因

当前只实现了 API Model Agent Loop 的上层抽象和测试替身，没有实现设计方案要求的 Rust 持有凭据、Sidecar 不接触明文、按 Run 创建 Egress Lease 的可信边界。

#### 影响

- API Model 虽可作为职员底座配置，但不能完成真实任务。
- Sidecar 若绕开 Broker 直接持有 API Key，会违反凭据边界。
- 无法验证 Provider 域名白名单、DNS 重绑定、重定向和 SSRF 防护。
- 设计方案的基础能力与产品对外描述不成立。

#### 目标状态

Sidecar 只发送 `credential_ref`、Provider/Model 标识和请求意图。Rust 从 Keychain 读取凭据，在内存中短时持有并 zeroize；所有 API Model 网络请求通过每 Run 独立的 Rust CONNECT Proxy。Sidecar、SQLite、日志、事件和崩溃报告中均不得出现明文凭据。

#### 实施步骤

1. **冻结反向 RPC 协议**
   - 在 `packages/rpc-schema` 增加 Credential Broker、Egress Lease、HTTP Start/Cancel/Probe 的完整 request/response/error schema。
   - request id 使用与正向 RPC 不冲突的命名空间，并要求 `ipc_session_id`、`run_id`、`credential_ref`、deadline 和 trace id。
   - 明确定义流式响应帧、取消帧、终止帧和连接断开后的状态。

2. **实现同连接双向多路复用**
   - Rust 与 Sidecar 继续使用已认证的 UDS，不开放额外本地 TCP 控制端口。
   - 双方维护 pending request map、deadline、取消信号和连接代次。
   - Sidecar 重连后，旧 session 的 pending 请求全部以可重试错误结束，禁止复用旧 lease。

3. **实现 Credential Broker**
   - Rust 按 `{profile_directory_id}/provider/{credential_ref}` 从 Keychain 读取。
   - 验证当前 Profile、Provider Release、Model Binding 与 Run 的关联。
   - 凭据只进入实现 `Zeroize` 的内存对象；不得序列化到日志或 RPC 响应。
   - 删除、损坏、无权限和临时不可用使用不同稳定错误码。

4. **实现每 Run 独立 CONNECT Proxy**
   - 只绑定 `127.0.0.1` 随机端口。
   - 生成 32 字节随机 Token，保存于 Rust 内存，不写数据库。
   - 只允许设计目录为该 Agent/Provider Release 声明并由 Catalog 校验过的域名。
   - CONNECT 前解析 DNS，拒绝 loopback、private、link-local、multicast、保留地址和 IP 字面量。
   - 连接建立前和重定向后重新校验目标，防止 DNS rebinding。
   - Run 终止、取消、超时或 Rust 重启时立即撤销 lease。

5. **连接 Built-in Agent Runtime**
   - `ModelRuntime` 获取的是短期 broker handle 或本地代理地址，不是 API Key。
   - Provider Adapter 统一处理 streaming、tool call、usage、finish reason、retry-after 和取消。
   - 重试只允许在没有产生不可重复副作用时发生，并受 Run deadline 约束。

6. **补齐观测与审计**
   - 只记录 Provider id、Model id、目标规范化域名、字节数、耗时、状态码类别和 lease id。
   - 请求正文、响应正文、Authorization、Token、API Key、代理 Token 一律脱敏或禁止记录。

#### 预计修改范围

- `apps/desktop-core/src/rpc/reverse.rs`
- `apps/desktop-core/src/security/egress.rs`
- `apps/desktop-core/src/security/keychain.rs`
- `sidecar/ibreeze/runtime/transport.py`
- `sidecar/ibreeze/runtime/model_runtime.py`
- `sidecar/ibreeze/runtime/run_executor.py`
- `packages/rpc-schema/reverse-methods.v1.json`
- `packages/rpc-schema/methods/`

#### 必须增加的测试

1. 使用本地 fake Provider 完成真实 streaming Agent Loop。
2. Sidecar 进程内存、日志、SQLite 和事件中搜索测试 API Key，结果必须为零。
3. DNS 指向私网、重绑定、30x 跳转私网、IP 字面量和未授权域名全部拒绝。
4. 同时运行多个 Run 时凭据和代理 Token 不串用。
5. Run 取消、Rust 崩溃、Sidecar 重连和 Provider 超时均能释放 lease。
6. Credential 删除、损坏、错误 Profile 和错误 session 返回稳定错误码。
7. macOS 真实 Keychain 集成测试和无 UI CI Keychain 测试。

#### 验收标准

- 一个 API Model 职员可在无明文凭据进入 Sidecar 的前提下完成含 Tool Call 的任务。
- 所有安全负向测试通过。
- Credential Broker 探测返回真实状态，不存在硬编码不可用或 stub 路径。
- 相关契约、代码生成、集成测试和 E2E 全部进入主质量门禁。

---

### CUR-P0-02：RPC 与 Domain Event 契约不完整且缺少强校验

#### 现象与证据

- 当前共有 241 个方法 schema 文件，但其中 76 个对象的 `properties` 为空；部分本应有字段的方法被生成为空对象。
- `review.submit.request.schema.json` 为空对象，而运行时处理器实际需要多个标识、结论和版本字段。
- `system.handshake`、`system.health`、`system.shutdown` 缺少成对的 request/response schema。
- schema 中存在至少 18 个未在公开方法所有权表登记的方法族，例如 `artifact.create`、`catalog.get`、`review.assign`、`task.supersede`。
- `packages/contracts/domain-events/registry.v1.json` 当前是“Registry 自身的 JSON Schema”，不是列出全部事件的 Registry 实例。
- 实际只有少量 Domain Event payload schema，未覆盖设计方案 H.4 的完整事件集合。
- Rust schema generator 对本地 `$ref` 和未知引用存在退化到 `serde_json::Value` 的路径。
- Sidecar RPC Server 只对部分方法使用手写 Pydantic 模型，未统一验证全部请求和响应。
- Rust 的方法所有权/类型判断仍存在手工 `sidecar_method_kind` 分支。

#### 根因

契约生成链以“文件存在且语法合法”为主要完成条件，没有把设计方案 J.14 的精确方法集合、字段、所有权和 Domain Event 清单作为唯一机器可读源，也没有在运行时边界强制校验。

#### 影响

- 两端可分别通过类型检查，但在真实调用时才发现字段不匹配。
- 空 schema 会把任意对象伪装成合法请求或响应。
- 手工方法列表会持续漂移。
- Event Replay、审计、投影和故障恢复不能依赖稳定事件契约。

#### 目标状态

建立一个可执行的 Canonical Contract Registry：公开 RPC、反向 RPC、Domain Event、错误码和所有权均由该 Registry 生成；集合缺失、多余、空字段、未解析引用或运行时响应不合约时，生成与 CI 必须失败。

#### 实施步骤

1. **创建唯一方法 Registry**
   - 每条记录至少包含 `method`、`owner`、`kind`、`idempotency_ttl`、`company_scope`、`request_schema`、`response_schema`、`errors`。
   - 用脚本校验其与设计方案 J.14 的方法集合完全相等。
   - 18 个额外方法若只是内部 Domain Action，应从公开 RPC schema 删除；确需公开者必须先写入设计方案与实施计划。

2. **补齐精确字段**
   - 为每个方法按设计方案固定字段、required、枚举、format、长度、分页和 `additionalProperties:false`。
   - 只有真正无参数的方法允许空对象，并通过 allowlist 明确声明。
   - 补齐三个 `system.*` 方法的 request/response。

3. **建立实际 Domain Event Registry**
   - 新增 registry 实例文件，逐项列出 `event_type`、`version`、`payload_schema`、是否要求 `company_id`、生产者和消费者。
   - H.4 中的每个事件都必须有 payload schema 和至少一个合法 fixture。
   - Event Store 写入前校验 payload；Replay 读取旧版本时通过显式 upcaster 升级。

4. **修复生成器**
   - 完整解析本地和跨文件 `$ref`，不允许静默退化为 `Value`/`Any`。
   - 遇到未知 format、循环引用、重复类型名和未登记方法时 fail-fast。
   - 从 Registry 生成 Rust 方法枚举、Sidecar dispatcher metadata、TypeScript client 和测试 fixtures。

5. **运行时双向校验**
   - 开发、测试和 CI 中对每个 request/response 做 JSON Schema 校验。
   - 生产环境至少对跨进程边界的 request 强制校验，并对响应采用生成类型序列化；关键安全方法继续执行响应校验。
   - Schema 失败映射为稳定的 `RPC_SCHEMA_VIOLATION`，记录 method、schema version 和字段路径，不记录敏感值。

6. **升级漂移检查**
   - 检查 Registry、schema、生成代码、OpenAPI 和文档表格的集合相等。
   - 测试刻意删除字段、增加未登记方法、制造空 schema 或破坏 `$ref` 时，检查必须失败。

#### 必须增加的测试

- 所有方法 request/response 的正例 fixture。
- required 缺失、额外字段、错误枚举、错误 UUID/日期格式的负例。
- 方法 Registry 与 Rust、Sidecar、TypeScript 方法集合精确相等。
- 每个 Domain Event 至少一个发布、持久化、Replay 和 upcast 测试。
- 生成器对未知 `$ref`、空 schema 和未登记方法 fail-fast。
- `review.submit`、`approval.resolve`、`auth.login` 等高风险方法端到端契约测试。

#### 验收标准

- 不存在未解释的空对象 schema。
- 不存在 Registry 外的公开方法或缺失的公开方法。
- Rust/Sidecar/Desktop 不再维护独立手工方法清单。
- 契约变更只修改 Canonical Registry/schema，生成与测试自动暴露所有受影响端。

---

### CUR-P0-03：Desktop 路由和 RPC 调用偏离公开契约

#### 现象与证据

1. `apps/desktop/src/app/routes.tsx` 使用 `/company/:companyId/...`，设计方案 K.1 和现有测试要求 `/companies/:companyId/...`。
2. `usePlan.ts` 调用未登记的 `planVersion.list`。
3. `useOrchestration.ts` 调用未登记的 `orchestration.list/listRuns/create/run/archive`；设计方案把编排定义为 Task/Run 内部能力，不是独立公开 CRUD。
4. `ApprovalListPage.tsx`：
   - `approval.listPending` 未传必填 `company_id`；
   - decision 使用 `approved/denied`，契约要求 `allow/deny`；
   - 未传 `expected_version`；
   - 局部调用使用 `idempotencyKey`，与统一 Tauri Command 的 `idempotency_key` 约定不一致。
5. `BackupPage.tsx` 使用固定 `companyId='default'`，不能保证当前公司隔离。
6. `shared/rpcClient.ts` 手工维护 `READ_OPERATIONS`，包含不存在的方法且遗漏多项真实读方法，导致读写和幂等键判断错误。
7. `tauriClient.ts` 对 origin 验证响应的 TypeScript 类型与 Rust `BackendValidation` 字段不一致。

#### 根因

Desktop 在契约生成完成前使用了页面原型期的本地接口和路由命名，之后没有由生成客户端替换；读写分类、参数和响应类型分散在 Hooks 与页面中。

#### 影响

- 当前 Desktop 测试已实际失败。
- 页面可能收到 `METHOD_NOT_FOUND` 或 schema validation 错误。
- 审批无法可靠执行，备份可能落入错误公司范围。
- 写请求可能因错误分类而缺少幂等键。

#### 目标状态

Desktop 只能通过生成的 typed RPC client 调用 Canonical Registry 中的方法。路由、公司上下文、请求字段、响应字段、写请求幂等键均由统一层处理。

#### 实施步骤

1. 将所有公司路由统一为 `/companies/:companyId/...`，更新导航、重定向、深链和测试。
2. 删除或改造独立 Orchestration CRUD 页面：
   - 公司任务编排映射到 `task.analyze/confirmPlan/getGraph` 和 `run.*`。
   - UI 需要的计划版本随 `task.get` 或 `task.getGraph` 返回，不新增未经设计的方法。
3. 由契约生成 TypeScript method map、request/response 类型和 `kind`，删除 `READ_OPERATIONS`。
4. `createRpcRequest` 只接受生成 method 字面量：
   - 读方法不生成幂等键；
   - 写方法强制 `idempotency_key`；
   - 禁止页面绕过统一 client 直接 `invoke`。
5. 修复审批页：
   - 从当前路由/Company Store 取得 `company_id`；
   - decision 仅为 `allow` 或 `deny`；
   - 使用当前行 `version` 作为 `expected_version`；
   - 展示 `execution_pending` 与冲突重载行为。
6. 修复备份页，所有列表、创建、恢复请求都绑定当前 `company_id`；无当前公司时禁用写操作。
7. 由 Rust Command schema 生成 `BackendValidation` 类型，删除手写响应接口。

#### 必须增加的测试

- 所有 K.1 路由的直接访问、刷新、无效 company id 和重定向测试。
- 静态测试：源码中出现 Registry 外 RPC 字符串时失败。
- Approval allow、deny、版本冲突、execution pending 和幂等重试组件测试。
- 两个公司切换后，Backup/Approval/Task 不发生数据串用。
- Desktop 与 mock Rust Core 的 request/response 契约集成测试。
- 至少一条从登录、选择公司、提交任务、确认计划到查看 Run 的 Playwright E2E。

#### 验收标准

- Desktop 全部测试通过。
- Desktop 源码不存在未登记 RPC 方法和固定 `'default'` 公司标识。
- 页面不直接维护 request/response DTO 或读写方法分类。

---

### CUR-P0-04：全量验证、覆盖率和 CI 不是 fail-closed

#### 现象与证据

- 当前提交删除了 `.github/workflows`，但设计方案和实施计划仍把 CI 作为强制质量与发布门禁。
- 根级 `test_ci_policy.py` 因找不到 `.github/workflows` 失败。
- `scripts/verify-all.sh` 只把 `node`、`npm`、`cargo` 作为必需工具。
- 缺少 `cargo-nextest` 时回退到 `cargo test`；缺少 `cargo-llvm-cov` 时直接跳过 Rust 覆盖率。
- Playwright 没有测试文件，脚本将 `No tests found` 当作跳过，而不是失败。
- Python 当前覆盖率只有 62.91%/77.21%，Desktop 抽样 4.36%，Admin 2.61%；TypeScript 未设置 100% 阈值。
- 旧功能测试目录没有进入主验证链，实际仍有 60 和 17 个失败。

#### 根因

质量脚本优先保证“开发机可运行”，而设计方案要求的是“依赖缺失、套件为空、覆盖不足或任一测试失败都阻断”。CI 删除与文档要求也没有同步做架构裁决。

#### 影响

- 本地输出“通过”不等于完整测试已执行。
- 无法证明 100% 单元测试覆盖率。
- 发布提交没有不可绕过的自动门禁。
- 测试目录可被遗漏而不触发失败。

#### 推荐决策

优先选择恢复 CI 工作流，因为这是当前两份文档明确要求的交付方式。如果产品明确决定不使用 GitHub Actions，则必须先修改设计方案、实施计划和验收标准，并提供同等不可绕过的其他 CI；仅删除工作流不构成一致方案。

#### 实施步骤

1. **恢复 CI**
   - 增加 PR 与主分支验证工作流、macOS Runtime 安全工作流、发布工作流。
   - 第三方 Action 固定完整 commit SHA。
   - 使用 `npm ci`、`uv sync --frozen`、`cargo --locked`。

2. **让验证脚本 fail-closed**
   - 必需工具加入 `uv`、`cargo-nextest`、`cargo-llvm-cov` 和 Playwright 浏览器探测。
   - 删除 fallback 和 coverage skip。
   - E2E spec 数量为 0 时失败。
   - 任一测试目录未被收集时失败。

3. **设置 100% 阈值**
   - Python 使用 statement、branch 全 100%。
   - Vitest 在 Desktop/Admin 同时设置 lines/functions/branches/statements 为 100%。
   - Rust 使用 `cargo llvm-cov --fail-under-lines 100` 并检查 branch/region 指标。
   - 排除项必须经过 allowlist，且禁止排除业务模块。

4. **统一测试集合**
   - 中心后台与 Sidecar 的旧功能测试逐项裁决后纳入同一 pytest collection。
   - 根级 contracts/integration/faults/security/performance/release 测试由 `verify-all.sh` 全部调用。
   - 禁止使用目录命名或单独配置隐藏失败套件。

5. **构建和发布约束**
   - 发布只接受已完成全部门禁的 commit SHA。
   - Release job 不重新解释测试结果，只下载同 SHA 的已签名构建产物。
   - macOS Seatbelt 真实机门禁不得改成可选或 nightly。

#### 必须增加的门禁自测

- 临时隐藏 `cargo-llvm-cov` 后验证脚本必须失败。
- 删除全部 E2E spec 后必须失败。
- 将任一覆盖率阈值降到 99 后 CI policy test 必须失败。
- 制造一个未被收集的测试目录，collection policy 必须失败。
- 修改生成文件但不提交源契约时 drift check 必须失败。
- 发布工作流引用未通过验证的 SHA 时必须拒绝。

#### 验收标准

- 干净环境执行唯一入口可完整通过，无跳过性告警。
- 四个主要代码域均提供 100% 覆盖率报告。
- E2E 至少覆盖登录、公司任务、部门执行、Review/返工、最终报告、离线与升级关键路径。
- PR 无法绕过必需检查合并，发布无法绕过已验证 SHA。

---

### CUR-P0-05：迁移、写队列、Worker 与数据库生命周期未形成统一闭环

#### 现象与证据

- `sidecar/ibreeze/local_db.py` 的 `initialize()` 先执行大型 `_CREATE_TABLES_SQL`。
- 应用之后才执行 `run_migrations()`，迁移不是从空库到目标版本的唯一事实来源。
- `LocalDB` 已持有多个读连接，应用又构造第二套 `ReadPool`，RPC 并未统一使用后者。
- `WriteQueue` 已启动，但 RPC Server 的幂等写路径仍直接使用 write connection，源码注释说明未来再集成。
- Analysis Worker 等路径仍存在直接数据库写入。
- 应用只启动部分 Worker，知识 Outbox、索引对账、备份调度、事件压缩/恢复等没有统一注册与监督。

#### 根因

持久化组件按模块分别实现，但没有一个 Application Lifecycle 负责“迁移完成—连接开放—单写者启动—Worker 启动—健康汇聚—有序关闭”。

#### 影响

- 新安装可能掩盖缺失迁移，升级路径无法被可靠测试。
- 多条写路径绕过队列，破坏单写者和备份 barrier 保证。
- 重复连接池浪费资源且读一致性语义不明确。
- Worker 崩溃后可能静默停止，数据投影长期落后。

#### 目标状态

迁移是 schema 唯一来源；所有业务写入经过一个可观测 WriteQueue；只存在一个读池；所有后台任务由统一 Worker Supervisor 管理；启动和关闭顺序可测试。

#### 实施步骤

1. **重构数据库引导**
   - 首次只创建最小 migration ledger。
   - 在开放业务连接前顺序执行带 checksum 的迁移。
   - 删除 `_CREATE_TABLES_SQL` 的重复业务 DDL，或把它拆成 `0001_initial.sql`。
   - schema version 高于当前程序时拒绝启动，不允许猜测降级。

2. **统一连接所有权**
   - `LocalDB` 持有唯一 write connection 和唯一 read pool。
   - 删除应用层重复 `ReadPool`。
   - 明确读事务、快照读和 read-after-write 的 API。

3. **落实单写者**
   - RPC 写方法、幂等记录、Outbox、Worker 状态和 Analysis 结果全部提交到 `WriteQueue`。
   - 提供 `execute_in_transaction(command)`，一个业务命令的状态、事件和幂等结果同事务提交。
   - 禁止业务模块直接获取原始 write connection；用架构测试扫描。

4. **实现 barrier 与反压**
   - Backup snapshot 先进入 barrier，等待已有写完成，阻止新写，再 checkpoint 和复制。
   - 队列满时返回稳定 `LOCAL_WRITE_BACKPRESSURE`，不得无限占用内存。
   - shutdown 先停止接收新 RPC，再 drain/rollback 队列。

5. **统一 Worker Supervisor**
   - 注册 Runtime、Analysis、Knowledge Outbox、Index Reconciliation、Backup Scheduler、Event Compactor 等 Worker。
   - 每个 Worker 记录 heartbeat、last_success、last_error、lag、restart_count。
   - 意外退出按有限退避重启；达到阈值后进入 degraded/failed，不得静默标记健康。

#### 必须增加的测试

- 空库只通过迁移生成完整 schema。
- 每一个历史版本到当前版本的升级测试。
- migration checksum 变化、迁移中断、磁盘满、数据库版本过高测试。
- 多 RPC 与 Worker 并发写的顺序、幂等和 Outbox 原子性测试。
- Backup barrier 期间写入阻塞、完成后恢复测试。
- Worker 崩溃、重启上限、关闭 drain 和健康降级测试。

#### 验收标准

- 业务表定义只存在于 migration chain。
- 代码扫描找不到绕过 WriteQueue 的业务写路径。
- 一个 Worker 人为崩溃后，健康接口在限定时间内显示 degraded，并记录可定位原因。
- 备份、恢复和升级故障注入不产生半提交业务状态。

---

### CUR-P0-06：Admin 登录与刷新协议偏离后端契约

#### 现象与证据

- Admin 登录页发送 `{username,password}`。
- 后端 `LoginRequest` 要求 `{identifier,password,device_id}`。
- Admin API Client 刷新时把当前 access token 作为 `{refresh_token: token}` 发送。
- 设计方案和后端管理员认证要求 Refresh Token 只在 HttpOnly Cookie 中传输，管理员响应正文不返回 refresh token。
- 仓库已有生成的 OpenAPI 类型，但登录页和通用 API Client 没有实际使用这些认证 DTO。
- 登录页按 `data.data` 读取统一 envelope，刷新路径却按 `data.access_token/data.user` 读取，响应解析规则也不一致。

#### 根因

Admin 使用了早期手写认证协议，后端已升级为统一 envelope、设备标识和管理员 Cookie refresh，但前端没有同步替换。

#### 影响

- 真实后端下管理员登录会返回 422 或协议错误。
- 刷新请求无法提供正确 Cookie 时，Access Token 到期后会话中断。
- 把 Access Token 放入 refresh body 混淆两类凭据，增加泄漏和审计误判风险。

#### 目标状态

Admin 使用 OpenAPI 生成客户端；登录发送 identifier、password 和稳定 device_id；Access Token 只保存在内存；Refresh Token 只由 HttpOnly/Secure/SameSite Cookie 管理；刷新请求不提交 token body。

#### 实施步骤

1. 重新生成并实际使用 `packages/contracts/openapi/openapi.json` 对应的 Admin API Client 和 DTO，禁止认证页面继续手写请求结构。
2. 登录表单字段展示可继续叫“用户名或邮箱”，请求字段固定为 `identifier`。
3. 首次打开生成随机 `device_id` 并持久化为非敏感设备标识；退出登录不必轮换，清除站点数据时自然重建。
4. 所有认证请求启用正确的 `credentials` 策略：
   - 同源生产部署使用 `same-origin`；
   - 若开发环境跨源，后端只允许明确 origin 并使用 `include`。
5. Refresh 请求使用空 body 或 OpenAPI 规定的请求体，绝不把 Access Token 当 Refresh Token。
6. 实现 401 single-flight：同一时刻只允许一个 refresh，其余请求等待；失败统一清空内存 Access Token 并跳转登录。
7. 校验 envelope、错误码和 `Cache-Control: no-store`。

#### 必须增加的测试

- MSW 或真实 ASGI 后端的登录成功/失败测试。
- 请求体必须包含 `identifier/device_id`，不得包含 `username` 或 `refresh_token`。
- Refresh 只依赖 HttpOnly Cookie，Access Token 不进入 localStorage/sessionStorage。
- 多请求同时 401 只触发一次 refresh。
- logout/change-password 后旧 Cookie family 被撤销。
- OpenAPI drift 与 Schemathesis 契约测试。

#### 验收标准

- Admin 对真实后端完成登录、刷新、退出和改密。
- 浏览器可访问存储中不存在 Access Token/Refresh Token。
- 前端不再手写认证请求和响应 DTO。

## 7. P1 问题与详细解决方案

### CUR-P1-01：CLI Runtime 未绑定真实工作区与完整 Seatbelt/Egress

#### 现象与证据

- CLI 执行路径生成临时 prompt 文件后启动 Supervisor，但没有完整证明子进程 `cwd` 为任务 Workspace。
- Seatbelt 静态模板只允许系统和临时目录，没有将当前 Workspace 的规范化路径动态加入读写规则。
- 当前 Egress 只分配端口，不存在真实 Proxy，因此 `HTTPS_PROXY` 安全边界无法成立。
- 进程登记、PID/PGID、反向进程通知、checkpoint/resume 和取消仍分散或不完整。
- 项目存在两套 CLI Adapter 相关实现，职责容易漂移。

#### 影响

- CLI 可能在错误目录执行，产生错误或越界修改。
- “工作区内可读写、工作区外只读”的权限模型未真正执行。
- 取消可能只结束父进程而遗留子进程。
- Codex CLI、Claude Code、OpenCode 的事件和恢复语义不一致。

#### 详细解决方案

1. 保留唯一 `CliAgentAdapter` 契约：`probe/build_invocation/parse_event/checkpoint/cancel`。
2. Run 创建时冻结 Execution Snapshot，记录 Workspace realpath、Agent Release、模型、Skill 和安全策略 hash。
3. Supervisor 必须使用 argv 数组和 Workspace realpath 作为 cwd，禁止 shell 拼接。
4. prompt 优先走 stdin；必须落盘时写入 Profile 私有 run 目录，权限 0600，启动后立即 unlink。
5. 动态生成并严格转义 Seatbelt Profile：
   - Workspace realpath 读写；
   - Workspace 外普通文件只读；
   - Keychain、浏览器资料、SSH 私钥、系统敏感路径显式拒绝；
   - 网络只允许当前 Run 的 loopback proxy 端口。
6. Rust 注册 PID、PGID、run_id、start time 和 lease；Sidecar 只保存非敏感进程引用。
7. cancel 先发送协议级取消，再 TERM 进程组，超时后 KILL；最终状态必须可重放且幂等。
8. 三类 Agent 的 stdout/stderr 转换成统一 Runtime Event，不把原始机密写入日志。
9. checkpoint 保存 native session id、已提交事件序号和 Adapter 版本；resume 验证 Execution Snapshot 未变化。

#### 测试与验收

- 对三类 CLI 各有 fake contract test 和至少一条真实锁版本集成测试。
- 从 Workspace 内写入成功，Workspace 外读取成功、写入失败。
- 直接 DNS/TCP/UDP 出站失败，仅带有效 Token 的代理连接成功。
- fork 子进程后 cancel 不残留进程。
- 首次、resume、cancel 的事件序列稳定；macOS 最低和最高支持版本真实 Seatbelt 发布门禁通过。

---

### CUR-P1-02：Review、部门完成和公司完成的权威状态转换仍不完整

#### 现象与证据

Review Service 的局部校验已经补齐，`CompletionGate` 也进入部分 Run 结束路径；但尚未形成可验证的单一业务状态机，证明以下动作都由权威命令驱动：

- `review.submit` 后如何更新 EmployeeTask/DepartmentTask；
- 所有阻断问题关闭后如何触发部门负责人最终 Review；
- 部门报告通过后如何更新 CompanyTask；
- 总经理最终 Review、最终报告和 `completed` 如何保持同事务或可恢复一致；
- 返工后旧报告和旧 Review 如何 supersede，而不是继续参与完成判断。

#### 影响

- Task 可能在有未解决 Review Issue 时完成。
- 部门已完成但公司任务无法推进。
- 事件重放后状态与在线状态不同。
- 最终报告可能引用过期 Artifact。

#### 详细解决方案

1. 定义唯一状态转换表，覆盖 CompanyTask、DepartmentTask、EmployeeTask、Run、Review、Issue、Report。
2. 每个转换只由一个 Command Handler 负责，Handler 在同一 WriteQueue 事务中：
   - 校验 expected_version；
   - 更新聚合状态；
   - 写 Domain Event；
   - 写 Outbox；
   - 保存幂等响应。
3. `review.submit` 只提交 Review；由 `ReviewSubmitted` projector/transition service 计算是否达到下一阶段。
4. Completion Gate 固定检查：
   - 所有必需 Deliverable 存在且 SHA 匹配；
   - 所有参与执行职员已提交执行/Review 报告；
   - blocker/critical/high Issue 已 resolved 或被有效 supersede；
   - 最近一轮测试报告通过；
   - 所有前置 DepartmentTask 完成；
   - 最终负责人 Review 通过。
5. 返工创建新 attempt/revision，旧 Artifact、Review、Issue 和 Report 保留审计但不参与当前 Gate。
6. 最终报告记录参与 Gate 的实体 id/version/SHA，保证审计可复现。

#### 测试与验收

- 为状态转换表的每条合法边和非法边生成参数化测试。
- 并发提交 Review、重复事件、乱序事件和进程崩溃恢复测试。
- 软件研发标准流从需求、架构、开发、测试、返工、复测到总经理报告完整 E2E。
- 任一 blocker 未关闭、报告 SHA 过期或部门前置未完成时，公司任务不得完成。

---

### CUR-P1-03：自动更新解包、切换与回滚不具备生产安全性

#### 现象与证据

- Updater 使用系统 `tar -xzf` 直接解包到目标附近目录。
- 未发现完整的 archive path traversal、绝对路径、symlink、hardlink、device file 和压缩炸弹校验。
- 没有明确 staging 完整校验后再原子切换的实现。
- 首次启动稳定性检查主要验证 Sidecar 可执行文件和版本，没有持续健康窗口与崩溃计数。
- Restore/rollback 对目标包 hash、布局和原子替换的保证不足。

#### 影响

- 恶意或损坏更新包可能越界写文件。
- 断电或磁盘满可能留下半更新状态。
- 新版本一启动即崩溃时不能可靠回滚。

#### 详细解决方案

1. 不调用外部 `tar` 直接写最终路径，使用安全 archive reader 逐条验证后解包到随机 staging。
2. 拒绝：
   - 绝对路径、`..`、NUL、重复规范化路径；
   - symlink/hardlink/device/FIFO；
   - 超出 manifest 的文件；
   - 文件数、单文件大小和总解压大小超限。
3. 验证 manifest 签名、每文件 SHA-256、权限 allowlist、版本和 package layout。
4. staging 与目标位于同一文件系统；文件和目录 fsync 后通过平台原子 rename/swap helper 切换。
5. 保存上一个稳定版本的只读 manifest 和 hash，禁止用未经验证的备份回滚。
6. 首次启动进入 probation：
   - Sidecar handshake 成功；
   - migration 完成；
   - health 连续稳定指定窗口；
   - 无崩溃循环。
7. probation 失败自动切回旧版本并记录稳定错误码；迁移必须遵循设计中的可回滚/forward-only 策略。

#### 测试与验收

- 恶意 tar 路径穿越、symlink、hardlink、超大文件全部拒绝。
- 在解包、fsync、切换、首次启动各阶段注入断电/异常，重启后只能进入旧稳定版或新完整版本。
- 新 Sidecar handshake 失败和健康窗口失败触发自动回滚。
- 签名、manifest、文件 hash 或 rollback 包任一不匹配均拒绝。

---

### CUR-P1-04：部署配置仍是开发级别且 MinIO 端口错误

#### 现象与证据

- `deploy/docker-compose.yml` 中 MinIO 进程使用 `--console-address ":51901"`，但容器端口映射是宿主 `51901` 到容器 `9001`，进程应监听容器内 `9001`。
- 当前 Compose 以开发便利为主，未形成明确的生产 TLS、Secret、网络隔离、资源限制、迁移和备份方案。
- 镜像虽然填写 digest 形式，但交付前仍需验证这些 digest 可拉取且对应预期架构。

#### 影响

- MinIO Console 端口可能不可达。
- 直接把开发 Compose 当生产部署会暴露数据库/对象存储或使用不安全 Secret。
- 无法执行可审计的备份、恢复和滚动升级。

#### 详细解决方案

1. 把 MinIO 启动参数改为 `--console-address ":9001"`。
2. 拆分 `compose.dev.yml` 与 `compose.prod.yml`：
   - 开发允许本机映射；
   - 生产只暴露 TLS Gateway，PostgreSQL/MinIO 不映射公共宿主端口。
3. 生产使用 Docker Secret 或外部 Secret Manager，禁止 `.env` 保存真实 Secret。
4. 增加 one-shot migration job；Backend 仅在 migration 成功后启动。
5. 为 Backend、PostgreSQL、MinIO、Gateway 增加可用性 healthcheck、资源 limit/reservation 和 restart policy。
6. TLS 1.2+，明确证书轮换、HSTS、CSP、上传大小和超时。
7. PostgreSQL 与 MinIO 备份采用同一备份批次标识，记录校验和；定期自动 restore drill。
8. 对锁定 digest 执行多架构 pull、SBOM 和漏洞扫描，结果进入发布门禁。

#### 测试与验收

- Compose config 和容器 smoke test 通过。
- MinIO API/Console、Backend readiness 和 Gateway TLS 可用。
- 从空环境迁移、备份、删除环境、恢复后目录版本与对象引用一致。
- 生产网络扫描只能看到 Gateway 端口。
- Secret 不出现在镜像、Compose 展开输出、日志和仓库。

---

### CUR-P1-05：旧功能测试大面积失败但未纳入门禁

#### 现象与证据

- 中心后台额外功能测试：118 通过、60 失败。
- Sidecar 额外功能测试：90 通过、17 失败。
- 主验证脚本未运行这些套件，因此主测试通过不能覆盖这些失败。
- 抽样可见部分失败源于旧构造器和旧接口，也可能混有真实回归。

#### 根因

测试重组后形成“主测试”和“旧功能测试”两套入口，后者没有完成迁移裁决，导致失败长期不影响质量结论。

#### 详细解决方案

1. 导出所有失败 node id，建立逐项表：
   - 对应设计条款；
   - 当前公开接口；
   - 测试期望；
   - 判定为产品缺陷、测试失效、fixture 失效或环境缺失。
2. 产品缺陷先写最小复现，再修代码。
3. 测试失效只有在设计条款和新测试已覆盖相同行为时才能删除；在提交说明中记录替代测试。
4. fixture 统一经公开 factory 创建，禁止依赖已废弃构造器。
5. 所有有效测试合并到标准目录和唯一配置。
6. 添加 collection manifest，测试文件新增或移动后必须被唯一入口收集。

#### 验收标准

- 77 个当前失败全部有可审计裁决。
- 保留的测试全部通过并进入 `verify-all.sh`。
- 不存在“legacy/functional”目录因名称而被门禁排除。
- 删除的每个测试都有设计依据和替代覆盖证明。

---

### CUR-P1-06：真实健康状态没有从进程、队列和 Worker 汇聚

#### 现象与证据

- Sidecar 健康响应中的部分指标仍是常量或占位值，例如 event lag/process pool 状态。
- Rust `system_health` 仍存在硬编码式返回，未汇聚 UDS、Sidecar heartbeat、Credential Broker、Egress、Worker 和数据库实际状态。
- 应用启动后设置健康，但未形成持续监督；Worker 后续退出不能保证反映到系统健康。

#### 影响

- UI 可能显示“健康”，实际 Run、索引或备份 Worker 已停止。
- 自动更新 probation、故障恢复和运维告警会基于错误信号做决定。

#### 详细解决方案

1. 定义统一 Health Snapshot：
   - component、status、last_success、lag、queue_depth、restart_count、error_code、observed_at。
2. Sidecar 实时提供 DB、WriteQueue、Runtime/Analysis/Knowledge/Backup/Event Worker 状态。
3. Rust 汇聚：
   - Sidecar 进程和 heartbeat；
   - UDS session；
   - Keychain/Credential Broker probe；
   - Egress listener；
   - updater probation；
   - 磁盘空间和 Profile lock。
4. 总状态规则固定：
   - 核心 RPC/DB 不可用为 `unhealthy`；
   - 非关键投影落后或 Worker 重启为 `degraded`；
   - 所有必需组件在 SLA 内才是 `healthy`。
5. 每个字段带观测时间，过期数据不得继续显示健康。
6. Desktop 显示可操作错误，不把诊断详情中的敏感路径或凭据直接暴露。

#### 测试与验收

- 杀死每个 Worker、阻塞 WriteQueue、断开 UDS、破坏 Broker、填满磁盘的故障注入测试。
- 健康状态在规定时间内降级，恢复后在稳定窗口内恢复。
- Updater 只在连续健康窗口后标记新版本 stable。
- Health API 不存在固定 `ready/0` 占位返回。

## 8. P2 问题与详细解决方案

### CUR-P2-01：Desktop/Admin 首屏产物过大

#### 证据

- Desktop 构建的 `vendor-antd` 约 1075.72 kB。
- Admin 主产物约 1414.30 kB。
- 构建成功但均出现大 chunk 警告。

#### 解决方案

1. 对路由级页面使用 `React.lazy` 动态加载。
2. 按页面引入图表、编辑器和大型 Ant Design 子模块。
3. 分离 Admin 与 Desktop 不共享的依赖。
4. 使用 bundle visualizer 记录依赖贡献，不仅依赖手工 `manualChunks`。
5. 在 CI 设置 gzip/brotli 首屏预算和单 chunk 预算；超限必须说明并审批。

#### 验收标准

- 以产品性能预算为准，建议首屏关键 JS gzip 不超过 350 KiB、单个非懒加载 chunk gzip 不超过 250 KiB。
- 登录页和基础壳不加载任务图、编辑器和管理目录模块。
- 冷启动指标在受支持最低配置机器上满足设计 SLA。

---

### CUR-P2-02：契约、客户端和方法分类仍有多处手工维护

#### 证据

- Desktop 手工维护 `READ_OPERATIONS`。
- Rust 手工维护部分方法 ownership/kind 分派。
- Admin 手写认证 DTO。
- Sidecar 手写部分 schema 模型和 dispatcher 参数处理。

#### 解决方案

该问题与 CUR-P0-02 共用 Canonical Registry，但需要明确删除重复源：

1. Registry 生成 Rust `MethodMeta`、Python `MethodMeta` 和 TypeScript client。
2. 所有业务调用通过生成 client；页面和 service 不接受任意字符串 method。
3. 生成代码只允许由脚本修改，CI 执行生成后检查 `git diff --exit-code`。
4. 对无法生成的复杂语义校验建立显式 validator hook，但基础字段仍由 schema 生成。
5. 删除手工列表前先用集合相等测试锁定行为，避免迁移期间丢方法。

#### 验收标准

- 一项方法的 owner/kind/schema 只在一个源文件定义。
- 新增方法时，不需要分别编辑 Rust、Python 和 TypeScript 方法列表。
- 任一生成产物被手工改动都会被 drift check 拒绝。

## 9. 推荐整改顺序与依赖

```text
阶段 A：交付门禁止血
  CUR-P0-03 Desktop 明确失败
  CUR-P0-04 CI/覆盖率 fail-closed
  CUR-P1-05 测试套件裁决

阶段 B：契约唯一事实来源
  CUR-P0-02 Canonical Contract Registry
  CUR-P2-02 删除手工契约副本
  CUR-P0-06 Admin 认证协议迁移

阶段 C：本地核心可靠性
  CUR-P0-05 迁移/连接/WriteQueue/Worker
  CUR-P1-06 实时健康汇聚
  CUR-P1-02 业务状态机与 Completion Gate

阶段 D：Runtime Gateway
  CUR-P0-01 API Model Broker/Egress
  CUR-P1-01 CLI Runtime/Seatbelt/Egress

阶段 E：生产交付
  CUR-P1-03 Updater
  CUR-P1-04 生产部署
  CUR-P2-01 前端性能
```

依赖约束：

- CUR-P0-02 应在大规模修复 Desktop/Admin RPC 前完成，否则前端仍会针对不稳定契约重复修改。
- CUR-P0-05 是 CUR-P1-02 和 CUR-P1-06 的基础，状态转换与健康不能继续绕过统一写队列和 Worker Supervisor。
- CUR-P0-01 与 CUR-P1-01 共用 Egress Proxy、进程/Run 生命周期和健康探测，应复用同一 Rust 安全组件。
- CUR-P0-04 必须尽早落地，并贯穿所有后续阶段；每个阶段结束都要在完整门禁中验证。

## 10. 第三方实施时的通用约束

1. 不通过新增未登记 RPC 来快速适配页面；先更新设计和 Canonical Registry。
2. 不允许以 mock/stub 通过生产代码探测；stub 只能存在于测试注入。
3. 不允许通过降低覆盖率阈值、排除文件、跳过工具或忽略空套件让门禁通过。
4. 不根据旧测试盲目回滚正确接口；先完成设计条款映射。
5. 不让 Sidecar、WebView 或日志持有 Provider/API/Refresh 明文凭据。
6. 不允许业务写路径绕过 WriteQueue。
7. 不直接使用系统 `tar`、shell 拼接或未经规范化的文件路径处理更新与工具调用。
8. 每个问题修复提交必须同时包含：
   - 最小复现测试；
   - 实现；
   - 契约/文档同步；
   - 负向测试；
   - 全量门禁结果。

## 11. 最终验收清单

### 11.1 功能闭环

- [ ] API Model 职员通过真实 Broker/Egress 完成含 Tool Call 的任务。
- [ ] Codex CLI、Claude Code、OpenCode 在真实 Workspace 和 Seatbelt 下完成首次、恢复和取消。
- [ ] 公司任务经过总经理确认、部门执行、职员协作 Review、返工、复测和最终报告闭环。
- [ ] 两个公司之间 Task、Conversation、Artifact、Approval、Backup 完全隔离。
- [ ] Admin 可完成登录、刷新、退出、改密和目录管理。

### 11.2 契约

- [ ] J.14 方法集合与 Registry、Rust、Sidecar、Desktop 完全相等。
- [ ] 每个方法有非占位 request/response schema 和正负 fixture。
- [ ] H.4 每个 Domain Event 有 registry 条目、payload schema、生产者、消费者和 Replay 测试。
- [ ] 不存在未知 `$ref` 退化为 `Any/Value`。

### 11.3 安全

- [ ] 凭据不进入 Sidecar、WebView、SQLite、日志、事件和崩溃报告。
- [ ] Egress 拒绝私网、重绑定、重定向绕过和未授权域名。
- [ ] Workspace 外写入只能走一次性 Human Approval + Rust receipt。
- [ ] Updater 拒绝恶意 archive 并可在任意阶段安全恢复。
- [ ] 生产部署不暴露 PostgreSQL/MinIO，不在文件中保存真实 Secret。

### 11.4 可靠性

- [ ] 所有 schema 只由 migration chain 创建和升级。
- [ ] 所有业务写入经过 WriteQueue，备份 barrier 可证明一致性。
- [ ] 所有 Worker 被持续监督，故障实时反映到 Health。
- [ ] 自动更新经过连续健康窗口后才标记 stable。

### 11.5 测试与交付

- [ ] `scripts/verify-all.sh` 在干净环境完整通过且没有 skip/fallback 警告。
- [ ] Rust、Backend、Sidecar、Desktop、Admin 达到约定的 100% 单元测试覆盖率。
- [ ] 77 个旧功能测试失败全部完成裁决并纳入统一门禁。
- [ ] Playwright 关键业务 E2E 不为空且通过。
- [ ] macOS 真实 Seatbelt、更新、签名和安装测试通过。
- [ ] CI 与发布门禁恢复，发布产物绑定已验证 commit SHA。

## 12. 最终判定规则

只有同时满足以下条件，才能把项目状态从“整改中”改为“实现完成”：

1. 本报告 14 个问题均有对应提交、测试和验收证据。
2. 两份核心设计文档与 Canonical Contract Registry、运行时代码不存在方法、字段、状态机或安全边界冲突。
3. 全量验证在干净环境一次通过，且没有因工具缺失、套件为空或覆盖率不足而跳过。
4. 关键业务 E2E、真实 Runtime、故障恢复、升级回滚和生产部署演练均通过。
5. 重新执行独立全量 Review 后没有 P0/P1 未关闭问题。

在达到上述条件前，当前版本应标记为“基础框架和部分业务实现已完成，仍存在核心运行时与交付门禁缺口”，不应对外宣称设计方案已经 100% 落地。
