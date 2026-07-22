# iBreeze AI 公司桌面应用设计方案

版本：1.0

文档状态：正式设计基线

目标读者：产品、架构、客户端、服务端、测试、运维及第三方实施团队

首发客户端：macOS Apple Silicon

### 文档规范

本文档是 iBreeze 代码库的唯一目标设计。正文定义产品行为和架构边界，规范性技术附录定义唯一实现方案；二者具有同等约束力。

关键词解释：

- **必须**：实现和测试均不可省略。
- **禁止**：实现中不得出现对应行为。
- **固定**：不得由开发者替换技术或参数；变更必须先修改本文档。
- **默认**：产品初始值，用户只能在本文档明确给出范围时修改。

本文档没有“建议实现”“可自行选择”“或等价方案”。第三方开发团队若发现本文档未覆盖的实现决策，必须先补充设计并通过 Review，不能在代码中自行决定。

## 1. 产品定义

iBreeze 是一个以“模拟公司运作方式”组织多个 Agent 协作完成任务的桌面应用。应用中的公司、部门、总经理、部门负责人和职员均为 Agent 工作流概念，不代表真实企业、客户组织或租户。

用户在本地创建多个模拟公司，为公司配置部门和职员，再通过公司级会话向总经理提出任务。总经理负责分析、编排、拆分和分派；部门负责人负责部门内计划与协作；职员调用 Codex CLI、Claude Code、OpenCode 或 API Model 完成执行与交叉 Review；最终由部门负责人和总经理逐级汇总、修复和验收。

产品由两个独立交付物组成：

1. **iBreeze 桌面客户端**：保存全部公司业务数据，运行任务编排与 Agent Runtime。
2. **iBreeze 管理后台服务**：提供用户认证以及全局 Agent、模型、API Provider、Skill 和兼容规则目录，不保存桌面业务数据。

## 2. 目标与非目标

### 2.1 产品目标

- v1 内置并验收 Codex CLI、Claude Code、OpenCode 三种 CLI 职员底座。新增其他 CLI 必须随桌面客户端发布新的内置 Adapter，并在后台目录声明最低客户端版本；禁止仅靠后台下发任意命令模板动态执行未知 Agent。
- 支持 API Model 作为职员模型底座，由 iBreeze Built-in Agent Runtime 驱动完整 Agent Loop。
- 支持同一任务由多个不同 Agent 协作产出、交叉 Review、修复和复测。
- 用公司、部门、职员和逐级汇报表达可理解、可观察、可恢复的 Agent 编排。
- 支持多个本地公司，并在数据、会话、知识、Workspace 和运行上下文层面严格隔离。
- 让总经理根据公司介绍和内部业务流转说明安排部门任务。
- 让部门负责人根据部门职能说明组织本部门工作。
- 由独立后台统一发布 Agent、模型、Provider、Skill 和兼容性基础目录。
- 保证任务的计划、确认、执行、Review、修复、测试和报告均有可追溯证据。

### 2.2 明确非目标

- 不建立真实企业组织、客户组织、租户或多租户 SaaS 模型。
- 不把公司、部门、职员实例、任务、会话、报告、知识或 Workspace 上传后台。
- 不在后台执行用户任务或托管 Agent 运行进程。
- 不设计预算、费用审批或成本配额功能。
- 未确认公司级计划时只允许总经理执行 `company_plan` 分析 Run；禁止启动部门执行、Review、修复、验证、合并或汇总 Run。
- 不把普通多模型聊天作为产品主流程。
- 不依赖 Prompt 实现公司隔离、文件权限或工具权限。

## 3. 核心设计原则

1. **本地业务事实来源**：桌面客户端是公司、任务和会话数据的唯一事实来源。
2. **后台基础目录事实来源**：管理后台是用户、Agent、模型、Provider、Skill、兼容规则和目录发布的唯一事实来源。
3. **公司是最高业务隔离边界**：不同公司之间不共享任务上下文、会话、知识、职员实例或文件。
4. **职责驱动而非名称驱动**：总经理按部门职能和交付能力分派任务，不在代码中硬编码“架构部”“开发部”等名称。
5. **计划先于执行**：总经理先给出计划，用户确认后才创建可执行部门任务。
6. **执行者同时参与 Review**：部门任务参与职员均进入交叉 Review 池，不维护独立 Review 职员池；任何人不得 Review 自己的产物。
7. **运行快照不可漂移**：任务启动时锁定公司说明、部门职能、职员底座、模型、Skill、工具权限和目录版本。
8. **权限由执行层强制**：Workspace 内默认可读写，Workspace 外默认只读；越界写入必须逐目标授权。
9. **适配器可替换**：编排领域模型不依赖任何 Agent CLI 或模型厂商的内部对象。
10. **证据驱动完成**：没有可验证产物、测试结果、Review 问题关闭记录和最终报告，任务不得完成。

## 4. 数据归属与信任边界

| 数据或能力 | 桌面客户端 | 管理后台服务 |
|---|---|---|
| 应用用户与管理员账号 | 保存登录令牌引用 | 唯一事实来源 |
| 公司、介绍和业务流转 | 唯一事实来源 | 不接收、不保存 |
| 部门、职能和职员实例 | 唯一事实来源 | 不接收、不保存 |
| 任务、会话、报告和审计 | 唯一事实来源 | 不接收、不保存 |
| Workspace、文件和知识 | 唯一事实来源 | 不接收、不保存 |
| API Key、CLI 登录态 | Keychain 或 CLI 自有凭据区 | 不接收、不保存 |
| Agent、模型和 Provider 目录 | 签名缓存 | 唯一事实来源 |
| Skill 包和版本 | 安装缓存 | 唯一事实来源 |
| 兼容规则和紧急禁用 | 执行已同步规则 | 唯一事实来源 |

后台不得提供上传本地业务数据的接口。客户端的诊断导出默认只生成本地文件，由用户自行决定是否发送。

## 5. 总体架构

```text
┌──────────────────── iBreeze 桌面客户端 ────────────────────┐
│ React + TypeScript                                          │
│        │ Tauri Command / Event                              │
│ Rust Desktop Core                                           │
│ ├─ Window / Keychain / File Grant                           │
│ └─ Python Sidecar Supervisor                                │
│        │ authenticated local IPC                            │
│ Python Sidecar（单进程）                                    │
│ ├─ Local Application Service                                │
│ │  ├─ Company / Department / Employee                       │
│ │  ├─ Conversation / Task / Artifact / Review               │
│ │  └─ Catalog Cache / Knowledge / Audit / SQLite            │
│ ├─ Agent Orchestration Platform                             │
│ └─ Agent Runtime Gateway                                    │
│    ├─ Built-in Agent Runtime                                │
│    ├─ Codex / Claude Code / OpenCode Adapter                │
│    ├─ Model Transport Adapter                               │
│    └─ Tool / Permission / Workspace / Checkpoint            │
└─────────────────────────────────────────────────────────────┘
                         │ HTTPS
                         ▼
┌────────────── iBreeze 管理后台服务 ─────────────────────────┐
│ Admin Web                                                   │
│ Backend API                                                 │
│ ├─ Authentication / User Administration                    │
│ ├─ Agent / Model / Provider Catalog                         │
│ ├─ Skill Registry / Compatibility                           │
│ ├─ Catalog Release / Distribution                           │
│ └─ Admin Audit                                              │
│ PostgreSQL + S3-Compatible Object Storage                   │
└─────────────────────────────────────────────────────────────┘
```

桌面端固定只有一个 Python Sidecar 进程。本地领域服务、Agent Orchestration Platform 和 Agent Runtime Gateway 是该进程内的三个模块，不允许拆成三个独立进程。CLI Agent 是 Sidecar 监管的子进程。管理后台不参与本地任务调度或执行。

固定技术栈：

| 交付物 | 技术基线 |
|---|---|
| 桌面 UI | React 19、TypeScript 5.7、Vite 6、TanStack Query 5、Zustand 5 |
| 桌面壳 | Tauri 2、Rust 2021、Tokio 1 |
| Sidecar | Python 3.12、asyncio、Pydantic 2、aiosqlite、LanceDB、ONNX Runtime |
| 管理后台 API | Python 3.12、FastAPI、SQLAlchemy 2 Async、asyncpg、Alembic |
| 管理后台数据 | PostgreSQL 16、S3 API；参考部署固定使用 MinIO |
| 管理后台 UI | React 19、TypeScript 5.7、Vite 6、Ant Design 5、TanStack Query 5 |
| 密码与令牌 | Argon2id、Ed25519 JWT；目录签名使用独立 Ed25519 密钥 |
| 契约 | OpenAPI 3.1、JSON-RPC 2.0、JSON Schema 2020-12 |
| 测试 | Vitest、Testing Library、pytest、cargo test、Playwright、Schemathesis |

### 5.1 桌面组件职责

- **React UI**：展示公司、会话、任务、运行状态和管理页面，不直接访问数据库、Keychain 或 CLI。
- **Rust Desktop Core**：负责桌面系统集成、Keychain、文件授权、本地进程监管和前端 IPC。
- **Local Application Service**：负责本地领域模型、事务、编排、会话投影、目录缓存和审计。
- **Agent Runtime Gateway**：负责 CLI/API Model 的统一执行、权限、Workspace、工具、事件和恢复。

### 5.2 后台组件职责

- **Authentication Service**：应用用户注册登录、管理员登录、Token 颁发和撤销。
- **User Administration**：两类用户的管理与保护账号约束。
- **Catalog Service**：维护 Agent、模型、Provider 和 Skill 元数据。
- **Compatibility Service**：维护 Agent—版本—模型—Skill 兼容矩阵。
- **Distribution Service**：发布带签名的不可变目录快照和 Skill 包。
- **Admin Audit Service**：记录所有后台管理操作。

## 6. 用户与认证

### 6.1 用户类型

`users.user_type` 只能取：

- `admin`：登录管理后台；只能在后台用户管理模块中创建和管理。
- `app_user`：登录 iBreeze 桌面客户端；可公开注册，也可由管理员创建。

两类用户不属于任何组织或租户。后台数据库不得出现 `organization_id`、`tenant_id` 或真实公司归属字段。

### 6.2 应用用户注册

注册页面字段：

- 邮箱；
- 密码；
- 确认密码。

规则：

- 不发送邮箱验证码，不要求验证邮箱所有权。
- 邮箱去除首尾空格并转换为小写后唯一。
- 密码长度为 8 至 128 个 Unicode 字符。
- 客户端校验密码与确认密码一致；服务端再次校验密码规则。
- 注册接口固定创建 `app_user`，忽略并拒绝任何 `user_type`、`role` 或管理员字段。
- 密码使用 Argon2id 哈希；日志、审计和错误响应不得包含密码。

### 6.3 登录与令牌

- Access Token 有效期 15 分钟。
- Refresh Token 有效期 30 天，服务端仅保存哈希。
- 桌面客户端把 Refresh Token 与 OfflineSessionTicket 作为一个 session bundle 保存到系统 Keychain 的固定账号项；本地数据库不保存 Token、票据或 Keychain persistent reference。
- 管理后台 Web 只把 Access Token 保存在页面内存；管理员 Refresh Token 使用 `Secure; HttpOnly; SameSite=Strict; Path=/admin/api/v1/auth` Cookie，禁止写入 localStorage、sessionStorage 或 IndexedDB。
- 修改密码、管理员重置密码、禁用用户或“退出全部设备”必须撤销全部 Refresh Token。
- 后台 API 使用独立的管理员登录入口，并验证 `user_type=admin`。
- 应用用户不能访问 `/admin/*`；管理员令牌不能用于桌面业务接口。

### 6.4 默认管理员

首次启动后台数据库迁移时幂等创建：

```text
username = admin
password = admin123456
user_type = admin
protected = true
must_change_password = true
```

约束：

- 账号不可删除、不可禁用、不可修改用户名、不可改为应用用户。
- 首次登录后只能访问修改密码接口；修改成功后方可使用其他后台功能。
- 默认密码可被修改，修改后不得再次自动重置。
- API 与数据库双重约束 `protected=true` 的删除操作。

### 6.5 本地用户隔离

桌面客户端按 `backend_origin + app_user_id` 创建独立本地数据目录。不同应用用户不能打开彼此的 SQLite、Workspace、Skill 私有配置或 Keychain 引用。用户退出登录会撤销服务端 session family 并删除本地 session bundle，但不删除本地业务数据；重新登录同一后台和同一账号后恢复对应本地资料。

## 7. 管理后台基础目录

### 7.1 Agent Catalog

`AgentCatalogRevision` 字段：

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | UUID | 主键 |
| `key` | string | 逻辑 key，如 `codex_cli`；与 `catalog_revision` 组合唯一 |
| `catalog_revision` | integer | 从 1 单调递增 |
| `display_name` | string | 非空 |
| `description` | string | 非空 |
| `status` | enum | `draft/validated/published`；停用通过紧急禁用发布表达 |

每个 Agent revision 包含一至多个 `AgentVersionRange`：

| 字段 | 类型 | 约束 |
|---|---|---|
| `id/agent_id` | UUID | 区间 id 和所属 revision |
| `executable_names` | string[] | 允许探测的可执行文件名 |
| `supported_platforms` | enum[] | `macos_arm64` 等 |
| `min_version` | semver | 非空 |
| `max_version_exclusive` | semver | 非空；首版所有 Agent 都必须声明经过验收的版本上界 |
| `probe_command` | string[] | 固定参数数组，不通过 Shell 解释 |
| `capability_tags` | string[] | `code`、`writing`、`review` 等 |
| `network_domains` | string[] | CLI 自身认证、模型与更新检查所需 HTTPS 域名白名单 |
| `adapter_contract_version` | integer | 客户端内置 Adapter 契约版本 |
| `content_sha256` | SHA-256 | RFC 8785 内容哈希 |

首版正式目录必须包含 Codex CLI、Claude Code 和 OpenCode。

### 7.2 Model 与 Provider Catalog

`ModelCatalogItem` 描述模型身份和能力，不保存用户凭据。关键字段：`provider_key`、`model_key`、`display_name`、`context_window`、`supports_tools`、`supports_streaming`、`supports_vision`、`status`。

`AgentModelBinding` 定义某 Agent 可选择的模型及 Agent 版本范围。`ProviderModelBinding` 定义 API Provider 可调用的模型、API 协议和能力。

客户端展示的最终可用模型为：

```text
后台已发布目录
∩ Agent/Provider 兼容规则
∩ 本机 Agent 版本与认证探测
∩ 本地凭据配置
```

### 7.3 Skill Registry

`SkillVersion` 为不可变发布物，包含：

- `skill_id`、语义版本和显示名称；
- 描述、能力标签和入口说明；
- Skill 包对象存储地址；
- SHA-256 内容哈希和服务端签名；
- 支持的 Agent/API Runtime、模型能力和平台；
- 所需工具、网络域名和文件权限声明；
- 冲突 Skill 与最低依赖版本；
- 风险等级和状态。

已发布版本不能覆盖；任何内容变化必须发布新版本。

### 7.4 兼容规则

兼容规则是可执行数据，不允许客户端根据描述文本猜测。每条规则包含主体类型、主体版本范围、依赖类型、依赖版本范围、结果 `allow/deny`、原因代码和优先级。`deny` 高于 `allow`，紧急禁用高于全部普通规则。

### 7.5 目录发布与同步

目录发布生成一个不可变 `CatalogRelease`：

- 单调递增 `release_sequence`；
- `release_id` 和 `created_at`；
- 全量 manifest；
- 各资源内容哈希；
- Ed25519 签名；
- 最低客户端版本。

紧急禁用是独立的单调递增签名发布流，不修改 CatalogRelease，也不嵌入历史 manifest。客户端同步目录后必须再同步最新 `EmergencyDisableRelease`，运行时以 `max(cached_sequence, fetched_sequence)` 为准，禁止回退。

客户端同步过程：

```text
登录成功
→ 获取 manifest
→ 比较 release_sequence
→ 下载增量资源或完整快照
→ 验证签名、哈希和引用完整性
→ 写入临时目录
→ SQLite 事务切换 active_release
→ 异步执行本机可用性探测
```

任一步失败均保留上一有效快照。后台离线时，已登录过的用户可使用本地数据和最后有效目录继续任务，但不能注册、刷新登录、安装新 Skill 或获取新目录。

## 8. 公司、部门与职员

### 8.1 Company

`Company` 是本地最高业务隔离和编排容器。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | 主键 |
| `name` | string | 1 至 100 字符，当前本地用户内唯一 |
| `introduction` | text | 1 至 20000 字符；公司定位、部门协作关系和内部业务流转说明 |
| `introduction_version` | integer | 每次编辑递增 |
| `general_manager_office_id` | UUID | 唯一总经理办公室 |
| `general_manager_employee_id` | UUID | 唯一总经理 |
| `company_conversation_id` | UUID | 唯一公司级会话 |
| `status` | enum | `active/archived` |
| `created_at/updated_at` | datetime | UTC 存储 |

新增公司必须要求用户输入名称、介绍、总经理名称并选择一个有效职员模型底座。若尚无已发布底座，创建向导必须引导用户先创建底座，不得生成不可运行的占位总经理。

在同一 SQLite 事务中创建公司、总经理办公室、总经理职员实例、公司级会话和总经理办公室部门级会话。总经理办公室的初始职能说明固定为“接收用户任务，依据公司介绍完成需求梳理、计划编排、部门分派、跨部门 Review、问题处理和最终汇报”，用户后续可以补充但不能删除这些职责。任一创建失败则全部回滚。

编辑 `introduction` 必须生成新版本。运行中任务使用其 `TaskContextSnapshot.company_introduction`，不随公司编辑变化。

### 8.2 Department

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | 主键 |
| `company_id` | UUID | 隔离键 |
| `name` | string | 1 至 100 字符，公司内唯一 |
| `type` | enum | `general_manager_office/standard` |
| `function_description` | text | 1 至 10000 字符；职责、输入、输出、上下游和质量要求 |
| `function_version` | integer | 每次编辑递增 |
| `leader_employee_id` | UUID | 唯一负责人 |
| `department_conversation_id` | UUID | 唯一部门级会话 |
| `status` | enum | `active/archived` |

普通部门新增时必须输入名称、职能说明、负责人名称并选择负责人的有效职员模型底座。系统在同一事务内创建部门、负责人职员实例和部门级会话。已有职员只能通过显式调岗流程成为新部门负责人，不能在新建部门事务中跨部门直接复用。总经理办公室不能删除、归档或改为普通部门。

部门职能说明必须被总经理的部门匹配器和部门负责人的计划器读取。任务快照锁定所用说明版本。

### 8.3 DepartmentResponsibility

一个部门可配置多项结构化职责：

- `responsibility_key`；
- 名称与说明；
- `accepted_task_types[]`；
- `required_capability_tags[]`；
- `deliverable_types[]`；
- `default_quality_gates[]`；
- 上游和下游职责引用。

系统提供架构、开发、测试、内容和数据部门模板，但创建公司时只自动创建总经理办公室；其他部门由用户显式创建或从模板实例化。

### 8.4 Employee

职员是某个职员模型底座在具体公司和部门中的实例。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | 主键 |
| `company_id/department_id` | UUID | 归属与隔离 |
| `display_name` | string | 部门会话中显示的名称 |
| `base_profile_version_id` | UUID | 锁定底座版本 |
| `workflow_role` | enum | `general_manager/department_leader/member` |
| `status` | enum | `active/draining/inactive/unavailable` |

同一部门内职员名称唯一。部门负责人和总经理也是职员，不使用单独账号系统。

职员调岗必须在无 active assignment 后执行；否则先进入 `draining`。已运行任务继续使用原归属快照，新任务使用新部门。`employee.updateBaseProfile` 只接受 published 且兼容的底座版本，按 `expected_version` 更新；已创建任务继续使用 `execution_snapshots` 锁定的旧版本，更新只影响更新后新建的 EmployeeTask。`employee.updateDisplayName` 按部门内规范化名称唯一规则更新。除 `company.archive` 的内部级联外，总经理职员禁止调岗、停用或改为其他角色；总经理办公室不接受 `department.setLeader`，总经理只允许改显示名和底座版本，从而始终满足办公室负责人和公司总经理是同一职员。

普通部门 `department.setLeader` 的目标必须是该部门 active 职员。命令在单一事务把旧负责人 `workflow_role` 改为 `member`、目标改为 `department_leader`、更新 `departments.leader_employee_id/version` 并写事件；目标与当前负责人相同按幂等成功返回。旧负责人有 active assignment 不阻止换负责人，因为任务快照不漂移，但不得同时调岗或停用。

## 9. 职员模型底座

### 9.1 类型

`EmployeeBaseProfile.type` 只能取：

- `agent_cli`：选择 Agent Catalog 项和该 Agent 可用模型。
- `api_model`：选择 API Provider 和模型；任务由 Built-in Agent Runtime 驱动完整 Agent Loop。

底座是本地可复用模板，不属于任何公司；职员实例才属于公司。

### 9.2 版本字段

`EmployeeBaseProfileVersion` 包含：

- `profile_id`、版本号、名称和描述；
- 类型及后台目录引用；
- Agent、Provider、模型和参数；
- System Prompt 和角色工作规范；
- Skill 版本锁定列表；
- 工具与网络策略；
- 上下文策略、超时和重试上限；
- Workspace 权限模板；
- 任务能力标签；
- 内容哈希与 `draft/published/retired` 状态。

发布后不可原地修改。升级职员底座必须显式选择新版本；运行中的任务不自动升级。

`profile.retireVersion` 只允许非 current published version，且没有 active/draining Employee 直接引用；它把版本置 retired，使其不能用于新职员或新 `execution_snapshots`，但历史 AgentRun 恢复仍可读取。`profile.retire` 要求没有 active/draining Employee、没有 draft version，并把底座及 current version 置 retired。退休不可逆，历史 Snapshot、Skill 包和 Artifact 保留。

### 9.3 Skill 装配校验

发布底座前必须校验：

1. Agent 或 API Model 在当前目录中已发布。
2. Agent 版本、模型和 Skill 兼容。
3. Skill 所需工具存在且权限模板允许。
4. Skill 之间无拒绝规则或版本冲突。
5. Skill 包已下载且签名、哈希有效。
6. 本机环境满足平台和运行时要求。

任务启动时生成 `ExecutionSnapshot`（表 `execution_snapshots`），锁定所有上述内容。

`catalog.installSkill` 流式下载到 Profile 临时目录，按 G.8 完成全部校验后 fsync、原子 rename 到 `skills/{skill_id}/{version}/{package_sha256}.zip`，再插入 `installed_skill_versions`；失败删除临时文件且不写 installed。紧急禁用只把 installed 状态置 disabled，不删除包。`catalog.removeSkill` 仅在没有任何非 retired 底座版本绑定、没有 `execution_snapshots` 锁定该版本且没有 active Run 时删除数据库行和包；否则返回 `STATE_TRANSITION_INVALID`。删除失败保留数据库行并返回错误，禁止留下“记录已删但文件操作未知”的状态。

## 10. 会话体系

### 10.1 公司级会话

每个公司只有一个公司级会话，参与者为：

- 用户；
- 总经理；
- 各部门负责人；
- 总经理办公室中参与当前任务分析和 Review 的职员。

用户输入直接由总经理接收。总经理必须先分析并展示处理意见和部门分派方案，等待用户确认后执行。

部门负责人完成任务后，在公司级会话发布部门报告。总经理在同一会话发布跨部门问题、返工任务和最终报告。

### 10.2 部门级会话

每个部门只有一个部门级会话，参与者为部门负责人和本部门当前任务参与职员。

参与执行的职员同时构成交叉 Review 池，不单独指定一批固定 Reviewer。系统按产物生成 Review 分配，并保证 Reviewer 不是该产物贡献者。只有一名执行职员且部门负责人没有参与该产物时，由部门负责人 Review；若部门负责人也是唯一贡献者，则必须增加另一名可用参与职员，否则任务进入 `waiting_resource`，不能以自审代替 Review。

### 10.3 消息模型

`ConversationMessage` 关键字段：

- `id/company_id/conversation_id/task_id`；
- `sender_type=user/employee/system`；
- `sender_employee_id`；
- `message_type=user_input/analysis/plan/confirmation/assignment/progress/report/review/system`；
- `content`；
- `artifact_refs[]`；
- `source_event_id`；
- `created_at`。

职员消息在 UI 中显示 `Employee.display_name`，Agent 和模型仅在运行详情中显示。

会话是领域事件的可读投影，不是任务状态事实来源。删除或重建消息投影不得改变任务状态。

`conversation.submitUserMessage` 请求固定含 `company_id/conversation_id/content/target_task_id/supersedes_task_id`，后两个字段互斥且普通公司级输入都为 null。Command Handler 在同一事务写用户消息事件、创建 draft CompanyTask 并把 `user_message_event_id` 绑定该事件；随后异步进入 analyzing 并创建 company_plan Run。只有从待确认计划卡发送“要求修改”时才传 `target_task_id`，目标必须处于 `awaiting_user_confirmation/revision_requested`，此时消息追加到同一 CompanyTask 并生成下一 PlanVersion，不创建新任务。已 approved 或更后状态的任务不能接收计划修改；用户必须先显式取消原任务，再通过“基于此任务重新发起”传 `supersedes_task_id`，目标必须属于同公司且为 cancelled/failed。系统可把用户在确认对话中勾选的原任务需求和 Artifact 引用作为只读输入，但不得改写原 TaskContextSnapshot。

## 11. Agent Orchestration Platform

### 11.1 公司级计划

用户发起任务后的固定门禁：

```text
user_input
→ general_manager_analysis
→ company_plan_draft
→ plan_validation
→ awaiting_user_confirmation
→ approved 或 revision_requested/rejected
```

总经理生成计划时必须加载：

- 用户原始需求；
- 当前 `Company.introduction`；
- 所有 active 部门的 `function_description` 和职责；
- 可用部门负责人和职员能力摘要；
- Workspace 和权限约束；
- 用户给出的验收标准。

计划必须列出目标、非目标、部门任务、依赖、交付物、验收标准、参与职员选择规则、权限请求、失败处理和最终汇总方式。

用户可确认、要求修改或拒绝。未确认前只能创建由总经理职员承担、`run_purpose=company_plan`、Workspace 只读且无外部写工具的 Plan AgentRun；禁止创建 DepartmentTask、EmployeeTask，以及 task_execution/review/verification/repair/merge/summary Run 或任何 Workspace 写入动作。用户要求修改时可再创建下一次 company_plan Run，用户拒绝后不得继续创建 Run。

### 11.2 PlanValidator

PlanValidator 逐条执行下列固定规则；任一失败都返回 `PLAN_VALIDATION_FAILED` 和对应 rule id，不得只返回自然语言：

| Rule id | 拒绝条件 |
|---|---|
| `PV-001` | `goals`、部门任务 `objective`、`deliverables` 或 `acceptance_criteria` 为空 |
| `PV-002` | 引用的部门不存在、非 active，或未命中任何声明职责且未标记总经理办公室临时承接 |
| `PV-003` | DepartmentTask 依赖引用不存在、自依赖或拓扑排序后仍有环 |
| `PV-004` | 部门没有 active 负责人，或参与职员候选集合为空 |
| `PV-005` | 任何 company/department/employee/artifact 引用不属于当前 `company_id` |
| `PV-006` | Workspace 外写入没有规范化绝对目标、动作和预期影响摘要 |
| `PV-007` | 任一交付物未声明 Review 策略和 Review 轮次 |
| `PV-008` | 任一交付物无法分配至少一名非贡献者 Reviewer |
| `PV-009` | 最终汇总阶段没有依赖全部叶子部门报告，或缺少最终验收标准 |
| `PV-010` | 阶段使用未发布底座、未签名 Skill、被紧急禁用项或不满足兼容规则的能力 |
| `PV-011` | 请求的工具、网络或文件权限超出职员底座策略或本产品权限上限 |

### 11.3 部门匹配

部门匹配输入为任务类型、所需能力、交付物类型、质量门禁和公司流转说明。输出包含候选部门、匹配职责和置信说明。总经理可以选择候选项，但必须在计划中记录选择理由。

没有匹配部门时，计划只能提出以下处理方式：

- 用户创建或配置合适部门；
- 用户为现有部门补充职责和职员；
- 由总经理办公室临时承接，并明确缺失能力风险。

### 11.4 部门执行前可用性检查

创建 AgentRun 前，为每名参与职员生成 `EmployeeAvailabilitySnapshot`：

1. 职员和部门为 active。
2. Agent CLI 已安装、版本兼容、认证可用，或 API Provider 凭据有效。
3. 模型、Skill 和本机运行时兼容。
4. Skill 包完整且签名有效。
5. Workspace 和所需工具可用。
6. 本地运行并发槽位可取得。
7. Agent/Provider 健康探测在超时内通过。

任一必需职员不可用时，部门任务进入 `waiting_resource`。负责人只能通过 `departmentTask.replaceEmployee` 选择同部门、active、能力覆盖且探测通过的既有职员，或向总经理上报。若需要改 Agent 或模型，用户必须先发布新底座版本并创建/更新职员，再把该职员作为替代者；禁止给已确认任务临时改写运行快照。替代导致已确认目标、权限、交付物或质量门禁变化时，总经理必须生成新计划并再次请求用户确认。

### 11.5 部门内协作

DepartmentTask 的固定启动顺序为：检查负责人可用性 → 为负责人创建 `interactive_turn` Run 分析目标 → 负责人选择协作策略和参与职员 → 对全部拟参与职员执行 11.4 七项检查 → 在单一事务创建 EmployeeTask 与 ExecutionSnapshot → 调度执行。负责人分析 Run 自身也必须先有 AvailabilitySnapshot/ExecutionSnapshot，不能以“只是分析”为由跳过探测。职员集合或底座变化后，未开始的旧快照保留为未使用证据但禁止被新 Run 引用，必须重新检查；任一 AvailabilitySnapshot 超过 5 分钟不得启动 Run。

支持四种显式协作策略：

- `independent_drafts`：多个职员从同一输入快照独立产出，再综合。
- `section_partition`：按互斥范围分工，合并后整体 Review。
- `primary_with_peer_review`：主执行者产出，其他参与职员交叉 Review。
- `sequential_refinement`：后续职员基于前一不可变快照改进。

负责人选择策略并生成职员子任务。协作过程不能让多个 Agent 无隔离地并发写同一文件。

### 11.6 Review 闭环

`ArtifactReviewAssignment` 包含贡献者、Reviewer、产物快照哈希和轮次。校验器强制贡献者集合与 Reviewer 集合不相交。

`ReviewReport` 必须包含：

- `verdict=pass/needs_changes/failed`；
- 问题严重级别、类别、描述；
- 文件、行号、命令输出或产物引用；
- 期望与实际结果；
- 推荐解决方案；
- Reviewer 和被审快照哈希。

修复生成新产物快照，旧 Review 自动失效。阻断问题未关闭时，部门负责人不得提交完成报告。

### 11.7 报告上报

部门报告必须包含完成项、交付物、验证结果、Review 轮次、已关闭问题、残余风险和证据引用。总经理汇总全部部门报告，执行跨部门一致性 Review；发现问题时创建有归属的返工任务。全部质量门禁通过后生成最终报告。

## 12. 软件需求开发标准工作流

系统内置 `software_requirement_delivery` 模板。模板按职责匹配部门，不依赖部门显示名称。

### 12.1 阶段与依赖

```text
总经理办公室：需求梳理、范围确认、计划与用户确认
  ↓
架构职责部门：需求文档、设计方案、实施计划、文档 Review
  ↓ 文档基线通过
  ├──────────────────────────────┐
  ↓                              ↓
开发职责部门                      测试职责部门
代码实现与单元测试                基于需求和设计编写测试用例
  └───────────────┬──────────────┘
                  ↓
测试职责部门：首轮 Review/测试，输出问题与推荐方案
                  ↓
开发职责部门：修复、补充单元测试、全量代码 Review
                  ↓
测试职责部门：最终回归检测与问题关闭确认
                  ↓
总经理办公室：证据链检查、整体 Review、最终报告
```

### 12.2 阶段完成条件

- 架构阶段：三份文档均通过部门内交叉 Review，需求到设计到计划可追踪。
- 开发首轮：代码编译通过，单元测试通过，实现报告引用对应需求和设计章节。
- 测试设计：测试用例独立来源于需求与设计，形成需求—用例追踪矩阵。
- 测试首轮：每个失败项包含复现步骤、证据、严重级别和推荐修复方案。
- 开发修复：所有接受的问题有修复提交、回归单元测试和全量 Review 结果。
- 测试终轮：首轮问题全部复测，并运行受影响范围的回归测试。
- 总经理终审：部门报告齐全、阻断问题为零、验收项均有证据。

## 13. 任务与状态机

### 13.1 层级

```text
CompanyTask
└─ DepartmentTask[]
   └─ EmployeeTask[]
      └─ AgentRun[]
```

每个下级对象必须继承同一 `company_id`，数据库外键和应用服务均校验，禁止跨公司引用。

### 13.2 CompanyTask 状态

```text
draft → analyzing → awaiting_user_confirmation
awaiting_user_confirmation → approved | revision_requested | rejected
approved → dispatching → checking_resources → executing
executing → reviewing → fixing → final_review → completed
```

辅助状态：`waiting_dependency`、`waiting_resource`、`waiting_permission`、`paused`、`cancelling`、`cancelled`、`failed`。

只有 `final_review` 且全部验收证据满足时可进入 `completed`。

### 13.3 AgentRun 状态

```text
queued → probing → starting → running ↔ waiting_approval
running → verifying → succeeded
```

异常分支：`waiting_resource`、`retrying`、`cancelled`、`timed_out`、`failed`、`lost`。

状态迁移使用乐观版本号和幂等键。非法迁移返回 `STATE_TRANSITION_INVALID`。

### 13.4 DepartmentTask 与 EmployeeTask 状态

`DepartmentTask`：

```text
draft → checking_resources → ready → executing → reviewing
reviewing → fixing → reviewing
reviewing → completed
```

辅助状态：`waiting_dependency`、`waiting_resource`、`waiting_permission`、`cancelled`、`failed`。

`EmployeeTask`：

```text
assigned → ready → running → submitted → peer_reviewing
peer_reviewing → changes_requested → running
peer_reviewing → accepted
```

辅助状态：`waiting_resource`、`cancelled`、`failed`。部门任务只有在全部必需 EmployeeTask 为 `accepted` 且 Review 阻断问题清零后才能完成。

## 14. Agent Runtime Gateway

### 14.1 运行路径

CLI Agent 路径：

```text
Employee(agent_cli)
→ Agent Runtime Gateway
→ Codex/Claude Code/OpenCode Adapter
→ CLI 自身 Agent Loop
→ 标准事件与结果
```

API Model 路径：

```text
Employee(api_model)
→ iBreeze Built-in Agent Runtime
→ Agent Loop / Tool / Permission / Context / Verification
→ Model Transport Adapter
→ API Provider + Model
```

API Model 是职员模型底座；Built-in Agent Runtime 是其任务执行引擎。两者不得混称为同一 Adapter。

### 14.2 从 Codex CLI 抽象的通用能力

- Agent Loop；
- Plan 与 Execute 分离；
- Tool Registry；
- Workspace Sandbox；
- Permission Gateway；
- Context Engine 与确定性压缩；
- 流式事件；
- 会话恢复与检查点；
- Patch、命令输出和证据记录；
- Verification Loop；
- 取消、超时和进程监管。

这些是 iBreeze 自有契约，不复制 Codex CLI 内部代码，也不要求其他 Adapter 暴露其私有对象。

### 14.3 CLI AgentAdapter 契约

```text
probe(config) -> Availability
list_models(catalog, local_config) -> ModelAvailability[]
start(run_spec) -> NativeSessionRef
resume(native_session_ref, run_spec) -> NativeSessionRef
send(input) -> AsyncEventStream
approve(native_approval_ref, decision) -> Result
cancel(reason) -> Result
collect_result() -> AgentRunResult
dispose() -> Result
```

首版实现 `CodexCliAdapter`、`ClaudeCodeAdapter` 和 `OpenCodeAdapter`。每个 Adapter 必须提供版本解析、认证探测、模型映射、事件解析、原生会话恢复、取消和退出码映射。

### 14.4 ModelTransportAdapter 契约

```text
probe(credential_ref, model) -> Availability
complete(messages, tools, options) -> AsyncModelStream
cancel(request_id) -> Result
normalize_usage(native_usage) -> UsageRecord
```

ModelTransportAdapter 不负责任务拆分、工具循环、权限、Workspace、验证或恢复；这些由 Built-in Agent Runtime 负责。

### 14.5 Built-in Agent Runtime

单次 turn 的确定流程：

```text
加载 RunSpec 与 Checkpoint
→ 构建 Context Pack
→ 调用 ModelTransport
→ 若返回工具调用：Permission Gateway 校验
→ Tool Executor 执行并记录证据
→ 将工具结果加入上下文
→ 继续模型调用
→ 产物生成后运行 Verification Commands
→ 未通过则在最大循环次数内反馈修复
→ 保存最终结果与 Checkpoint
```

默认最大工具循环 50 次、最大验证修复循环 5 次；底座版本可向下调整，不能超过应用只读安全上限。

### 14.6 标准事件

所有执行路径必须归一化为：

- `run.started`；
- `model.output.delta`；
- `model.output.compacted`；
- `tool.requested/approved/rejected/started/completed/failed`；
- `workspace.changed`；
- `verification.started/completed`；
- `approval.requested/resolved`；
- `checkpoint.created`；
- `run.completed/failed/cancelled`。

事件 envelope 固定包含 `event_id`、`run_id`、`sequence`、`trace_id`、`occurred_at`、`event_type` 和 `payload`。每种载荷必须有 `packages/contracts/events/{event_type}.v1.schema.json`，`event_type` 未注册或载荷校验失败时 Adapter Run 失败 `ADAPTER_RESULT_MISMATCH`，原生事件只进入脱敏诊断。`sequence` 在单个 Run 内严格递增，`event_id` 为 UUID v4。

## 15. Workspace 与权限

### 15.1 Workspace 隔离

目录结构：

```text
profiles/{app_user_id}/
└─ companies/{company_id}/
   ├─ shared/
   ├─ tasks/{task_id}/
   │  ├─ baseline/
   │  ├─ employees/{employee_id}/
   │  ├─ reviews/
   │  └─ final/
   ├─ knowledge/
   └─ backups/
```

代码任务优先使用 Git Worktree；文档和通用文件任务使用隔离目录和不可变基线。并行职员不能同时写同一路径，合并只能由显式 Merge Task 执行。

### 15.2 默认权限

| 范围 | 权限 |
|---|---|
| 当前 AgentRun Workspace | 读、写、创建、修改、删除 |
| 当前任务共享产物 | 按计划授予只读或合并写入 |
| 其他职员私有执行区 | 不可访问 |
| 其他公司或其他本地用户数据区 | 不可访问 |
| Workspace 外普通文件 | 只读，受操作系统权限限制 |
| Workspace 外写入 | 默认拒绝；按明确路径和单次动作请求用户授权 |
| Keychain、Token、凭据文件 | Agent 不可直接读取；仅 Credential Broker 代用 |
| 系统保护路径 | 不可访问 |

“Workspace 外只读”不覆盖其他 iBreeze 用户、其他公司隔离目录、Keychain 和系统保护路径。

该表是产品权限上限，不代表每个 Run 都取得全部权限；ExecutionSnapshot 必须按 purpose 缩小权限，interactive_turn/company_plan/review/summary 的 Workspace 固定只读，具体执行规则以 I.8 为准。

### 15.3 执行层校验

- 所有路径先解析绝对路径和符号链接，再判定权限。
- Shell 命令在沙箱中执行，工作目录固定为当前 Workspace。
- 对外部写入的批准绑定规范化路径、动作、内容哈希和有效期，防止批准后替换目标。
- 文件变更记录旧哈希、新哈希、操作者、Run 和时间。
- 删除、覆盖外部文件、发布和凭据变更均为逐次批准动作。

## 16. Context、知识与记忆

### 16.1 Context Pack

每次运行只接收经编排平台授权的 Context Pack：

- 任务目标、验收标准和依赖；
- 公司介绍快照；
- 当前部门职能说明快照；
- 职员执行快照；
- 当前会话相关消息摘要；
- 允许读取的产物和知识引用；
- Workspace 和工具权限；
- 上一次 Checkpoint。

Context Pack 包含来源引用和内容哈希，不允许 Agent 自行加载其他公司上下文。

### 16.2 本地知识

原始会话、任务事件和可检索知识分开保存。知识条目必须带 `company_id`、来源、可见范围、内容哈希和生成时间。检索先计算公司和任务权限，再执行全文或向量检索；禁止先跨公司召回再由模型忽略。

### 16.3 会话恢复

CLI Adapter 优先使用原生 session id 恢复。原生恢复失败时，使用标准化转录、确定性摘要和最近 Checkpoint 创建新会话。API Model 底座始终由 Built-in Agent Runtime 使用本地标准上下文恢复。

## 17. 本地持久化模型

### 17.1 核心表

| 表 | 关键职责 |
|---|---|
| `local_profile` | 后台来源与 app_user_id 的本地隔离映射 |
| `companies` | 公司名称、介绍和版本 |
| `departments` | 部门职能、负责人和状态 |
| `department_responsibilities` | 结构化职责 |
| `employee_base_profiles` | 底座身份 |
| `employee_base_profile_versions` | 不可变底座版本 |
| `profile_skill_bindings` | 底座与 Skill 版本锁定 |
| `employees` | 公司职员实例 |
| `conversations` | 公司级和部门级会话 |
| `conversation_messages` | 消息投影 |
| `company_tasks` | 公司任务及确认状态 |
| `department_tasks` | 部门任务与依赖 |
| `employee_tasks` | 职员任务 |
| `task_context_snapshots` | 公司、部门和能力快照 |
| `employee_availability_snapshots` | 执行前可用性证据 |
| `execution_snapshots` | 职员任务不可变运行配置与权限快照 |
| `workspace_grants/task_workspaces` | 文件选择授权以及任务仓库、基线和集成 Worktree |
| `agent_runs` | 运行状态和原生会话引用 |
| `agent_run_events` | 归一化事件流 |
| `checkpoints` | 可恢复检查点 |
| `artifacts` | 产物、哈希和路径 |
| `artifact_contributors` | 产物贡献者 |
| `review_assignments` | 交叉 Review 分配 |
| `review_reports/review_issues` | Review 和问题闭环 |
| `catalog_cache_releases/catalog_cache_resources` | 已验签目录缓存及其资源快照 |
| `catalog_trust_keys/auth_verification_keys` | Catalog 信任链与离线验票公钥 |
| `installed_skill_versions/emergency_disable_cache` | Skill 安装状态与紧急禁用发布缓存 |
| `audit_logs` | 本地操作审计 |
| `outbox_events` | 事务外事件投递 |

### 17.2 通用约束

- 所有业务表使用 UUID 主键和 UTC 时间。
- 公司聚合根和需要按公司直接查询的表必须带 `company_id`；纯子表可以经唯一父外键继承 company scope。任何同时引用两个公司业务对象的表必须用含 `company_id` 的组合外键，或在同一 Command 事务中显式断言两者 scope 相同并由测试覆盖，禁止只依赖 UUID 全局唯一性推断隔离正确。
- 可变聚合带 `version` 实现乐观并发控制。
- 写命令带 `idempotency_key`，相同键和相同请求返回原结果；相同键不同请求返回冲突。
- SQLite Schema 变更全部通过 `sidecar/migrations/YYYYMMDDHHMMSS_description.sql`。
- 迁移使用 `CREATE ... IF NOT EXISTS`；增加列前检查 `PRAGMA table_info`。

## 18. 后台持久化模型

| 表 | 关键职责 |
|---|---|
| `users` | 两类用户、保护标识和密码哈希 |
| `refresh_token_families/refresh_tokens` | Token 轮换 family、哈希、设备和撤销状态 |
| `api_idempotency` | 后台非认证写请求幂等结果 |
| `agents/agent_versions` | Agent 与版本规则 |
| `models` | 模型能力 |
| `agent_model_bindings` | Agent—模型关系 |
| `api_providers/provider_model_bindings` | API Provider 与模型 |
| `skills/skill_versions` | Skill 元数据和不可变版本 |
| `compatibility_rules` | 兼容与拒绝规则 |
| `catalog_releases/catalog_release_items` | 目录发布快照 |
| `emergency_disable_releases` | 已签名紧急禁用发布 |
| `admin_audit_logs` | 管理操作审计 |

PostgreSQL Schema 不包含公司、部门、职员实例、任务、会话、报告、知识或 Workspace 表。

## 19. 通信与 API

### 19.1 桌面本地 IPC

WebView 只能经 Tauri Command 调用 Rust Core。Rust Core 与唯一的 Python Sidecar 使用应用私有 Unix Domain Socket，权限 `0600`，启动时用一次性 nonce 认证；Local Application Service 与 Runtime Gateway 都是该 Sidecar 进程内模块，不启动第二个 Python 服务进程。

本地 RPC 使用 JSON-RPC 2.0：

```json
{
  "jsonrpc": "2.0",
  "id": "request-id",
  "method": "task.confirmPlan",
  "params": {},
  "meta": {
    "trace_id": "uuid",
    "idempotency_key": "uuid"
  }
}
```

### 19.2 后台公开 API

基础路径 `/api/v1`：

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /auth/logout-all`
- `POST /auth/change-password`
- `GET /auth/keys`
- `GET /catalog/manifest`
- `GET /catalog/keys`
- `GET /catalog/releases/{id}`
- `GET /catalog/releases/{id}/resources/{type}`
- `GET /catalog/agents`
- `GET /catalog/agents/{agent_id}/models`
- `GET /catalog/providers`
- `GET /catalog/providers/{provider_id}/models`
- `GET /catalog/skills`
- `GET /catalog/skills/{skill_id}/versions/{version}/package`
- `GET /catalog/compatibility`
- `GET /catalog/emergency-disables/latest`

`register/login` 无需 Token；`refresh` 只接受请求正文中的 Refresh Token 并执行 G.5 轮换；`logout` 同时要求 Access Token 和当前 Refresh Token；`logout-all/change-password/auth/keys` 以及全部 Catalog 接口要求应用用户 Access Token。任何认证接口都不得接受管理员 audience 的 Token。

### 19.3 后台管理 API

基础路径 `/admin/api/v1`：

- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `POST /auth/change-password`
- `GET/POST /users`
- `GET/PATCH/DELETE /users/{id}`
- `POST /users/{id}/reset-password`
- `POST /users/{id}/revoke-sessions`
- Agent、模型、Provider、Skill 和兼容规则的 CRUD；
- `POST /catalog/validate`；
- `POST /catalog/releases`；
- `POST /catalog/releases/{id}/publish`；
- `POST /emergency-disables`；
- `GET /audit-logs`。

保护管理员删除、禁用、改名或改类型返回 `PROTECTED_USER_OPERATION_DENIED`。

### 19.4 后台响应格式

```json
{
  "data": {},
  "meta": {"request_id": "uuid"},
  "error": null
}
```

成功响应使用上述 envelope。错误响应不使用成功 envelope，固定返回 `application/problem+json` 的 RFC 9457 Problem Details，并包含稳定 `code`、`request_id` 和 `field_errors`；详细格式以附录 G.10 为准。

## 20. 错误码

| 错误码 | 含义 |
|---|---|
| `AUTH_INVALID_CREDENTIALS` | 登录失败，响应不区分账号不存在或密码错误 |
| `AUTH_TOKEN_EXPIRED` | Access Token 过期 |
| `AUTH_USER_DISABLED` | 用户被禁用 |
| `AUTH_EMAIL_EXISTS` | 注册邮箱已存在 |
| `AUTH_PASSWORD_CHANGE_REQUIRED` | 默认管理员必须修改密码 |
| `PROTECTED_USER_OPERATION_DENIED` | 保护管理员操作被拒绝 |
| `CATALOG_SIGNATURE_INVALID` | 目录签名无效 |
| `CATALOG_VERSION_ROLLBACK` | 收到低于当前的目录版本 |
| `CATALOG_ITEM_DISABLED` | 目录项已禁用 |
| `COMPANY_SCOPE_VIOLATION` | 发生跨公司访问 |
| `PLAN_CONFIRMATION_REQUIRED` | 未确认计划试图执行 |
| `PLAN_VALIDATION_FAILED` | 计划结构或依赖无效 |
| `EMPLOYEE_UNAVAILABLE` | 职员可用性检查失败 |
| `REVIEW_SELF_ASSIGNMENT` | 贡献者被安排 Review 自己的产物 |
| `WORKSPACE_ACCESS_DENIED` | 文件权限不足 |
| `EXTERNAL_WRITE_APPROVAL_REQUIRED` | Workspace 外写入需要批准 |
| `AGENT_NOT_INSTALLED` | CLI 未安装 |
| `AGENT_AUTH_UNAVAILABLE` | CLI 或 API 凭据不可用 |
| `AGENT_VERSION_INCOMPATIBLE` | 本机 Agent 版本不兼容 |
| `MODEL_UNAVAILABLE` | 模型不可用 |
| `SKILL_INCOMPATIBLE` | Skill 兼容校验失败 |
| `STATE_TRANSITION_INVALID` | 状态迁移非法 |
| `RUN_RECOVERY_UNCERTAIN` | 无法确定外部副作用是否完成 |
| `IDEMPOTENCY_CONFLICT` | 幂等键与不同请求冲突 |
| `OFFLINE_TICKET_INVALID` | 离线票据签名、绑定、时效或设备校验失败 |
| `PROFILE_VERSION_INVALID` | 底座版本不存在、未发布或与目录不兼容 |
| `NAME_EXISTS` | 规范化后的公司、部门或同部门职员名称已存在 |
| `OPTIMISTIC_LOCK_CONFLICT` | `version/If-Match` 已过期 |
| `LEADER_PROFILE_UNAVAILABLE` | 部门负责人底座当前不可用 |
| `RESPONSIBILITY_CYCLE` | 部门职责或上下游关系存在有向环 |
| `EMPLOYEE_HAS_ACTIVE_ASSIGNMENT` | 职员仍有非终态任务，不能转移或停用 |
| `COMPANY_ARCHIVED` | 已归档公司拒绝新写入或新任务 |
| `PLAN_OUTPUT_INVALID` | Plan Agent 修复两次后仍不符合 Schema |
| `PLAN_VERSION_CONFLICT` | 确认的计划 id、version 或哈希不是当前版本 |
| `CATALOG_REVISION_IMMUTABLE` | 尝试修改已发布目录 revision |
| `ADAPTER_RESULT_MISMATCH` | CLI 退出状态、最终事件或结果文件互相矛盾 |
| `METHOD_NOT_ALLOWED` | IPC 方向或调用方不允许使用该方法 |
| `RUN_LIMIT_REACHED` | Agent Loop 达到工具调用或修复轮次上限 |
| `CONTEXT_REQUIRED_CONTENT_TOO_LARGE` | 不可截断的上下文已超过模型输入容量 |
| `APPROVAL_TARGET_CHANGED` | 审批后目标路径或旧内容哈希发生变化 |
| `REVIEW_ISSUE_TRANSITION_INVALID` | Review 问题状态迁移、负责人或证据不合法 |
| `EVENT_SEQUENCE_INVALID` | 事件游标非法、签名失败或请求了未来序号 |
| `RESOURCE_NOT_FOUND` | 资源不存在，或调用方无权获知其存在 |
| `VALIDATION_FAILED` | 请求字段或契约 Schema 校验失败 |
| `RATE_LIMITED` | 认证或公开接口触发限速 |
| `INTERNAL_ERROR` | 未分类内部异常；只向调用方返回安全摘要和 trace id |

HTTP 接口必须按下表映射；本地专用错误没有 HTTP 状态。未列出的请求字段/Schema 错误统一为 RFC 9457 `VALIDATION_FAILED/422`，资源不存在统一为 `RESOURCE_NOT_FOUND/404`，认证限速统一为 `RATE_LIMITED/429`。

| HTTP 状态 | 错误码 |
|---:|---|
| 401 | `AUTH_INVALID_CREDENTIALS`、`AUTH_TOKEN_EXPIRED` |
| 403 | `AUTH_USER_DISABLED`、`AUTH_PASSWORD_CHANGE_REQUIRED`、`PROTECTED_USER_OPERATION_DENIED` |
| 404 | `RESOURCE_NOT_FOUND` |
| 409 | `AUTH_EMAIL_EXISTS`、`CATALOG_VERSION_ROLLBACK`、`CATALOG_REVISION_IMMUTABLE`、`OPTIMISTIC_LOCK_CONFLICT`、`IDEMPOTENCY_CONFLICT` |
| 422 | `VALIDATION_FAILED`、`CATALOG_SIGNATURE_INVALID`、`SKILL_INCOMPATIBLE` |
| 429 | `RATE_LIMITED` |
| 503 | `CATALOG_ITEM_DISABLED` |

## 21. 崩溃恢复与备份

### 21.1 恢复原则

- 所有状态迁移先写数据库，再通过 Outbox 发布事件。
- 每次工具调用前后保存调用哈希、状态和结果摘要。
- 无外部副作用的步骤可按幂等键自动重试。
- 无法证明是否完成的外部副作用不得自动重放，进入 `waiting_approval`。
- CLI 原生会话恢复后必须校验 company、task、employee 和 Workspace 上下文一致。

### 21.2 启动对账

桌面启动后：

1. 检查数据库迁移和文件目录。
2. 查找非终态 AgentRun。
3. 对账本地子进程、原生 session 和最后 Checkpoint。
4. 可确定恢复的 Run 进入 `retrying` 后恢复。
5. 无法确定副作用的 Run 进入 `waiting_approval`。
6. 重建会话和任务读模型。

### 21.3 备份

- 每日和应用升级前创建本地一致性备份。
- 备份包含 SQLite、已引用 Artifact CAS、目录 manifest 和 Skill 锁文件；不复制用户外部代码仓库或临时 Worktree，代码变更以 Artifact patch/commit 证据恢复。
- 恢复后校验数据库完整性、文件哈希和公司隔离约束。
- 备份不包含 Keychain 明文、CLI 凭据或后台密码。

## 22. UI 信息架构

### 22.1 桌面客户端

未登录路由：

- `/auth/server`
- `/auth/login`
- `/auth/register`
- `/auth/change-password`
- `/offline-unlock`

登录后主导航：

- 公司
- 会话
- 任务
- 职员模型底座
- Agent Runtime
- Skill
- 设置

公司页面支持新建、编辑、归档和切换公司。新增/编辑表单必须包含公司介绍及内部部门业务流转说明。公司详情显示总经理办公室、部门流转、职员可用性和当前任务。

部门页面必须包含部门职能说明、结构化职责、负责人、职员和上下游部门。

会话页面先选择公司，再展示公司级会话与部门级会话。待确认计划以独立卡片显示“确认执行、要求修改、拒绝”操作。

任务页面展示部门依赖图、职员子任务、Review 轮次、问题关闭状态和证据链。

职员模型底座页面明确选择 `Agent CLI` 或 `API Model`，显示后台目录允许状态、本机探测状态、模型和 Skill 兼容结果。

所有时间统一转换为 `Asia/Shanghai` 显示；无时区字符串按北京时间墙钟时间解释。数值统一最多显示两位小数且不补零。

### 22.2 管理后台

主导航：

- 仪表盘
- 用户管理
- Agent 管理
- 模型管理
- API Provider 管理
- Skill 管理
- 兼容规则
- 目录发布
- 管理审计

用户管理显示用户类型、状态、注册时间和最近登录时间。默认 `admin` 显示保护标识并禁用删除、禁用、改名和改类型入口。

目录编辑只产生草稿；只有发布目录版本后客户端才能读取。发布前必须运行引用完整性、版本兼容和 Skill 包签名检查。

## 23. 安全设计

- 后台所有外部通信使用 TLS 1.2 以上。
- 密码使用 Argon2id；Refresh Token 仅存哈希；API Key 仅存桌面 Keychain。
- 登录和注册接口按 IP 与账号标识限速；不使用验证码不等于不做防暴力保护。
- 管理操作使用管理员 Access Token 并写不可修改的审计记录。
- CORS 仅允许配置的 Admin Web 来源；桌面客户端使用原生 HTTPS 客户端。
- Skill 包和目录均验证签名与哈希，压缩包解压必须阻止路径穿越。
- CLI 子进程使用最小环境变量集合，不把无关凭据传入。
- 日志自动脱敏 Authorization、Cookie、密码、Token、API Key 和常见凭据格式。
- 本地 RPC 仅监听应用私有 UDS，不开放 TCP 端口。
- 公司隔离、用户隔离和 Workspace 权限必须有负向测试，不能只测试成功路径。

## 24. 可观测性与审计

### 24.1 本地

统一关联字段：`trace_id`、`company_id`、`task_id`、`department_task_id`、`employee_id` 和 `run_id`。

本地审计记录：公司/部门/职员配置变化、计划确认、任务分派、职员替换、权限批准、工具调用、外部写入、Review 问题状态和任务完成。

运行日志默认保留 30 天，可由用户本地调整；审计日志随公司数据保留。日志不得上传后台。

### 24.2 后台

后台指标只覆盖认证、目录请求、Skill 下载、发布和服务健康。后台不得记录用户公司名称、任务内容、会话内容、Workspace 路径或 Agent 输出。

## 25. 测试策略

### 25.1 单元测试

必须覆盖：

- 公司创建默认资源的事务原子性；
- 公司介绍和部门职能版本锁定；
- 部门职责匹配和依赖图校验；
- 用户确认门禁；
- 职员可用性检查；
- 贡献者与 Reviewer 不重叠；
- 所有任务与 AgentRun 状态迁移；
- Built-in Agent Runtime 的工具循环和验证循环；
- Workspace 内读写、外部只读和外部写入审批；
- 目录签名、同步、回滚拒绝和紧急禁用；
- 注册、登录、令牌撤销和保护管理员约束。

### 25.2 Adapter 契约测试

每个 CLI Adapter 使用可控假 CLI 覆盖：探测、版本、认证、模型列表、流式事件、工具批准、取消、超时、异常退出、原生恢复和转录兜底。

每个 ModelTransportAdapter 使用假模型服务覆盖：流式输出、结构化工具调用、限流、断流、取消和错误映射。

### 25.3 集成测试

- Codex CLI、Claude Code 和 OpenCode 的受支持真实版本矩阵。
- API Model 职员由 Built-in Agent Runtime 完成含工具调用和验证的任务。
- 公司级计划确认后跨部门执行，未确认时零 AgentRun。
- 软件需求标准流程完成两轮测试与修复闭环。
- 后台目录发布、客户端同步、断网降级和恢复。
- 桌面崩溃后的 Run 对账、恢复和不确定副作用处理。
- 不同公司、不同本地用户之间的权限逃逸测试。

### 25.4 端到端测试

完整场景：

```text
注册 → 登录 → 创建职员底座 → 创建公司
→ 创建架构/开发/测试职责部门并招揽职员
→ 在公司会话输入需求 → 查看并确认总经理计划
→ 架构文档 → 开发与测试设计并行
→ 测试首轮 → 开发修复与 Review → 测试终轮
→ 总经理终审 → 最终报告
```

### 25.5 发布门禁

- 单元、契约、集成和端到端测试全部通过。
- TypeScript、Rust、Python 静态检查无错误。
- 数据库迁移从空库和上一正式版本升级均通过。
- 安全负向测试和路径逃逸测试通过。
- 三个 CLI Adapter 真实冒烟测试通过。
- 后台不得出现桌面业务数据写入接口或表。

## 26. 部署设计

### 26.1 桌面客户端

- Tauri 安装包包含 Rust Core 和一个同时承载 Local Application Service、Orchestration 与 Runtime 的 Python Sidecar，不要求用户安装 Python。
- Codex CLI、Claude Code 和 OpenCode 由用户自行安装和登录，客户端负责探测并显示状态。
- 本地数据目录、Workspace 和日志目录在设置页可查看；业务数据库不可通过 WebView 直接打开。
- macOS 包必须完成签名、公证和自动更新校验。

### 26.2 管理后台

正式部署单元：

- `admin-web` 静态站点；
- `backend-api` 无状态服务；
- PostgreSQL；
- S3-Compatible Object Storage；
- TLS 反向代理。

部署时必须配置数据库连接、对象存储、JWT 签名密钥、目录 Ed25519 私钥和允许的 Admin Web Origin。目录签名私钥不得存入数据库或镜像。

数据库首次迁移创建保护管理员。生产部署文档必须明确首次登录使用 `admin/admin123456`，并立即完成强制改密。

## 27. 验收标准

以下条件必须全部满足：

1. 应用用户能以邮箱、密码和确认密码完成无验证码注册，并在后台用户管理中出现。
2. 管理员只能通过后台用户管理模块创建和管理管理员用户。
3. 默认 `admin/admin123456` 可首次登录、必须改密且账号不可删除。
4. 后台能发布 Agent、模型、Provider、Skill 和兼容规则目录。
5. 客户端只接受签名有效的新目录，离线时使用上一有效目录。
6. 后台数据库和 API 不保存本地公司、部门、职员实例、任务、会话、报告、知识或 Workspace。
7. 用户能创建多个相互隔离的本地公司。
8. 公司创建时原子生成总经理办公室、总经理、公司级会话和办公室部门级会话。
9. 公司新增和编辑包含介绍及内部部门业务流转说明。
10. 部门新增和编辑包含部门职能说明。
11. 总经理生成计划时使用公司介绍、部门职能和结构化职责。
12. 用户未确认计划时只运行 Workspace 只读的总经理 company_plan Agent，不创建可执行部门任务或其他 purpose 的 AgentRun。
13. 部门执行前检查全部参与职员的实际可用性。
14. 职员底座支持 `agent_cli` 和 `api_model`，并可绑定版本化 Skill。
15. Codex CLI、Claude Code 和 OpenCode 均可通过统一 Runtime Gateway 完成任务。
16. API Model 作为职员底座时，由 Built-in Agent Runtime 驱动完整 Agent Loop。
17. 同一任务能由多个不同 Agent 协作产出并交叉 Review。
18. 部门任务参与职员同时进入 Review 池，且任何职员不能 Review 自己的产物。
19. 软件需求能完成架构、开发、测试首轮、开发修复、测试终轮和总经理终审闭环。
20. Workspace 内默认可读写，Workspace 外普通文件默认只读，越界写入必须逐目标批准。
21. 不同公司、其他职员私有执行区和其他本地用户数据不可访问。
22. Agent 崩溃或应用重启后能恢复确定性步骤；不确定外部副作用不会被自动重放。
23. 部门报告和最终报告能追溯到产物、测试、Review、修复和复测证据。
24. CLI Agent 不能绕过按 Run 生成的 Egress Broker 直接访问公网，未声明域名连接必须失败。
25. Refresh Token 与 OfflineSessionTicket 以单个 Keychain session bundle 原子轮换，数据库、日志和 WebView 均不能读取其明文。

## 附录 A：固定工程结构

```text
ibreeze/
├─ apps/
│  ├─ desktop/                  # React UI，独立 package.json/package-lock.json
│  ├─ desktop-core/             # Tauri/Rust，含 Keychain、Supervisor、Egress Broker
│  ├─ admin-web/                # 后台 Web，独立 package.json/package-lock.json
│  └─ backend-api/              # FastAPI Python package
│     ├─ pyproject.toml
│     ├─ uv.lock
│     ├─ src/ibreeze_backend/
│     │  ├─ auth/
│     │  ├─ users/
│     │  ├─ catalog/
│     │  ├─ skills/
│     │  ├─ compatibility/
│     │  └─ releases/
│     └─ migrations/
├─ sidecar/
│  ├─ pyproject.toml
│  ├─ uv.lock
│  ├─ ibreeze/
│  │  ├─ application/           # 本地领域服务
│  │  ├─ orchestration/         # 公司/部门编排
│  │  ├─ runtime/               # Gateway、CLI Adapter 与 Built-in Agent Runtime
│  │  ├─ domain/
│  │  ├─ persistence/
│  │  ├─ rpc/
│  │  ├─ events/
│  │  ├─ workspace/
│  │  ├─ artifacts/
│  │  ├─ review/
│  │  ├─ knowledge/
│  │  ├─ backup/
│  │  └─ main.py
│  ├─ migrations/
│  └─ tests/
├─ packages/
│  ├─ contracts/                # OpenAPI、事件、Artifact、Skill 等 JSON Schema
│  ├─ rpc-schema/               # 本地 JSON-RPC 请求/响应 Schema
│  └─ ui/
├─ tests/
│  ├─ contract/
│  ├─ integration/
│  ├─ e2e/
│  └─ security/
└─ docs/
```

## 附录 B：本地调用边界

WebView 只能调用附录 J.14 列出的公开 JSON-RPC 方法。`rpc_request` 先由 Rust Core 按 J.14 的固定所有权表路由：登录前认证、Backend Origin、Profile 打开/关闭由 Rust Core 本地处理，Profile 打开后的业务方法才转发唯一 Sidecar。总经理分析、Plan 生成、部门任务分派、Review 分配、Run 创建、Artifact 合并、知识索引和最终汇总都是 Sidecar 进程内 Application Service 调用 Orchestration/Runtime 模块的内部动作，不注册为公开 RPC，前端不能直接跳过状态机触发。

公开 RPC 的唯一方法名、读写类别和幂等期限以附录 J.14 为准；请求与响应 Schema 的文件布局和生成规则以附录 J.11、J.14 为准。正文其他位置只描述业务行为，不再定义第二份方法清单。

## 附录 C：关键时序

### C.1 用户任务确认与跨部门执行

```mermaid
sequenceDiagram
    participant U as 用户
    participant GM as 总经理
    participant O as Orchestration Platform
    participant D as 部门负责人
    participant E as 参与职员
    U->>GM: 公司级会话输入任务
    GM->>O: 读取公司介绍与部门职能并生成计划
    O-->>U: 展示计划与部门分派
    U->>O: 确认执行
    O->>D: 创建部门任务
    D->>O: 检查全部职员可用性
    O->>E: 分派隔离子任务
    E-->>D: 产物与执行报告
    D->>E: 安排参与职员交叉 Review
    E-->>D: Review 报告
    D-->>GM: 部门最终报告
    GM->>O: 跨部门整体 Review
    GM-->>U: 最终报告
```

### C.2 API Model 职员执行

```mermaid
sequenceDiagram
    participant O as Orchestration Platform
    participant R as Built-in Agent Runtime
    participant M as Model Transport
    participant P as Permission Gateway
    participant T as Tool Executor
    O->>R: AgentRunSpec
    R->>M: messages + tools
    M-->>R: tool call
    R->>P: authorize(tool, target)
    P-->>R: allow/approval/deny
    R->>T: execute
    T-->>R: result + evidence
    R->>M: tool result
    M-->>R: final output
    R->>R: verification loop
    R-->>O: AgentRunResult
```

## 附录 D：不可违反的不变量

1. 后台永远不保存桌面业务数据。
2. 不存在真实组织、租户或跨用户公司共享模型。
3. 每个公司恰有一个总经理办公室、一个总经理和一个公司级会话。
4. 每个部门恰有一个负责人和一个部门级会话。
5. 任何可执行任务都引用已确认的公司级计划版本。
6. 任一任务及其下级对象的 `company_id` 必须一致。
7. 任一 Review 的贡献者与 Reviewer 集合不得相交。
8. API Model 职员必须通过 Built-in Agent Runtime 执行完整 Agent Loop。
9. Workspace 外写入必须绑定明确目标并获得授权。
10. 运行快照中的公司说明、部门职能、底座、模型和 Skill 不随编辑漂移。
11. 阻断 Review 问题未关闭时，部门任务和公司任务不得完成。
12. 默认保护管理员不可删除、不可禁用、不可改名、不可改类型。

## 附录 E：关键 DTO 契约

以下 DTO 是跨模块事实来源。实现可以使用不同语言类型，但字段语义、必填性和枚举值不得自行改变。

### E.1 注册与登录

桌面注册表单包含 `email`、`password` 和 `confirm_password`；调用服务端前校验后两者相等。注册请求：

```json
{
  "email": "user@example.com",
  "password": "password-value"
}
```

注册成功返回：

```json
{
  "data": {
    "user": {
      "id": "uuid",
      "user_type": "app_user",
      "email": "user@example.com",
      "display_name": "user@example.com",
      "status": "active"
    }
  },
  "meta": {"request_id": "uuid"},
  "error": null
}
```

注册成功后跳转登录页，不自动创建公司，也不自动登录。登录请求：

```json
{
  "identifier": "user@example.com",
  "password": "password-value",
  "device_id": "installation-uuid"
}
```

应用登录响应的 `user.user_type` 必须为 `app_user`。管理员登录使用相同字段结构，但 `identifier` 为管理员用户名，并通过 `/admin/api/v1/auth/login` 调用。

桌面登录/刷新成功正文固定为：

```json
{
  "data": {
    "user": {
      "id": "uuid",
      "user_type": "app_user",
      "email": "user@example.com",
      "display_name": "user@example.com",
      "status": "active"
    },
    "access_token": "jwt",
    "access_token_expires_in": 900,
    "refresh_token": "opaque-256-bit-token",
    "refresh_token_expires_in": 2592000,
    "offline_session_ticket": "jwt",
    "offline_session_ticket_expires_in": 2592000
  },
  "meta": {"request_id": "uuid"},
  "error": null
}
```

管理员登录/刷新使用同一 envelope，但 `user.user_type=admin`，正文省略 `refresh_token/refresh_token_expires_in/offline_session_ticket/offline_session_ticket_expires_in`，Refresh Token 仅通过 G.11 规定的 Cookie 下发。所有 token 响应均带 `Cache-Control: no-store` 和 `Pragma: no-cache`。

### E.2 CatalogManifest

```json
{
  "release_id": "uuid",
  "release_sequence": 42,
  "created_at": "2026-01-01T00:00:00Z",
  "minimum_client_version": "1.0.0",
  "resources": [
    {
      "type": "agent_catalog",
      "version": "content-version",
      "sha256": "hex",
      "download_path": "/api/v1/catalog/releases/uuid/resources/agent_catalog"
    }
  ],
  "signature_algorithm": "Ed25519",
  "signature": "base64"
}
```

签名输入为排除 `signature` 字段后、按 RFC 8785 规范化的完整 JSON 字节。

### E.3 CreateCompanyCommand

```json
{
  "name": "产品研发公司",
  "introduction": "说明公司定位、各部门流转顺序和最终汇报方式",
  "general_manager": {
    "display_name": "总经理",
    "base_profile_version_id": "uuid"
  }
}
```

命令结果必须同时返回 `company_id`、`general_manager_office_id`、`general_manager_employee_id`、`company_conversation_id` 和 `office_conversation_id`。任何字段对应对象创建失败均不得返回部分成功。

### E.4 CreateDepartmentCommand

```json
{
  "company_id": "uuid",
  "name": "研发部",
  "function_description": "负责代码实现、单元测试、缺陷修复和代码 Review",
  "responsibilities": [
    {
      "responsibility_key": "software_development",
      "name": "软件开发",
      "description": "按照设计方案实现并验证功能",
      "accepted_task_types": ["software_requirement"],
      "required_capability_tags": ["code", "review"],
      "deliverable_types": ["source_code", "unit_tests", "implementation_report"],
      "default_quality_gates": ["build_passed", "unit_tests_passed"]
    }
  ],
  "leader": {
    "display_name": "研发负责人",
    "base_profile_version_id": "uuid"
  }
}
```

结果必须同时创建部门、负责人和部门会话。

### E.5 EmployeeBaseProfileDraft

CLI Agent 底座：

```json
{
  "name": "Codex 高级开发职员",
  "description": "负责代码实现、单元测试和交叉 Review",
  "type": "agent_cli",
  "runtime_binding": {
    "agent_id": "uuid",
    "agent_version_id": "uuid",
    "model_id": "uuid"
  },
  "system_prompt": "角色工作规范",
  "skill_versions": ["skill-version-uuid"],
  "capability_tags": ["code", "unit_test", "review"],
  "timeout_seconds": 3600,
  "max_retries": 2,
  "workspace_policy": "workspace_rw_external_ro"
}
```

API Model 底座：

```json
{
  "name": "API 架构设计职员",
  "description": "负责需求分析、架构设计和文档 Review",
  "type": "api_model",
  "runtime_binding": {
    "provider_id": "uuid",
    "model_id": "uuid",
    "credential_ref": "keychain-item-id"
  },
  "system_prompt": "角色工作规范",
  "skill_versions": ["skill-version-uuid"],
  "capability_tags": ["architecture", "writing", "review"],
  "timeout_seconds": 3600,
  "max_retries": 2,
  "workspace_policy": "workspace_rw_external_ro"
}
```

`credential_ref` 只在本地保存和解析，不进入日志、目录同步或后台 API。

### E.6 CompanyPlan

```json
{
  "id": "uuid",
  "company_task_id": "uuid",
  "version": 1,
  "company_introduction_version": 3,
  "summary": "需求处理意见",
  "goals": ["明确目标"],
  "non_goals": ["明确非目标"],
  "department_tasks": [
    {
      "local_ref": "architecture",
      "department_id": "uuid",
      "matched_responsibility_keys": ["requirements_and_architecture"],
      "objective": "形成需求、设计和实施计划基线",
      "dependency_refs": [],
      "deliverables": ["requirements_document", "design_document", "implementation_plan"],
      "acceptance_criteria": ["三份文档交叉一致并通过 Review"],
      "required_capability_tags": ["architecture", "writing", "review"],
      "required_external_writes": []
    }
  ],
  "final_acceptance_criteria": ["所有部门报告通过总经理终审"],
  "status": "awaiting_user_confirmation",
  "content_hash": "sha256"
}
```

确认命令必须携带 `plan_id`、`version` 和 `content_hash`。任一值不匹配当前待确认版本时返回 `PLAN_VERSION_CONFLICT`，禁止确认被替换的计划。

### E.7 EmployeeAvailabilitySnapshot

```json
{
  "employee_id": "uuid",
  "base_profile_version_id": "uuid",
  "catalog_release_id": "uuid",
  "agent_or_provider_status": "available",
  "model_status": "available",
  "skills_status": "available",
  "workspace_status": "available",
  "runtime_slot_status": "available",
  "probe_evidence_refs": ["artifact-or-log-ref"],
  "checked_at": "2026-01-01T00:00:00Z",
  "expires_at": "2026-01-01T00:05:00Z",
  "overall_status": "available"
}
```

进入 `starting` 前快照必须未过期；过期则重新探测。

### E.8 AgentRunSpec

```json
{
  "run_id": "uuid",
  "run_purpose": "task_execution",
  "company_id": "uuid",
  "company_task_id": "uuid",
  "department_task_id": "uuid",
  "employee_task_id": "uuid",
  "employee_id": "uuid",
  "conversation_id": "uuid",
  "work_item_id": "uuid",
  "availability_snapshot_id": "uuid",
  "execution_snapshot_id": "uuid",
  "objective": "明确目标",
  "acceptance_criteria": ["可验证条件"],
  "input_artifact_refs": ["uuid"],
  "workspace": {
    "root": "/absolute/managed/path",
    "shared_readonly_paths": [],
    "external_readonly_paths": []
  },
  "tool_policy": "policy-version-id",
  "verification_commands": [["command", "arg1"]],
  "timeout_seconds": 3600,
  "max_retries": 2,
  "idempotency_key": "uuid"
}
```

`run_purpose` 枚举与 H.11 一致。company_plan/interactive_turn/summary 的 `department_task_id/employee_task_id` 为 null；review/verification/repair/merge 的 `employee_task_id` 可为 null，但 `work_item_id` 必须与 ExecutionSnapshot 中对应 Assignment 或 Artifact 的 id 相同；task_execution 两者必填且 `work_item_id=employee_task_id`。`availability_snapshot_id/execution_snapshot_id` 必须通过 H.6 的员工、公司、work item、配置哈希和有效期一致性断言。`conversation_id` 必须属于同公司，后台知识索引作业不创建 AgentRunSpec。

命令以参数数组保存和执行，不拼接为 Shell 字符串；确需 Shell 语法时必须使用专门工具类型并进入权限校验。

### E.9 ExecutionReport 与 ReviewReport

```json
{
  "summary": "执行摘要",
  "completed_items": ["完成项"],
  "deliverable_refs": ["artifact-uuid"],
  "verification_results": [
    {
      "name": "unit_tests",
      "status": "passed",
      "evidence_ref": "artifact-uuid"
    }
  ],
  "residual_risks": [],
  "evidence_refs": ["artifact-uuid"]
}
```

```json
{
  "verdict": "needs_changes",
  "reviewer_employee_id": "uuid",
  "reviewed_snapshot_hash": "sha256",
  "review_round": 1,
  "issues": [
    {
      "severity": "high",
      "category": "functional",
      "description": "问题说明",
      "expected": "期望结果",
      "actual": "实际结果",
      "evidence_refs": ["artifact-uuid"],
      "suggested_fix": "推荐解决方案"
    }
  ]
}
```

严重级别固定为 `blocker/high/medium/low`。`blocker` 或 `high` 未关闭时任务不得完成；`medium` 和 `low` 必须被修复或由部门负责人记录接受理由，并在总经理终审中显式展示。

## 附录 F：进程、依赖与本地通信规范

### F.1 依赖锁定

所有交付物必须提交锁文件：

- 桌面和后台 Web：`package-lock.json`。
- Rust：`Cargo.lock`。
- Sidecar 和后台 API：`uv.lock`。

CI 使用 `npm ci`、`cargo build --locked` 和 `uv sync --frozen`。禁止在 CI 或发布脚本中自动更新依赖。依赖升级是独立变更，必须同时运行单元、契约、集成、安全和打包测试。

直接依赖职责固定如下；精确 patch 版本由首次实现提交的锁文件确定，代码不得引入同职责的第二套库：

| 交付物 | 生产直接依赖 |
|---|---|
| Desktop Web | `react/react-dom` 19、`@tanstack/react-query` 5、`zustand` 5、`react-router` 7、`zod` 3 |
| Admin Web | Desktop Web 同类依赖，加 `antd` 5；不得引入第二套组件库 |
| Rust Core | `tauri` 2、`tauri-plugin-updater` 2、`tokio` 1、`reqwest` 0.12、`httparse` 1、`serde/serde_json` 1、`uuid` 1、`url` 2、`semver` 1、`sha2` 0.10、`hmac` 0.12、`base64` 0.22、`ed25519-dalek` 2、`jsonwebtoken` 9、`security-framework` 3、`nix` 0.29、`secrecy` 0.10、`zeroize` 1、`tracing` 0.1 |
| Python Sidecar | `pydantic` 2、`aiosqlite` 0.20、`lancedb` 0.20、`onnxruntime` 1.20、`tokenizers` 0.21、`tiktoken` 0.8、`tree-sitter` 0.24、`zstandard` 0.23、`semantic-version` 2、`rfc8785` 0.1、`structlog` 24、`psutil` 6 |
| Backend API | 附录 G.1 所列依赖，加 `rfc8785` 0.1；对象存储统一由 `boto3` 访问 |

开发依赖固定为 TypeScript `typescript` 5.7、Vite 6、ESLint 9、Vitest 2、Testing Library 16、Playwright 1；Python `pytest` 8、`pytest-cov` 6、`mypy` 1.14、`ruff` 0.9、`hypothesis` 6、`schemathesis` 3、`testcontainers` 4、`pyinstaller` 6；Rust 使用 `cargo-nextest`、`cargo-llvm-cov`、Clippy。主版本升级必须先修改本文档技术基线。

### F.2 桌面进程拓扑

```text
Tauri WebView
  └─ Tauri Command/Event
Rust Desktop Core
  └─ Unix Domain Socket
Python Sidecar（唯一）
  ├─ Local Application Service
  ├─ Agent Orchestration Platform
  ├─ Agent Runtime Gateway
  ├─ ProcessPoolExecutor Workers
  └─ Codex / Claude Code / OpenCode 子进程组
```

WebView 禁止直接访问文件系统、数据库、Keychain、后台 API 和 CLI。访问后台 API 的 HTTP Client 在 Rust Core 中实现；目录响应经 Rust 验签后才传给 Sidecar。

### F.3 Sidecar 启动

Rust 固定执行：

1. 解析当前登录 Profile。
2. 创建 `${profile}/run/{launch_uuid}`，权限 `0700`。
3. 生成 32 字节 CSPRNG 启动令牌。
4. 创建 UDS 路径 `${run_dir}/sidecar.sock`。
5. 以参数数组启动 Sidecar：`ibreeze-sidecar --socket {path} --profile {path} --app-version {version} --protocol-version {version}`。
6. 通过 Sidecar stdin 写入 base64 启动令牌和换行，随后关闭 stdin。
7. 等待 UDS 最长 10 秒。
8. 连接后发送 `system.handshake`。

启动令牌不得出现在 argv、环境变量、日志或磁盘文件中。

`system.handshake` 参数：

```json
{
  "app_version": "1.0.0",
  "protocol_version": 1,
  "launch_id": "uuid",
  "nonce": "base64-32-bytes",
  "proof": "base64-hmac-sha256"
}
```

`proof = HMAC(startup_token, app_version || protocol_version || launch_id || nonce)`。Sidecar 验证后清除内存中的启动令牌，只保留随机 `ipc_session_id`。

### F.4 UDS 与帧

- UDS 父目录 `0700`，Socket `0600`。
- 仅允许一个 Rust Core 连接。
- 帧为 4 字节无符号大端长度加 UTF-8 JSON。
- 单帧最大 16 MiB；0 字节和超限立即断开。
- JSON 必须是单个对象，禁止顶层数组和批量 JSON-RPC。
- 大于 1 MiB 的输出正文必须写 Artifact，RPC 仅返回引用。

JSON-RPC 请求必须包含：

```json
{
  "jsonrpc": "2.0",
  "id": "uuid",
  "method": "namespace.action",
  "params": {},
  "meta": {
    "trace_id": "uuid",
    "ipc_session_id": "uuid-or-null",
    "window_session_id": "uuid",
    "idempotency_key": "uuid-or-null"
  }
}
```

读方法的 `idempotency_key` 为 null；写方法必须是 UUID。Rust本地认证与Profile生命周期写方法只用该key合并当前进程内尚未完成的同请求，请求完成立即删除，不持久化密码、Token或响应；用户显式重试必须生成新key。Sidecar业务写方法按J.14期限持久化幂等结果。`ipc_session_id` 仅允许在 Rust 本地方法和首次 `system.handshake` 时为 null；Sidecar业务方法、握手后的Supervisor方法及反向调用必须携带当前session id。Rust收到WebView提供的非当前session id时拒绝请求，且不会把调用方值替换为有效值后继续执行。

RPC 是双向的：Rust 发起的 id 使用 `core:{uuid}`，Sidecar 发起的 id 使用 `sidecar:{uuid}`。Sidecar 只允许反向调用 `credential.http.start`、`credential.http.cancel`、`credential.probe`，并允许发送无 id 的 `runtime.processRegistered/runtime.processExited` 通知；Rust 收到其他反向方法立即返回 `METHOD_NOT_ALLOWED` 并写安全审计。进程通知只接受当前 ipc session，Rust 必须用系统进程信息验证 PID/PGID、可执行路径和 Sidecar 父子关系后才登记。

### F.5 心跳与重启

- Rust 每 5 秒调用 `system.health`，超时 3 秒。
- 连续 3 次失败判定 Sidecar lost。
- 60 秒窗口内最多重启 3 次。
- 每次重启前终止旧进程组并等待退出。
- 第 4 次失败进入诊断页，不继续自动重启。
- 正常退出调用 `system.shutdown`；10 秒未退出执行 SIGTERM，5 秒后执行 SIGKILL。

Sidecar Health 不依赖外部 Agent 或 Provider，返回：

```text
status healthy | degraded | unhealthy
database_status
migration_version
event_loop_lag_ms
write_queue_depth
runtime_queue_depth
process_pool_status
```

### F.6 asyncio 与数据库并发

- Sidecar 主线程只运行 asyncio 事件循环。
- SQLite 写操作进入一个 `asyncio.Queue`，由单写协程串行执行。
- SQLite 读连接池上限 8。
- CLI stdout/stderr 各一个异步读取任务。
- CPU 密集型 embedding、Tree-sitter 解析和摘要后处理进入 `ProcessPoolExecutor`。
- ProcessPool 上限 `min(4, os.cpu_count())`，最少 1。
- CLI 全局并发默认 4，用户配置范围 `1..16`。
- 单个 EmployeeTask 只能有一个 active Run。
- 单个会话线程只能有一个 active turn。

### F.7 后台 HTTP Client

Rust 使用 `reqwest`：

- connect timeout 5 秒；
- request timeout 30 秒；
- Skill 下载 timeout 10 分钟；
- 最大响应正文 16 MiB，Skill 下载采用流式文件；
- 只跟随同 origin HTTPS 重定向，最多 3 次；
- Access Token 只在 Rust 内存中使用；Refresh Token 和 OfflineSessionTicket 以单个 session bundle 存入 Keychain。

### F.8 在线与离线认证

正常应用登录响应同时返回 Access Token、Refresh Token 和 OfflineSessionTicket；`must_change_password=true` 的受限登录不签发 OfflineSessionTicket，具体响应与权限以 G.11 为准。

OfflineSessionTicket Claims：

```text
iss           Backend Origin 对应 issuer
aud           ibreeze-offline
sub           app_user_id
device_id     本机 installation id
backend_origin
iat
exp           30 天
jti
```

Rust 验证签名、issuer、audience、device、origin 和时间。后台可访问时必须在线刷新，不能主动选择离线进入。后台网络错误且票据有效时允许进入本地 Profile；离线模式禁止用户注册、目录同步、Skill 下载和 API Key 在线探测。

### F.9 本地目录权限

Backend Origin 规范化固定为：仅保留 `scheme://IDNA-ASCII-lowercase-host:effective-port`，禁止 userinfo、path、query 和 fragment；HTTPS 默认端口写为 `443`，开发例外 HTTP 写为 `80`。`profile_directory_id = lowercase-base32(SHA-256(canonical_origin || 0x00 || app_user_id))`，不截断。Rust 只用该值拼接 Profile 路径，并在打开后校验 `local_profile.backend_origin/app_user_id` 完全一致；不一致立即拒绝，不尝试修复或复用目录。

认证响应同时返回服务端生成的 `masked_identifier`：邮箱 local-part 只保留第一个 Unicode scalar value，后接 `***` 和完整 IDNA 规范化 domain，例如 `k***@example.com`；空或非法邮箱响应视为认证契约错误。该值只在成功在线认证后写入 `local_profile.masked_identifier`，仅用于离线 Profile 选择，不参与目录寻址或认证。

```text
profiles/                         0700
profiles/{profile_directory_id}/  0700
profile-meta.v1.json              0600
profile.db                        0600
catalog/                          0700
skills/                           0700
agent-state/                      0700
companies/                        0700
logs/                             0700
backups/                          0700
```

创建文件后立即设置权限，不依赖进程 umask。Sidecar 启动时发现更宽权限时自动收紧并写本地审计。

Rust 用 `profiles/{profile_directory_id}/profile-meta.v1.json` 发现可选 Profile；文件固定为 `{schema_version:1,profile_directory_id,backend_origin,app_user_id,masked_identifier}`，只在成功在线认证后通过同目录临时文件、fsync 和 rename 更新。读取时必须重新规范化 origin、重算 directory id、校验目录 basename 和全部字符串长度，任一不一致就忽略该条并在诊断页显示损坏项。该文件只用于登录前列表展示，不能代替 `local_profile` 校验，也不能授予数据访问；只有对应 Keychain session bundle 存在且 OfflineSessionTicket 验证成功后才可启动该 Profile 的 Sidecar。

macOS Keychain service 固定为 `com.ibreeze.desktop`。账号名固定为 `{profile_directory_id}/session-bundle` 和 `{profile_directory_id}/provider/{credential_ref}`。前者的 value 是 `{schema_version,refresh_token,offline_session_ticket,family_id,issued_at}` JSON；Rust 先在内存校验全部字段，再通过一次 Keychain update 原子替换整个 value，避免 Token 轮换后只保存一半。数据库只保存 Provider 凭据的随机 UUID `credential_ref`，不得保存 Keychain persistent reference 原始字节、Token 或 API Key。删除 Provider 凭据时先删除 Keychain item，再在本地事务把引用置 unavailable；Keychain 删除失败则数据库不变。

## 附录 G：管理后台实施规范

### G.1 Python 依赖

`apps/backend-api/pyproject.toml` 必须包含：

```text
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
asyncpg
alembic
pydantic
pydantic-settings
argon2-cffi
pyjwt[crypto]
boto3
email-validator
semantic-version
python-multipart
structlog
prometheus-client
```

生产代码禁止导入 `sqlite3` 或 `aiosqlite`。后台测试使用 PostgreSQL 16 Testcontainer，不以 SQLite 代替。

### G.2 密码参数

Argon2id 固定参数：

```text
memory_cost = 65536 KiB
time_cost = 3
parallelism = 4
salt_len = 16
hash_len = 32
```

登录时若存量哈希参数低于当前值，验证成功后在同一请求中重新哈希。密码和确认密码不能写日志、审计、异常详情或指标标签。

### G.3 PostgreSQL 用户 DDL

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    user_type VARCHAR(16) NOT NULL
        CHECK (user_type IN ('admin', 'app_user')),
    username VARCHAR(64),
    email VARCHAR(320),
    password_hash TEXT NOT NULL,
    display_name VARCHAR(320) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_login_count >= 0),
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
    CHECK (
        (user_type = 'admin' AND username IS NOT NULL AND email IS NULL)
        OR
        (user_type = 'app_user' AND email IS NOT NULL AND username IS NULL)
    ),
    CHECK (NOT protected OR user_type = 'admin')
);

CREATE UNIQUE INDEX uq_users_username_lower
    ON users (lower(username)) WHERE username IS NOT NULL;
CREATE UNIQUE INDEX uq_users_email_lower
    ON users (lower(email)) WHERE email IS NOT NULL;
CREATE INDEX ix_users_type_status ON users (user_type, status, created_at, id);

CREATE TABLE refresh_token_families (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    revoke_reason VARCHAR(64),
    UNIQUE (user_id, device_id, id)
);

CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY,
    family_id UUID NOT NULL REFERENCES refresh_token_families(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    replaced_by_id UUID REFERENCES refresh_tokens(id),
    revoked_at TIMESTAMPTZ
);

CREATE INDEX ix_refresh_tokens_family_active
    ON refresh_tokens (family_id, expires_at)
    WHERE revoked_at IS NULL;

CREATE TABLE api_idempotency (
    principal_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    method VARCHAR(8) NOT NULL,
    path TEXT NOT NULL,
    idempotency_key UUID NOT NULL,
    request_sha256 CHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK(status IN ('processing','completed','failed')),
    response_status INTEGER,
    response_content_type VARCHAR(100),
    response_body JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(principal_user_id, method, path, idempotency_key)
);
CREATE INDEX ix_api_idempotency_expiry ON api_idempotency(expires_at);
```

### G.4 保护管理员数据库约束

Alembic 创建 Trigger：

```sql
CREATE OR REPLACE FUNCTION protect_system_admin()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.protected THEN
            RAISE EXCEPTION 'protected user cannot be deleted';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.protected THEN
        IF NEW.username IS DISTINCT FROM OLD.username
           OR NEW.user_type IS DISTINCT FROM OLD.user_type
           OR NEW.status IS DISTINCT FROM OLD.status
           OR NEW.protected IS DISTINCT FROM OLD.protected THEN
            RAISE EXCEPTION 'protected user fields cannot be changed';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_protect_system_admin
BEFORE UPDATE OR DELETE ON users
FOR EACH ROW EXECUTE FUNCTION protect_system_admin();
```

初始化迁移生成 UUID，创建 `username=admin/display_name=admin/password=admin123456` 的 Argon2id 哈希，并设置 `protected=true`、`must_change_password=true`。迁移只在不存在 `lower(username)='admin'` 时创建；若存在但不是保护管理员则迁移失败，禁止覆盖。

### G.5 登录限速与 Token 旋转

- Nginx 对 `/auth/login`、`/auth/register` 使用每 IP 每分钟 10 次、burst 5 的限速区。
- 应用层在用户行上执行 `SELECT ... FOR UPDATE`。
- 15 分钟内累计 5 次失败设置 `locked_until=now()+15 minutes`。
- 成功登录清零计数和锁定时间。
- Refresh 时锁定 Token 行；已 consumed Token 再次出现时撤销整个 family。
- 每用户最多 20 个未撤销 family；创建第 21 个时撤销 `last_used_at` 最早的 family。

### G.6 目录 DDL

Agent、Model、API Provider 和 Skill 每一行都代表一个 `catalog_revision`，状态机固定为 `draft → validated → published`。`draft` 可编辑；校验成功进入 `validated`，字段变化必须退回 `draft`；进入任何 published CatalogRelease 后由 Trigger 冻结。修改已发布对象时，管理 API 复制为 `catalog_revision + 1` 的新 draft；Agent 与 Skill 的子版本随父 revision 一起复制或新增。已发布内容需要停用时只能发布签名的 `emergency_disable_release`，不得修改历史目录行。客户端和 CatalogRelease 永远引用具体 row id/version id，不引用 latest。

```sql
CREATE TABLE agents (
    id UUID PRIMARY KEY,
    key VARCHAR(64) NOT NULL,
    catalog_revision INTEGER NOT NULL CHECK(catalog_revision > 0),
    display_name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('draft','validated','published')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(key, catalog_revision)
);

CREATE TABLE agent_versions (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES agents(id),
    min_version VARCHAR(64) NOT NULL,
    max_version_exclusive VARCHAR(64) NOT NULL,
    executable_names JSONB NOT NULL,
    supported_platforms JSONB NOT NULL,
    probe_argv JSONB NOT NULL,
    capability_tags JSONB NOT NULL,
    network_domains JSONB NOT NULL,
    adapter_contract_version INTEGER NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(agent_id, min_version, max_version_exclusive),
    CHECK(min_version <> max_version_exclusive)
);

CREATE TABLE models (
    id UUID PRIMARY KEY,
    provider_key VARCHAR(64) NOT NULL,
    model_key VARCHAR(200) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    context_window INTEGER NOT NULL CHECK (context_window > 0),
    max_output_tokens INTEGER NOT NULL CHECK (max_output_tokens > 0),
    tokenizer_key VARCHAR(100) NOT NULL,
    supports_tools BOOLEAN NOT NULL,
    supports_streaming BOOLEAN NOT NULL,
    supports_vision BOOLEAN NOT NULL,
    catalog_revision INTEGER NOT NULL CHECK(catalog_revision > 0),
    status VARCHAR(16) NOT NULL CHECK (status IN ('draft','validated','published')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(provider_key, model_key, catalog_revision)
);

CREATE TABLE agent_model_bindings (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL REFERENCES agents(id),
    model_id UUID NOT NULL REFERENCES models(id),
    min_agent_version VARCHAR(64) NOT NULL,
    max_agent_version_exclusive VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(agent_id, model_id, min_agent_version, max_agent_version_exclusive)
);

CREATE TABLE api_providers (
    id UUID PRIMARY KEY,
    key VARCHAR(64) NOT NULL,
    catalog_revision INTEGER NOT NULL CHECK(catalog_revision > 0),
    display_name VARCHAR(100) NOT NULL,
    protocol VARCHAR(32) NOT NULL
        CHECK (protocol IN ('openai_responses','anthropic_messages','openai_chat_completions')),
    base_url TEXT NOT NULL,
    auth_scheme VARCHAR(32) NOT NULL CHECK (auth_scheme IN ('bearer','x-api-key')),
    status VARCHAR(16) NOT NULL CHECK (status IN ('draft','validated','published')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(key, catalog_revision)
);

CREATE TABLE provider_model_bindings (
    id UUID PRIMARY KEY,
    provider_id UUID NOT NULL REFERENCES api_providers(id),
    model_id UUID NOT NULL REFERENCES models(id),
    provider_model_name VARCHAR(200) NOT NULL,
    request_defaults JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(provider_id, model_id)
);

CREATE TABLE skills (
    id UUID PRIMARY KEY,
    key VARCHAR(100) NOT NULL,
    catalog_revision INTEGER NOT NULL CHECK(catalog_revision > 0),
    display_name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('draft','validated','published')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(key, catalog_revision)
);

CREATE TABLE skill_versions (
    id UUID PRIMARY KEY,
    skill_id UUID NOT NULL REFERENCES skills(id),
    version VARCHAR(64) NOT NULL,
    manifest_json JSONB NOT NULL,
    object_key TEXT NOT NULL UNIQUE,
    object_size BIGINT NOT NULL CHECK (object_size BETWEEN 1 AND 52428800),
    object_sha256 CHAR(64) NOT NULL,
    signature TEXT NOT NULL,
    signing_key_id VARCHAR(100) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(skill_id, version)
);

CREATE TABLE compatibility_rules (
    id UUID PRIMARY KEY,
    subject_type VARCHAR(32) NOT NULL
        CHECK (subject_type IN ('agent','model','skill','client')),
    subject_id UUID NOT NULL,
    subject_version_range VARCHAR(200) NOT NULL,
    dependency_type VARCHAR(32) NOT NULL
        CHECK (dependency_type IN ('agent','model','skill','platform','client')),
    dependency_key VARCHAR(200) NOT NULL,
    dependency_version_range VARCHAR(200) NOT NULL,
    decision VARCHAR(8) NOT NULL CHECK (decision IN ('allow','deny')),
    reason_code VARCHAR(100) NOT NULL,
    priority INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('draft','validated','published')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX ix_compatibility_subject
    ON compatibility_rules(subject_type, subject_id, priority DESC);
```

目录校验器必须执行：所有版本字段按 SemVer 解析；`min_version < max_version_exclusive`；同一 Agent revision、同一 platform 的版本区间不得重叠；AgentModelBinding 区间必须完全落在该 Agent revision 至少一个已声明区间内；`context_window >= 8192` 且 `1 <= max_output_tokens <= context_window-4096`；支持 API Model 的 Model 必须 `supports_streaming=true`，需要工具的底座必须 `supports_tools=true`。Agent `network_domains` 和 Skill 同名字段使用 G.8 的规范化域名语法，必须至少包含对应版本契约测试观测到的认证和模型端点，不允许 IP 或全局通配。Provider `base_url` 必须是绝对 HTTPS URL，禁止 userinfo/query/fragment，host 经 IDNA 规范化，DNS/IP 不得落入 loopback、private、link-local、multicast 或保留地址；尾部 `/` 统一去除后保存。`request_defaults` 由协议专属 JSON Schema 校验，禁止包含 model、stream、tools、messages/input、Authorization、api_key 或 URL 字段。

### G.7 发布 DDL

```sql
CREATE TABLE catalog_releases (
    id UUID PRIMARY KEY,
    release_sequence BIGINT NOT NULL UNIQUE CHECK (release_sequence > 0),
    minimum_client_version VARCHAR(64) NOT NULL,
    manifest_object_key TEXT NOT NULL UNIQUE,
    manifest_sha256 CHAR(64) NOT NULL,
    signature TEXT NOT NULL,
    signing_key_id VARCHAR(100) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (status IN ('publishing','published','failed')),
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);

CREATE TABLE catalog_release_items (
    release_id UUID NOT NULL REFERENCES catalog_releases(id),
    resource_type VARCHAR(32) NOT NULL CHECK(resource_type IN (
        'agent_revision','agent_version','model','provider',
        'skill_revision','skill_version','compatibility_rule'
    )),
    resource_id UUID NOT NULL,
    resource_version_id UUID NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    PRIMARY KEY(release_id, resource_type, resource_id, resource_version_id)
);

CREATE TABLE emergency_disable_releases (
    id UUID PRIMARY KEY,
    sequence BIGINT NOT NULL UNIQUE,
    payload_json JSONB NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    signature TEXT NOT NULL,
    signing_key_id VARCHAR(100) NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE admin_audit_logs (
    id UUID PRIMARY KEY,
    actor_user_id UUID,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id UUID,
    request_id UUID NOT NULL,
    outcome VARCHAR(16) NOT NULL CHECK (outcome IN ('success','denied','failed')),
    before_json JSONB,
    after_json JSONB,
    error_code VARCHAR(100),
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_admin_audit_created ON admin_audit_logs(created_at DESC, id);
CREATE INDEX ix_admin_audit_resource ON admin_audit_logs(resource_type, resource_id, created_at DESC);
```

`emergency_disable_releases.payload_json` 固定符合：

```json
{
  "sequence": 7,
  "created_at": "2026-01-01T00:00:00Z",
  "directives": [
    {
      "resource_type": "agent_version",
      "resource_id": "uuid",
      "resource_version_id": "uuid",
      "action": "disable",
      "reason_code": "SECURITY_INCIDENT"
    }
  ]
}
```

`resource_type` 只能为 `agent_revision/agent_version/model/provider/skill_revision/skill_version/compatibility_rule/client_version`；不使用版本子资源时 `resource_version_id=null`。`action` 为 `disable/enable`。签名输入是 payload 的 RFC 8785 字节；恢复只能发布更高 sequence 的 `enable` directive，不删除历史记录。客户端按目标取最大 sequence directive 计算有效状态，先执行 disable/enable，再执行普通兼容规则。

`catalog_release_items` 中，`agent_version/skill_version` 的 `resource_id` 是父 revision id、`resource_version_id` 是子版本 id；其他类型没有子版本，两个 id 必须相同。发布校验器必须验证该约束和真实外键归属；由于一张多态表无法声明完整 SQL 外键，发布事务在插入前按 `resource_type` 执行带行锁的显式查询，缺失或父子不一致即回滚。

数据库必须安装以下不可变约束。`catalog_resource_revision_guard` 允许 `draft/validated` 正常编辑和 `validated → published`，但 published 行禁止 UPDATE/DELETE；`catalog_version_guard` 允许首次填写 `published_at`，之后禁止 UPDATE/DELETE；published Release 与所有 ReleaseItem 永久不可变。业务层的同类校验只用于返回友好错误，不替代 Trigger。

```sql
CREATE OR REPLACE FUNCTION protect_catalog_resource_revision()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'draft' THEN
            RAISE EXCEPTION 'catalog revision must be inserted as draft'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' AND OLD.status = 'published' THEN
        RAISE EXCEPTION 'published catalog revision is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = 'published' THEN
        RAISE EXCEPTION 'published catalog revision is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'UPDATE'
       AND NEW.status = 'published'
       AND OLD.status <> 'validated' THEN
        RAISE EXCEPTION 'only validated revision can be published'
            USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agents_revision_guard
BEFORE INSERT OR UPDATE OR DELETE ON agents
FOR EACH ROW EXECUTE FUNCTION protect_catalog_resource_revision();
CREATE TRIGGER models_revision_guard
BEFORE INSERT OR UPDATE OR DELETE ON models
FOR EACH ROW EXECUTE FUNCTION protect_catalog_resource_revision();
CREATE TRIGGER providers_revision_guard
BEFORE INSERT OR UPDATE OR DELETE ON api_providers
FOR EACH ROW EXECUTE FUNCTION protect_catalog_resource_revision();
CREATE TRIGGER skills_revision_guard
BEFORE INSERT OR UPDATE OR DELETE ON skills
FOR EACH ROW EXECUTE FUNCTION protect_catalog_resource_revision();
CREATE TRIGGER compatibility_rules_guard
BEFORE INSERT OR UPDATE OR DELETE ON compatibility_rules
FOR EACH ROW EXECUTE FUNCTION protect_catalog_resource_revision();

CREATE OR REPLACE FUNCTION protect_catalog_version()
RETURNS trigger AS $$
DECLARE
    parent_status VARCHAR(16);
    parent_id UUID;
BEGIN
    IF TG_TABLE_NAME = 'agent_versions' THEN
        IF TG_OP = 'DELETE' THEN parent_id := OLD.agent_id; ELSE parent_id := NEW.agent_id; END IF;
        SELECT status INTO parent_status FROM agents
        WHERE id = parent_id FOR UPDATE;
    ELSIF TG_TABLE_NAME = 'skill_versions' THEN
        IF TG_OP = 'DELETE' THEN parent_id := OLD.skill_id; ELSE parent_id := NEW.skill_id; END IF;
        SELECT status INTO parent_status FROM skills
        WHERE id = parent_id FOR UPDATE;
    END IF;
    IF parent_status = 'published' THEN
        RAISE EXCEPTION 'published parent revision children are immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.published_at IS NOT NULL THEN
            RAISE EXCEPTION 'catalog version must be inserted unpublished'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.published_at IS NOT NULL THEN
        RAISE EXCEPTION 'published catalog version is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    IF NEW.published_at IS NOT NULL AND OLD.published_at IS NULL THEN
        RETURN NEW;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agent_versions_guard
BEFORE INSERT OR UPDATE OR DELETE ON agent_versions
FOR EACH ROW EXECUTE FUNCTION protect_catalog_version();
CREATE TRIGGER skill_versions_guard
BEFORE INSERT OR UPDATE OR DELETE ON skill_versions
FOR EACH ROW EXECUTE FUNCTION protect_catalog_version();

CREATE OR REPLACE FUNCTION protect_agent_model_binding()
RETURNS trigger AS $$
DECLARE parent_status VARCHAR(16);
BEGIN
    IF TG_OP = 'DELETE' THEN
        SELECT status INTO parent_status FROM agents WHERE id = OLD.agent_id FOR UPDATE;
    ELSE
        SELECT status INTO parent_status FROM agents WHERE id = NEW.agent_id FOR UPDATE;
    END IF;
    IF parent_status = 'published' THEN
        RAISE EXCEPTION 'published agent bindings are immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER agent_model_bindings_guard
BEFORE INSERT OR UPDATE OR DELETE ON agent_model_bindings
FOR EACH ROW EXECUTE FUNCTION protect_agent_model_binding();

CREATE OR REPLACE FUNCTION protect_provider_model_binding()
RETURNS trigger AS $$
DECLARE parent_status VARCHAR(16);
BEGIN
    IF TG_OP = 'DELETE' THEN
        SELECT status INTO parent_status FROM api_providers WHERE id = OLD.provider_id FOR UPDATE;
    ELSE
        SELECT status INTO parent_status FROM api_providers WHERE id = NEW.provider_id FOR UPDATE;
    END IF;
    IF parent_status = 'published' THEN
        RAISE EXCEPTION 'published provider bindings are immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER provider_model_bindings_guard
BEFORE INSERT OR UPDATE OR DELETE ON provider_model_bindings
FOR EACH ROW EXECUTE FUNCTION protect_provider_model_binding();

CREATE OR REPLACE FUNCTION reject_catalog_release_item_mutation()
RETURNS trigger AS $$
DECLARE
    parent_status VARCHAR(16);
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT status INTO parent_status
        FROM catalog_releases
        WHERE id = NEW.release_id
        FOR UPDATE;
        IF parent_status IS DISTINCT FROM 'publishing' THEN
            RAISE EXCEPTION 'items can only be inserted into publishing release'
                USING ERRCODE = '55000';
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'catalog release item is immutable'
        USING ERRCODE = '55000';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER catalog_release_items_immutable
BEFORE INSERT OR UPDATE OR DELETE ON catalog_release_items
FOR EACH ROW EXECUTE FUNCTION reject_catalog_release_item_mutation();

CREATE OR REPLACE FUNCTION reject_append_only_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only row is immutable'
        USING ERRCODE = '55000';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER emergency_disable_releases_immutable
BEFORE UPDATE OR DELETE ON emergency_disable_releases
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();
CREATE TRIGGER admin_audit_logs_immutable
BEFORE UPDATE OR DELETE ON admin_audit_logs
FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation();

CREATE OR REPLACE FUNCTION protect_catalog_release()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'publishing' THEN
            RAISE EXCEPTION 'catalog release must be inserted as publishing'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'DELETE' AND OLD.status = 'published' THEN
        RAISE EXCEPTION 'published catalog release is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = 'published' THEN
        RAISE EXCEPTION 'published catalog release is immutable'
            USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER catalog_releases_guard
BEFORE INSERT OR UPDATE OR DELETE ON catalog_releases
FOR EACH ROW EXECUTE FUNCTION protect_catalog_release();
```

### G.8 Skill ZIP 校验

Skill ZIP 最大 50 MiB、最多 1000 个条目、解压后最大 200 MiB。必须包含 `skill.json` 和 `instructions.md`。禁止：

- 绝对路径；
- `..` 路径段；
- Symlink、Hardlink 和设备文件；
- 重复规范化路径；
- 未在 manifest 声明的脚本；
- 文件哈希不一致。

`skill.json` 固定使用 JSON Schema 2020-12 的 `packages/contracts/skill-manifest.v1.schema.json`，字段如下：

```json
{
  "schema_version": 1,
  "key": "code-review",
  "version": "1.0.0",
  "display_name": "Code Review",
  "description": "Review source code and produce structured issues.",
  "entrypoint": "instructions.md",
  "capability_tags": ["code", "review"],
  "supported_runtime_types": ["agent_cli", "api_model"],
  "supported_agent_keys": ["codex_cli", "claude_code", "opencode"],
  "model_requirements": {
    "supports_tools": true,
    "supports_vision": false,
    "minimum_context_window": 32000
  },
  "supported_platforms": ["macos_arm64"],
  "required_tools": ["read_file", "search_text"],
  "network_domains": [],
  "file_policy": "workspace_rw_external_ro",
  "risk_level": "medium",
  "dependencies": [],
  "conflicts": [],
  "files": [
    {
      "path": "instructions.md",
      "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
      "executable": false,
      "interpreter": null
    }
  ]
}
```

`key` 必须与父 Skill revision key 相同，`version` 必须与 `skill_versions.version` 相同。`supported_agent_keys=[]` 表示不限制内置 CLI Adapter；对 `api_model` 不读取该字段。`network_domains=[]` 表示不需要网络域名；只允许规范化 DNS 名称或 `*.example.com` 左侧单级通配，禁止 URL、IP、`*`。`dependencies/conflicts` 元素固定为 `{skill_key, version_range}`。`interpreter` 只能为 null、`python3` 或 `zsh`；`executable=true` 时必须非 null。ZIP 中除目录项外每个文件必须在 `files` 恰好出现一次，且 manifest 自身不列入 `files`。

上传校验按 ZIP 原始字节计算 `object_sha256`，按 RFC 8785 规范化 manifest 计算 `content_sha256`，再使用 Catalog key 对 ASCII 字节 `skill-v1\n{skill_id}\n{version}\n{object_sha256}\n{content_sha256}` 做 Ed25519 签名。Runtime 安装时必须同时验证对象哈希、manifest 哈希、签名、逐文件哈希和当前 CatalogRelease 引用。

对象键固定为 `skills/{skill_id}/{version}/{sha256}.zip`。API 流式写入应用私有临时文件，校验后上传；数据库失败的孤儿对象由每日 GC 清理，安全窗 24 小时。

### G.9 目录发布事务

发布固定执行：

1. `pg_advisory_xact_lock(hashtext('catalog-release'))`。
2. `REPEATABLE READ` 读取状态为 `validated` 的待发布选择和全部引用；任何 draft 或已发布行混入都失败。
3. 校验版本区间、引用完整性、Skill 对象、唯一逻辑 key 和最低客户端版本。
4. 在 advisory lock 保护下执行 `SELECT COALESCE(MAX(release_sequence),0)+1` 分配序号。
5. 生成 RFC 8785 Canonical JSON 和 SHA-256。
6. 使用 Catalog Ed25519 私钥签名。
7. 上传 `catalog/{sequence}/{sha256}.json`。
8. 插入 release 与 items；先把入选 `agent_versions/skill_versions.published_at` 置为当前事务时间，再把入选父资源置为 `published`，最后把 release 置为 `published` 后提交事务。
9. 更新 S3 `catalog/latest.json` 指针。

第 9 步失败不回滚已发布目录；API 从 PostgreSQL 最大 published sequence 返回事实结果，并每分钟重试指针更新。

发布事务在第 8 步前失败时，已上传 manifest 可能成为孤儿。每日 GC 只删除创建超过 24 小时、且 `manifest_object_key` 不存在于 `catalog_releases` 的 `catalog/` 对象；删除前再次查询 PostgreSQL。GC 不处理 `catalog/latest.json` 和任何已引用对象。

### G.9.1 Catalog 签名密钥轮换

桌面安装包内嵌初始 Catalog Trust Key。`GET /api/v1/catalog/keys` 返回 RFC 8785 规范化的 append-only 公钥集与 `signatures[]`；每个 signature 含 `signing_key_id` 和 Ed25519 签名。客户端只有在至少一个签名可由本地已信任 key 验证时才接受 keyset，并把新增 public key 原子加入本地信任集。公钥记录只允许 `active/retired`，永不从 keyset 删除，用于验证历史 Release、紧急禁用和 Auth keyset。

轮换顺序固定为：生成离线 Ed25519 key；把新 public key 加入 keyset并由旧 active key 签名；发布包含该 keyset 的后台版本；等待 24 小时；用新旧 key 同时签名 keyset；切换 Catalog Release signer 为新 key；保留旧 public key；最后销毁旧 private key。私钥文件权限必须为 `0400`，进程只在启动时读取，日志和健康接口只输出 key id。

### G.10 REST 统一规范

- 前缀：应用 `/api/v1`，后台 `/admin/api/v1`。
- 时间：RFC 3339 UTC，必须带 `Z`。
- 内容类型：`application/json`；Skill 上传使用 `multipart/form-data`。
- 列表：cursor 分页，默认 50、最大 200。
- 更新：必须带 `If-Match` 聚合 version。
- 除 `/auth/*` 外的写入必须带 `Idempotency-Key` UUID；认证端点涉及密码或 Token 轮换，禁止写入通用幂等响应缓存。
- 错误：`application/problem+json`，符合 RFC 9457。

幂等处理必须与业务写入处于同一 PostgreSQL 事务：先 `INSERT ... ON CONFLICT DO NOTHING`，再 `SELECT ... FOR UPDATE`；同 key 且 request SHA 不同返回 `IDEMPOTENCY_CONFLICT`，completed/failed 返回原 status/content-type/body，processing 且持锁事务仍存在时等待数据库锁后重读。记录保留 30 天；清理只删除已过期 completed/failed，processing 超过 10 分钟先标 failed。响应缓存禁止包含 password、Access/Refresh Token、Cookie 或签名私钥。

错误正文：

```json
{
  "type": "https://docs.ibreeze/errors/OPTIMISTIC_LOCK_CONFLICT",
  "title": "Resource version conflict",
  "status": 409,
  "detail": "The resource changed after it was loaded.",
  "instance": "/admin/api/v1/users/uuid",
  "code": "OPTIMISTIC_LOCK_CONFLICT",
  "request_id": "uuid",
  "field_errors": []
}
```

### G.11 认证 REST

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
POST /api/v1/auth/logout-all
POST /api/v1/auth/change-password
GET  /api/v1/auth/keys

POST /admin/api/v1/auth/login
POST /admin/api/v1/auth/refresh
POST /admin/api/v1/auth/logout
POST /admin/api/v1/auth/change-password
```

应用注册请求只接受 email/password；出现未知权限字段返回 422。服务端把规范化后的 email 同时作为初始 `display_name`，注册成功不自动登录。管理员可在用户管理中修改显示名。任一 `must_change_password=true` 用户在除改密和 logout 外的接口上返回 `AUTH_PASSWORD_CHANGE_REQUIRED`；默认管理员和被重置密码的用户遵循同一门禁。

正常应用登录和每次成功刷新在 JSON 正文同时返回 Access Token、轮换后的 Refresh Token、新签发的 30 天 OfflineSessionTicket 与 `family_id`，供 Rust Core 在验证后用 F.9 的一次 Keychain update 原子替换 session bundle。`must_change_password=true` 的应用登录只返回 `pwd_change_required=true` 的 5 分钟受限 Access Token、Refresh Token 和 family_id，不签发 OfflineSessionTicket，也不打开本地 Profile；受限 Access/Refresh Token 只保存在 Rust 的零化内存，进程退出后要求重新登录，且只能调用 change-password/logout。若已登录用户在服务端被设置 `must_change_password=true`，下一次 refresh 消费旧 Token并返回同样的受限响应；Rust 收到该响应后删除旧 session bundle。Keychain 写入失败时，新 Refresh Token 不得再次展示或写日志，客户端清空 Access Token并回到登录页；用户重新登录即可创建新 family。响应带 `Cache-Control: no-store`。管理员登录/刷新不在 JSON 返回 Refresh Token，而是设置仅限 `/admin/api/v1/auth` 的 `Secure; HttpOnly; SameSite=Strict` Cookie，JSON 只返回 Access Token；Admin Web 将 Access Token 只保存在 React 内存状态。应用和管理员 logout 均撤销当前 family；应用端收到成功响应后删除 session bundle，管理员端清 Cookie。两类 Access Token 的 `aud` 分别固定为 `ibreeze-desktop` 与 `ibreeze-admin`，服务端不得跨 audience 接受。

Access、OfflineSessionTicket 和 Refresh Token 原始值均由 32 字节 CSPRNG 或 Ed25519 签名生成；Refresh Token 数据库存 `SHA-256(token)`。每个 JWT Header 必须含 `alg=EdDSA`、`typ=JWT` 和 `kid`，验证端拒绝 Header 指定其他算法。

Access Token claims 固定为 `iss/aud/sub/user_type/sid/jti/iat/nbf/exp/pwd_change_required`；普通 Token 的最后一项为 false，受限改密 Token 为 true。`sid` 是 RefreshTokenFamily id，`nbf=iat-60s`，验证允许最大 60 秒时钟偏差。API 从 `Authorization: Bearer` 读取 Access Token，校验签名、issuer、audience、时间、用户状态和 user_type；不得只解码不验签。修改密码/禁用/撤销后，已签发 Access Token 最多继续存在 15 分钟；全部 `/admin/api/v1` 非 GET/HEAD 接口还必须查询该 `sid` family 未撤销，因此管理员撤销对写操作立即生效。

`GET /api/v1/auth/keys` 返回 OfflineSessionTicket 验证公钥集、`issued_at/expires_at`、key 状态和 Catalog Key 对整个 keyset 的 Ed25519 签名。桌面先使用内嵌 Catalog Trust Key 验证 keyset，再原子缓存。Auth 私钥轮换顺序固定为：发布包含新 public key 的签名 keyset并等待 24 小时、切换 JWT signer、保留旧 public key 至旧 OfflineSessionTicket 最长有效期 30 天加 10 分钟时钟偏差后再移除。Access Token 验证公钥遵循同一 keyset。

`change-password` 请求为 `{current_password,new_password}`；任一被管理员 reset 且 `must_change_password=true` 的用户仍必须提交当前临时密码。成功后在同一事务更新 hash、清除 `must_change_password`、撤销除当前请求外的全部 family；随后当前 family 也消费并签发一个新 family，避免旧 Refresh Token 继续有效。应用端响应同时返回新的 Access/Refresh/Offline bundle，管理员端按本节 Cookie 规则返回新 session。`logout` 撤销当前 family，`logout-all` 撤销用户全部 family。

### G.12 用户管理 REST

```text
GET    /admin/api/v1/users
POST   /admin/api/v1/users
GET    /admin/api/v1/users/{id}
PATCH  /admin/api/v1/users/{id}
DELETE /admin/api/v1/users/{id}
POST   /admin/api/v1/users/{id}/reset-password
POST   /admin/api/v1/users/{id}/revoke-sessions
```

DELETE 先锁定用户、校验非保护、撤销 Token、写审计，再物理删除。审计只保留删除前用户 UUID、类型和脱敏标识。

创建请求按 `user_type` 二选一：admin 必须提交 `username/display_name/password` 且禁止 email；app_user 必须提交 `email/display_name/password` 且禁止 username。PATCH 只允许 `display_name/status`，普通 admin 另允许 username，app_user 另允许 email；保护 admin 只能改 display_name。`reset-password` 请求固定为 `{new_password}`，复用 8–128 字符规则，设置新 Argon2id hash、`must_change_password=true` 并撤销全部 family；用户下次登录只可改密或 logout。`revoke-sessions` 撤销全部 family 但不改变密码。所有响应禁止返回 `password_hash`、失败计数、Token 哈希或 Cookie。

### G.13 目录 REST

应用接口：

```text
GET /api/v1/catalog/manifest
GET /api/v1/catalog/keys
GET /api/v1/catalog/releases/{id}
GET /api/v1/catalog/releases/{id}/resources/{type}
GET /api/v1/catalog/agents
GET /api/v1/catalog/agents/{agent_id}/models
GET /api/v1/catalog/providers
GET /api/v1/catalog/providers/{provider_id}/models
GET /api/v1/catalog/skills
GET /api/v1/catalog/compatibility
GET /api/v1/catalog/emergency-disables/latest
GET /api/v1/catalog/skills/{skill_id}/versions/{version}/package
```

未带 release id 的目录查询固定读取当前最大 published release，并在响应 `meta.catalog_release_id` 返回所用版本，禁止从 draft 表直接拼实时结果。

管理接口的完整资源路由如下；未列出的目录写路由不属于 v1。所有写接口都要求 `Idempotency-Key`；PATCH/DELETE 还要求 `If-Match`。列表均使用 G.10 的 cursor 契约。

```text
GET/POST           /admin/api/v1/agents
GET/PATCH/DELETE   /admin/api/v1/agents/{id}
POST               /admin/api/v1/agents/{id}/validate
POST               /admin/api/v1/agents/{id}/revisions
GET/POST           /admin/api/v1/agents/{id}/versions
DELETE             /admin/api/v1/agents/{id}/versions/{version_id}
GET/POST           /admin/api/v1/agents/{id}/model-bindings
DELETE             /admin/api/v1/agents/{id}/model-bindings/{binding_id}

GET/POST           /admin/api/v1/models
GET/PATCH/DELETE   /admin/api/v1/models/{id}
POST               /admin/api/v1/models/{id}/validate
POST               /admin/api/v1/models/{id}/revisions

GET/POST           /admin/api/v1/providers
GET/PATCH/DELETE   /admin/api/v1/providers/{id}
POST               /admin/api/v1/providers/{id}/validate
POST               /admin/api/v1/providers/{id}/revisions
GET/POST           /admin/api/v1/providers/{id}/model-bindings
DELETE             /admin/api/v1/providers/{id}/model-bindings/{binding_id}

GET/POST           /admin/api/v1/skills
GET/PATCH/DELETE   /admin/api/v1/skills/{id}
POST               /admin/api/v1/skills/{id}/validate
POST               /admin/api/v1/skills/{id}/revisions
GET/POST           /admin/api/v1/skills/{id}/versions
DELETE             /admin/api/v1/skills/{id}/versions/{version_id}

GET/POST           /admin/api/v1/compatibility-rules
GET/PATCH/DELETE   /admin/api/v1/compatibility-rules/{id}
POST               /admin/api/v1/compatibility-rules/{id}/validate
```

状态语义固定如下：

- `POST /admin/api/v1/{agents|models|providers|skills}` 创建 `catalog_revision=1` 的 draft；Skill 的逻辑实体创建后通过 version 子资源上传包。
- `PATCH/DELETE /admin/api/v1/{resource}/{id}` 只允许 draft/validated；PATCH 改变任何发布字段时状态强制退回 draft。
- `POST /admin/api/v1/{resource}/{id}/validate` 执行 Schema、引用、版本区间、URL 与兼容性校验，成功后置 validated。
- `POST /admin/api/v1/{resource}/{id}/revisions` 只接受 published 源 id，复制全部字段和子绑定为 `catalog_revision+1` 的新 draft，并返回新 id。
- `POST /admin/api/v1/agents/{id}/versions` 和 `POST /admin/api/v1/skills/{id}/versions` 只在父 revision 非 published 时创建。Agent 子资源以 JSON 提交 `min_version/max_version_exclusive/executable_names/supported_platforms/probe_argv/capability_tags/network_domains/adapter_contract_version`；Skill 子资源以 `multipart/form-data` 提交唯一 `package` 文件和 `version` 字段。Agent 版本上下限按 SemVer 解析且下限必须小于上限；Skill version 必须与包内 manifest 完全一致。子版本 DELETE 只允许父 revision 为 draft/validated 且子版本未发布。
- Agent/Provider 的 model-binding POST 请求分别与 G.6 对应：前者提交 `model_id/min_agent_version/max_agent_version_exclusive`，后者提交 `model_id/provider_model_name/request_defaults`。DELETE 只允许父 revision 为 draft/validated；添加或删除 binding 后父状态强制退回 draft。
- published 资源的 PATCH/DELETE 返回 `CATALOG_REVISION_IMMUTABLE`；停用必须发布紧急禁用记录。

其中 `{resource}` 只展开为 `agents`、`models`、`providers`、`skills`；compatibility-rules 没有 revision clone，发布后同样不可变，修改时创建新 rule id。管理接口还提供：

```text
POST /admin/api/v1/catalog/validate
POST /admin/api/v1/catalog/releases
POST /admin/api/v1/catalog/releases/{id}/publish
POST /admin/api/v1/emergency-disables
GET  /admin/api/v1/audit-logs
```

客户端启动、登录、每 15 分钟和每次 AgentRun 前检查紧急禁用。命中后禁止新 Run，已有 Run 在下一模型或工具边界进入 `waiting_resource`。

### G.14 OpenAPI 生成

CI 从 FastAPI 导出 `packages/contracts/openapi.json`。Admin Web 使用 `openapi-typescript` 生成 TypeScript 类型；Rust Core 使用 `progenitor` 根据同一 OpenAPI 生成 reqwest Client 和 Serde 类型。生成文件有差异但未提交时 CI 失败。REST DTO 禁止手写第二份定义。

## 附录 H：本地领域与 SQLite 规范

### H.1 Profile 数据库

每个 Profile 只有一个 `profile.db`。启动连接固定设置：

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;
```

Sidecar 发布包必须绑定同一 SQLite `>=3.45,<3.46` 动态库，不使用 macOS 系统 SQLite。启动时执行 `SELECT sqlite_version()`、`PRAGMA compile_options`、`SELECT json_valid('{}')` 和临时 FTS5 建表探测；缺少 foreign key、JSON1 或 FTS5 能力时 `system.health=unhealthy` 并拒绝打开 Profile。上述 PRAGMA 对池内每个连接设置，写连接额外执行 `PRAGMA wal_autocheckpoint=1000`；正常退出执行 `PRAGMA wal_checkpoint(TRUNCATE)`。

迁移文件命名 `YYYYMMDDHHMMSS_description.sql`。迁移记录：

```sql
CREATE TABLE schema_migrations (
    version TEXT PRIMARY KEY,
    script_sha256 TEXT NOT NULL CHECK(length(script_sha256)=64),
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running','completed','failed')),
    error_message TEXT
);
```

已完成 migration 的脚本哈希变化时拒绝启动。

迁移器按文件名升序执行并持有 Profile 单实例文件锁。除首次创建 `schema_migrations` 外，每个脚本流程固定为：事务 A 插入/更新 running 后提交；事务 B `BEGIN IMMEDIATE` 执行脚本、运行 `PRAGMA foreign_key_check`，成功时同事务更新 completed 并提交；失败回滚事务 B，再用事务 C 更新 failed/error_message。启动发现 running 记录视为上次中断，重新执行该幂等脚本。已有 Profile 执行版本升级前必须成功创建 J.9 的 `pre_upgrade` 备份；全新空库不要求备份。备份失败禁止迁移。

### H.2 本地 Profile、底座与 Skill

```sql
CREATE TABLE local_profile (
    id TEXT PRIMARY KEY,
    backend_origin TEXT NOT NULL,
    app_user_id TEXT NOT NULL,
    masked_identifier TEXT NOT NULL,
    device_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_opened_at TEXT NOT NULL,
    UNIQUE(backend_origin, app_user_id)
);

CREATE TABLE local_preferences (
    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
    cli_global_concurrency INTEGER NOT NULL DEFAULT 4
        CHECK(cli_global_concurrency BETWEEN 1 AND 16),
    log_retention_days INTEGER NOT NULL DEFAULT 30
        CHECK(log_retention_days BETWEEN 1 AND 365),
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)
);
INSERT OR IGNORE INTO local_preferences(
    singleton_id, cli_global_concurrency, log_retention_days, updated_at, version
) VALUES (1, 4, 30, strftime('%Y-%m-%dT%H:%M:%fZ','now'), 1);

CREATE TABLE employee_base_profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    normalized_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    current_version_id TEXT REFERENCES employee_base_profile_versions(id)
        DEFERRABLE INITIALLY DEFERRED,
    status TEXT NOT NULL CHECK(status IN ('active','retired')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0)
);

CREATE TABLE employee_base_profile_versions (
    id TEXT PRIMARY KEY,
    profile_id TEXT NOT NULL REFERENCES employee_base_profiles(id),
    version_number INTEGER NOT NULL CHECK(version_number > 0),
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    description TEXT NOT NULL,
    profile_type TEXT NOT NULL CHECK(profile_type IN ('agent_cli','api_model')),
    runtime_binding_json TEXT NOT NULL CHECK(json_valid(runtime_binding_json)),
    system_prompt TEXT NOT NULL,
    capability_tags_json TEXT NOT NULL CHECK(json_valid(capability_tags_json)),
    tool_policy_json TEXT NOT NULL CHECK(json_valid(tool_policy_json)),
    timeout_seconds INTEGER NOT NULL CHECK(timeout_seconds BETWEEN 1 AND 86400),
    max_retries INTEGER NOT NULL CHECK(max_retries BETWEEN 0 AND 5),
    workspace_policy TEXT NOT NULL CHECK(workspace_policy='workspace_rw_external_ro'),
    catalog_release_id TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
    status TEXT NOT NULL CHECK(status IN ('draft','published','retired')),
    created_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(profile_id, version_number),
    CHECK((status='draft' AND published_at IS NULL)
       OR (status IN ('published','retired') AND published_at IS NOT NULL))
);
CREATE UNIQUE INDEX uq_employee_profile_single_draft
    ON employee_base_profile_versions(profile_id) WHERE status='draft';

CREATE TABLE profile_skill_bindings (
    profile_version_id TEXT NOT NULL REFERENCES employee_base_profile_versions(id),
    skill_id TEXT NOT NULL,
    skill_version_id TEXT NOT NULL,
    skill_version TEXT NOT NULL,
    package_sha256 TEXT NOT NULL CHECK(length(package_sha256)=64),
    load_order INTEGER NOT NULL CHECK(load_order >= 0),
    PRIMARY KEY(profile_version_id, skill_version_id),
    UNIQUE(profile_version_id, load_order)
);

CREATE TRIGGER employee_profile_version_published_guard
BEFORE UPDATE ON employee_base_profile_versions
WHEN OLD.status IN ('published','retired')
BEGIN
    SELECT CASE WHEN OLD.status='published' AND NEW.status='retired'
        AND NEW.id IS OLD.id
        AND NEW.profile_id IS OLD.profile_id
        AND NEW.version_number IS OLD.version_number
        AND NEW.name IS OLD.name
        AND NEW.description IS OLD.description
        AND NEW.profile_type IS OLD.profile_type
        AND NEW.runtime_binding_json IS OLD.runtime_binding_json
        AND NEW.system_prompt IS OLD.system_prompt
        AND NEW.capability_tags_json IS OLD.capability_tags_json
        AND NEW.tool_policy_json IS OLD.tool_policy_json
        AND NEW.timeout_seconds IS OLD.timeout_seconds
        AND NEW.max_retries IS OLD.max_retries
        AND NEW.workspace_policy IS OLD.workspace_policy
        AND NEW.catalog_release_id IS OLD.catalog_release_id
        AND NEW.content_sha256 IS OLD.content_sha256
        AND NEW.created_at IS OLD.created_at
        AND NEW.published_at IS OLD.published_at
      THEN NULL
      ELSE RAISE(ABORT, 'published profile version content is immutable')
    END;
END;
CREATE TRIGGER employee_profile_version_no_delete
BEFORE DELETE ON employee_base_profile_versions
WHEN OLD.status IN ('published','retired')
BEGIN SELECT RAISE(ABORT, 'published profile version is immutable'); END;

CREATE TRIGGER profile_skill_bindings_insert_guard
BEFORE INSERT ON profile_skill_bindings
WHEN (SELECT status FROM employee_base_profile_versions WHERE id=NEW.profile_version_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'only draft profile version skills are mutable'); END;
CREATE TRIGGER profile_skill_bindings_update_guard
BEFORE UPDATE ON profile_skill_bindings
WHEN (SELECT status FROM employee_base_profile_versions WHERE id=OLD.profile_version_id) <> 'draft'
   OR (SELECT status FROM employee_base_profile_versions WHERE id=NEW.profile_version_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'only draft profile version skills are mutable'); END;
CREATE TRIGGER profile_skill_bindings_delete_guard
BEFORE DELETE ON profile_skill_bindings
WHEN (SELECT status FROM employee_base_profile_versions WHERE id=OLD.profile_version_id) <> 'draft'
BEGIN SELECT RAISE(ABORT, 'only draft profile version skills are mutable'); END;
```

发布底座版本时在同一 `BEGIN IMMEDIATE` 事务内把版本状态从 `draft` 改为 `published`、设置 `published_at`，把该版本 `name/description` 及规范化名称同步到 `employee_base_profiles`，更新 `current_version_id` 并递增 profile `version`。规范化同样使用 H.3 的 NFKC/trim/空白折叠/lowercase 算法，名称在本地 Profile 内唯一。提交前必须查询并断言 `current_version_id` 所指版本的 `profile_id` 等于当前 profile 且状态为 `published`；SQLite 外键保证存在性，Command Handler 保证同属关系和状态。

目录缓存与已安装 Skill：

```sql
CREATE TABLE catalog_trust_keys (
    key_id TEXT PRIMARY KEY,
    public_key_base64 TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active','retired')),
    introduced_by_keyset_sha256 TEXT NOT NULL CHECK(length(introduced_by_keyset_sha256)=64),
    trusted_at TEXT NOT NULL
);

CREATE TABLE auth_verification_keys (
    key_id TEXT PRIMARY KEY,
    public_key_base64 TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active','retired')),
    signed_keyset_sha256 TEXT NOT NULL CHECK(length(signed_keyset_sha256)=64),
    not_before TEXT NOT NULL,
    retire_after TEXT,
    cached_at TEXT NOT NULL
);

CREATE TABLE catalog_cache_releases (
    release_id TEXT PRIMARY KEY,
    release_sequence INTEGER NOT NULL UNIQUE CHECK(release_sequence > 0),
    manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
    manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64),
    signature TEXT NOT NULL,
    signing_key_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('staging','active','retired','invalid')),
    downloaded_at TEXT NOT NULL,
    activated_at TEXT
);
CREATE UNIQUE INDEX uq_active_catalog_release
    ON catalog_cache_releases(status) WHERE status='active';

CREATE TABLE catalog_cache_resources (
    release_id TEXT NOT NULL REFERENCES catalog_cache_releases(release_id),
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    resource_version_id TEXT NOT NULL,
    content_json TEXT NOT NULL CHECK(json_valid(content_json)),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
    PRIMARY KEY(release_id, resource_type, resource_id, resource_version_id)
);

CREATE TABLE installed_skill_versions (
    skill_version_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL,
    version TEXT NOT NULL,
    package_path TEXT NOT NULL,
    package_sha256 TEXT NOT NULL CHECK(length(package_sha256)=64),
    catalog_release_id TEXT NOT NULL REFERENCES catalog_cache_releases(release_id),
    status TEXT NOT NULL CHECK(status IN ('installed','disabled','corrupt')),
    installed_at TEXT NOT NULL,
    UNIQUE(skill_id, version)
);

CREATE TABLE emergency_disable_cache (
    sequence INTEGER PRIMARY KEY CHECK(sequence > 0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256)=64),
    signature TEXT NOT NULL,
    signing_key_id TEXT NOT NULL,
    activated_at TEXT NOT NULL
);
```

目录同步先写 staging release 及 resources，完成签名、哈希、引用和兼容校验后在单个事务把旧 active 改 retired、新 release 改 active。同步失败删除 staging，不改变 active。

安装包内嵌 Catalog key 在首次迁移写入 `catalog_trust_keys`，`introduced_by_keyset_sha256` 使用内嵌 keyset 的 SHA-256。后续 key 只有通过 G.9.1 信任链后才能插入。`auth_verification_keys` 只有在完整 Auth keyset 通过 Catalog key 签名、时间和 key id 唯一性校验后才整体替换；离线验票只读取该表，不访问网络。

目录清理至少保留当前 active 和最近 2 个 retired release。更旧 retired release 只有在没有 EmployeeBaseProfileVersion、ExecutionSnapshot、installed Skill 或非终态 AgentRun 引用时才可连同 resources 删除；清理前用 JSON 字段解析和关系表双重扫描，存在无法解析的引用时按“仍被引用”处理。紧急禁用 cache 永久保留 sequence 历史，不接受较低 sequence 覆盖。

### H.3 公司、部门和职员

所有 id 由应用生成 UUID v4。所有时间以 UTC RFC 3339 文本保存。

```sql
CREATE TABLE companies (
    id TEXT PRIMARY KEY,
    normalized_name TEXT NOT NULL UNIQUE,
    current_revision_id TEXT NOT NULL,
    general_manager_office_id TEXT NOT NULL,
    general_manager_employee_id TEXT NOT NULL,
    company_conversation_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active','archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    FOREIGN KEY(current_revision_id, id) REFERENCES company_revisions(id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(general_manager_office_id, id) REFERENCES departments(id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(general_manager_employee_id, id) REFERENCES employees(id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(company_conversation_id, id) REFERENCES conversations(id, company_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE company_revisions (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    revision_number INTEGER NOT NULL CHECK(revision_number > 0),
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    introduction TEXT NOT NULL CHECK(length(introduction) BETWEEN 1 AND 20000),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
    created_by_type TEXT NOT NULL CHECK(created_by_type IN ('user','system')),
    created_at TEXT NOT NULL,
    UNIQUE(id, company_id),
    UNIQUE(company_id, revision_number)
);
CREATE TABLE departments (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    department_type TEXT NOT NULL CHECK(department_type IN ('general_manager_office','standard')),
    normalized_name TEXT NOT NULL,
    current_revision_id TEXT NOT NULL,
    leader_employee_id TEXT NOT NULL,
    department_conversation_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active','archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    UNIQUE(id, company_id),
    UNIQUE(company_id, normalized_name),
    FOREIGN KEY(current_revision_id, id, company_id)
        REFERENCES department_revisions(id, department_id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(leader_employee_id, company_id) REFERENCES employees(id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(department_conversation_id, company_id)
        REFERENCES conversations(id, company_id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE UNIQUE INDEX uq_company_gm_office
    ON departments(company_id) WHERE department_type='general_manager_office';

CREATE TABLE department_revisions (
    id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL,
    company_id TEXT NOT NULL REFERENCES companies(id),
    revision_number INTEGER NOT NULL CHECK(revision_number > 0),
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
    function_description TEXT NOT NULL CHECK(length(function_description) BETWEEN 1 AND 10000),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
    created_at TEXT NOT NULL,
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id),
    UNIQUE(id, department_id, company_id),
    UNIQUE(department_id, revision_number)
);
CREATE TABLE department_responsibilities (
    id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    responsibility_key TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    accepted_task_types_json TEXT NOT NULL CHECK(json_valid(accepted_task_types_json)),
    required_capability_tags_json TEXT NOT NULL CHECK(json_valid(required_capability_tags_json)),
    deliverable_types_json TEXT NOT NULL CHECK(json_valid(deliverable_types_json)),
    quality_gates_json TEXT NOT NULL CHECK(json_valid(quality_gates_json)),
    upstream_keys_json TEXT NOT NULL CHECK(json_valid(upstream_keys_json)),
    downstream_keys_json TEXT NOT NULL CHECK(json_valid(downstream_keys_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id),
    UNIQUE(department_id, responsibility_key)
);

CREATE TABLE employees (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    department_id TEXT NOT NULL,
    display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 1 AND 100),
    normalized_display_name TEXT NOT NULL,
    base_profile_version_id TEXT NOT NULL REFERENCES employee_base_profile_versions(id),
    workflow_role TEXT NOT NULL
        CHECK(workflow_role IN ('general_manager','department_leader','member')),
    status TEXT NOT NULL CHECK(status IN ('active','draining','inactive','unavailable')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id),
    UNIQUE(id, company_id),
    UNIQUE(department_id, normalized_display_name)
);

CREATE TRIGGER company_revisions_no_update
BEFORE UPDATE ON company_revisions
BEGIN SELECT RAISE(ABORT, 'company revision is immutable'); END;
CREATE TRIGGER company_revisions_no_delete
BEFORE DELETE ON company_revisions
BEGIN SELECT RAISE(ABORT, 'company revision is immutable'); END;
CREATE TRIGGER department_revisions_no_update
BEFORE UPDATE ON department_revisions
BEGIN SELECT RAISE(ABORT, 'department revision is immutable'); END;
CREATE TRIGGER department_revisions_no_delete
BEFORE DELETE ON department_revisions
BEGIN SELECT RAISE(ABORT, 'department revision is immutable'); END;
```

Company、Department 与 Employee 的循环引用使用预生成 id 和 `PRAGMA defer_foreign_keys=ON` 在单个 `BEGIN IMMEDIATE` 事务创建。提交前 Command Handler 显式查询并断言所有引用存在；断言失败回滚。

`normalized_name/normalized_display_name` 固定为名称执行 Unicode NFKC、去首尾空白、连续空白折叠为一个空格、Unicode lowercase 后的结果。Company 在 Profile 内唯一；Department 在 Company 内唯一；Employee display name 在 Department 内唯一。历史 Revision 允许保留旧名称。

### H.4 会话、事件与幂等

```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    conversation_type TEXT NOT NULL CHECK(conversation_type IN ('company','department')),
    department_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('active','archived')),
    created_at TEXT NOT NULL,
    UNIQUE(id, company_id),
    UNIQUE(company_id, conversation_type, department_id),
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id)
);

CREATE TABLE domain_events (
    row_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    company_id TEXT NOT NULL REFERENCES companies(id),
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    aggregate_version INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    trace_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE(event_id, company_id)
);
CREATE INDEX ix_domain_events_company_sequence
    ON domain_events(company_id, row_sequence);
CREATE INDEX ix_domain_events_aggregate
    ON domain_events(aggregate_type, aggregate_id, aggregate_version);
CREATE TRIGGER domain_events_no_update
BEFORE UPDATE ON domain_events
BEGIN SELECT RAISE(ABORT, 'domain event is immutable'); END;
CREATE TRIGGER domain_events_no_delete
BEFORE DELETE ON domain_events
BEGIN SELECT RAISE(ABORT, 'domain event is immutable'); END;

CREATE TABLE outbox_events (
    id TEXT PRIMARY KEY,
    domain_event_id TEXT NOT NULL REFERENCES domain_events(event_id),
    topic TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    status TEXT NOT NULL CHECK(status IN ('pending','processing','delivered','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL,
    last_error TEXT,
    created_at TEXT NOT NULL,
    delivered_at TEXT
);
CREATE INDEX ix_outbox_ready ON outbox_events(status, next_attempt_at, created_at);

CREATE TABLE projection_offsets (
    projection_name TEXT PRIMARY KEY,
    last_row_sequence INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE conversation_messages (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    task_id TEXT,
    source_event_id TEXT NOT NULL UNIQUE,
    sender_type TEXT NOT NULL CHECK(sender_type IN ('user','employee','system')),
    sender_employee_id TEXT,
    message_type TEXT NOT NULL,
    content TEXT NOT NULL,
    artifact_refs_json TEXT NOT NULL CHECK(json_valid(artifact_refs_json)),
    created_at TEXT NOT NULL,
    FOREIGN KEY(conversation_id, company_id) REFERENCES conversations(id, company_id),
    FOREIGN KEY(source_event_id, company_id) REFERENCES domain_events(event_id, company_id),
    FOREIGN KEY(task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(sender_employee_id, company_id) REFERENCES employees(id, company_id)
);
CREATE INDEX ix_messages_conversation_time
    ON conversation_messages(conversation_id, created_at, id);

CREATE TABLE rpc_idempotency (
    method TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64),
    status TEXT NOT NULL CHECK(status IN ('processing','completed','failed')),
    response_json TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY(method, idempotency_key)
);
```

DomainEvent 类型注册表固定存放 `packages/contracts/domain-events/registry.v1.json`，v1 必须包含 `company.created/updated/archived`、`department.created/updated/leader_changed/archived`、`employee.created/updated/transferred/status_changed`、`conversation.user_message_submitted`、`task.created/plan_generated/plan_confirmed/status_changed/superseded`、`department_task.created/status_changed/report_submitted`、`employee_task.created/status_changed`、`artifact.created`、`review.assigned/submitted/issue_changed`、`approval.requested/resolved` 和 `workspace.status_changed`。每个类型指向独立 payload JSON Schema；未注册类型禁止写入。所有 payload 至少含 `company_id/aggregate_id/aggregate_version`，引用其他对象时必须含其 id，不嵌入 Prompt、Token 或完整文件正文。

### H.5 公司和部门事务

公司创建固定预生成 `company_id`、`company_revision_id`、`office_id`、`office_revision_id`、`gm_employee_id`、两个 conversation id。事务顺序：

1. 校验底座版本 published、名称当前唯一。
2. `PRAGMA defer_foreign_keys=ON`。
3. 插入 Company、CompanyRevision。
4. 插入总经理办公室、DepartmentRevision 和固定职责。
5. 插入总经理 Employee。
6. 插入公司级与办公室部门级 Conversation。
7. 查询六项不变量。
8. 写 `company.created` DomainEvent 与 Outbox。
9. Commit。

第 7 步的六项不变量固定为：current CompanyRevision 属于本公司；恰有一个 active `general_manager_office`；总经理 Employee 属于该办公室且角色为 `general_manager`；办公室 `leader_employee_id` 等于总经理；公司会话类型为 company 且 department_id 为 null；办公室会话类型为 department、department_id 等于办公室且两个 conversation 指针分别一致。

部门创建同理，固定预生成 Department、Revision、Leader Employee 和 Conversation id，并在一个事务内完成。任何失败均不得返回部分对象。

公司或部门改名时，Command Handler 必须在同一 `BEGIN IMMEDIATE` 事务内：按预期 `version` 锁定当前事实、生成新 Revision、更新 `current_revision_id` 与 `normalized_name`、递增聚合 `version`、写 DomainEvent 和 Outbox。名称唯一约束失败统一映射为 `NAME_EXISTS`；不得只追加 Revision 而遗漏当前聚合上的 `normalized_name`。

职员改显示名不创建 Revision，但必须在同一事务按 `expected_version` 同步更新 `display_name/normalized_display_name`、递增 `version` 并写事件；唯一约束失败同样映射 `NAME_EXISTS`。

### H.6 任务与计划 DDL

```sql
CREATE TABLE company_tasks (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    supersedes_task_id TEXT,
    company_conversation_id TEXT NOT NULL,
    user_message_event_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'draft','analyzing','awaiting_user_confirmation','approved',
        'revision_requested','rejected','dispatching','checking_resources',
        'executing','reviewing','fixing','final_review','completed',
        'waiting_dependency','waiting_resource','waiting_permission','paused',
        'cancelling','cancelled','failed'
    )),
    resume_state TEXT CHECK(resume_state IS NULL OR resume_state IN (
        'analyzing','dispatching','checking_resources','executing','reviewing','fixing','final_review'
    )),
    active_plan_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(id, company_id),
    FOREIGN KEY(company_conversation_id, company_id)
        REFERENCES conversations(id, company_id),
    FOREIGN KEY(user_message_event_id, company_id)
        REFERENCES domain_events(event_id, company_id),
    FOREIGN KEY(supersedes_task_id, company_id)
        REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(active_plan_id, id, company_id)
        REFERENCES company_plan_versions(id, company_task_id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    CHECK((status IN ('waiting_dependency','waiting_resource','waiting_permission','paused')
           AND resume_state IS NOT NULL)
       OR (status NOT IN ('waiting_dependency','waiting_resource','waiting_permission','paused')
           AND resume_state IS NULL)),
    CHECK(supersedes_task_id IS NULL OR supersedes_task_id <> id)
);

CREATE TABLE company_plan_versions (
    id TEXT PRIMARY KEY,
    company_task_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    canonical_json TEXT NOT NULL CHECK(json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
    generated_by_run_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'draft','awaiting_user_confirmation','approved','superseded','rejected'
    )),
    created_at TEXT NOT NULL,
    confirmed_at TEXT,
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(generated_by_run_id, company_id) REFERENCES agent_runs(id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    UNIQUE(id, company_task_id, company_id),
    UNIQUE(company_task_id, version_number)
);

CREATE TABLE task_context_snapshots (
    id TEXT PRIMARY KEY,
    company_task_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    company_revision_id TEXT NOT NULL,
    plan_version_id TEXT NOT NULL,
    department_revision_map_json TEXT NOT NULL CHECK(json_valid(department_revision_map_json)),
    catalog_release_id TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
    created_at TEXT NOT NULL,
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(company_revision_id, company_id)
        REFERENCES company_revisions(id, company_id),
    FOREIGN KEY(plan_version_id, company_task_id, company_id)
        REFERENCES company_plan_versions(id, company_task_id, company_id),
    UNIQUE(company_task_id)
);
CREATE TRIGGER task_context_snapshots_no_update
BEFORE UPDATE ON task_context_snapshots
BEGIN SELECT RAISE(ABORT, 'task context snapshot is immutable'); END;
CREATE TRIGGER task_context_snapshots_no_delete
BEFORE DELETE ON task_context_snapshots
BEGIN SELECT RAISE(ABORT, 'task context snapshot is immutable'); END;

CREATE TABLE department_tasks (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_id TEXT NOT NULL,
    stage_key TEXT NOT NULL,
    objective TEXT NOT NULL,
    deliverables_json TEXT NOT NULL CHECK(json_valid(deliverables_json)),
    acceptance_criteria_json TEXT NOT NULL CHECK(json_valid(acceptance_criteria_json)),
    status TEXT NOT NULL CHECK(status IN (
        'draft','checking_resources','ready','executing','reviewing','fixing',
        'completed','waiting_dependency','waiting_resource','waiting_permission',
        'cancelled','failed'
    )),
    resume_state TEXT CHECK(resume_state IS NULL OR resume_state IN (
        'checking_resources','ready','executing','reviewing','fixing'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id),
    UNIQUE(id, company_id),
    UNIQUE(id, company_task_id, company_id),
    UNIQUE(company_task_id, stage_key),
    CHECK((status IN ('waiting_dependency','waiting_resource','waiting_permission')
           AND resume_state IS NOT NULL)
       OR (status NOT IN ('waiting_dependency','waiting_resource','waiting_permission')
           AND resume_state IS NULL))
);

CREATE TABLE department_task_dependencies (
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_task_id TEXT NOT NULL,
    depends_on_task_id TEXT NOT NULL,
    PRIMARY KEY(department_task_id, depends_on_task_id),
    FOREIGN KEY(department_task_id, company_task_id, company_id)
        REFERENCES department_tasks(id, company_task_id, company_id),
    FOREIGN KEY(depends_on_task_id, company_task_id, company_id)
        REFERENCES department_tasks(id, company_task_id, company_id),
    CHECK(department_task_id <> depends_on_task_id)
);

CREATE TABLE employee_tasks (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    department_task_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    acceptance_criteria_json TEXT NOT NULL CHECK(json_valid(acceptance_criteria_json)),
    status TEXT NOT NULL CHECK(status IN (
        'assigned','ready','running','submitted','peer_reviewing',
        'changes_requested','accepted','waiting_resource','cancelled','failed'
    )),
    resume_state TEXT CHECK(resume_state IS NULL OR resume_state IN (
        'assigned','ready','running','changes_requested'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(department_task_id, company_id)
        REFERENCES department_tasks(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id),
    UNIQUE(id, company_id),
    CHECK((status='waiting_resource' AND resume_state IS NOT NULL)
       OR (status<>'waiting_resource' AND resume_state IS NULL))
);

CREATE TABLE employee_availability_snapshots (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_task_id TEXT,
    work_item_type TEXT NOT NULL CHECK(work_item_type IN (
        'interactive_turn','company_plan','task_execution','review',
        'verification','repair','merge','summary'
    )),
    work_item_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    base_profile_version_id TEXT NOT NULL REFERENCES employee_base_profile_versions(id),
    prospective_execution_sha256 TEXT NOT NULL CHECK(length(prospective_execution_sha256)=64),
    catalog_release_id TEXT NOT NULL,
    checks_json TEXT NOT NULL CHECK(json_valid(checks_json)),
    overall_status TEXT NOT NULL CHECK(overall_status IN ('available','unavailable')),
    checked_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(company_task_id, company_id)
        REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(department_task_id, company_id)
        REFERENCES department_tasks(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id),
    UNIQUE(id, company_id)
);
CREATE TRIGGER availability_snapshots_no_update
BEFORE UPDATE ON employee_availability_snapshots
BEGIN SELECT RAISE(ABORT, 'availability snapshot is immutable'); END;
CREATE TRIGGER availability_snapshots_no_delete
BEFORE DELETE ON employee_availability_snapshots
BEGIN SELECT RAISE(ABORT, 'availability snapshot is immutable'); END;

CREATE TABLE execution_snapshots (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_id TEXT NOT NULL,
    department_task_id TEXT,
    employee_task_id TEXT,
    employee_id TEXT NOT NULL,
    task_workspace_id TEXT,
    snapshot_purpose TEXT NOT NULL CHECK(snapshot_purpose IN (
        'interactive_turn','company_plan','task_execution','review',
        'verification','repair','merge','summary'
    )),
    work_item_id TEXT NOT NULL,
    company_revision_id TEXT NOT NULL,
    department_revision_id TEXT NOT NULL,
    base_profile_version_id TEXT NOT NULL REFERENCES employee_base_profile_versions(id),
    catalog_release_id TEXT NOT NULL,
    runtime_binding_json TEXT NOT NULL CHECK(json_valid(runtime_binding_json)),
    skill_lock_json TEXT NOT NULL CHECK(json_valid(skill_lock_json)),
    tool_policy_json TEXT NOT NULL CHECK(json_valid(tool_policy_json)),
    workspace_policy_json TEXT NOT NULL CHECK(json_valid(workspace_policy_json)),
    verification_commands_json TEXT NOT NULL CHECK(json_valid(verification_commands_json)),
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
    created_at TEXT NOT NULL,
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(department_id, company_id) REFERENCES departments(id, company_id),
    FOREIGN KEY(department_task_id, company_id) REFERENCES department_tasks(id, company_id),
    FOREIGN KEY(employee_task_id, company_id) REFERENCES employee_tasks(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id),
    FOREIGN KEY(task_workspace_id, company_task_id, company_id)
        REFERENCES task_workspaces(id, company_task_id, company_id),
    FOREIGN KEY(company_revision_id, company_id)
        REFERENCES company_revisions(id, company_id),
    FOREIGN KEY(department_revision_id, department_id, company_id)
        REFERENCES department_revisions(id, department_id, company_id),
    UNIQUE(id, company_id),
    UNIQUE(snapshot_purpose, work_item_id, employee_id, content_sha256),
    CHECK((snapshot_purpose = 'task_execution' AND employee_task_id IS NOT NULL)
       OR snapshot_purpose <> 'task_execution')
);
CREATE TRIGGER execution_snapshots_no_update
BEFORE UPDATE ON execution_snapshots
BEGIN
    SELECT RAISE(ABORT, 'execution snapshot is immutable');
END;
CREATE TRIGGER execution_snapshots_no_delete
BEFORE DELETE ON execution_snapshots
BEGIN
    SELECT RAISE(ABORT, 'execution snapshot is immutable');
END;
```

每个 AgentRun（包括总经理 Plan Run）都必须先对拟执行配置生成 RFC 8785 JSON 和 `prospective_execution_sha256`，所有可用性检查通过后在同一事务 get-or-create `execution_snapshots`；其 `content_sha256` 必须与该 prospective hash 相同，否则返回 `PROFILE_VERSION_INVALID`。同一 purpose/work item/employee/hash 已存在时复用该不可变 Snapshot，但每次启动仍要求新的未过期 AvailabilitySnapshot。创建 AgentRun 时必须写入两种 snapshot id，并断言二者 employee/company/work item 相同、`prospective_execution_sha256=content_sha256`、availability 为 available 且尚未过期。总经理 Plan Run 使用总经理职员、总经理办公室 revision，`department_task_id/employee_task_id` 为 null。Snapshot 插入后禁止 UPDATE/DELETE。`departmentTask.replaceEmployee` 必须把尚未运行的旧 EmployeeTask 置 `cancelled`，为替代职员创建新 EmployeeTask、可用性证据和 ExecutionSnapshot；不得修改旧 EmployeeTask 的 `employee_id` 或旧 Snapshot。

### H.7 状态迁移实现

每种聚合在 Python 中使用一张不可变迁移表：

```python
ALLOWED_TRANSITIONS: dict[State, frozenset[State]]
```

状态命令固定步骤：读取当前 state/version、检查迁移表、校验业务 guard、`UPDATE ... WHERE id=? AND version=?`、检查影响行数为 1、写事件。禁止直接设置任意状态的通用 Repository 方法。

以下表是 `ALLOWED_TRANSITIONS` 的唯一来源。`—` 表示终态，任何迁移都返回 `STATE_TRANSITION_INVALID`。

CompanyTask：

| 当前状态 | 允许目标状态 |
|---|---|
| `draft` | `analyzing/cancelling` |
| `analyzing` | `awaiting_user_confirmation/waiting_resource/cancelling/failed` |
| `awaiting_user_confirmation` | `approved/revision_requested/rejected/cancelling` |
| `revision_requested` | `analyzing/rejected/cancelling` |
| `approved` | `dispatching/cancelling` |
| `dispatching` | `checking_resources/waiting_dependency/waiting_resource/cancelling/failed` |
| `checking_resources` | `executing/waiting_dependency/waiting_resource/waiting_permission/cancelling/failed` |
| `executing` | `reviewing/waiting_dependency/waiting_resource/waiting_permission/paused/cancelling/failed` |
| `reviewing` | `fixing/final_review/waiting_resource/waiting_permission/paused/cancelling/failed` |
| `fixing` | `reviewing/waiting_resource/waiting_permission/paused/cancelling/failed` |
| `final_review` | `completed/fixing/waiting_resource/waiting_permission/paused/cancelling/failed` |
| `waiting_dependency/waiting_resource/waiting_permission/paused` | 当前 `resume_state`、`cancelling` 或 `failed` |
| `cancelling` | `cancelled/failed` |
| `rejected/completed/cancelled/failed` | — |

DepartmentTask：

| 当前状态 | 允许目标状态 |
|---|---|
| `draft` | `checking_resources/cancelled` |
| `checking_resources` | `ready/waiting_resource/waiting_permission/cancelled/failed` |
| `ready` | `executing/waiting_dependency/waiting_resource/waiting_permission/cancelled/failed` |
| `executing` | `reviewing/waiting_resource/waiting_permission/cancelled/failed` |
| `reviewing` | `fixing/completed/waiting_resource/waiting_permission/cancelled/failed` |
| `fixing` | `reviewing/waiting_resource/waiting_permission/cancelled/failed` |
| `waiting_dependency/waiting_resource/waiting_permission` | 当前 `resume_state`、`cancelled` 或 `failed` |
| `completed/cancelled/failed` | — |

EmployeeTask：

| 当前状态 | 允许目标状态 |
|---|---|
| `assigned` | `ready/waiting_resource/cancelled/failed` |
| `ready` | `running/waiting_resource/cancelled/failed` |
| `running` | `submitted/waiting_resource/cancelled/failed` |
| `submitted` | `peer_reviewing/changes_requested/accepted/failed` |
| `peer_reviewing` | `changes_requested/accepted/failed` |
| `changes_requested` | `ready/waiting_resource/cancelled/failed` |
| `waiting_resource` | 当前 `resume_state`、`cancelled` 或 `failed` |
| `accepted/cancelled/failed` | — |

AgentRun：

| 当前状态 | 允许目标状态 |
|---|---|
| `queued` | `probing/cancelled` |
| `probing` | `starting/waiting_resource/cancelled/failed` |
| `starting` | `running/retrying/waiting_resource/cancelled/timed_out/failed` |
| `running` | `waiting_approval/verifying/retrying/waiting_resource/cancelled/timed_out/failed/lost` |
| `waiting_approval/waiting_resource` | 当前 `resume_state`、`cancelled/timed_out/failed` |
| `verifying` | `succeeded/retrying/waiting_approval/waiting_resource/cancelled/timed_out/failed` |
| `retrying` | `starting/cancelled/timed_out/failed` |
| `lost` | `retrying/waiting_approval/cancelled/failed` |
| `succeeded/cancelled/timed_out/failed` | — |

其他聚合：

| 聚合 | 当前状态 | 允许目标状态 |
|---|---|---|
| CompanyPlanVersion | `draft` | `awaiting_user_confirmation/rejected` |
| CompanyPlanVersion | `awaiting_user_confirmation` | `approved/superseded/rejected` |
| CompanyPlanVersion | `approved/superseded/rejected` | — |
| ReviewAssignment | `assigned` | `in_review/stale/cancelled` |
| ReviewAssignment | `in_review` | `submitted/stale/cancelled` |
| ReviewAssignment | `submitted` | `stale` |
| ReviewAssignment | `stale/cancelled` | — |
| ReviewIssue | `open` | `fixing/rejected` |
| ReviewIssue | `fixing` | `resolved` |
| ReviewIssue | `resolved` | `verified/fixing` |
| ReviewIssue | `verified` | `closed/fixing` |
| ReviewIssue | `closed/rejected` | — |
| TaskWorkspace | `preparing` | `active/abandoned` |
| TaskWorkspace | `active` | `ready_to_apply/abandoned` |
| TaskWorkspace | `ready_to_apply` | `applied/abandoned` |
| TaskWorkspace | `applied/abandoned` | — |

CompanyTask/DepartmentTask 进入 `waiting_dependency/waiting_resource/waiting_permission/paused` 中其状态集合包含的等待态时，`resume_state` 必须等于迁移前状态；EmployeeTask 进入 `waiting_resource` 时同理。AgentRun 进入 `waiting_resource` 时记录迁移前状态；进入 `waiting_approval` 时，外部写审批的 resume state 等于迁移前的 `running/verifying`，不确定恢复审批固定为 `retrying`。离开等待态时必须在同一次 UPDATE 清空；恢复命令只能回到该值，调用方不能传任意目标。`rejected` 只允许 `medium/low` ReviewIssue，必须填写 `rejection_reason`；`blocker/high` 只能走 `fixing → resolved → verified → closed`。当被审 Artifact 出现新版本时，所有指向旧哈希且未 stale/cancelled 的 ReviewAssignment 在同一事务变为 `stale`。

### H.8 Plan 生成与确认

总经理 Plan AgentRun 使用 `company-plan.schema.json`。模型输出解析失败后只允许两次格式修复；第三次失败设置 CompanyTask `failed` 和 `PLAN_OUTPUT_INVALID`。

部门候选评分：

```text
40 × task_type_match(0或1)
+ 30 × capability_coverage(0..1)
+ 20 × deliverable_coverage(0..1)
+ 10 × quality_gate_coverage(0..1)
```

低于 60 不进入候选。相同分数按 Department.created_at、id 升序。PlanValidator 禁止模型选择候选外部门，唯一例外是明确标记 `general_manager_office_temporary_assignment=true`。

确认必须提交 plan id、version 和 SHA-256。事务内只确认当前 `awaiting_user_confirmation` 版本，创建 DepartmentTask、Dependencies 和 TaskContextSnapshot。任何不一致返回 `PLAN_VERSION_CONFLICT`。

同一 CompanyTask 只允许在首次 approved 前生成多个 PlanVersion；要求修改时旧 awaiting 版本变 superseded，再生成下一版本。首次确认并创建 TaskContextSnapshot 后，Plan 与 Snapshot 永久锁定。若执行中替代资源会改变目标、权限、交付物或质量门禁，Orchestrator 返回影响摘要并拒绝替换；用户必须显式取消原任务及非终态下级对象。待 active Run 终止且原任务进入 cancelled/failed 后，用户从公司会话发起新任务，Command Handler 创建 draft CompanyTask，`supersedes_task_id` 指向原任务，复用用户明确选择的原始需求和 Artifact 引用并补充变化原因，再走完整分析和用户确认。目标任务必须属于同公司、创建时间更早且已进入 cancelled/failed，因而继任链不能成环。禁止覆盖旧计划、旧 Snapshot 或旧 DepartmentTask。

### H.9 标准软件需求工作流模板

应用资源内固定文件 `workflow-templates/software_requirement_delivery.v1.json`：

```json
{
  "key": "software_requirement_delivery",
  "version": 1,
  "stages": [
    {"key":"requirements_architecture","responsibility":"requirements_architecture","depends_on":[]},
    {"key":"implementation","responsibility":"software_development","depends_on":["requirements_architecture"]},
    {"key":"test_design","responsibility":"software_testing","depends_on":["requirements_architecture"]},
    {"key":"first_validation","responsibility":"software_testing","depends_on":["implementation","test_design"]},
    {"key":"repair_and_review","responsibility":"software_development","depends_on":["first_validation"]},
    {"key":"final_validation","responsibility":"software_testing","depends_on":["repair_and_review"]},
    {"key":"general_manager_final_review","responsibility":"general_management","depends_on":["final_validation"]}
  ]
}
```

实现和测试设计并行，其他依赖不可改变。模板文件带 SHA-256 并写入 Plan 快照。

### H.10 Runtime 队列与 Lease

```sql
CREATE TABLE runtime_queue (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    work_item_type TEXT NOT NULL CHECK(work_item_type IN (
        'interactive_turn','company_plan','employee_task','review',
        'verification','repair','merge','summary','knowledge_index'
    )),
    work_item_id TEXT NOT NULL,
    job_id TEXT NOT NULL UNIQUE,
    run_id TEXT UNIQUE,
    priority INTEGER NOT NULL CHECK(priority IN (0,10,20,30)),
    status TEXT NOT NULL CHECK(status IN ('ready','leased','completed','cancelled')),
    queued_at TEXT NOT NULL,
    leased_at TEXT,
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id)
        DEFERRABLE INITIALLY DEFERRED,
    CHECK((work_item_type='knowledge_index' AND run_id IS NULL)
       OR (work_item_type<>'knowledge_index' AND run_id IS NOT NULL)),
    UNIQUE(id, job_id)
);
CREATE UNIQUE INDEX uq_runtime_queue_active_work_item
    ON runtime_queue(work_item_type, work_item_id)
    WHERE status IN ('ready','leased');

CREATE TABLE runtime_company_fairness (
    company_id TEXT PRIMARY KEY,
    last_dispatched_at TEXT NOT NULL
);

CREATE TABLE runtime_leases (
    id TEXT PRIMARY KEY,
    queue_id TEXT NOT NULL UNIQUE REFERENCES runtime_queue(id),
    job_id TEXT NOT NULL UNIQUE,
    run_id TEXT UNIQUE,
    employee_id TEXT,
    company_id TEXT NOT NULL,
    conversation_id TEXT,
    acquired_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY(queue_id, job_id) REFERENCES runtime_queue(id, job_id),
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id),
    FOREIGN KEY(conversation_id, company_id) REFERENCES conversations(id, company_id),
    CHECK((run_id IS NULL AND employee_id IS NULL AND conversation_id IS NULL)
       OR (run_id IS NOT NULL AND employee_id IS NOT NULL AND conversation_id IS NOT NULL))
);
```

Run purpose 到 Queue work item type 的固定映射为：`interactive_turn→interactive_turn`、`company_plan→company_plan`、`task_execution→employee_task`、`review→review`、`verification→verification`、`repair→repair`、`merge→merge`、`summary→summary`。知识索引没有 AgentRun。优先级：interactive_turn/company_plan/summary 为 0，task_execution/repair/merge 为 10，review/verification 为 20，knowledge_index 为 30。同优先级先选 `last_dispatched_at` 最早的公司，再选最早 queue entry。获取 queue、global slot、employee slot 和 conversation slot 必须在同一 `BEGIN IMMEDIATE` 事务完成；知识索引没有 Employee/Conversation slot，只占一个 ProcessPool slot。Lease 30 秒，每 5 秒续租。

### H.11 AgentRun、事件和 Checkpoint

```sql
CREATE TABLE agent_runs (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    employee_task_id TEXT,
    employee_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    availability_snapshot_id TEXT NOT NULL,
    execution_snapshot_id TEXT NOT NULL,
    run_purpose TEXT NOT NULL CHECK(run_purpose IN (
        'interactive_turn','company_plan','task_execution','review','verification',
        'repair','merge','summary'
    )),
    adapter_type TEXT NOT NULL CHECK(adapter_type IN ('codex_cli','claude_code','opencode','api_model')),
    native_session_id TEXT,
    process_pid INTEGER,
    process_group_id INTEGER,
    process_started_at TEXT,
    run_spec_json TEXT NOT NULL CHECK(json_valid(run_spec_json)),
    run_spec_sha256 TEXT NOT NULL CHECK(length(run_spec_sha256)=64),
    status TEXT NOT NULL CHECK(status IN (
        'queued','probing','starting','running','waiting_approval','verifying',
        'retrying','succeeded','waiting_resource','cancelled','timed_out','failed','lost'
    )),
    resume_state TEXT CHECK(resume_state IS NULL OR resume_state IN (
        'probing','starting','running','verifying','retrying'
    )),
    attempt INTEGER NOT NULL CHECK(attempt BETWEEN 1 AND 6),
    started_at TEXT,
    completed_at TEXT,
    exit_code INTEGER,
    failure_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(employee_task_id, company_id) REFERENCES employee_tasks(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id),
    FOREIGN KEY(conversation_id, company_id) REFERENCES conversations(id, company_id),
    FOREIGN KEY(availability_snapshot_id, company_id)
        REFERENCES employee_availability_snapshots(id, company_id),
    FOREIGN KEY(execution_snapshot_id, company_id)
        REFERENCES execution_snapshots(id, company_id),
    UNIQUE(id, company_id),
    CHECK((run_purpose = 'task_execution' AND employee_task_id IS NOT NULL)
       OR (run_purpose <> 'task_execution')),
    CHECK((status IN ('waiting_approval','waiting_resource') AND resume_state IS NOT NULL)
       OR (status NOT IN ('waiting_approval','waiting_resource') AND resume_state IS NULL)),
    CHECK((process_pid IS NULL AND process_group_id IS NULL AND process_started_at IS NULL)
       OR (process_pid > 0 AND process_group_id > 0 AND process_started_at IS NOT NULL))
);

CREATE TABLE agent_run_events (
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    event_id TEXT NOT NULL UNIQUE,
    sequence INTEGER NOT NULL CHECK(sequence > 0),
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    native_event_json TEXT CHECK(native_event_json IS NULL OR json_valid(native_event_json)),
    trace_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    PRIMARY KEY(run_id, sequence)
);
CREATE TRIGGER agent_run_events_no_update
BEFORE UPDATE ON agent_run_events
BEGIN SELECT RAISE(ABORT, 'agent run event is immutable'); END;
CREATE TRIGGER agent_run_events_no_delete
BEFORE DELETE ON agent_run_events
WHEN OLD.event_type <> 'model.output.delta'
BEGIN SELECT RAISE(ABORT, 'non-delta agent run event is immutable'); END;

CREATE TABLE checkpoints (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    sequence INTEGER NOT NULL,
    boundary_type TEXT NOT NULL,
    storage_type TEXT NOT NULL CHECK(storage_type IN ('sqlite_blob','file')),
    compressed_blob BLOB,
    file_path TEXT,
    uncompressed_size INTEGER NOT NULL,
    sha256 TEXT NOT NULL CHECK(length(sha256)=64),
    created_at TEXT NOT NULL,
    CHECK(
        (storage_type='sqlite_blob' AND compressed_blob IS NOT NULL AND file_path IS NULL)
        OR
        (storage_type='file' AND compressed_blob IS NULL AND file_path IS NOT NULL)
    ),
    UNIQUE(run_id, sequence)
);

CREATE TABLE tool_executions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES agent_runs(id),
    tool_call_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    input_json TEXT NOT NULL CHECK(json_valid(input_json)),
    input_sha256 TEXT NOT NULL CHECK(length(input_sha256)=64),
    status TEXT NOT NULL CHECK(status IN ('requested','approved','started','completed','failed','uncertain')),
    result_json TEXT CHECK(result_json IS NULL OR json_valid(result_json)),
    result_sha256 TEXT,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(run_id, tool_call_id)
);

CREATE TABLE human_approvals (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    approval_type TEXT NOT NULL CHECK(approval_type IN ('external_write','uncertain_recovery')),
    target_json TEXT NOT NULL CHECK(json_valid(target_json)),
    target_sha256 TEXT NOT NULL CHECK(length(target_sha256)=64),
    status TEXT NOT NULL CHECK(status IN ('pending','allowed','denied','expired','consumed')),
    requested_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    resolved_at TEXT,
    consumed_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id)
);

CREATE TABLE verification_results (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    round_number INTEGER NOT NULL CHECK(round_number BETWEEN 1 AND 6),
    command_argv_json TEXT NOT NULL CHECK(json_valid(command_argv_json)),
    exit_code INTEGER NOT NULL,
    stdout_artifact_id TEXT,
    stderr_artifact_id TEXT,
    status TEXT NOT NULL CHECK(status IN ('passed','failed','timed_out')),
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    UNIQUE(run_id, round_number, command_argv_json),
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id),
    FOREIGN KEY(stdout_artifact_id, company_id) REFERENCES artifacts(id, company_id),
    FOREIGN KEY(stderr_artifact_id, company_id) REFERENCES artifacts(id, company_id)
);

CREATE TABLE workspace_grants (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    normalized_path TEXT NOT NULL,
    security_bookmark BLOB NOT NULL,
    path_type TEXT NOT NULL CHECK(path_type IN ('code_repository','import_source')),
    status TEXT NOT NULL CHECK(status IN ('active','revoked','stale')),
    created_at TEXT NOT NULL,
    last_resolved_at TEXT,
    UNIQUE(id, company_id)
);
CREATE UNIQUE INDEX uq_workspace_active_path
    ON workspace_grants(normalized_path) WHERE status='active';

CREATE TABLE task_workspaces (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    workspace_grant_id TEXT NOT NULL,
    repository_root TEXT NOT NULL,
    baseline_commit_sha TEXT NOT NULL CHECK(length(baseline_commit_sha) IN (40,64)),
    user_branch_name TEXT NOT NULL,
    integration_branch_name TEXT NOT NULL,
    integration_worktree_path TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN (
        'preparing','active','ready_to_apply','applied','abandoned'
    )),
    applied_commit_sha TEXT,
    cleaned_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(workspace_grant_id, company_id) REFERENCES workspace_grants(id, company_id),
    UNIQUE(id, company_id),
    UNIQUE(id, company_task_id, company_id),
    UNIQUE(company_task_id)
);
```

### H.12 Artifact 与 Review DDL

```sql
CREATE TABLE artifacts (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    company_task_id TEXT NOT NULL,
    department_task_id TEXT,
    employee_task_id TEXT,
    artifact_type TEXT NOT NULL CHECK(artifact_type IN (
        'source_code_patch','document','test_case','test_result','review_report',
        'execution_report','department_report','final_report','log','diff',
        'checkpoint','transcript','diagnostic','imported_file','merge_report','git_bundle','manifest'
    )),
    logical_name TEXT NOT NULL,
    object_sha256 TEXT NOT NULL CHECK(length(object_sha256)=64),
    object_size INTEGER NOT NULL CHECK(object_size >= 0),
    media_type TEXT NOT NULL,
    metadata_json TEXT NOT NULL CHECK(json_valid(metadata_json)),
    supersedes_artifact_id TEXT,
    created_by_type TEXT NOT NULL CHECK(created_by_type IN ('user','agent','system')),
    created_by_run_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(id, company_id),
    FOREIGN KEY(company_task_id, company_id) REFERENCES company_tasks(id, company_id),
    FOREIGN KEY(department_task_id, company_id) REFERENCES department_tasks(id, company_id),
    FOREIGN KEY(employee_task_id, company_id) REFERENCES employee_tasks(id, company_id),
    FOREIGN KEY(supersedes_artifact_id, company_id) REFERENCES artifacts(id, company_id),
    FOREIGN KEY(created_by_run_id, company_id) REFERENCES agent_runs(id, company_id),
    CHECK((created_by_type='agent' AND created_by_run_id IS NOT NULL)
       OR (created_by_type<>'agent' AND created_by_run_id IS NULL))
);
CREATE INDEX ix_artifacts_task_type
    ON artifacts(company_task_id, artifact_type, created_at);

CREATE TABLE artifact_contributors (
    artifact_id TEXT NOT NULL,
    company_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    PRIMARY KEY(artifact_id, employee_id),
    FOREIGN KEY(artifact_id, company_id) REFERENCES artifacts(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id)
);

CREATE TABLE review_assignments (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    reviewer_employee_id TEXT NOT NULL,
    review_round INTEGER NOT NULL CHECK(review_round > 0),
    reviewed_sha256 TEXT NOT NULL CHECK(length(reviewed_sha256)=64),
    status TEXT NOT NULL CHECK(status IN ('assigned','in_review','submitted','stale','cancelled')),
    assigned_at TEXT NOT NULL,
    submitted_at TEXT,
    FOREIGN KEY(artifact_id, company_id) REFERENCES artifacts(id, company_id),
    FOREIGN KEY(reviewer_employee_id, company_id) REFERENCES employees(id, company_id),
    UNIQUE(id, company_id),
    UNIQUE(artifact_id, reviewer_employee_id, review_round)
);

CREATE TABLE review_reports (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    assignment_id TEXT NOT NULL UNIQUE,
    reviewer_run_id TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK(verdict IN ('pass','needs_changes','failed')),
    report_artifact_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(id, company_id),
    FOREIGN KEY(assignment_id, company_id) REFERENCES review_assignments(id, company_id),
    FOREIGN KEY(reviewer_run_id, company_id) REFERENCES agent_runs(id, company_id),
    FOREIGN KEY(report_artifact_id, company_id) REFERENCES artifacts(id, company_id)
);

CREATE TABLE review_issues (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    review_report_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('blocker','high','medium','low')),
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    expected TEXT NOT NULL,
    actual TEXT NOT NULL,
    suggested_fix TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL CHECK(json_valid(evidence_refs_json)),
    status TEXT NOT NULL CHECK(status IN ('open','fixing','resolved','verified','closed','rejected')),
    assignee_employee_id TEXT,
    verifier_employee_id TEXT,
    rejection_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    CHECK(status <> 'rejected' OR (severity IN ('medium','low') AND rejection_reason IS NOT NULL)),
    FOREIGN KEY(review_report_id, company_id) REFERENCES review_reports(id, company_id),
    FOREIGN KEY(assignee_employee_id, company_id) REFERENCES employees(id, company_id),
    FOREIGN KEY(verifier_employee_id, company_id) REFERENCES employees(id, company_id)
);

CREATE TRIGGER artifacts_no_update
BEFORE UPDATE ON artifacts
BEGIN
    SELECT RAISE(ABORT, 'artifact is immutable');
END;
CREATE TRIGGER artifacts_no_delete
BEFORE DELETE ON artifacts
BEGIN
    SELECT RAISE(ABORT, 'artifact is immutable');
END;
```

`metadata_json` 按 artifact type 使用 `packages/contracts/artifacts/{artifact_type}.metadata.schema.json` 校验；document 的 `document_role` 固定为 `requirements/design/implementation_plan/general`。

document、source_code_patch、test_case、test_result、execution_report、department_report 和 merge_report 进入 Review；final_report、review_report、log、diff、checkpoint、transcript、diagnostic、imported_file、git_bundle 和 manifest 是闭环结果、证据或输入，不再递归 Review。

普通部门交付物的 `eligible = DepartmentTask 参与职员 - Artifact 贡献者`，部门负责人未贡献时加入。document role 为 requirements/design/implementation_plan 的文档，以及 source_code_patch、test_case 和 test_result 是关键产物，分配 `min(2, eligible数量)` 人；其他可 Review 产物分配 1 人。department_report 改用公司级池：总经理未参与该报告时必选，再从总经理办公室当前任务参与职员中按相同负载规则补足至 2 人；所有贡献者仍必须排除。final_report 只有在所有 department_report 通过公司级 Review、所有 blocker/high 问题 closed 且总经理完成跨部门一致性检查后才能生成，因此不再分配后续 Review。eligible 为空时任务进入 `waiting_resource`。

提交 ReviewReport 时 Command Handler 必须断言 `reviewer_run_id.employee_id = assignment.reviewer_employee_id`、Run purpose 为 review、`reviewed_sha256 = artifact.object_sha256`，且 `report_artifact_id` 类型为 review_report、由该 Run 创建；任一不符返回 `REVIEW_SELF_ASSIGNMENT` 或 `VALIDATION_FAILED`。

### H.13 知识 DDL

```sql
CREATE TABLE knowledge_items (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id),
    source_artifact_id TEXT,
    source_message_id TEXT,
    owner_employee_id TEXT,
    department_id TEXT,
    task_id TEXT,
    visibility TEXT NOT NULL CHECK(visibility IN ('company','department','task','private')),
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
    embedding_generation_id TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(id, company_id)
);

CREATE VIRTUAL TABLE knowledge_fts USING fts5(
    knowledge_id UNINDEXED,
    company_id UNINDEXED,
    title,
    content,
    tokenize='unicode61'
);

CREATE TABLE embedding_generations (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    model_key TEXT NOT NULL,
    vector_dimension INTEGER NOT NULL CHECK(vector_dimension=384),
    status TEXT NOT NULL CHECK(status IN ('building','active','retired','failed')),
    created_at TEXT NOT NULL,
    activated_at TEXT
);
CREATE UNIQUE INDEX uq_active_embedding_generation
    ON embedding_generations(company_id) WHERE status='active';

CREATE TABLE knowledge_access_logs (
    row_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    company_id TEXT NOT NULL REFERENCES companies(id),
    run_id TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    query_sha256 TEXT NOT NULL CHECK(length(query_sha256)=64),
    visibility_scope_json TEXT NOT NULL CHECK(json_valid(visibility_scope_json)),
    candidate_ids_json TEXT NOT NULL CHECK(json_valid(candidate_ids_json)),
    selected_ids_json TEXT NOT NULL CHECK(json_valid(selected_ids_json)),
    context_pack_sha256 TEXT NOT NULL CHECK(length(context_pack_sha256)=64),
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id, company_id) REFERENCES agent_runs(id, company_id),
    FOREIGN KEY(employee_id, company_id) REFERENCES employees(id, company_id)
);
CREATE INDEX ix_knowledge_access_run
    ON knowledge_access_logs(run_id, row_sequence);
CREATE TRIGGER knowledge_access_logs_no_update
BEFORE UPDATE ON knowledge_access_logs
BEGIN SELECT RAISE(ABORT, 'knowledge access log is immutable'); END;
CREATE TRIGGER knowledge_access_logs_no_delete
BEFORE DELETE ON knowledge_access_logs
BEGIN SELECT RAISE(ABORT, 'knowledge access log is immutable'); END;
```

LanceDB 表字段固定为 `knowledge_id`、`company_id`、`visibility`、`department_id`、`task_id`、`owner_employee_id`、`vector[384]` 和 `content_sha256`。激活 generation 前必须对账 SQLite 数量和哈希。

### H.13.1 备份记录

```sql
CREATE TABLE backup_records (
    id TEXT PRIMARY KEY,
    backup_type TEXT NOT NULL CHECK(backup_type IN ('daily','weekly','manual','pre_upgrade')),
    archive_path TEXT NOT NULL UNIQUE,
    archive_size INTEGER NOT NULL CHECK(archive_size > 0),
    archive_sha256 TEXT NOT NULL CHECK(length(archive_sha256)=64),
    manifest_json TEXT NOT NULL CHECK(json_valid(manifest_json)),
    status TEXT NOT NULL CHECK(status IN ('creating','completed','failed','deleted')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    error_code TEXT
);
```

清理只删除 status completed 且超出保留策略的自动备份；先把状态改 deleted，再删除文件，失败时恢复 completed 并记录错误。

### H.14 本地审计

```sql
CREATE TABLE audit_logs (
    row_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    company_id TEXT,
    actor_type TEXT NOT NULL CHECK(actor_type IN ('user','employee','system')),
    actor_id TEXT,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    outcome TEXT NOT NULL CHECK(outcome IN ('success','denied','failed')),
    detail_json TEXT NOT NULL CHECK(json_valid(detail_json)),
    trace_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX ix_audit_company_sequence ON audit_logs(company_id, row_sequence);
CREATE TRIGGER audit_logs_no_update
BEFORE UPDATE ON audit_logs
BEGIN SELECT RAISE(ABORT, 'audit log is immutable'); END;
CREATE TRIGGER audit_logs_no_delete
BEFORE DELETE ON audit_logs
BEGIN SELECT RAISE(ABORT, 'audit log is immutable'); END;
```

审计 detail 在写入前删除 Prompt、消息正文、密码、Token、API Key 和完整文件内容，仅保存哈希、相对路径和稳定枚举。

## 附录 I：Agent Runtime Gateway 实施规范

### I.1 模块与入口

```text
sidecar/ibreeze/runtime/
├── gateway.py
├── scheduler.py
├── process_supervisor.py
├── event_normalizer.py
├── checkpoint.py
├── context_engine.py
├── verification_loop.py
├── permission_gateway.py
├── workspace_broker.py
├── tools/
├── cli_adapters/
│   ├── codex.py
│   ├── claude_code.py
│   └── opencode.py
└── model_runtime/
    ├── agent_loop.py
    └── transports/
```

Orchestration 只能调用：

```python
start(run_spec: AgentRunSpec) -> RunHandle
cancel(run_id: UUID, reason: str) -> None
resume(run_id: UUID) -> RunHandle
get_status(run_id: UUID) -> AgentRun
```

禁止其他模块直接调用 `asyncio.create_subprocess_exec` 或模型 HTTP API。

### I.2 CLI 版本门禁

首个目录发布：

```text
Codex CLI       >=0.144.0 <0.145.0
Claude Code     >=2.1.0   <2.2.0
OpenCode        >=1.18.0  <1.19.0
```

版本范围以 `semantic-version` 解析。命令输出无法解析、低于下限或达到上限均返回 `AGENT_VERSION_INCOMPATIBLE`。后台发布新范围前必须提交该范围的契约测试证据。

Adapter Registry key 与 Agent Catalog key 完全一致，v1 只注册 `codex_cli/claude_code/opencode`，AgentRun 的 `adapter_type` 直接保存该 key。目录出现客户端未注册 key 时显示“需要升级客户端”并标记 unavailable，禁止退回通用 Shell 命令执行。

### I.3 Agent 原生状态目录

```text
profiles/{profile}/agent-state/codex/
profiles/{profile}/agent-state/claude/
profiles/{profile}/agent-state/opencode/config/
profiles/{profile}/agent-state/opencode/data/
profiles/{profile}/agent-state/opencode/cache/
```

环境变量：

```text
CODEX_HOME={codex_dir}
CLAUDE_CONFIG_DIR={claude_dir}
XDG_CONFIG_HOME={opencode_config_dir}
XDG_DATA_HOME={opencode_data_dir}
XDG_CACHE_HOME={opencode_cache_dir}
```

用户在 iBreeze Agent 登录终端中完成原生登录。状态目录不进入 Context、备份或日志。

### I.4 Codex Adapter

探测：

```text
codex --version
codex login status
```

首次执行 argv：

```text
codex exec
--json
--color never
--strict-config
--ignore-user-config
--sandbox workspace-write
--cd {workspace}
--model {model}
--output-last-message {run_temp}/last-message.txt
-
```

非 Git Workspace 增加 `--skip-git-repo-check`。Prompt 通过 stdin 写入并关闭 stdin。

恢复 argv：

```text
codex exec
--json
--color never
--strict-config
--ignore-user-config
--sandbox workspace-write
--cd {workspace}
--model {model}
--output-last-message {run_temp}/last-message.txt
resume
{native_session_id}
-
```

stdout 逐行 JSON 解析；首个 thread/session started 事件必须提供 native session id。completed 事件最终文本与 last-message 文件分别做 SHA-256；不一致返回 `ADAPTER_RESULT_MISMATCH`。禁止任何 dangerous bypass 参数。

### I.5 Claude Code Adapter

探测：

```text
claude --version
claude auth status --json
```

首次执行 argv：

```text
claude
--print
--input-format stream-json
--output-format stream-json
--include-partial-messages
--safe-mode
--strict-mcp-config
--setting-sources ""
--model {model}
--permission-mode dontAsk
--allowedTools Bash Read Edit Write Glob Grep
--session-id {generated_uuid}
```

恢复追加 `--resume {native_session_id}`，禁止使用 `--continue`。输入和后续 turn 均为 stream-json。`--safe-mode` 关闭用户插件、Hooks、CLAUDE.md、MCP 和自动记忆；Skill 由 iBreeze Context Engine 注入。禁止 `--dangerously-skip-permissions` 和 `--max-budget-usd`。

### I.6 OpenCode Adapter

探测：

```text
opencode --version
opencode auth list --pure
opencode models
```

Runtime 把完整 Prompt 写入 `{run_temp}/task.md`，权限 `0600`，作为 `--file` 附件保留到 Run 终止后删除。argv：

```text
opencode run
--pure
--format json
--model {provider/model}
--agent build
--dir {workspace}
--auto
--file {run_temp}/task.md
Read the attached task.md and execute every instruction.
```

恢复时追加 `--session {native_session_id}`。禁止 `--share`、`--attach` 和固定监听端口。`--auto` 只有 Seatbelt Profile 探测与加载成功后才允许使用。

### I.7 子进程监管

- 每个 Run 创建独立进程组。
- CLI 启动成功后立即把 PID、PGID 和进程启动时间写入 `agent_runs` 并通过 `runtime.processRegistered` 事件通知 Rust；Rust 在 Sidecar 心跳丢失时按 PGID 终止已登记进程组。重新启动时 Sidecar 用 PID+启动时间+可执行文件路径三项校验，防止 PID 复用后误杀无关进程。
- stdout/stderr 分开读取；单行最大 4 MiB。
- stderr 最近 1 MiB写诊断记录，完整日志滚动写文件。
- 超时或取消：SIGINT 等 5 秒、SIGTERM 等 5 秒、SIGKILL 整个进程组。
- 退出时记录 exit code、signal、最后 sequence、stdout/stderr SHA-256。
- 子进程不得双重 fork 或脱离进程组；安全测试发现即禁用版本。

### I.8 macOS Seatbelt

所有 CLI Agent 和 `run_shell` 通过：

```text
/usr/bin/sandbox-exec -f {run_temp}/profile.sb command args...
```

模板：

```scheme
(version 1)
(deny default)
(allow process*)
(allow sysctl-read)
(allow mach-lookup)
(deny mach-lookup (global-name "com.apple.securityd"))
(deny mach-lookup (global-name "com.apple.secd"))
(deny mach-lookup (global-name "com.apple.SecurityServer"))
(allow file-read*)
(deny file-read* (subpath "${OTHER_PROFILE_ROOTS}"))
(deny file-read* (subpath "${OTHER_COMPANY_ROOTS}"))
(deny file-read* (subpath "${OTHER_EMPLOYEE_PRIVATE_ROOTS}"))
(deny file-read* (subpath "${USER_HOME}/.ssh"))
(deny file-read* (subpath "${USER_HOME}/.gnupg"))
(deny file-read* (subpath "${USER_HOME}/.aws"))
(deny file-read* (subpath "${USER_HOME}/.azure"))
(deny file-read* (subpath "${USER_HOME}/.kube"))
(deny file-read* (subpath "${USER_HOME}/.docker"))
(deny file-read* (subpath "${USER_HOME}/.config/gcloud"))
(deny file-read* (subpath "${USER_HOME}/Library/Keychains"))
(deny file-read* (literal "${USER_HOME}/.netrc"))
(deny file-read* (literal "${USER_HOME}/.npmrc"))
(deny file-read* (literal "${USER_HOME}/.pypirc"))
(deny file-read* (literal "${USER_HOME}/.git-credentials"))
(allow file-read* (subpath "${RUN_WORKSPACE}"))
(allow file-read* (subpath "${RUN_TEMP}"))
(allow file-read* (subpath "${AGENT_STATE}"))
(allow file-write* (subpath "${RUN_WORKSPACE}"))
(allow file-write* (subpath "${RUN_TEMP}"))
(allow file-write* (subpath "${AGENT_STATE}"))
(allow network-outbound (remote tcp "localhost:${EGRESS_PROXY_PORT}"))
(deny network-inbound)
```

`${...}` 不是文本拼接；生成器只接受经 `realpath` 解析、验证归属的路径并执行 SBPL 字符串转义，端口只接受 Rust 创建监听器后返回的十进制 `1024..65535`。Workspace Grant 不能选择上述凭据目录或文件，也不能选择其他 Profile/Company/Employee 私有目录。生成文件 `0600`，保存 SHA-256。启动探测若 `/usr/bin/sandbox-exec` 不存在或最小 allow/deny/代理测试失败，CLI 职员全部 unavailable。

上述 Workspace 写规则只在 `run_purpose` 为 task_execution/verification/repair/merge 时生成；interactive_turn/company_plan/review/summary 必须完全省略 `${RUN_WORKSPACE}` 的 `file-write*`，只保留 RUN_TEMP 和 AGENT_STATE 写入。Built-in API Model 对这四类只读 purpose 同步使用无 write_file/apply_patch/run_shell-write 工具的 ToolPolicy。任何只读 purpose Run 观测到 Workspace 内容哈希变化都以 `WORKSPACE_ACCESS_DENIED` 失败并写安全审计。

每个受支持 CLI 版本必须通过：Workspace 写成功、外部普通文件只读、其他公司不可读、其他职员私有区不可读、外部写失败、直接公网连接失败、只允许代理白名单 HTTPS、后台进程不能逃逸和认证文件不能被 Agent 工具输出。

常驻 CLI 子进程的 Seatbelt Profile 永远不加入 Workspace 外写权限。审批通过后的外部写入只能由 Tool Executor 启动一次性子进程或原子文件操作执行：根据 `human_approvals.target_json` 生成只含一个规范化目标的临时 SBPL allow 规则，校验旧/新哈希，执行后立即把审批置 `consumed` 并删除 Profile。CLI 自身即使在审批后也不能直接写该路径。

### I.8.1 CLI Network Egress Broker

Rust Core 为每个 CLI AgentRun 创建独立的 loopback HTTP CONNECT 代理，绑定随机端口并生成 32 字节代理 Token；端口和 Token 只通过子进程环境 `HTTPS_PROXY=http://ibreeze:{token}@127.0.0.1:{port}`、`HTTP_PROXY` 和 `ALL_PROXY` 传入，不写数据库或日志。Seatbelt 只允许连接该端口，CLI 直接 DNS、TCP 或 UDP 出站均被拒绝。

代理只接受带正确 Basic Auth 的 `CONNECT normalized-host:443`，拒绝明文 HTTP、其他端口、IP literal、userinfo 和非 CONNECT 方法。Run allowlist 是已验签 AgentVersionRange `network_domains`、已锁定 Skill `network_domains` 与计划显式声明域名的并集；域名按 IDNA ASCII lowercase 精确匹配，`*.example.com` 只匹配一个左侧 label。代理解析 DNS 后拒绝 loopback、private、link-local、multicast 和保留地址，并在每次新连接时重新解析；重定向后的新 host 必须重新经过 CONNECT 与 allowlist 校验。每 Run 最大 32 个并发隧道、每隧道空闲 120 秒、总连接建立速率 60/min；关闭 Run 时先停接收新连接，再关闭全部隧道并清零 Token。

CLI 版本契约测试必须证明其认证、模型调用和原生恢复均遵循代理变量；不遵循即把该 AgentVersionRange 标记 incompatible，禁止用放开公网作为降级方案。Skill `network_domains=[]` 不增加额外域名；API Model 的网络工具同样把请求交给 Rust Credential/Network Broker，禁止 Python 直接创建外网 socket。

### I.9 Credential HTTP Broker

API Key 只存 macOS Keychain。Sidecar 不接收明文 Key。Sidecar 通过双向本地 RPC 请求 Rust：

```text
credential.http.start
credential.http.cancel
credential.probe
```

请求包含 `credential_ref`、Provider Catalog id/version、method、relative path、非认证 headers 和 body。Rust：

1. 校验调用来自已认证 Sidecar ipc session。
2. 校验 Provider base URL 与已验签目录一致。
3. 从 Keychain 加载 Key。
4. 按 Provider auth scheme 注入 Authorization 或 x-api-key。
5. 用 reqwest 发起 HTTPS 请求。
6. 以 sequence 事件把状态、headers 白名单和 body chunks 返回 Sidecar。
7. 清除 Key 内存缓冲。

禁止 Sidecar传绝对 URL、覆盖 Host/Authorization、跟随跨 origin 重定向或访问 loopback/private/link-local 地址。DNS 解析后的每个 IP 都必须执行 SSRF 检查。

### I.10 ModelTransport

协议固定：

| protocol | endpoint | 流式 |
|---|---|---|
| `openai_responses` | `POST /v1/responses` | SSE |
| `anthropic_messages` | `POST /v1/messages` | SSE |
| `openai_chat_completions` | `POST /v1/chat/completions` | SSE |

Sidecar 构造请求，Rust Credential Broker 负责传输和认证。只重试 408、429、500、502、503、504 和连接中断；最多 3 次，延迟 1/2/4 秒加 0–250ms 抖动。401/403 标记凭据 unavailable；400/404 标记配置错误。

流式响应只有在收到协议完成事件后才写入对话事实；中断片段只写诊断并在重试时丢弃。

### I.11 Built-in Agent Loop

```text
build_context
→ model_request
→ parse_response
→ execute_tools
→ model_request
→ produce_artifact
→ verify
→ repair | complete
```

约束：

- 最多 50 个工具调用。
- 最多 5 个 verification repair round。
- 写工具严格串行。
- 最多并行 4 个声明为 read-only 且路径集合不冲突的工具。
- Tool Call 必须来自协议结构化字段；正文代码块不执行。
- 达到限制返回 `RUN_LIMIT_REACHED`。

### I.12 Tool Registry

| Tool | 输入要点 | 实现与限制 |
|---|---|---|
| `list_directory` | path、depth | 最大 depth 5、最多 5000 条 |
| `read_file` | path、offset、length | 单次最多 1 MiB |
| `search_text` | query、paths、glob | 固定 `rg --json` 参数数组 |
| `apply_patch` | unified diff | 先验证全部目标，再临时文件+原子 rename |
| `create_file` | path、content | 目标存在即失败 |
| `delete_path` | path | 仅 Run Workspace，先进入本地任务 Trash |
| `run_process` | argv、cwd、timeout | 无 Shell，Seatbelt 包裹 |
| `run_shell` | script、cwd、timeout | `/bin/zsh -lc`，Seatbelt 包裹 |
| `git_status/diff/commit` | 固定字段 | 固定 Git 参数，禁止 remote/force |
| `report_progress` | message、percent | percent 0..100 |
| `request_external_write` | path、operation、hash | 只创建审批 |

所有输入由 JSON Schema 校验。输出超过 1 MiB 写 Artifact；返回摘要、大小和引用。工具前后均写 Checkpoint。

### I.13 Workspace 外单次审批

审批绑定：

```text
realpath
operation
expected_old_sha256
new_content_sha256
run_id
expires_at（最长 10 分钟）
```

执行前重新解析路径并计算旧哈希；变化返回 `APPROVAL_TARGET_CHANGED`。批准只适用一次动作，不创建目录级永久授权。

### I.14 Context 容量计算

Catalog Model 必须给出 `context_window`、`max_output_tokens`、`tokenizer_key`。计算：

```text
output_reserve = min(max_output_tokens, floor(context_window * 0.20))
safety_reserve = 4096
input_budget = context_window - output_reserve - safety_reserve
```

`tokenizer_key` 只能是 `tiktoken:o200k_base`、`tiktoken:cl100k_base`、`hf:{runtime_asset_key}` 或 `byte_upper_bound_v1`。HF tokenizer 必须来自 J.6 同类的应用签名资源；未知 key 使模型 unavailable。`byte_upper_bound_v1` 按 UTF-8 每个 byte 计 1 token，并为每条 message/tool schema 额外计 32 tokens，作为保守上界。容量统计必须覆盖 system、messages、tool schemas、tool results 和预期协议包装，不只统计正文。

优先级：System/Skill/安全规则、任务目标和验收、最近 8 组消息与工具结果、直接引用产物、历史会话和知识。前两类不得截断；如果前两类已超 input budget，Run 在模型调用前失败 `CONTEXT_REQUIRED_CONTENT_TOO_LARGE`。

旧历史超限时由同一模型生成符合 `context-summary.schema.json` 的事实/决策/未完成项/来源摘要。最多尝试 1 次；失败后确定性保留最新内容并写 `context.summary_failed`。

### I.15 Checkpoint

边界：模型前后、工具前后、Artifact 提交后、Verification 前后。JSON 使用 zstd level 3 压缩并计算 SHA-256。压缩结果不超过 1 MiB 存 SQLite BLOB，否则写 `${task}/checkpoints/{run}/{sequence}.json.zst` 临时文件、fsync、rename。

恢复：完成且有结果哈希的工具不重放；未开始工具重做；started 未完成的只读工具重做；写入或外部副作用状态不确定进入 `RUN_RECOVERY_UNCERTAIN`。CLI 优先原生 session，失败后使用标准 transcript 和 Checkpoint 创建新 session。

## 附录 J：Workspace、Artifact、知识、备份与前端同步规范

### J.1 代码项目准入

软件开发任务必须选择 Git 仓库根目录。Rust 检查：

```text
git rev-parse --show-toplevel
git status --porcelain=v1
git rev-parse --verify HEAD
git symbolic-ref --quiet --short HEAD
git rev-parse -q --verify MERGE_HEAD
git rev-parse -q --verify CHERRY_PICK_HEAD
git rev-parse --git-path rebase-merge
git rev-parse --git-path rebase-apply
```

v1 的一个软件 CompanyTask 必须且只能绑定一个 Git 仓库。工作区必须干净、处于命名分支、且无 merge/rebase/cherry-pick；detached HEAD 同样拒绝。`MERGE_HEAD/CHERRY_PICK_HEAD` 能解析或 `rebase-merge/rebase-apply` 路径存在即视为进行中。否则任务进入 `waiting_resource`，用户自行处理；iBreeze 禁止自动 stash、WIP commit、reset 或 checkout 用户文件。

用户确认计划时，Rust 解析 security bookmark 并返回规范化仓库根；Sidecar 在同一事务创建 `task_workspaces`，锁定 `workspace_grant_id/repository_root/baseline_commit_sha/user_branch_name`，预生成 integration branch/path。`repository_root` 必须等于 grant 的 `normalized_path`，后续所有 Worktree 命令从该记录读取，不接受模型或前端传入替代路径。

同一规范化路径在整个本地 Profile 中只能属于一个 active company grant；选择已被其他公司占用的路径返回 `WORKSPACE_ACCESS_DENIED` 且不泄露对方公司内容。Grant 仅在没有非终态 TaskWorkspace/AgentRun 时可撤销，撤销后原公司历史 Artifact 仍可读，但不能恢复或新建该路径上的 Run；其他公司必须重新通过文件选择器授权，不能复用旧 security bookmark。

### J.2 Worktree 与分支

基线为确认任务时 HEAD。分支：

```text
ibreeze/{task_id}/integration
ibreeze/{task_id}/{employee_id}/{attempt}
```

Worktree 在 Profile 公司任务目录。每个职员从同一 baseline 建立独立分支。Run 完成后若有变更，先运行 Verification，再以 `ibreeze({task_short_id}): {employee_task_title}` 提交。

首次创建固定使用参数数组：

```text
git -C {repository_root} worktree add -b {integration_branch} {integration_path} {baseline_sha}
git -C {repository_root} worktree add -b {employee_branch} {employee_path} {baseline_sha}
```

命令成功并校验 `git worktree list --porcelain` 后才把 `task_workspaces.status` 置 active。恢复时若分支/路径已存在，必须同时验证 branch ref、Worktree HEAD、记录路径和 baseline；全部一致则复用，任一不一致进入 `waiting_resource`，禁止 `-B`、`--force` 或删除碰撞分支。

禁止 push、fetch、修改 remote、force、rebase baseline、删除用户分支或切换用户当前 Worktree。

### J.3 合并

按 DepartmentTask 依赖拓扑、EmployeeTask created_at、id 排序，逐个执行：

```text
git -C {integration} merge --no-ff --no-commit {employee_branch}
```

无冲突时运行合并质量门禁后提交 merge commit。有冲突立即 `git merge --abort`，保存冲突路径和 base/ours/theirs blob SHA，创建 Merge EmployeeTask。Merge Task 只在 integration Worktree 执行。最终 integration branch 不自动合入用户 branch。

`workspace.apply` 前再次确认用户根 Worktree 干净、仍位于 `user_branch_name` 且 HEAD 等于 baseline，然后执行 `git merge --no-ff --no-commit {integration_branch}`、运行最终质量门禁并以 `ibreeze({task_short_id}): apply completed task` 提交；记录 applied commit 并把状态置 applied。任一检查不满足时不修改用户 Worktree，而是生成包含新 HEAD、integration HEAD、潜在冲突和建议命令的人工合并计划 Artifact，等待用户处理，禁止直接覆盖。

`workspace.abandon` 只把 ready_to_apply 状态置 abandoned，不删除用户文件。`workspace.cleanupTask` 仅允许 applied/abandoned 且无 active Run：先生成包含所有受管 branch ref 的 Git bundle Artifact并验证 `git bundle verify`，再对记录中的干净受管 Worktree 执行非 force `git worktree remove`，最后只删除名称与数据库记录完全一致的 `ibreeze/{task_id}/...` 受管分支。全部完成后设置 `cleaned_at`；重复调用按幂等成功返回。任何一步失败立即停止并保留剩余对象；永远不删除或切换 `user_branch_name`。

### J.4 文档 Workspace

```text
baseline/
employees/{employee_id}/{attempt}/
reviews/
merged/
final/
```

Baseline 在任务确认后只读。部门负责人通过 Merge Task 综合草稿，不能由系统按字符串拼接。merged 产物必须重新 Review；final 只由部门验收命令写入。

### J.5 Artifact CAS

对象路径：`objects/sha256/{hash_prefix}/{sha256}`。写入：同目录临时文件、fsync、SHA-256、原子 rename、父目录 fsync、数据库插入。相同 Profile 内去重，不跨 Profile 去重。

正式 Artifact 不可变；修复创建新 id 和 `supersedes_artifact_id`。Manifest 字段：relative_path、create/modify/delete、before/after SHA、size、mode。二进制不生成文本 diff；文本 diff 超 5 MiB写独立 Artifact。

Symlink 保存 target，但解析后指向 Workspace 外时工具拒绝访问。

### J.6 知识 embedding

固定模型 `intfloat/multilingual-e5-small`，384 维，ONNX Runtime CPU。ONNX 模型、tokenizer 和 config 作为 Tauri 签名安装包资源随应用交付，`runtime-assets.v1.json` 固定每个文件的相对路径、大小和 SHA-256；首次使用先校验 manifest 与文件哈希，再以只读方式映射，不从 Backend 或第三方站点运行时下载。校验失败拒绝索引并进入诊断页。

分块：Markdown 按标题最大 800 tokens/重叠 100；纯文本 800/100；代码用 Tree-sitter 按函数类最大 1200；JSON/YAML 按顶层对象最大 800。Embedding 在 ProcessPool 执行。

### J.7 检索

权限先过滤：company、department、task、private。用户本人可在 UI 查看全部本地公司数据，但 Agent 只按职员上下文授权。

算法：FTS5 BM25 前 50、LanceDB cosine 前 50、RRF `score += 1/(60+rank)`、重叠去重、前 12 进入 Context。每次检索必须写 `knowledge_access_logs`，记录 query SHA-256、权限范围、候选顺序、最终命中顺序和 Context Pack SHA-256；不得保存原始 query 文本。

只有 Review 通过 Artifact、完成报告、用户导入文件和用户显式标记消息可进入长期知识。token delta、工具日志、失败草稿和未通过 Review 产物禁止索引。

### J.8 SQLite 与 LanceDB 对账

知识写 Outbox 创建新 embedding generation。构建完成后校验：条目数、knowledge id 集合、内容哈希、维度。全部一致后单事务把新 generation 设 active、旧 generation retired。启动时发现 building 超过 1 小时则标记 failed 并重建。

### J.9 备份

触发：距成功备份超过 24 小时且空闲、应用升级前、用户手动。保留最近 7 个日备份、4 个周备份；手动备份不自动清理。

流程：暂停新写命令、等待当前写事务最多 10 秒、SQLite Online Backup、收集数据库引用 CAS/目录 manifest/Skill lock、生成 SHA manifest、打包 tar.zst、原子移动。禁止包含 Keychain、CLI 状态、API Key、日志和临时 Worktree。

### J.10 恢复

恢复到 Profile 内 staging，校验路径、链接、哈希、`PRAGMA integrity_check`、migration、组合外键和 Artifact 引用，重建 FTS/LanceDB。恢复副本中的 `workspace_grants` 一律置 stale，要求用户重新经文件选择器授权；Keychain 凭据和 CLI 状态未包含，所有 Provider/Agent 在首次 Run 前重新探测。全部通过后关闭连接，将 active 原子重命名为 restore-before backup，再把 staging 切为 active并重启 Sidecar。任何失败保持原 Profile。

### J.11 RPC Schema 生成

JSON Schema 2020-12 分别存放于 `packages/rpc-schema`、`packages/contracts/events`、`packages/contracts/domain-events`、`packages/contracts/artifacts` 和本文指定的顶层契约文件。CI 使用 `json-schema-to-typescript` 生成 TypeScript、`datamodel-code-generator` 生成 Pydantic 2 模型、Rust `typify` 生成 Serde 类型。任何生成差异未提交则失败。三端禁止手写同名 DTO。

### J.12 事件补拉

每个 AgentRun 和 CompanyTask sequence 独立递增。`event.subscribe(scope, after_sequence)` 先回放数据库事件，发送 `replay_complete` 水位，再进入实时。订阅登记和水位读取在同一 EventBus 锁内，避免竞态。

前端发现跳号立即暂停该 scope 实时应用并调用 `event.replay`。Run 完成 24 小时后，Compactor 按连续 sequence 范围把 `model.output.delta` 合成为 transcript Artifact，追加一个 `model.output.compacted` 事件，载荷固定为 `{covered_from_sequence,covered_to_sequence,artifact_id,artifact_sha256}`，提交后才删除被覆盖 delta 行；其他事件禁止删除。`event.replay` 遇到已压缩区间时返回该 marker，客户端把整个 covered range 视为连续并按需加载 transcript，不把它误判为丢事件。

### J.13 前端状态边界

- TanStack Query：公司、部门、职员、任务、会话、运行、目录等事实状态。
- Zustand：当前 Profile/Company、导航、输入草稿和瞬时 UI。
- 禁止在 Zustand 复制领域实体。
- Query Key 必含 backend origin、app user、company、resource type/id。
- 写命令不乐观改变领域状态；显示 pending，等待事件或查询确认。

token delta 每 50ms 或 100 字符批量刷新。单 Run 内存缓冲最大 1 MiB；页面不可见时停止 token 渲染但继续推进 sequence。任务图最多每 200ms 重绘一次。

时间统一从 UTC 转 `Asia/Shanghai`；无时区字符串按北京时间墙钟解释。普通数值最多两位小数，不补零。

### J.14 本地 RPC 方法表

公开方法按进程固定分区：`backend.validateOrigin`、`auth.register`、`auth.login`、`auth.changePassword`、`auth.logout`、`auth.listOfflineProfiles`、`auth.openProfile`、`auth.closeProfile` 由 Rust Core 本地实现，禁止转发 Sidecar；表内其余业务方法由 Rust 校验当前 Profile 和 IPC session 后转发 Sidecar。F.3–F.5 的 `system.handshake/health/shutdown` 只用于 Rust 与 Sidecar 的监督通道，不接受 WebView 调用。

Rust 本地方法的 params/response 固定如下，密码只存在于 WebView 提交到 Rust 的单次 IPC 请求及 Rust 零化内存，不进入 Sidecar、日志、事件或持久化：

| 方法 | params | response |
|---|---|---|
| `backend.validateOrigin` | `{origin}` | `{canonical_origin,ready}`；只有 `/health/ready` 成功才保存为当前登录Origin |
| `auth.register` | `{email,password}` | `{app_user_id,email,masked_identifier}`；注册成功不自动登录 |
| `auth.login` | `{email,password}` | `{status,profile_directory_id,masked_identifier,catalog_release_sequence}`；status仅为`password_change_required/profile_opened` |
| `auth.changePassword` | `{current_password,new_password}` | 与 `auth.login` 相同；成功原子保存新session bundle并打开Profile |
| `auth.logout` | `{}` | `{closed_profile,revoked_family}`；先停止Sidecar，再撤销在线family并删除本地bundle |
| `auth.listOfflineProfiles` | `{}` | `{profiles:[{profile_directory_id,backend_origin,masked_identifier,expires_at}]}`；只返回meta、bundle和票据均有效的条目 |
| `auth.openProfile` | `{profile_directory_id}` | `{profile_directory_id,mode,catalog_release_sequence}`；mode仅为`online/offline` |
| `auth.closeProfile` | `{}` | `{closed_profile}`；停止新请求、关闭Sidecar并清理内存Access Token，不删除Keychain bundle |

`auth.login` 固定执行 REST 登录 → 验证响应与OfflineSessionTicket → 单次Keychain bundle update → 获取并验签Catalog → 原子更新Profile meta → 启动Sidecar → Sidecar校验 `local_profile` → 返回 `profile_opened`。任一步失败不得返回已打开状态；Keychain更新后的后续失败保留有效bundle，关闭Sidecar并回登录页。`auth.openProfile` 在后台可达时必须先Refresh并按相同流程轮换bundle、同步Catalog；仅网络失败时才验证本地OfflineSessionTicket并以offline打开。`auth.changePassword` 只接受受限改密session，成功响应按G.11轮换后继续执行登录后半段。`auth.logout` 在离线模式无法联系后台时关闭本地Profile并删除bundle，后端family依靠Refresh过期/服务端撤销策略失效；UI必须明确显示离线退出未完成远端撤销。

| 方法 | 类型 | 幂等保留 | 主要错误 |
|---|---|---|---|
| `backend.validateOrigin` | 写 | 仅in-flight | `VALIDATION_FAILED` |
| `auth.register` | 写 | 仅in-flight | `AUTH_EMAIL_EXISTS` |
| `auth.login` | 写 | 仅in-flight | `AUTH_INVALID_CREDENTIALS` |
| `auth.changePassword` | 写 | 仅in-flight | `AUTH_PASSWORD_CHANGE_REQUIRED` |
| `auth.logout` | 写 | 仅in-flight | `STATE_TRANSITION_INVALID` |
| `auth.listOfflineProfiles` | 读 | 无 | 无 |
| `auth.openProfile` | 写 | 仅in-flight | `OFFLINE_TICKET_INVALID` |
| `auth.closeProfile` | 写 | 仅in-flight | `STATE_TRANSITION_INVALID` |
| `company.create` | 写 | 30d | `PROFILE_VERSION_INVALID`、`NAME_EXISTS` |
| `company.get/list` | 读 | 无 | `COMPANY_SCOPE_VIOLATION` |
| `company.update` | 写 | 30d | `OPTIMISTIC_LOCK_CONFLICT` |
| `company.archive` | 写 | 30d | `STATE_TRANSITION_INVALID` |
| `department.create` | 写 | 30d | `LEADER_PROFILE_UNAVAILABLE` |
| `department.get/list` | 读 | 无 | `COMPANY_SCOPE_VIOLATION` |
| `department.update` | 写 | 30d | `RESPONSIBILITY_CYCLE` |
| `department.archive` | 写 | 30d | `STATE_TRANSITION_INVALID` |
| `department.setLeader` | 写 | 30d | `LEADER_PROFILE_UNAVAILABLE` |
| `department.responsibility.create/update/delete` | 写 | 30d | `RESPONSIBILITY_CYCLE` |
| `employee.create` | 写 | 30d | `PROFILE_VERSION_INVALID` |
| `employee.get/list` | 读 | 无 | `COMPANY_SCOPE_VIOLATION` |
| `employee.updateStatus` | 写 | 30d | `EMPLOYEE_HAS_ACTIVE_ASSIGNMENT` |
| `employee.updateDisplayName` | 写 | 30d | `NAME_EXISTS` |
| `employee.updateBaseProfile` | 写 | 30d | `PROFILE_VERSION_INVALID` |
| `employee.transfer` | 写 | 30d | `EMPLOYEE_HAS_ACTIVE_ASSIGNMENT` |
| `profile.createDraft/updateDraft` | 写 | 30d | `OPTIMISTIC_LOCK_CONFLICT` |
| `profile.get/list` | 读 | 无 | `PROFILE_VERSION_INVALID` |
| `profile.bindSkill/unbindSkill/validate` | 写 | 30d | `SKILL_INCOMPATIBLE` |
| `profile.publish` | 写 | 30d | `SKILL_INCOMPATIBLE` |
| `profile.retireVersion/retire` | 写 | 30d | `EMPLOYEE_HAS_ACTIVE_ASSIGNMENT` |
| `conversation.submitUserMessage` | 写 | 30d | `COMPANY_ARCHIVED` |
| `conversation.getCompany/getDepartment/listMessages` | 读 | 无 | `COMPANY_SCOPE_VIOLATION` |
| `task.confirmPlan` | 写 | 30d | `PLAN_VERSION_CONFLICT` |
| `task.requestPlanRevision/rejectPlan` | 写 | 30d | `STATE_TRANSITION_INVALID` |
| `task.pause/resume/cancel` | 写 | 24h | `STATE_TRANSITION_INVALID` |
| `task.get/list/getGraph/getEvidence` | 读 | 无 | `COMPANY_SCOPE_VIOLATION` |
| `departmentTask.checkResources` | 写 | 24h | `EMPLOYEE_UNAVAILABLE` |
| `departmentTask.replaceEmployee` | 写 | 30d | `EMPLOYEE_UNAVAILABLE` |
| `departmentTask.getReport` | 读 | 无 | `COMPANY_SCOPE_VIOLATION` |
| `runtime.probeAgent/probeProvider` | 写 | 24h | `AGENT_AUTH_UNAVAILABLE` |
| `runtime.listAvailableModels/getStatus` | 读 | 无 | `MODEL_UNAVAILABLE` |
| `run.cancel/resume` | 写 | 24h | `RUN_RECOVERY_UNCERTAIN` |
| `run.get/list/listEvents` | 读 | 无 | `COMPANY_SCOPE_VIOLATION` |
| `approval.listPending` | 读 | 无 | `COMPANY_SCOPE_VIOLATION` |
| `approval.resolve` | 写 | 30d | `APPROVAL_TARGET_CHANGED` |
| `artifact.list/getSnapshot` | 读 | 无 | `WORKSPACE_ACCESS_DENIED` |
| `workspace.get` | 读 | 无 | `RESOURCE_NOT_FOUND` |
| `workspace.apply/abandon/cleanupTask` | 写 | 30d | `WORKSPACE_ACCESS_DENIED` |
| `review.submit` | 写 | 30d | `REVIEW_SELF_ASSIGNMENT` |
| `review.listIssues` | 读 | 无 | `COMPANY_SCOPE_VIOLATION` |
| `review.rerun` | 写 | 30d | `STATE_TRANSITION_INVALID` |
| `review.resolveIssue` | 写 | 30d | `REVIEW_ISSUE_TRANSITION_INVALID` |
| `catalog.sync` | 写 | 24h | `CATALOG_SIGNATURE_INVALID` |
| `catalog.getActiveRelease/listAgents/listModels/listSkills` | 读 | 无 | `CATALOG_ITEM_DISABLED` |
| `catalog.installSkill/removeSkill/verifyCache` | 写 | 30d | `SKILL_INCOMPATIBLE` |
| `knowledge.import/remove` | 写 | 30d | `WORKSPACE_ACCESS_DENIED` |
| `knowledge.list/search` | 读 | 无 | `COMPANY_SCOPE_VIOLATION` |
| `backup.create/restore` | 写 | 30d | `STATE_TRANSITION_INVALID` |
| `backup.list` | 读 | 无 | `RESOURCE_NOT_FOUND` |
| `settings.get` | 读 | 无 | `RESOURCE_NOT_FOUND` |
| `settings.update` | 写 | 30d | `VALIDATION_FAILED` |
| `event.subscribe/replay` | 读 | 无 | `EVENT_SEQUENCE_INVALID` |

斜杠表示同一类型的多个独立方法，例如 `company.get/list` 展开为 `company.get` 和 `company.list`，不得把斜杠作为实际方法名。所有读取列表采用 cursor，cursor 是 base64url 编码的排序字段和 id，并用 Profile 内随机 HMAC key 签名，防止调用方篡改。

每个方法必须在 `packages/rpc-schema/methods/{namespace}.{action}.request.schema.json` 和 `.response.schema.json` 各有一个 JSON Schema；`packages/rpc-schema/ownership.v1.json` 固定记录 `rust_core/sidecar/supervisor_only` 三类所有权，生成器拒绝未分配或重复分配的方法。`get` 请求固定为 `{id, company_id}`；`list` 固定为 `{company_id, filter, cursor, limit}`，`limit` 默认 50、范围 1..200；`update/resolve` 必须含 `expected_version`。跨公司对象 id 即使真实存在也返回 `RESOURCE_NOT_FOUND`，不得泄露其他公司存在性。写请求的幂等键只放在 RPC `meta`，禁止在 params 重复定义。

JSON-RPC 协议错误使用标准码 `-32700/-32600/-32601/-32602/-32603`。所有领域错误固定使用 `-32000`，并返回：

```json
{
  "jsonrpc": "2.0",
  "id": "core:uuid",
  "error": {
    "code": -32000,
    "message": "Stable user-safe message",
    "data": {
      "code": "OPTIMISTIC_LOCK_CONFLICT",
      "trace_id": "uuid",
      "field_errors": []
    }
  }
}
```

`message` 不作为程序判断依据；前端只能依据 `error.data.code`。未知异常映射为 `INTERNAL_ERROR`，写完整堆栈到脱敏本地日志，RPC 不返回堆栈、SQL、绝对 Profile 路径或 Agent Prompt。

## 附录 K：页面、部署、观测与测试规范

### K.1 桌面路由

```text
/auth/server
/auth/login
/auth/register
/auth/change-password
/offline-unlock
/companies
/companies/:companyId/overview
/companies/:companyId/departments
/companies/:companyId/employees
/companies/:companyId/conversations/company
/companies/:companyId/conversations/departments/:departmentId
/companies/:companyId/tasks
/companies/:companyId/tasks/:taskId
/profiles
/runtime
/skills
/settings
/diagnostics
```

路由 loader 必须校验登录状态和 company scope。URL 中 company id 与当前 Query 数据不一致时拒绝加载，不自动切换公司。

### K.2 认证页面

正式构建只接受 HTTPS Backend Origin，唯一例外是 `http://127.0.0.1` 开发模式。保存前调用 `/health/ready`。

注册字段为 email/password/confirm password，成功后跳转登录并预填 email，不自动登录。登录响应为 `must_change_password=true` 时只能进入 `/auth/change-password`，页面固定提交当前临时密码、新密码和确认密码；修改成功并原子保存新 session bundle 后才进入首次向导或公司页。普通登录成功先同步目录；同步失败且有有效缓存时进入并显示缓存 release sequence。

后台可访问时必须在线认证；仅网络失败且 OfflineSessionTicket 有效时显示离线进入。

`/offline-unlock` 只列出本机已有且票据未过期的 Profile 脱敏邮箱，不接受账号密码，也不能创建新 Profile。用户选择后由 Rust 从 Keychain 读取 OfflineSessionTicket并验证 F.8 全部 claims 与本地 `auth_verification_keys`；成功才启动 Sidecar。Keychain 拒绝、票据过期、backend origin/device 不匹配或本地公钥缺失均停留登录页。离线状态在全局标题栏持续显示，网络恢复后立即尝试 Refresh；Refresh 失败则关闭在线态但不删除本地数据。

### K.3 首次向导

```text
Agent/Provider 检测
→ 创建总经理底座
→ 创建公司
→ 从模板创建部门或跳过
→ 公司级会话
```

没有 published 总经理底座时公司创建按钮禁用并跳到底座向导。每步独立提交，退出后从第一个未完成步骤恢复。

### K.4 公司和部门表单

公司：名称 1–100、介绍与业务流转 1–20000、创建时总经理名称和底座。编辑展示 Revision diff；保存只影响新任务。

部门：名称 1–100、职能 1–10000、负责人名称与底座、结构化职责、上下游。职责图有环时前端提示，Sidecar再次校验。参与职员同时承担 Review，不提供独立 Reviewer 配置。

归档普通部门前要求该部门无非终态 DepartmentTask/EmployeeTask、active Run 和待审批；同一事务把部门置 archived、部门会话置 archived、全部职员置 inactive 并写事件，不删除历史。总经理办公室禁止归档。

归档公司前要求全公司无非终态任务、active Run 和待审批。同一事务把公司、全部部门及会话置 archived、全部职员置 inactive并写事件；归档不删除，不提供恢复 RPC。已归档公司只允许读取、导出和备份，拒绝配置编辑、新会话消息和新任务。

### K.5 会话页面

公司级计划卡显示需求理解、部门分派、DAG、交付物、验收、外部写入和资源风险。按钮固定为确认、要求修改、拒绝。确认前重新查询 Plan version/hash；409 时刷新，不重试。

待确认时新用户消息作为修改意见生成新 Plan version，不新建并行 CompanyTask。

已 approved 的任务不显示“修改计划”，只显示“取消任务”；任务进入 cancelled/failed 后显示“基于此任务重新发起”，二次确认页列出将只读引用的需求和 Artifact，提交时使用 10.3 的 `supersedes_task_id`。

部门会话显示分析、可用性、分派、执行、Artifact、Review、修复、复测和报告。资源失败必须提供重新检测、替换职员和上报总经理。

### K.6 任务与 Runtime 页面

任务页固定包含状态、DAG、EmployeeTask、Artifact 版本链、Review 问题、Verification、AgentRun 时间线和证据。

软件任务完成后显示 integration commit、与 baseline 的 diff 摘要以及“应用到项目”“放弃应用”按钮；只有 workspace applied/abandoned 且无 active Run 时显示“清理受管 Worktree”。所有按钮先展示 J.3 的目标分支、HEAD 和影响，再发送对应幂等命令。

审批显示职员、任务、规范化路径、动作、旧哈希、新内容摘要和过期时间；只允许本次或拒绝。

Runtime 显示 queue、lease、PID、adapter、native session、checkpoint、最后 sequence、退出码和诊断引用。取消按钮要求原因并使用幂等命令。

设置页只提供两项 Profile 级可写配置：CLI 全局并发 `1..16`（默认 4）和日志保留天数 `1..365`（默认 30），通过 `settings.update(expected_version)` 保存；并发新值只影响尚未获取 Lease 的任务。Backend Origin 只能在 `/auth/server` 退出当前 Profile 后切换，不作为设置项。诊断导出和更新检查分别跳转 `/diagnostics` 与调用 `updater_check`，不混入设置保存。

### K.7 管理后台路由与行为

```text
/admin/login
/admin/change-initial-password
/admin/dashboard
/admin/users
/admin/agents
/admin/models
/admin/providers
/admin/skills
/admin/compatibility
/admin/releases
/admin/emergency-disables
/admin/audit
```

默认管理员首次登录只能进入改密和 logout。用户列表支持类型、状态、identifier筛选和 cursor 分页。保护管理员删除/禁用/改名/改类型按钮不渲染，后端仍校验。

目录对象状态 `draft → validated → published`。字段变化使 validated 退回 draft。published 不可修改；停用动作创建已签名紧急禁用发布。发布页二次确认 sequence、资源数量、最低客户端版本和 manifest SHA。

### K.8 前端错误策略

- 字段错误显示字段下。
- GET 网络错误最多重试 2 次，延迟 1/2 秒。
- 401 只刷新一次 Token；仍失败退出在线态。
- 409 不重试，刷新事实状态。
- 写请求不自动重试；用户显式重试复用 Idempotency-Key。
- 系统错误跳诊断页并显示 request/trace id，不显示堆栈和 SQL。

### K.9 桌面构建发布

`tauri.conf.json` 的生产 CSP 固定为：

```text
default-src 'self';
script-src 'self';
style-src 'self' 'unsafe-inline';
img-src 'self' asset: https://asset.localhost data:;
font-src 'self' data:;
connect-src 'self' ipc: http://ipc.localhost https://ipc.localhost;
object-src 'none';
base-uri 'none';
frame-ancestors 'none';
```

WebView 的 Tauri capability 只暴露 `rpc_request`、`workspace_select`、`readonly_file_select`、`external_write_resolve`、`external_open`、`diagnostics_export`、`updater_check` 和 `updater_install` 八个自定义 Command。禁止向 WebView 暴露 shell、filesystem、http、process、clipboard-write 或任意 updater 插件权限。Rust Command 必须校验 `window_session_id`，只允许主窗口调用；文件选择结果转换为 Rust 持有的 grant id，前端不得把任意路径直接作为授权依据。

```text
uv sync --frozen
→ pytest/coverage/ruff/mypy
→ PyInstaller arm64 Sidecar
→ cargo test/llvm-cov/clippy
→ npm ci/test/build
→ Tauri bundle external binary
→ codesign
→ Apple notarytool
→ stapler
→ 干净机器安装测试
```

Sidecar、Rust 和 RPC Schema 带同一 protocol version。版本不一致拒绝启动。发布包不得下载 Python 运行环境。

### K.10 后台容器

固定镜像：Admin Web、Backend API、PostgreSQL 16、MinIO、Nginx 1.27。生产顺序：PostgreSQL 备份、独立 Alembic Job、API 部署与 ready、Web 部署、Nginx切换、认证/目录/Skill 冒烟。API 启动不自动迁移。

v1 服务端固定使用 Docker Compose v2，交付 `deploy/compose.yml` 和 `deploy/.env.example`；不同时维护 Kubernetes 清单。所有基础镜像在 Compose 中按 immutable digest 锁定，禁止 `latest`。Backend 使用 Python 3.12 slim 多阶段镜像、非 root UID 10001、只读根文件系统和独立 `/tmp` tmpfs；Admin Web 静态文件由非 root Nginx 容器提供。PostgreSQL、MinIO 和备份目录使用独立持久卷，API/Web/Nginx 无持久业务卷。容器删除全部 Linux capabilities，Nginx 监听非特权 8080/8443，由宿主机映射 443。

Nginx 必须配置：

```nginx
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=10r/m;
client_max_body_size 52m;

add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "no-referrer" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;

location ~ ^/(api/v1|admin/api/v1)/auth/(login|register)$ {
    limit_req zone=auth_limit burst=5 nodelay;
    proxy_pass http://backend_api;
}

location /api/ {
    proxy_request_buffering on;
    proxy_read_timeout 600s;
    proxy_pass http://backend_api;
}
```

FastAPI CORS 只允许 `ADMIN_WEB_ORIGIN` 的精确 origin，允许方法 `GET/POST/PATCH/DELETE/OPTIONS`，允许请求头 `Authorization, Content-Type, Idempotency-Key, If-Match`，允许凭据，禁止 `*`。生产 Admin Web 与 API 必须经同一 HTTPS site 提供；Nginx 强制 TLS 1.2/1.3 和 HSTS `max-age=31536000; includeSubDomains`。

生产 PostgreSQL 每日执行 `pg_dump --format=custom`，保留 7 个日备份和 4 个周备份。MinIO bucket 必须开启 versioning；PostgreSQL、MinIO 数据卷和备份卷所在宿主文件系统必须使用平台全盘加密，Compose 启动检查由部署脚本读取运维显式确认文件 `deploy/state/storage-encryption-verified`，缺失时生产 profile 拒绝启动。每月自动执行一次在隔离环境恢复 PostgreSQL 与抽样校验 Skill 对象哈希的演练；失败阻止下一次目录发布。

### K.10.1 桌面自动更新

固定使用 Tauri Updater。Rust 内嵌更新公钥，每 24 小时和用户手动检查时请求 HTTPS 更新 manifest。只有无 active AgentRun、无待审批且最近一次本地备份成功后允许安装。下载包必须通过 Tauri 签名、Apple Code Signing 和 Notary 三重校验。

安装前缓存当前已签名安装包版本。更新后首次启动若 Sidecar 协议、迁移或 `system.health` 在 30 秒内失败，应用进入恢复界面，允许用户关闭新版本并使用缓存的上一版本安装包重新安装；数据库升级前备份用于数据恢复，应用不得自动执行破坏性数据库降级。

### K.11 后台配置

无生产默认值：

```text
DATABASE_URL
S3_ENDPOINT
S3_BUCKET
S3_ACCESS_KEY
S3_SECRET_KEY
AUTH_JWT_PRIVATE_KEY_FILE
AUTH_JWT_PUBLIC_KEYS_FILE
CATALOG_PRIVATE_KEY_FILE
CATALOG_PUBLIC_KEYS_FILE
PUBLIC_BASE_URL
ADMIN_WEB_ORIGIN
TLS_CERT_FILE
TLS_KEY_FILE
```

固定默认：Access 900 秒、Refresh/Offline 2592000 秒、Skill 52428800 bytes。秘密缺失直接退出，不生成临时密钥。

Backend 每个进程固定 SQLAlchemy `pool_size=20/max_overflow=20/pool_timeout=10s/pool_recycle=1800s`，连接设置 PostgreSQL `statement_timeout=30s`、`lock_timeout=5s`、`idle_in_transaction_session_timeout=60s`。Uvicorn 每容器 2 workers；扩容通过增加容器副本，目录发布仍由 PostgreSQL advisory lock 串行化。Auth、Catalog 和 TLS 密钥/证书必须由只读 Secret volume 挂载，私钥 mode `0400`、公钥/证书 mode `0444`，应用或 Nginx 验证权限过宽即拒绝启动。

### K.12 健康检查

- `/health/live` 只检查进程。
- `/health/ready` 依次检查 PostgreSQL `SELECT 1`、Alembic head、S3 bucket `HeadBucket`、Auth active private/public key 配对、Catalog active private/public key 配对和默认保护管理员存在；任一失败返回 503，正文只给稳定组件代码，不包含连接串、bucket key 或密钥路径。
- `/metrics` 只监听容器私网 `0.0.0.0:9090`，Compose 不发布宿主端口且 Nginx 不配置公网 location；只有加入独立 `monitoring` Docker network 的监控服务可以访问。
- `system.health` 检查本地 DB、迁移、event loop lag、write queue、runtime queue 和 ProcessPool；外部 Agent unavailable 不使 Sidecar unhealthy。

### K.13 日志

Python 用 structlog JSON。后台 stdout；桌面单文件 20 MiB、最多 10 个，保留天数使用 Profile 设置 `1..365`（默认 30），文件数量或保留天数任一达到上限即清理最旧文件。固定脱敏 password、authorization、cookie、token、api_key、credential、Prompt 和消息正文。

后台 Prometheus：HTTP、登录、锁定、目录发布、Skill、PostgreSQL/S3。桌面指标仅本地：Run、队列、重启、Checkpoint、恢复、Adapter 和检索，不上传遥测。

### K.14 测试与覆盖率

TypeScript 使用 Vitest/Testing Library，Python 使用 pytest/pytest-cov，Rust 使用 cargo test/cargo llvm-cov，API 使用 httpx/Schemathesis，E2E 使用 Playwright/Tauri WebDriver，后台集成使用 PostgreSQL 16 和 MinIO Testcontainer。

手写可执行源码 lines、branches、functions、statements 均为 100%。仅排除自动生成 DTO、纯 DDL、无逻辑启动入口和签名公证外部包装；排除写入 `coverage-exclusions.yml`。禁止以 pragma 排除普通业务分支。

### K.15 必测追踪矩阵

| 设计点 | 单元 | 契约 | 集成/E2E | 安全/恢复 |
|---|---|---|---|---|
| 公司/部门原子创建 | 回滚分支 100% | RPC Schema | 向导创建 | 崩溃注入 |
| Plan 确认 | 状态/Hash | RPC | 会话确认 | 并发 409 |
| 职责匹配 | 评分边界 | Plan Schema | 标准研发流程 | 候选越权 |
| Review | 分配/状态 | Report Schema | 修复复测 | 自审逃逸 |
| CLI Adapter | 事件解析 | 假 CLI | 真实 CLI | Seatbelt/Egress/取消/恢复 |
| API Model | Agent Loop | 三协议 | 工具任务 | Key/SSRF/断流 |
| Workspace | 路径/哈希 | Tool Schema | Git 合并 | Symlink/外部写 |
| Catalog | 兼容计算 | OpenAPI | 发布同步 | 签名/降级/禁用 |
| Auth | Token/锁定 | OpenAPI | 注册登录/Keychain bundle 轮换 | 重放/保护 admin |
| Backup | manifest | 格式 Schema | 恢复 | 损坏/中断 |

### K.16 性能门禁

桌面基线为 Apple M1、8 CPU Core、16GB、空闲系统且接交流电；后台基线为同一局域网内 4 vCPU/8GB API 主机、4 vCPU/8GB PostgreSQL 主机和 1Gbps MinIO。每项预热 5 次后执行 3 轮，每轮 30 样本，任一轮 p95 超限即发布失败。固定 fixture 与门禁如下：

| 指标 | 固定 fixture 与起止点 | 门禁 |
|---|---|---:|
| Sidecar 冷启动 | 1GB Profile DB、100 公司、1 万任务；Rust spawn 到 `system.health=healthy` | p95 < 3s |
| 本地事实列表 | 同 fixture；`task.list` 首屏 50 条，从 UDS 写请求到完整响应 | p95 < 50ms |
| 事件到 UI | 1000 条/s 合成 RunEvent；SQLite commit 到 React Query observer 收到目标 sequence | p95 < 100ms |
| 本地知识检索 | 1 万个 384 维条目；J.7 全流程到返回前 12 条 | p95 < 500ms |
| 任务恢复 | 10 个 queued/running Run 的本地 Checkpoint 对账，不包含外部模型响应时间 | p95 < 10s |
| Catalog manifest | 10 MiB 已发布 manifest；API 收到请求到 body 完成 | p95 < 200ms |
| 后台并发读取 | 100 个并发连接持续 60 秒读取 manifest 和四类目录列表，比例 1:1:1:1:1 | 错误率 0，p95 < 500ms |

CLI 启动、CLI 原生 session 恢复和 API Provider 模型响应只记录分位数，不作为上述发布阻断项，因为它们依赖本机安装、账号状态和外部网络；Adapter 自身的参数构造、事件解析、超时和恢复决策仍受单元与契约测试门禁约束。

### K.17 最终发布门禁

- 全量测试和 100% 覆盖率门禁通过。
- OpenAPI/JSON Schema/生成代码无差异。
- 三类真实 CLI 冒烟通过。
- macOS 签名、公证、干净机安装通过。
- 空库安装和上一正式版本迁移通过。
- 后台没有桌面业务表和公司/任务/会话/运行 API。
- blocker/high Review 问题为零。
- 设计文档、DDL、契约生成物和代码一致。
