# AI 公司桌面应用二次全量复核报告

## 1. 报告信息

| 项目 | 内容 |
|---|---|
| 复核基线 | Git `9a158ff` |
| 复核日期 | 2026-07-28 |
| 复核范围 | 两份核心文档、Contracts、Rust Core、Sidecar、Desktop、Admin、Backend、部署与测试 |
| 上一份报告 | `docs/review报告/AI公司桌面应用-当前问题汇总与详细解决方案.md` |
| 架构整改设计 | `docs/设计方案/iBreeze五项核心架构重构设计方案.md` |
| 结论 | 不能确认全部问题已修复 |

## 2. 执行摘要

当前代码相对 `f14425c` 修复了 Desktop 公司路由、部分公司上下文、Admin 登录请求、Worker 基础监控和 MinIO 配置的部分表面问题，但没有关闭上一轮的核心架构缺口。

上一轮 14 个问题状态：

| 状态 | 数量 |
|---|---:|
| 已关闭 | 0 |
| 部分修复 | 5 |
| 未修复 | 9 |

“已关闭为 0”并不表示没有任何有效改动，而是每个问题的原始关闭标准仍至少有一项未满足。截图列出的五项复杂问题全部仍然成立。

## 3. 实际验证结果

### 3.1 通过项

| 检查 | 结果 |
|---|---|
| Contracts JSON Schema 语法 | 266 个通过 |
| Rust fmt/clippy | 通过 |
| Rust 测试 | 94 项通过 |
| Backend lint/typecheck | 通过 |
| Backend 测试 | 204 项通过 |
| Desktop lint/typecheck | 通过 |
| Desktop 测试 | 39 项通过 |
| Admin lint/typecheck | 通过 |
| Admin 测试 | 16 项通过 |
| Contract drift | 通过 |
| Desktop/Admin build | 通过 |

### 3.2 失败项

| 检查 | 实际结果 | 判定 |
|---|---|---|
| `scripts/verify-all.sh` | 在 Rust coverage 阶段失败 | 全量门禁未通过 |
| Rust coverage | 本机缺 `cargo-llvm-cov` | 无覆盖率证明 |
| Sidecar lint | 2 个未使用 import | 失败 |
| Sidecar mypy | 3 个泛型类型错误 | 失败 |
| Sidecar pytest | 1113 通过、1 跳过 | 测试行为通过 |
| Sidecar coverage | 76.43%，当前阈值 77% | 失败 |
| Backend coverage | 62.89% | 远低于设计 100% |
| Desktop coverage | statements 9.83% | 远低于设计 100% |
| Admin coverage | statements 2.61% | 远低于设计 100% |
| 根级测试 | 148 通过、24 失败 | Python import 环境未正确配置 |
| Playwright E2E | 没有任何 `.spec.ts` | 无端到端证明 |
| CI | 最新提交删除全部 workflow | 与设计冲突 |

### 3.3 测试入口缺陷

`scripts/verify-all.sh` 存在以下问题：

1. `required_tools` 未包含 `uv`、`cargo-nextest`、`cargo-llvm-cov`。
2. `cargo-nextest` 缺失时仍回退，违反固定工具链要求。
3. Backend/Sidecar coverage 阈值仍是 62/77，而文档要求 100%。
4. 根级测试使用系统 `python3`，没有安装 pytest 或 Sidecar package。
5. E2E 文件为空。
6. `.github/workflows` 是本机残留空目录；Git 不会提交空目录，干净 clone 中 `test_workflows_directory_exists` 会失败。
7. CI policy 测试遇到 workflow 列表为空时直接 return，无法证明 workflow 完整。

## 4. 上一轮问题逐项复核

### CUR-P0-01：API Model Runtime Broker 与 Egress

状态：**未修复**

证据：

- `sidecar/ibreeze/runtime/transport.py` 仍默认创建 stub `ReverseRpcClient`。
- 真实 UDS 路径仍抛出 `NotImplementedError`。
- Rust `credential.http.start/cancel` 固定返回 `CREDENTIAL_BROKER_NOT_OPERATIONAL`。
- `credential.probe` 固定返回 false。
- Egress Broker 只分配空闲端口后释放，没有监听器、CONNECT tunnel 或认证。

影响：API Model 职员不能执行真实任务；CLI 也无法获得可信网络边界。

处理：按《iBreeze五项核心架构重构设计方案》第 6–8 节整体重写。

### CUR-P0-02：RPC 与 Domain Event 契约

状态：**未修复**

实测：

- 方法 schema 文件：241。
- 根对象 `properties` 为空：76。
- `review.submit.request` properties：0，required：0。
- Domain Event payload schema：只有 `knowledge.imported`、`knowledge.removed`。
- Rust/Python/TypeScript 仍维护手工方法集合。
- Desktop 仍调用 Registry 外的 `planVersion.*`、`orchestration.*`。

Contract lint 通过只证明 JSON 文件语法合法，不能证明业务契约完整。

处理：按目标架构第 4–6 节建立单一 Registry、完整 schema、生成器和运行时验证。

### CUR-P0-03：Desktop 路由与 RPC

状态：**部分修复**

已修：

- 公司路由已改为 `/companies/:companyId`。
- 多数页面已从路由读取 company id。

未修：

- `planVersion.list` 仍不存在于公开契约。
- `orchestration.list/listRuns/create/run/archive` 仍不存在于公开契约。
- Approval `decision` 仍发送 `approved/rejected`，设计要求 `allow/deny`。
- Approval 缺少 `expected_version`。
- 页面直接 `invoke` 时使用 `idempotencyKey`，Rust Command 参数应为 `idempotency_key`。
- `READ_OPERATIONS` 仍为手工列表并包含 Registry 外方法。

处理：删除 Registry 外 Hooks/页面入口，所有调用改用生成 Client。

### CUR-P0-04：验证、覆盖率与 CI

状态：**未修复**

证据见第 3 节。最新提交 `9a158ff` 删除全部 GitHub workflow，与两份核心文档的强制 CI 要求冲突。

处理：

- 恢复或建立同等不可绕过 CI；
- 固定工具链；
- 五个代码域覆盖率 100%；
- E2E 非空；
- 所有失败 fail-closed。

### CUR-P0-05：数据库、WriteQueue 与 Worker 生命周期

状态：**部分修复**

已修：

- Application 开始把 WriteQueue 注入 RPC/Worker。
- Analysis/Runtime Worker 增加基础 alive/heartbeat。

未修：

- `LocalDB.initialize()` 仍先执行 `_CREATE_TABLES_SQL`，Migration 不是唯一 DDL。
- `LocalDB` 自带读池，Application 又创建第二套 ReadPool。
- `_idempotent_call` 仍直接 `BEGIN IMMEDIATE` 并明确标注 WriteQueue 后续集成。
- Worker 仍存在直接写路径。
- 只启动 Analysis/Runtime 两个 Worker。
- Worker 只更新 alive，没有完整重启、lag、错误和健康监督。
- 启动顺序仍是先初始化整库后 Migration。

处理：按目标架构第 10–11 节删除旧数据库入口，重建 Persistence Kernel。

### CUR-P0-06：Admin 认证协议

状态：**部分修复**

已修：

- Login 改为 `identifier/password/device_id`。
- Access Token 只保存在 Zustand 内存态。
- Refresh 使用 Cookie，不再把 Access Token 作为 refresh token。

未修：

- 每次登录重新生成 device id，没有稳定设备标识。
- Refresh 成功后读取 `data.access_token/data.user`，后端使用统一 `data.data` envelope。
- Login/API Client 没有实际使用生成的 OpenAPI DTO。
- 认证流程缺少集成测试。

处理：消费生成 OpenAPI Client，固定稳定 device id 和统一 envelope parser。

### CUR-P1-01：CLI Runtime、Seatbelt 与 Egress

状态：**未修复**

证据：

- CLI Egress 依赖的 Proxy 未实现。
- Seatbelt 没有完整 Workspace 动态策略和每 Run 端口。
- Process 注册反向通知 handler 为空。
- 取消、进程组回收、代理撤销、Prompt 清理和 Resume 未形成同一生命周期。
- CLI Adapter 仍有重复职责。

处理：按目标架构第 8–9 节重建 Runtime。

### CUR-P1-02：Review 与完成状态机

状态：**部分修复**

已修：

- CompletionGate 已有 Employee/Department/Company 查询。
- Run 完成路径会调用部分 Gate。

未修：

- Run 完成函数仍直接 SQL UPDATE EmployeeTask/DepartmentTask/CompanyTask。
- 直接把 EmployeeTask 设置为 `submitted/needs_review/needs_rework`。
- Department/Company 也直接判断后设置状态，没有统一 Command Handler。
- 状态、Domain Event、Outbox、幂等结果不在统一 Unit of Work。
- `review.submit` 没有驱动权威状态转换。
- Artifact supersede、旧 Review stale 和返工 attempt 仍未完整整合。

处理：按目标架构第 12 节重建 Review/Completion Engine。

### CUR-P1-03：Updater 安全

状态：**未修复**

签名和 hash 校验已存在，但安全解包、staging 原子切换、恶意 archive 防护、健康 probation 和自动 rollback 仍未达到上一报告关闭标准。

### CUR-P1-04：生产部署

状态：**未修复**

- 两个 Compose 的 MinIO 仍使用容器内 `--console-address ":51901"`，映射目标为 9001。
- 仍没有正式 dev/prod 分离、Secret、只暴露 Gateway、资源限制和恢复演练。

### CUR-P1-05：测试套件漂移

状态：**未修复**

- 根级 24 项因 Sidecar import 环境失败。
- E2E 为空。
- 主测试与根级测试仍不是同一锁定运行环境。
- Sidecar 测试本身通过，但 lint/type/coverage 失败。

### CUR-P1-06：实时 Health

状态：**部分修复**

已修：

- Sidecar Health 开始计算 event loop lag、DB 和 queue depth。
- Worker 增加基础 heartbeat。

未修：

- Rust `system_health` 仍硬编码 healthy。
- Sidecar process pool 可能为 unknown。
- Credential/Egress Broker 无真实探测。
- Health monitor 不监督 UDS、磁盘、Outbox、Knowledge、Backup 等组件。
- Worker 崩溃没有完整重启和失败阈值。

### CUR-P2-01：前端包体

状态：**未修复**

- Desktop `vendor-antd` 约 1075.72 kB，gzip 337.73 kB。
- Admin `vendor-antd` 约 1081.39 kB，gzip 339.51 kB。
- 构建继续产生超过 500 kB 警告。

### CUR-P2-02：手工契约副本

状态：**未修复**

Desktop `READ_OPERATIONS`、Rust 方法分派、Sidecar handler 参数和 Admin 认证 DTO 仍有手工维护路径。

## 5. 新发现问题

### NEW-P0-01：整改提交引入 Sidecar 静态检查回归

- `sidecar/ibreeze/application/app.py` 导入未使用 `time`。
- `sidecar/ibreeze/workers/runtime.py` 导入未使用 `time`。
- 两个文件存在 3 项 mypy 泛型类型错误。

这些问题使主验证在进入测试前即失败。

### NEW-P0-02：CI Policy 测试存在本机空目录假通过

最新提交删除 workflow 后，本机仍残留 `.github/workflows` 空目录，导致目录存在测试通过；Git 干净 clone 不会包含空目录。其余 policy 测试在没有 workflow 时直接 return。

该测试无法验证 CI 存在，更无法验证八个必需 workflow。

### NEW-P1-01：Admin Refresh 响应解析回归

Login 使用 `data.data`，Refresh 使用 `data`。两条认证路径对同一个后端 envelope 作出不同解释，真实 refresh 后会把 undefined 写入认证状态。

### NEW-P1-02：测试构建修改被跟踪的 `tsconfig.tsbuildinfo`

Desktop build 会把生成 RPC 声明加入已跟踪的 build info，说明生成文件、tsconfig include 和缓存文件版本控制策略不一致。`tsconfig.tsbuildinfo` 应从 Git 删除并加入 `.gitignore`，构建不得污染工作树。

## 6. 文档一致性

两份核心文档：

- 未发现 `Review 问题汇总`、`review 结论`、上一轮清单或临时迭代批注。
- 产品边界、Rust/Python 分工、公司数据本地化、API Model Agent Loop、CLI Adapter、Review 原则整体一致。
- 当前主要矛盾是代码没有达到文档要求，不是两份核心文档互相冲突。

五项复杂问题的固定目标架构已写入：

`docs/设计方案/iBreeze五项核心架构重构设计方案.md`

## 7. 最终结论

当前版本不能关闭上一轮 Review，也不能作为符合设计方案的最终交付。

下一步必须按全新项目一次性重构：

1. Canonical Contract Registry；
2. Duplex UDS、Credential HTTP Broker、CONNECT Egress；
3. 全新 SQLite Persistence Kernel；
4. CLI Runtime/Seatbelt/Process Supervisor；
5. Review/Completion 状态机；
6. 生成客户端、真实 Health 和 fail-closed 测试门禁。

在目标架构的完成定义全部满足前，不得再次声明“所有问题已经修复”。
