# iBreeze 智能聚合路由设计方案

## 1. 文档定位

本文档定义 iBreeze “双层混合智能路由”目标架构，是《AI公司桌面应用设计方案》中 Agent Orchestration Platform、Agent Runtime Gateway、Execution Snapshot、Catalog 和 Review 数据闭环的专项细化规范。

本文档中的“必须”“禁止”“仅允许”均为强制实现要求。第三方实现不得用同义但语义不同的机制替代，也不得将未明确允许的行为解释为可扩展点。

对应实施计划：`docs/superpowers/plans/2026-08-13-ibreeze-hybrid-intelligent-routing.md`。

## 2. 设计目标

iBreeze 同时提供两个相互独立、上下衔接的路由层：

1. **业务编排路由**：总经理、部门负责人和职员根据公司流转说明、部门职责、职员能力和交付物要求，决定任务由哪个部门和哪些职员执行。
2. **模型调用路由**：仅在 API Model 职员的 Built-in Agent Runtime 内，对每一次模型 turn 选择单一模型或选择性多模型聚合。

目标能力如下：

- 保留现有公司、部门、职员、任务、会话、Artifact 和 Review 业务模型。
- 保留 Agent CLI/API Model 两类职员模型底座。
- API Model 职员支持 `fixed`、`smart_single`、`selective_ensemble` 三种路由模式。
- 每个 API Model turn 在不可变候选集合内完成能力过滤、难度分层、策略门控、模型选择、故障转移和审计。
- 低风险 turn 默认使用单模型；只有满足确定性触发条件时才使用多模型聚合。
- 多模型 proposer 只生成候选结果，只有 aggregator 能生成唯一最终响应或唯一工具调用。
- Provider 故障按结构化类型决定重试、冷却、故障转移或立即失败。
- 路由决策与实际调用、测试、Artifact、Review、修复轮次建立可审计关联。
- 第一阶段使用确定性规则；积累足够已验证结果后才允许启用本地学习型路由器。

## 3. 非目标与边界

以下内容不属于本方案：

- 不在中心后台保存公司、部门、职员实例、任务、会话、Prompt、Artifact 或 Review 数据。
- 不引入多租户组织模型。
- 不实现预算审批、费用配额或消费阻断。模型价格只作为路由评估和效果报告的元数据。
- 不把普通多模型聊天作为产品主流程。
- 不让中心后台参与本地任务调度、模型选择或 Provider 调用。
- 不尝试接管 Codex CLI、Claude Code、OpenCode 内部的每一次模型请求。
- 不允许在同一个 CLI 原生 session 中透明切换 Agent 类型或 Provider。
- 不允许 proposer 并发执行工具、写 Workspace 或产生外部副作用。
- 不允许 Sidecar 读取 API Key；Credential 仍只在 Rust 内展开。
- 不直接复制第三方路由模型权重或训练数据。引入任何第三方代码、模型资产或特征实现时必须完成许可证和 THIRD_PARTY_NOTICES 审核。

## 4. 术语

| 术语 | 定义 |
|---|---|
| Business Router | 公司到部门、部门到职员的任务级编排逻辑 |
| Turn Router | API Model Agent Loop 每次调用模型前执行的本地路由器 |
| Deployment | `(provider_release_id, model_binding_id, credential_ref)` 的可执行组合；`credential_ref` 是引用 Rust Keychain 条目的 UUID，不是 Key 名称或明文；同一 Model Binding 可配置不同 Credential |
| Anchor Deployment | 职员底座配置的固定安全回退 Deployment |
| Candidate Set | Execution Snapshot 固定的、当前 Run 唯一允许使用的 Deployment 集合 |
| Route Decision | 对一个 Agent Loop turn 产生的单模型或聚合选择结果 |
| Route Attempt | 一次真实 Provider HTTP 调用，包括 proposer、aggregator、single 和 fallback |
| Proposer | 聚合模式中生成不可执行候选结果的模型调用 |
| Aggregator | 聚合模式中读取候选并生成唯一可执行结果的模型调用 |
| Capability Gate | 根据 tools、vision、streaming、context、reasoning 等硬能力过滤 Deployment |
| Health Ledger | 按 Deployment 记录失败、冷却和恢复状态的本地账本 |
| Outcome | Route Decision 后续关联到的验证、Review、Artifact 和任务结果 |

## 5. 总体架构

```text
用户任务
  → 公司/部门/职员业务编排
  → 创建 AgentRun 与 Execution Snapshot
  → API Model Built-in Agent Runtime
      → RoutingContextBuilder
      → CandidateResolver
      → CapabilityGate
      → TierClassifier
      → RoutingPolicyEngine
      → single 或 ensemble
      → Rust Credential HTTP Broker
      → Provider
      → 唯一响应/工具调用
  → 工具结果、Artifact、验证和 Review
  → RouteOutcomeProjector
  → 本地路由评估与后续校准
```

职责边界：

| 组件 | 职责 | 禁止事项 |
|---|---|---|
| 管理后台 | 发布 Agent、Model、Provider、Skill 和路由元数据目录 | 不接收本地业务或路由结果 |
| Desktop React | 配置职员路由策略、展示决策和健康状态 | 不在前端计算路由 |
| Python Sidecar | 构建上下文、选择模型、执行聚合、持久化决策和结果 | 不读取凭据明文，不直连 Provider |
| Rust Desktop Core | 验证 Snapshot 授权、解析 Credential、执行 HTTP、归一化网络错误 | 不决定业务难度或聚合阵容 |
| Provider | 执行一个物理模型请求 | 不可信，不作为状态事实来源 |

## 6. 路由模式

### 6.1 `fixed`

- 每个 turn 只使用 Anchor Deployment。
- Anchor 不可用时仅按固定 fallback chain 故障转移。
- 不执行难度分层和 ensemble 选择，但仍执行能力校验、健康检查、Attempt 记录和 Outcome 关联。
- Router 不可用、配置损坏或模型元数据不完整时必须降级到此模式。

### 6.2 `smart_single`

- 每个 turn 从 Candidate Set 选择一个最合适的 Deployment。
- 选择结果必须先经过 Capability Gate 和 Health Ledger。
- 只允许在模型产生可见内容或工具调用之前透明故障转移。
- 路由器失败时使用 Anchor Deployment。

### 6.3 `selective_ensemble`

- 先执行与 `smart_single` 相同的单模型选择，结果作为 anchor proposer。
- Routing Policy 满足聚合触发条件时，构造 2–4 个 proposer 和 1 个 aggregator。
- 不满足触发条件时按 `smart_single` 执行。
- 聚合不可运行、未达到 quorum 或 aggregator 失败时回退到一个强单模型，不得直接输出未聚合候选。

新建 API Model 职员底座表单的默认模式为 `smart_single`，创建请求必须提交至少两个合法 Candidate 后才能保存。现有数据库行、旧 Snapshot 或导入的旧底座缺少 `routing_policy_json` 时按单候选 `fixed` 解释；兼容解释不得回写原记录，用户显式创建新 Draft 后才切换模式。

## 7. CLI Agent 边界

Codex CLI、Claude Code、OpenCode 只参与业务编排路由：

- 总经理和部门负责人可以把同一任务分配给多个基于不同 CLI 的职员。
- CLI 职员可使用现有 `independent_drafts`、`section_partition`、`primary_with_peer_review`、`sequential_refinement` 策略。
- CLI 的模型、原生 session、工具历史和 Provider 私有状态由 CLI Adapter 契约管理。
- iBreeze 不在 CLI 输出流中插入模型级 aggregator，也不根据 CLI 单个输出片段切换 Provider。
- CLI 失败时走职员任务重试、替换职员或重新规划，不走 API Model turn 级透明 fallback。

## 8. 中心 Catalog 扩展

中心后台仍只发布全局基础目录。`models` 增加以下字段：

| 字段 | 类型 | 约束 | 含义 |
|---|---|---|---|
| `routing_tier` | SMALLINT | `0..3` | 默认能力等级 C0–C3 |
| `quality_prior` | NUMERIC(5,4) | `0..1` | 冷启动质量先验 |
| `tool_reliability_prior` | NUMERIC(5,4) | `0..1` | Tool Call 可靠性先验 |
| `latency_prior_ms` | INTEGER | `>0` | 单次非流式首个完整结果的基线延迟 |
| `model_family` | VARCHAR(100) | 非空、规范化小写 | 模型家族 |
| `model_vendor` | VARCHAR(100) | 非空、规范化小写 | 供应商/研发方 |
| `architecture_class` | VARCHAR(64) | 非空 | `dense`、`moe`、`hybrid`、`unknown` |
| `supports_reasoning` | BOOLEAN | 非空 | 是否支持 reasoning 参数 |
| `reasoning_levels` | JSONB | 字符串数组 | `low`、`medium`、`high` 的子集 |
| `input_price_microusd_per_million` | BIGINT | `>=0` | 每百万输入 token 的微美元价格 |
| `output_price_microusd_per_million` | BIGINT | `>=0` | 每百万输出 token 的微美元价格 |
| `routing_enabled` | BOOLEAN | 非空 | 是否可进入智能路由候选 |

规则：

- 所有字段必须进入 Catalog Release manifest、签名内容和本地缓存。
- `routing_enabled=false` 的模型仍可作为旧固定底座的 Anchor，但不得进入智能候选集合。
- `quality_prior` 和 `tool_reliability_prior` 是目录发布先验，不允许桌面端覆盖原值；本地观测只能形成独立校准值。
- 价格为效果评估元数据，不触发预算阻断。
- `architecture_class=unknown` 可运行，但聚合选择时不获得架构多样性加分。

## 9. 职员底座路由配置

API Model Profile Version 新增不可变 `routing_policy_json`。其规范 Schema 为 `packages/contracts/routing/routing-policy.v1.schema.json`；RPC 请求只能通过 `$ref` 复用该 Schema，禁止复制并维护第二套定义。禁止继续把智能路由配置塞入旧 `runtime_binding_json`。

规范结构：

```json
{
  "schema_version": 1,
  "mode": "selective_ensemble",
  "anchor_candidate_id": "uuid",
  "candidates": [
    {
      "candidate_id": "uuid",
      "provider_release_id": "uuid",
      "model_binding_id": "uuid",
      "credential_ref": "uuid",
      "enabled": true,
      "eligible_roles": ["single", "proposer", "aggregator", "fallback"]
    }
  ],
  "fallback_order": ["candidate-uuid-1", "candidate-uuid-2"],
  "ensemble": {
    "max_proposers": 3,
    "min_successful_proposers": 2,
    "proposer_timeout_seconds": 120,
    "aggregator_timeout_seconds": 180,
    "proposer_max_retries": 1
  }
}
```

强制校验：

- `schema_version` 只能为 `1`。
- `mode` 只能为 `fixed`、`smart_single`、`selective_ensemble`。
- `anchor_candidate_id` 必须引用 candidates 中 `enabled=true` 的项。
- `candidate_id` 为 Profile Version 内生成的 UUID，按 `candidate_id` 唯一；Deployment 三元组也必须唯一，数量为 1–12。同一个 Model Binding 只有 Credential Ref 不同时才允许出现多次。
- 每个 candidate 的 Provider、Model Binding 必须属于 Profile 固定的 Catalog Release。
- Credential Ref 必须存在，但发布 Profile 时不得解析或保存凭据明文。
- 新建或更新的 Routing Policy 中所有 Candidate 都必须 `routing_enabled=true`。只有由旧数据库行/旧 Snapshot 生成的只读 `fixed` 兼容视图可以让 disabled 模型作为 Anchor，兼容视图不得重新发布为新 Version。
- `fixed` 至少 1 个 candidate；其他模式至少 2 个 candidate。
- `selective_ensemble` 至少有 2 个 proposer 角色和 1 个 aggregator 角色；同一 Deployment 可以同时具备 proposer 和 aggregator 角色。
- `eligible_roles` 只能包含 `single`、`proposer`、`aggregator`、`fallback` 且不得为空；Anchor 必须包含 `single` 和 `fallback`，fallback_order 引用的每项必须包含 `fallback`。
- `max_proposers` 为 2–4；`min_successful_proposers` 为 1–`max_proposers`。
- proposer timeout 为 10–300 秒；aggregator timeout 为 10–480 秒；proposer 重试为 0–2。
- fallback_order 只能引用 `candidate_id`，不能重复，Anchor Candidate 必须为最后安全回退项之一。

### 9.1 Credential Reference 管理

智能候选禁止手填未知 Credential UUID。Rust Core 必须提供 Profile-scoped 公共 RPC：

| 方法 | owner | 行为 |
|---|---|---|
| `credential.create` | Rust | 生成 UUID，把 Secret 写入 OS Keychain，把非敏感 metadata 写入本地索引 |
| `credential.list` | Rust | 返回 ref、label、Provider、auth type、状态和时间，不返回 Secret |
| `credential.updateSecret` | Rust | 原子替换同一 ref 的 Secret，不改变 Profile Policy |
| `credential.probe` | Rust | 使用固定 Provider Probe 验证 Secret，成功后把状态改为 ready |
| `credential.delete` | Rust | 通过删除屏障确认无引用、无活跃 Snapshot Lease 后删除 |

非敏感索引固定保存在 Profile 目录 `provider-credentials.v1.json`，文件权限 `0600`，规范 Schema 为 `packages/contracts/security/provider-credentials-index.v1.schema.json`。文件根字段为 `schema_version=1`、`revision`、`credentials[]`；每个 Credential 字段固定为 `credential_ref`、`label`、`normalized_label`、`provider_release_id`、`auth_type`、`state`（`creating|updating|unverified|ready|deleting`）、`resume_state`（仅过渡态保存 `unverified|ready`）、`metadata_version`、`active_secret_version`、`pending_secret_version`、`created_at`、`updated_at`。禁止保存 Secret、Secret hash、Header 或 Keychain account 完整名。Update/Probe/Delete 请求携带的是 `expected_metadata_version`，所有状态转换使用 CAS；文件级 `revision` 每次原子写递增，用于检测并发覆盖。

状态字段组合必须满足：`creating` 为 `active=null,pending=1,resume=null`；`updating` 为 `active>=1,pending=active+1,resume!=null`；`unverified|ready` 为 `active>=1,pending=null,resume=null`；`deleting` 为 `active>=1,pending=null,resume!=null`。任何其他组合在启动时视为 `CREDENTIAL_INDEX_CORRUPT`，不得尝试猜测恢复。

Keychain account 必须按 Secret Version 隔离，逻辑键为 `(profile_directory_id, credential_ref, secret_version)`。Create 原子序列固定为：持久化 `creating, metadata_version=1, active_secret_version=null, pending_secret_version=1` → 写 Keychain v1 → CAS 为 `unverified, metadata_version=2, active_secret_version=1, pending_secret_version=null`。Update 在确认无活跃 Lease 后固定执行：CAS 为 `updating`、保存 `resume_state`、设置 `pending_secret_version=active+1` 并递增 metadata version → 写新的版本化 Keychain entry → CAS 切换 active version、清空 pending、状态改为 `unverified` 并再次递增 metadata version → 删除旧 Secret Version。禁止覆盖当前 active Keychain entry。

同一 Provider 下 label 按 Unicode NFKC + casefold 后必须唯一，长度 1–100；Provider 的 `auth_scheme` 必须与提交的 `auth_type` 对应，禁止为 x-api-key Provider 保存 bearer Credential 或反向混用。

删除顺序必须为：Rust 将 metadata CAS 为 `deleting`、保存 `resume_state` 并持久化 → Rust 拒绝任何引用该 ref 的新 Snapshot 注册 → 通过当前认证 IPC Session 调用 Sidecar 内部方法 `credential.getReferences` 查询 active Profile Version、Draft 和非 terminal Run/Snapshot 引用 → 检查 Rust Snapshot Lease 引用 → 引用为零时删除 active/pending/孤儿 Keychain version，再删除 metadata；任一步失败恢复 `resume_state`。`credential.getReferences` 不是公共 RPC，不进入公共 Registry，也不允许 Desktop UI 直接调用。

启动恢复规则固定为：`creating` 的 pending entry 存在则完成切换到 `unverified`，不存在则删除 metadata；`updating` 的 pending entry 存在则完成 active 切换并删除旧 version，不存在则恢复 `resume_state` 并清空 pending；`deleting` 的任一 Keychain version 存在则恢复 `resume_state`，全部不存在则删除 metadata；最后清理不等于 active/pending 且不被 Snapshot Lease 引用的孤儿 Secret Version。不得留下 UI 已删除但 Keychain 仍存在，或新 metadata version 指向旧 Secret 的状态。

Execution Snapshot 必须固定 `credential_secret_version`。Rust 注册 Snapshot 和启动 Attempt 时都验证 metadata 的 `active_secret_version` 相同且 state=ready，并只加载该版本 Keychain entry。`credential.updateSecret` 在存在活跃 Snapshot Lease 时返回 `CREDENTIAL_IN_USE`；更新后所有尚未启动的旧 Snapshot 因 Secret Version 不匹配进入 `waiting_resource`，用户必须重新规划生成新 Snapshot，禁止用新 Secret 静默执行旧 Snapshot。

Sidecar 只允许通过 `credential.describe` reverse RPC 验证 ref、Provider 和状态；该响应不含 Secret。Profile 发布要求所有 Candidate Credential 为 `ready` 且 Provider 匹配。Create/更新 Secret 后必须显式 `credential.probe` 成功；网络 Probe 成功后 Rust 先等待 Sidecar 内部方法 `credential.probeSucceeded` 通过 WriteQueue 清除当前 Profile 内该 Credential Hash 的全部 `credential_invalid`，再把 metadata CAS 为 `ready`。Sidecar 确认失败时 Probe RPC 失败且 metadata 保持 `unverified`；若最终 metadata CAS 失败，Sidecar 已清除 health 但 Rust 仍会因 `unverified` 拒绝使用，属于安全失败，重试 Probe 可收敛。两个内部方法只接受当前认证 Rust IPC Session，不进入公共 Registry。

Credential metadata 和 Keychain Secret 均不进入可移植业务备份。恢复到没有对应 Credential 的设备后，旧 Policy/Snapshot 保持历史引用但 Run 进入 `waiting_resource`；用户必须在新 Draft 中选择新建且 Probe 成功的 Credential，禁止按 label 自动重绑。

## 10. Execution Snapshot v2

Execution Snapshot 仍然不可变，但从“固定一个模型绑定”升级为“固定候选集合和固定路由策略”。

`execution_snapshots` 增加：

| 字段 | 类型 | 说明 |
|---|---|---|
| `routing_policy_json` | TEXT JSON | Profile Version 路由策略的规范化副本 |
| `routing_policy_sha256` | TEXT(64) | RFC 8785 JSON 的 SHA-256 |
| `routing_classifier_version` | TEXT | `rules-v1` 或已发布本地模型版本 |
| `candidate_bindings_json` | TEXT JSON | 展开的不可变候选 Deployment 元数据 |
| `candidate_bindings_sha256` | TEXT(64) | 候选集合哈希 |

`candidate_bindings_json` 的规范 Schema 为 `packages/contracts/routing/candidate-bindings.v2.schema.json`，其中每项固定：

- `candidate_id`
- `provider_release_id`
- `provider_key`
- `provider_protocol`
- `model_binding_id`
- `model_id`
- `provider_model_name`
- `credential_ref`
- `credential_secret_version`
- Model capability 和路由元数据
- `eligible_roles`
- `request_defaults_sha256`

为避免跨语言浮点差异，`quality_prior` 和 `tool_reliability_prior` 在 `candidate_bindings_json` 中使用四位小数字符串（如 `"0.8500"`），价格和 token/latency 字段使用 JSON integer，其余字段禁止浮点数。规范化使用 RFC 8785；Sidecar 和 Rust 必须通过同一组跨语言 canonicalization fixture 后才能发布。

禁止事项：

- Run 启动后不得从当前 Catalog、Profile 或 UI 重新读取候选。
- Route Decision 不得引用 Snapshot 之外的 Model Binding。
- Catalog 更新不得改变已创建 Run 的候选集合。
- Candidate 不可用时只能跳过或触发 waiting/failed，不能临时从全局目录补一个模型。

对于 `sequential_refinement` 的延迟 EmployeeTask，确认事务写入的 dispatch spec 是唯一运行输入。依赖满足后，派发器必须先严格解析冻结的 `required_capability_tags` 数组，再校验 spec 冻结的员工部门归属、Profile Version、Catalog Release、能力标签与 Workspace Grant；任一引用不再有效或 spec 结构损坏时只能进入可见的 `failed`/资源等待状态，不得读取当前 Profile 替换绑定，也不得从全局 Catalog 补候选。

旧 Snapshot 没有 v2 字段时按单候选 `fixed` 执行，不做数据库原地补写。

## 11. Routing Context

`RoutingContextBuilder` 每个 turn 生成以下不可变输入：

| 字段 | 类型 | 来源 |
|---|---|---|
| `route_decision_id` | UUID | 本地生成 |
| `run_id` | UUID | AgentRun |
| `turn_index` | INTEGER | Agent Loop，从 1 开始 |
| `run_purpose` | ENUM | Execution Snapshot |
| `artifact_type` | STRING/NULL | 当前任务交付物 |
| `required_capability_tags` | STRING[] | Plan/Department Task |
| `message_char_count` | INTEGER | 当前规范化消息 |
| `estimated_input_tokens` | INTEGER | 当前消息和保留上下文 |
| `context_window_tokens` | INTEGER | Anchor Candidate Model 元数据 |
| `context_pressure` | DECIMAL | `estimated/anchor context_window`，截断至 `0..1` |
| `contains_code` | BOOLEAN | 确定性文本检测 |
| `contains_structured_schema` | BOOLEAN | JSON Schema/严格格式检测 |
| `attachment_types` | STRING[] | 当前 turn 附件 |
| `tool_count` | INTEGER | 当前允许工具数 |
| `prior_tool_failures` | INTEGER | 当前 Run |
| `provider_failures` | INTEGER | 当前 Run |
| `verification_failures` | INTEGER | 当前 Work Item |
| `open_blocker_high_count` | INTEGER | 当前 Artifact Review |
| `previous_tier` | `C0..C3`/NULL | 当前 Run 上一决策 |
| `previous_confidence` | DECIMAL/NULL | 当前 Run 上一决策 |
| `operator_forced_mode` | ENUM/NULL | 仅当前 Run 的显式控制 |
| `input_origin` | ENUM | `production` 或 `evaluation`；公共用户请求固定为 `production` |

Routing Context 不保存原始 Prompt。用于诊断的输入指纹为 `SHA-256(run_id + turn_index + canonical feature json)`。

派生规则固定如下：消息先做 Unicode NFKC 规范化；`message_char_count` 使用规范化后的 Unicode code point 数；优先使用 Catalog `tokenizer_key` 对 system、保留上下文和当前消息共同计数，tokenizer 不可用时按 `ceil(UTF-8 byte length / 4)` 估算并在 policy trail 写入 `token_estimator=fallback_bytes_v1`；`contains_code` 在存在 Markdown fenced code block，或至少两行匹配 `^\s*(def|class|fn|function|import|from|const|let|var|SELECT|INSERT|UPDATE|CREATE)\b` 时为 true；“要求分析、Review 或验证”按规范化文本命中 `分析|review|审查|检查|验证|verify|test`；`contains_structured_schema` 在文本包含 JSON Schema `$schema`/`properties` 组合、OpenAPI `openapi`/`paths` 组合，或明确出现“严格 JSON/固定字段/不得增加字段”时为 true。规则版本随 `routing_classifier_version` 发布，禁止运行时远程更新关键词。

## 12. 难度分层与策略门控

### 12.1 Rules v1 分层

初始 tier 为 C0，每条规则只允许提高 tier：

| 条件 | 最低 tier |
|---|---|
| `message_char_count >= 4000` 或 `estimated_input_tokens >= 8000` | C1 |
| 包含代码且要求分析、Review 或验证 | C2 |
| `contains_structured_schema=true` | C2 |
| `run_purpose` 为 `company_plan`、`review`、`verification`、`summary` | C2 |
| `run_purpose` 为 `repair` 或 `merge` | C3 |
| `context_pressure >= 0.75` | C2 |
| `context_pressure >= 0.90` | C3 |
| `prior_tool_failures >= 1` 或 `provider_failures >= 2` | 比当前结果提高一级 |
| `verification_failures >= 1` | C3 |
| `open_blocker_high_count >= 1` | C3 |

置信度规则：

- 只有一条明确规则命中：`0.70`。
- 两条及以上同向规则命中：`0.85`。
- 没有规则命中：`0.60`。
- 出现相互冲突的 operator 控制或缺失必要元数据：`0.40`，并使用 Anchor。

### 12.2 Capability Gate

`required_capability_tags` 属于 Plan/Department Task 的职员与部门能力约束：在公司级编排、部门匹配和确认计划的资源预检阶段使用，并在确认时冻结到 Run spec，供每个 turn 的 Context 指纹和审计追踪使用。它不是 API Model Catalog 的 Deployment 元数据，不能拿任务标签去过滤模型候选；模型候选只按本节列出的 Provider、工具、视觉、流式、上下文、tier、reasoning、role 和 Health 硬约束过滤。这样可以避免把“职员能完成的工作”误判成“某个模型声明了同名标签”。

Candidate 必须全部满足：

- `routing_enabled=true`，Anchor 在 `fixed` 降级时除外。
- 当前 Provider、Model Binding 和 Credential Probe 可用。
- 当前请求有工具时 `supports_tools=true`。
- 当前请求有图像时 `supports_vision=true`。
- API Model 调用必须 `supports_streaming=true`。
- `estimated_input_tokens + max_output_tokens <= context_window`。
- `routing_tier >= required_tier`；不得仅通过评分惩罚让低等级模型参与高等级 turn。
- 当前需要 reasoning level 时模型支持该 level；不支持时可降为该模型支持的最高 level，但不得低于策略要求的最低 level。
- 当前 role 在 candidate `eligible_roles` 内。

Capability Gate 没有候选时：

- Anchor 满足硬能力时使用 Anchor 并记录 `ROUTER_NO_ELIGIBLE_CANDIDATE`。
- Anchor 也不满足时 Run 进入 `waiting_resource`，failure code 为 `MODEL_CAPABILITY_UNAVAILABLE`。

Reasoning 参数由 required tier 唯一映射：C0 不发送 reasoning 参数，C1 请求 `low`，C2 请求 `medium`，C3 请求 `high`。模型不支持目标 level 时，只能选择同一模型声明支持且不低于目标 level 的最小 level；不存在这样的 level 时过滤该模型。Router 不改写 system prompt，也不对用户 Prompt 做压缩、摘要或语义重写。

### 12.3 单模型评分

对通过 Capability Gate 的候选计算：

```text
score = 0.40 * effective_quality
      + 0.20 * effective_tool_reliability
      + 0.15 * tier_affinity
      + 0.15 * health_score
      + 0.10 * latency_score
```

- `effective_quality = clamp(catalog quality prior + local calibration, 0, 1)`。
- `effective_tool_reliability` 无工具时按 `1.0` 处理。
- `tier_affinity = max(0, 1 - abs(candidate tier - required tier) / 3)`；低于 required tier 的候选已被 Capability/Policy Gate 排除。
- 健康正常为 `1.0`，有未达到冷却阈值的 strike 时为 `0.5`，benched 为不可选。
- `latency_score = 1 / (1 + latency_prior_ms / 1000)`。
- 同分依次按更高 effective quality、更低 latency、`model_binding_id`、`candidate_id` 字典序选择，保证同一 Binding 使用不同 Credential 时仍可确定性重放。

## 13. 选择性聚合触发

`selective_ensemble` 仅在以下任一条件成立时启用：

1. `verification_failures >= 1`。
2. `open_blocker_high_count >= 1`。
3. required tier 为 C3 且 confidence `< 0.70`。
4. required tier 为 C2 且 confidence `< 0.55`。
5. `provider_failures >= 2` 且至少存在两个健康、不同 Provider 的 proposer。
6. operator 对当前 Run 显式设置 `force_ensemble`。

以下情况禁止聚合：

- 当前 turn 含图像且少于两个 vision proposer 或 aggregator 不支持 vision。
- 通过 Capability Gate 的 proposer 少于 2。
- 没有健康 aggregator。
- 候选上下文无法容纳聚合候选包。预检 token 上界固定为 `estimated_input_tokens + 2000 + max_proposers * ceil(24000 * 4 / 4)`；其中 2000 是聚合指令/JSON envelope 保留量，`24000 * 4 / 4` 按最坏四字节 UTF-8 字符和 fallback tokenizer 估算。Aggregator 的 `context_window - max_output_tokens` 小于该值时不得选择该阵容。
- Run 已取消、超时或进入 terminal 状态。
- 当前 turn 是故障转移后的重放且上一次调用已产生工具调用或可见内容。

Operator Override 不能越过安全或灰度门禁：`force_fixed` 固定 Anchor；`force_single` 只禁止 ensemble，不跳过 Capability Gate；`force_ensemble` 仍必须满足本节全部禁止条件，且全局 rollout stage 必须为 `selective_ensemble` 或 `learning_candidate`。否则 `routing.setRunOverride` 返回 `ROUTING_OVERRIDE_NOT_AVAILABLE`，不得静默保存一个不会生效的值。

## 14. Ensemble 阵容和执行契约

### 14.1 角色

默认阵容按以下顺序选择：

1. `anchor`：单模型评分最高者。
2. `orthogonal_reviewer`：与 anchor 的 vendor、family、architecture、provider 差异得分最高者。
3. `strong_critic`：剩余候选中 effective quality 最高者。
4. `fast_sanity`：只有 C3 且 `max_proposers=4` 时使用，选择 latency score 最高者。

`orthogonal_reviewer` 相对 anchor 的差异分固定为：Provider 不同加 `0.30`、Model Vendor 不同加 `0.25`、Model Family 不同加 `0.25`、Architecture Class 不同且双方均非 `unknown` 加 `0.20`。同分依次按 effective quality 降序、latency 升序、`model_binding_id`、`candidate_id` 字典序选择。其余角色也使用同一稳定排序规则，禁止随机抽样。

Aggregator 从具备 `aggregator` role 的候选中选择，评分为：

```text
aggregator_score = 0.55 * effective_quality
                 + 0.20 * effective_tool_reliability
                 + 0.15 * health_score
                 + 0.10 * latency_score
```

允许 aggregator 与 proposer 使用同一 Deployment，但当另一个 aggregator 的分数差小于 `0.05` 时优先选择未参与 proposer 的 Deployment。

### 14.2 Proposer 请求

- proposer 并发执行。
- proposer 收到当前完整消息和工具名称/JSON Schema，但工具说明必须标记为不可执行建议。
- Provider 请求不得设置强制 tool choice。
- proposer 返回的 tool calls 必须转换为普通候选 JSON，不得进入 ModelRuntime 工具执行分支。
- Attempt 的创建、accepted/streaming/terminal CAS、Decision/Health 写入或 Rust 授权失败均属于路由安全错误：必须取消仍在运行的 Broker 请求并停止 retry/fallback，不得把审计写失败伪装成 Provider 错误。
- 每个候选最多 24,000 字符；超出时按 UTF-8 字符边界截断并记录 `candidate_truncated=true`。
- 每个 proposer 最多执行 `1 + proposer_max_retries` 次物理调用。

### 14.3 Quorum

- proposer 数为 2 时默认 quorum=2。
- proposer 数为 3 时默认 quorum=2。
- proposer 数为 4 时默认 quorum=3。
- 配置值不得低于上述默认值；较高配置值可保留。
- 达到 quorum 后等待 5 秒 grace；grace 后取消仍未完成的 proposer。
- 未达到 quorum 时不得调用 aggregator。

### 14.4 Aggregator 请求

Aggregator 输入包含：

- 原始 system prompt。
- 当前用户消息和保留上下文。
- 候选数组，每项只有 `candidate_id`、`role`、`content`、`suggested_tool_calls`。
- 明确指令：验证冲突、优先满足 acceptance criteria、只输出一个最终响应或一组合法工具调用、不得提及模型和聚合过程。

Aggregator 输出进入现有 `ModelTurn` 规范化和工具权限流程。只有该输出可以执行工具。

### 14.5 聚合降级

- 静态预检不足：直接执行 single anchor。
- proposer 未达 quorum：执行一次强 single fallback。
- aggregator 可重试错误：同一 aggregator 重试 1 次。
- aggregator 仍失败：执行一次强 single fallback。
- strong fallback 失败：按 Deployment fallback chain 执行；耗尽后 Run 失败。
- 所有降级必须复用原始 turn 上下文，禁止把失败响应或未验证候选伪装成用户输入。

## 15. Provider 错误与健康账本

Rust 必须把 Provider/网络错误归一化为：

| 错误 | 同 Deployment 重试 | 换 Deployment | Health strike |
|---|---:|---:|---:|
| `RATE_LIMITED` | 按 Retry-After 最多 1 次 | 是 | 立即 bench |
| `PROVIDER_OVERLOADED` | 最多 1 次 | 是 | 是 |
| `TRANSPORT_TRANSIENT` | 最多 2 次 | 是 | 是 |
| `TIMEOUT` | 最多 1 次 | 是 | 是 |
| `CONTEXT_OVERFLOW` | 否 | 仅换更大上下文模型 | 否 |
| `AUTH_INVALID` | 否 | 仅换不同 credential/provider | 否 |
| `MODEL_NOT_FOUND` | 否 | 是 | 立即 bench |
| `UNSUPPORTED_CAPABILITY` | 否 | 是 | 立即 bench |
| `INSUFFICIENT_CREDITS` | 否 | 仅换不同 credential/provider | 立即 bench |
| `BAD_REQUEST` | 否 | 否 | 否 |
| `POLICY_REFUSAL` | 否 | 否 | 否 |
| `INVALID_RESPONSE` | 最多 1 次 | 是 | 是 |

Health Ledger 以 `(company_id, provider_release_id, model_binding_id, credential_ref hash)` 为键；一个模拟公司的 Provider 故障不得自动 bench 另一个公司的 Deployment：

- 普通可计数错误连续 3 次 bench。
- `RATE_LIMITED` 使用 Retry-After；无 Retry-After 时 30 秒。
- `RATE_LIMITED` 的唯一一次同 Deployment 重试是当前 Decision 的保留例外：先写入 bench，再等待 Retry-After；等待时间超过 Run 剩余 deadline 时跳过该重试并直接 fallback。其他并发或后续 Decision 必须立即跳过该 benched Deployment。
- 其他 bench 默认 30 秒，最大 900 秒。
- 成功调用清除 strike 和 bench。
- `AUTH_INVALID` 不累计 strike，但把该 company/credential 的 `availability_state` 标记为 `credential_invalid`；Capability Gate 必须排除它，直到显式 `runtime.probeProvider` 成功或 Profile 使用新的 Credential Ref。
- Desktop 重启时保留未过期 bench，过期记录在启动清理。
- 对有副作用的工具调用，只有在 Provider 未产生可见内容且没有执行工具时才允许自动 fallback。
- ModelTurn 的 Rust Credential HTTP Broker 只执行一次物理 Provider 请求，不在 Broker 内部隐式重试；同一 Deployment 的重试次数、Retry-After 等待、Run deadline 判断和 fallback 全部由 Sidecar 按本节表格决定，并为每次重试创建新的 `RouteAttempt`。Credential Probe 不属于 RouteAttempt，可使用独立的 Broker 探测重试上限。

## 16. Rust Broker 授权契约

Run 启动时 Sidecar 必须先调用 `routing.snapshot.register`，传入 `run_id`、`execution_snapshot_id`、规范化 `candidate_bindings_json`、`candidate_bindings_sha256` 和 `run_deadline_at`。Deadline 固定为 AgentRun 首次进入 running 的时间加 Profile Version `timeout_seconds`，不得续租；单个 Provider 请求的 `deadline_at` 不得晚于该值。Rust 对规范化 JSON 原始 UTF-8 字节计算 SHA-256，哈希不一致时拒绝注册，并从该 JSON 解析 Candidate 授权项。

每个 Route Decision 持久化为 `planned` 后、创建首个 Attempt 前，Sidecar 必须调用 `routing.decision.register`：

```json
{
  "run_id": "uuid",
  "execution_snapshot_id": "uuid",
  "route_decision_id": "uuid",
  "turn_index": 1,
  "selections": [
    {"candidate_id": "uuid", "role": "single|proposer|aggregator|fallback"}
  ]
}
```

Rust 验证所有 selection 均属于 Snapshot 且 role 合法，并建立不可变 Decision Lease。`selections` 必须同时列出主选择和该 Decision 允许使用的完整 fallback chain；未列出的 Candidate 后续不得临时调用。相同 Decision ID、相同规范化内容重复注册返回原结果；内容不同返回 `ROUTE_DECISION_CONFLICT`。

`credential.http.start` 增加以下必填参数：

```json
{
  "execution_snapshot_id": "uuid",
  "route_decision_id": "uuid",
  "route_attempt_id": "uuid",
  "route_role": "single|proposer|aggregator|fallback",
  "candidate_id": "uuid",
  "provider_release_id": "uuid",
  "model_binding_id": "uuid",
  "credential_ref": "uuid"
}
```

五个路由授权字段必须整体出现或整体缺省：带有任一字段却缺少其他字段时，Rust 以 `ROUTING_SNAPSHOT_NOT_AUTHORIZED` fail-closed；只有不带任何路由字段的旧 fixed 直连兼容调用才允许走无 Snapshot 的历史路径。

Rust 处理顺序：

1. 校验认证 IPC Session。
2. 通过 Sidecar 在 Run 启动时注册的 Snapshot Authorization Lease 查找 `execution_snapshot_id`。
3. 验证 `route_decision_id` 已注册到该 Run/Snapshot，Candidate/Role 在不可变 Decision Lease 中，Attempt 尚未注册。
4. 验证 Candidate ID 存在，且 Provider、Model Binding、Credential Ref 三元组与该 Candidate 完全相同。
5. 验证 role 在 Candidate `eligible_roles` 中。
6. 验证 Provider endpoint、协议、request defaults 和域名策略来自相同 Catalog Release。
7. 创建 Attempt 并发送 HTTP。
8. 在完成、失败、取消和超时事件中返回归一化错误、usage 和 timing。

Rust 不接收 Sidecar 传来的 base URL、Authorization header、任意请求路径或任意 model 名。实际值必须从已验签 Catalog 和 Snapshot authorization lease 解析。
v2 Candidate 的 `request_defaults_sha256` 必须与 Rust 当前已验签 Catalog Binding 的规范化 `request_defaults` 字节哈希相等；不相等时在创建 Provider 请求前拒绝。旧 fixed 兼容 Snapshot 没有 v2 授权字段时不执行该比较，但仍使用 Catalog defaults。

## 17. 本地持久化

### 17.1 `route_decisions`

关键字段：

- `id`、`company_id`、`run_id`、`turn_index`
- `execution_snapshot_id`
- `routing_mode`
- `classifier_version`
- `input_fingerprint`
- `required_tier`、`confidence`
- `selected_kind`：`single` 或 `ensemble`
- `selected_bindings_json`：Candidate ID、role 和完整 fallback chain 的规范化数组
- `aggregator_candidate_id`
- `policy_trail_json`
- `status`：`planned`、`executing`、`succeeded`、`failed`、`cancelled`
- `created_at`、`completed_at`

唯一键为 `(run_id, turn_index)`。记录创建后，输入和选择字段不可修改；只允许状态和实际执行摘要按状态机更新。

### 17.2 `route_attempts`

关键字段：

- `id`、`route_decision_id`、`attempt_sequence`
- `role`、`candidate_id`、`provider_release_id`、`model_binding_id`
- `credential_ref_sha256`
- `request_id`
- `status`：`created`、`accepted`、`streaming`、`succeeded`、`failed`、`cancelled`、`timed_out`
- `failure_kind`、`http_status`
- `started_at`、`first_event_at`、`completed_at`、`latency_ms`
- `prompt_tokens`、`completion_tokens`、`total_tokens`
- `candidate_truncated`

唯一键为 `(route_decision_id, attempt_sequence)` 和非空 `request_id`。

### 17.3 `deployment_health`

保存 `company_id`、Deployment 三元组（Credential 只存 SHA-256）、`availability_state`（`ready` 或 `credential_invalid`）、strike、benched_until、last failure、last success 和版本。所有更新经 WriteQueue。`runtime.probeProvider` 成功必须以 CAS 清除相同 company/credential 的 `credential_invalid`。

### 17.4 `route_outcomes`

Outcome 是追加式关联记录：

- `route_decision_id`
- `outcome_type`：`tool_result`、`verification`、`artifact`、`review`、`task_terminal`
- `source_id`
- `score`：`0..1`
- `label`：稳定枚举
- `occurred_at`

同一 `(route_decision_id, outcome_type, source_id)` 只能写一次。Outcome 不反向修改历史 Route Decision。

### 17.5 `routing_run_controls`

保存 `company_id`、`run_id`、`override_mode`、`version`、`updated_at`，其中 override 只能为 `force_fixed`、`force_single`、`force_ensemble` 或 `NULL`。唯一键为 `(company_id, run_id)`。不存在控制行时对外返回 `version=0, override_mode=null`；以 `expected_version=0` 首次设置时插入 version 1，后续更新使用 CAS 并递增 version。Override 持续作用于设置后创建的所有 Decision，直到用户调用 `clear` 或 Run 进入 terminal；不得修改已存在的 Decision。

## 18. 状态机与幂等

Route Decision：

```text
planned → executing → succeeded
                    → failed
                    → cancelled
```

Route Attempt：

```text
created → accepted → streaming → succeeded
                              → failed
                              → cancelled
                              → timed_out
```

规则：

- 一个 `(run_id, turn_index)` 只能有一个 Route Decision。
- IPC 重放相同 `route_attempt_id` 必须返回原 Attempt 状态，不创建第二次 Provider 调用。
- 不同 Attempt 不得复用 Provider request id。
- Run 取消时先撤销所有活跃 Attempt，再把 Decision 标记为 cancelled。
- Sidecar 崩溃恢复时，`planned/executing` Decision 先与 Rust 活跃请求核对；无法证明请求仍活跃时标记 failed，禁止自动重放可能已产生内容的 Attempt。

## 19. Outcome 和本地校准

### 19.1 Outcome 映射

| 事件 | score | label |
|---|---:|---|
| 工具调用成功并通过 verifier | 1.0 | `tool_verified` |
| 工具拒绝或 schema 非法 | 0.0 | `tool_rejected` |
| verification 通过 | 1.0 | `verification_passed` |
| verification 失败 | 0.0 | `verification_failed` |
| Artifact Review pass | 1.0 | `review_passed` |
| Review needs_changes | 0.4 | `review_needs_changes` |
| Review failed 或存在 blocker | 0.0 | `review_failed` |
| Task succeeded | 1.0 | `task_succeeded` |
| Task failed/timed_out | 0.0 | `task_failed` |

### 19.2 本地校准

Rules v1 上线时不改变 Catalog prior。每个 Deployment 至少积累 30 个可验证 Outcome 后，才计算本地校准：

```text
local_quality = (sum(score) + 5 * catalog_quality_prior) / (sample_count + 5)
calibration = clamp(local_quality - catalog_quality_prior, -0.20, 0.20)
```

校准按 `run_purpose` 分桶；样本不足时使用全局桶。校准只影响桌面本地，不上传中心后台。

## 20. 学习型路由器发布边界

学习型路由器不是首期交付项。只有满足以下条件才允许替换 `rules-v1`：

- 至少 1,000 个具有 terminal Outcome 的 Route Decision。
- 每个 C0–C3 至少 100 个样本。
- 有独立 golden task 集，且训练数据与 golden 数据无任务重复。
- 候选模型在 shadow 模式运行至少 7 天。
- 相对当前规则，验证通过率不得下降超过 1 个百分点。
- blocker/high Review 问题率不得上升。
- P95 路由决策时间不得超过 50ms。
- 候选晋级、回滚和版本哈希有本地审计记录。

## 21. RPC 与 UI

新增公共 RPC：

| 方法 | 用途 |
|---|---|
| `routing.validatePolicy` | 校验 Profile 路由策略和候选绑定 |
| `routing.getRunSummary` | 查询 Run 的路由摘要 |
| `routing.listDecisions` | 分页查询 Route Decision |
| `routing.getDecision` | 查询 Decision、Attempts、policy trail 和 outcomes |
| `routing.listDeploymentHealth` | 查询候选健康状态 |
| `routing.setRunOverride` | 设置当前 Run 的 `force_fixed/force_single/force_ensemble/clear` |
| `routing.clearExpiredHealth` | 删除当前公司 `availability_state=ready` 且 bench 已过期的 Health 记录；active bench 和 `credential_invalid` 不允许删除 |

`routing.validatePolicy` 请求必须包含 `company_id`、`profile_type`、`policy`，并且 `profile_version_id` 与 `catalog_release_id` 恰好提供一个：编辑已有 Draft 时用前者解析固定 Release，新建 Profile 尚无 Version 时用后者。两者同时提供或同时缺失均返回 `VALIDATION_FAILED`。

稳定错误码至少包括：`ROUTING_POLICY_REQUIRED`、`ROUTING_POLICY_INVALID`、`ROUTING_ANCHOR_MISSING`、`ROUTING_CANDIDATE_OUTSIDE_RELEASE`、`ROUTING_CANDIDATE_DUPLICATE`、`ROUTING_ROLE_INSUFFICIENT`、`ROUTING_FALLBACK_INVALID`、`ROUTER_NO_ELIGIBLE_CANDIDATE`、`MODEL_CAPABILITY_UNAVAILABLE`、`ROUTING_SNAPSHOT_HASH_MISMATCH`、`ROUTING_SNAPSHOT_NOT_AUTHORIZED`、`ROUTE_DECISION_CONFLICT`、`ROUTE_ATTEMPT_CONFLICT`、`ROUTING_OVERRIDE_NOT_AVAILABLE`、`CREDENTIAL_MISSING`、`CREDENTIAL_NOT_READY`、`CREDENTIAL_IN_USE`、`CREDENTIAL_VERSION_MISMATCH`、`CREDENTIAL_LABEL_DUPLICATE`、`CREDENTIAL_PROVIDER_MISMATCH`、`CREDENTIAL_INDEX_CORRUPT`。这些值进入 RPC Error Registry 和安全日志，不得用自由文本替代程序分支。

UI 变更：

- 职员底座表单在 API Model 类型下显示路由模式、Anchor、Candidate、eligible roles、fallback 和 ensemble 参数。
- 设置页提供 Provider Credential 创建、列表、更新 Secret、Probe 和安全删除；Secret 输入提交后立即清空，列表只显示 label、Provider、状态和 Credential UUID 后 8 位。Candidate 只能下拉选择同 Provider 且 `state=ready` 的 Credential，禁止自由输入 UUID。
- Agent CLI 类型隐藏上述字段，并明确提示“CLI 使用任务级多职员协作，不支持内部 turn 路由”。
- Run 详情增加路由摘要、每 turn 模式、请求模型、实际模型、fallback hops、usage、latency 和错误类型。
- 设置页增加 Deployment Health，只提供查看和“清除已过期记录”；不得提供绕过 active bench 的按钮。Run Override 持续影响后续 turn，直到用户清除或 Run 结束，UI 必须明确显示该持续范围。
- 所有时间按 `Asia/Shanghai` 展示，数值默认最多两位小数且不补零。

## 22. 可观测性和隐私

日志和审计允许记录：

- route decision id、run id、turn index
- Provider/Model Binding id
- tier、confidence、policy stage
- usage、latency、failure kind、fallback hop
- Outcome 枚举和 score

禁止记录：

- Prompt、候选正文、aggregator 输入正文
- API Key、Authorization header
- Credential Ref 原文进入 route_attempts；只保存 SHA-256
- Workspace 文件内容和 Tool Result 正文

指标至少包括：

- `routing_decisions_total{mode,tier,kind,status}`
- `routing_attempts_total{role,provider,model,status,failure_kind}`
- `routing_decision_latency_ms`
- `routing_provider_latency_ms`
- `routing_fallback_hops_total`
- `routing_ensemble_quorum_failures_total`
- `routing_outcome_score{purpose,model}`

## 23. 灰度发布

全局阶段在 Sidecar 启动时只读取一次环境变量 `IBREEZE_ROUTING_STAGE`，合法值为 `observe`、`shadow`、`smart_single`、`selective_ensemble`、`learning_candidate`，默认 `observe`；非法值记录安全错误并按 `observe` 运行。该值不是用户业务数据，不写 SQLite，不允许通过公共 RPC 在进程内修改，变更后必须重启 Sidecar。

发布阶段固定为：

1. `observe`：执行当前 Anchor，只计算并记录建议选择。
2. `shadow`：仅当内部评测入口显式构造 `input_origin=evaluation` 时可对脱敏固定评测输入执行候选调用；所有公共用户请求强制为 `production`，禁止产生额外 Provider 调用。
3. `smart_single`：允许单模型动态选择和 fallback，不启用 ensemble。
4. `selective_ensemble`：只对满足第 13 节触发条件的 turn 启用。
5. `learning_candidate`：实际选择仍由已验收的 `rules-v1` 执行，学习型 Router 只记录建议，不改变选择；未安装已发布本地 Router 模型时等同 `selective_ensemble`，不得下载或临时训练模型。

任一阶段出现以下条件立即退回 `fixed`：

- 路由器错误率连续 5 分钟超过 1%。
- Snapshot authorization 拒绝出现非测试请求。
- 工具副作用重复执行。
- Review blocker/high 比基线增加超过 5 个百分点。
- Provider 请求无法关联到唯一 Attempt。

## 24. 测试和验收

### 24.1 必测矩阵

- 三种路由模式。
- C0–C3 规则和所有 purpose floor。
- tools、vision、context、reasoning 能力过滤。
- 同分稳定排序和重复执行确定性。
- 12 个候选边界、无候选、仅 Anchor、候选退役。
- 全部 ProviderFailureKind 的 retry/fallback/bench 行为。
- 2/3/4 proposer quorum、grace、timeout、cancel、aggregator retry。
- proposer tool call 不执行；aggregator tool call 只执行一次。
- Snapshot 外 binding、错误 credential、错误 role 和错误 Catalog Release 全部被 Rust 拒绝。
- Crash recovery 不重复 Provider 调用。
- Route Outcome 幂等和 Review/verification 关联。
- 旧 Snapshot 自动按 `fixed` 兼容。
- UI 时间和数值格式。

### 24.2 发布门禁

- Sidecar 路由模块 statement/branch coverage 均为 100%。
- Rust Broker 新增授权和错误分类模块 line/function/region coverage 均为 100%（以 `cargo llvm-cov` 为准）。
- 新增 RPC Schema contract drift 为零。
- Backend Catalog migration、manifest、签名和降级测试通过。
- Fake TLS Provider E2E 覆盖 single、ensemble、fallback、cancel 和 usage。
- 真实 staging Provider 至少覆盖两个不同 Provider 的 ensemble 和故障转移。
- 全量 `scripts/verify-all.sh` 通过，无新增 skip、xfail 或 coverage exclusion。

### 24.3 效果验收

Golden Task Set 固定为 200 个不重复任务，C0–C3 各 50 个；每个 tier 内代码实现、代码 Review、文档/方案、结构化 Schema、工具/故障恢复五类各 10 个。每项必须包含稳定 `task_id`、`tier`、`category`、`run_purpose`、脱敏输入 fixture 路径、所需工具、验收命令/断言、期望 Artifact 类型和最大运行时。四个实验组必须读取同一份带 SHA-256 的集合，失败重跑仍保留原结果且不得替换样本。Golden 输入不得来自本地校准训练样本。

同一任务集、同一模型池、同一 Provider 版本比较：

- 固定 Anchor。
- `smart_single`。
- 固定多模型阵容。
- `selective_ensemble`。

正式启用必须满足：

- `smart_single` 的验证通过率相对 Anchor 下降不超过 1 个百分点。
- `selective_ensemble` 在 C3/失败恢复样本中的验证通过率提升至少 5 个百分点，或平均修复轮次下降至少 20%。
- blocker/high Review 问题率不得上升。
- 路由错误不得导致工具重复执行。
- single 模式路由计算 P95 小于 20ms；后续本地学习模型小于 50ms。

## 25. 最终完成定义

只有以下条件全部满足，才能宣称完成智能聚合路由：

1. API Model 每个 turn 都产生唯一 Route Decision。
2. Execution Snapshot 固定候选集合，Rust 对每个物理请求重新授权。
3. `fixed`、`smart_single`、`selective_ensemble` 均可配置并通过测试。
4. proposer 永不执行工具，aggregator 只产生唯一可执行结果。
5. retry、fallback、health bench 和 crash recovery 不产生重复副作用。
6. Route Decision、Attempt、usage、latency、failure 和 Outcome 可完整关联。
7. CLI Agent 仍按任务级编排运行，没有伪造 turn 级路由能力。
8. 中心后台仍只保存全局 Catalog，所有业务和路由执行数据保存在桌面本地。
9. README、部署文档、总体设计、实施计划、RPC Schema 和实际代码一致。
10. 全量验证门禁和效果验收通过。
