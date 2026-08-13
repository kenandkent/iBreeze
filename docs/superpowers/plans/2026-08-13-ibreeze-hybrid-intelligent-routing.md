# iBreeze 双层混合智能路由 Implementation Plan

> 本计划按任务、数据契约、验证命令和发布门禁组织；复选框表示交付核验项，不能替代真实 Provider、跨进程和发布环境证据。

**Goal:** 在保留公司/部门/职员任务级编排的前提下，为 API Model Built-in Agent Runtime 增加 turn 级 `fixed`、`smart_single`、`selective_ensemble` 路由，形成可授权、可恢复、可观测、可验证的智能聚合路由闭环。

**Architecture:** Profile Version 固化路由策略，Execution Snapshot v2 固化候选 Deployment；Python Sidecar 负责上下文、规则分类、选路、聚合、健康和 Outcome，Rust Broker 对每个物理 Provider 请求按 Snapshot Lease 重新授权并归一化错误，React 只负责配置和展示。CLI Agent 继续使用任务级多职员协作，禁止伪装成 turn 级动态路由。

**Tech Stack:** FastAPI + SQLAlchemy + PostgreSQL/Alembic、Python 3.12 + Pydantic + aiosqlite、Rust 2021 + Tokio + reqwest、React 19 + TypeScript + Ant Design、JSON Schema + 现有代码生成器、pytest/Vitest/cargo-nextest/cargo-llvm-cov。

**规范依据：**

- `docs/设计方案/iBreeze智能聚合路由设计方案.md`
- `docs/设计方案/AI公司桌面应用设计方案.md`
- `docs/设计方案/AI公司桌面应用-实施计划.md`

## Global Constraints

1. 所有新增实现先写失败测试，再写最少实现使测试通过；禁止先提交无测试的生产代码。
2. Sidecar 不得直连 Provider、读取 API Key 或绕过 `credential.http.start`。
3. 所有 SQLite 写入必须经过 `WriteQueue` 和 `UnitOfWork`；不得向 worker 暴露 writer connection。
4. 每个物理 Provider 调用必须先持久化 `route_attempts.created`，再取得 Rust 授权；失败也必须形成终态。
5. Snapshot 创建后不得读取当前 Profile/Catalog 替换候选；旧 Snapshot 只允许按单候选 `fixed` 兼容。
6. proposer 永远不执行工具；只有 single/aggregator/fallback 返回的 `ModelTurn` 可进入工具执行。
7. 新增或变更 RPC 必须先修改 `packages/rpc-schema`，再生成 Python/TypeScript/Rust 产物；禁止手改 generated 文件。
8. 新增数据库表、状态、错误码、事件和用户可见行为必须同步更新 README、部署文档、总体设计和总体实施计划。
9. 前端时间统一按 `Asia/Shanghai` 展示；数值最多两位小数且不补零。
10. 首期路由器只允许 `rules-v1`。学习型 Router 只实现接口和 shadow 发布边界，不实现训练或自动上线。
11. 不实现预算、配额、消费审批；价格只进入观测与对比报告。
12. 每个 Task 完成后运行该 Task 指定的精确测试；全部 Task 完成后运行第 17 章全量门禁。

---

## Task 1: 扩展中心 Catalog 的模型路由元数据

**Files:**

- Create: `apps/backend-api/alembic/versions/005_model_routing_metadata.py`
- Modify: `apps/backend-api/src/ibreeze_backend/catalog/models.py`
- Modify: `apps/backend-api/src/ibreeze_backend/catalog/schemas.py`
- Modify: `apps/backend-api/src/ibreeze_backend/catalog/service.py`
- Modify: `apps/backend-api/src/ibreeze_backend/releases/manifest.py`
- Modify: `apps/backend-api/src/ibreeze_backend/releases/bundle.py`
- Modify: `apps/backend-api/tests/test_catalog.py`
- Modify: `apps/backend-api/tests/test_releases.py`
- Modify: `apps/backend-api/tests/test_release_immutability.py`
- Modify: `apps/backend-api/tests/test_migrations.py`
- Modify: `apps/admin-web/src/types/index.ts`
- Modify: `apps/admin-web/src/pages/ModelCatalogPage.tsx`
- Modify: `apps/admin-web/src/pages/ModelCatalogPage.test.tsx`

**Data contract:**

`ModelCreate`、`ModelUpdate`、`ModelResponse` 和 release model resource 必须包含：

```text
routing_tier: 0..3
quality_prior: decimal 0..1, four decimal places
tool_reliability_prior: decimal 0..1, four decimal places
latency_prior_ms: positive integer
model_family: normalized lowercase string, 1..100
model_vendor: normalized lowercase string, 1..100
architecture_class: dense|moe|hybrid|unknown
supports_reasoning: boolean
reasoning_levels: unique subset of low|medium|high
input_price_microusd_per_million: non-negative integer
output_price_microusd_per_million: non-negative integer
routing_enabled: boolean
```

`ModelCreate` 对上述全部字段均为 required。管理后台新建表单的初始值固定为 `routing_tier=1`、两个 prior 均为 `0.5`、`latency_prior_ms=3000`、`architecture_class=unknown`、`supports_reasoning=false`、`reasoning_levels=[]`、两项价格为 `0`、`routing_enabled=false`；`model_family` 和 `model_vendor` 不预填，必须由管理员输入。Migration 的 database server default 只为历史行和旧数据库工具提供防御性兼容：回填 family/vendor 为字符串 `unknown` 并保持 `routing_enabled=false`；管理员必须 clone 为新 draft、补齐真实值后才能启用路由。

- [ ] 在 `test_catalog.py` 写 create/update/response、边界值、未知枚举、重复 reasoning level、`supports_reasoning=false` 但 levels 非空的失败测试。
- [ ] 在 `test_releases.py` 写 manifest、签名输入和 release bundle 完整保留字段的测试。
- [ ] 在 `test_release_immutability.py` 写已发布 model 不可修改路由元数据的测试。
- [ ] 在 `test_migrations.py` 写升级/降级测试，验证 PostgreSQL CHECK 和 server default。
- [ ] 运行 `uv run --directory apps/backend-api pytest tests/test_catalog.py tests/test_releases.py tests/test_release_immutability.py tests/test_migrations.py -q`，确认 Catalog 字段、签名 Release 和迁移测试通过。
- [ ] 实现 Alembic `005`：增加列和 CHECK；使用 server default 回填旧数据，回填后保留 defaults 以保证旧客户端创建 draft 时安全禁用智能路由。
- [ ] 更新 SQLAlchemy/Pydantic/service/manifest/bundle；发布校验必须拒绝 `routing_enabled=true` 且 `model_family` 或 `model_vendor` 为空的模型。
- [ ] 运行 `bash scripts/generate-contracts.sh`，同步 Backend OpenAPI 和 `apps/admin-web/src/generated/openapi/api.ts`；禁止手改生成文件。
- [ ] 更新管理后台表单、列表和详情；prior 输入精度固定 4 位，价格使用整数输入，reasoning levels 使用去重多选。
- [ ] 运行 Backend 精确测试和 `npm --prefix apps/admin-web run test -- ModelCatalogPage.test.tsx`，预期全部通过。

## Task 2: 将路由元数据纳入 Catalog 契约、生成物和 Desktop 缓存

**Files:**

- Modify: `packages/contracts/artifacts/catalog-manifest.v1.schema.json`
- Create: `packages/contracts/fixtures/routing-canonical-json.v1.json`
- Modify: `scripts/schema-gen-rust/src/main.rs`（仅当现有递归生成无法表达新字段时）
- Modify: `apps/desktop-core/src/rpc/reverse.rs`
- Create: `sidecar/ibreeze/catalog/__init__.py`
- Create: `sidecar/ibreeze/catalog/sync.py`
- Create: `sidecar/ibreeze/catalog/service.py`
- Modify: `sidecar/ibreeze/application/public_rpc.py`
- Modify: `sidecar/tests/test_runtime_gateway_contract.py`
- Modify: `sidecar/tests/test_agent_runtime_gateway.py`
- Modify: `tests/integration/test_rust_sidecar_contract.py`

**Canonical cache shape:**

Desktop Catalog 中的 model resource 必须保持 Task 1 全部字段。`reasoning_levels` 必须按 `low, medium, high` 的固定顺序规范化；用于哈希前禁止沿用用户提交顺序。

- [ ] 先写 JSON Schema 正反例测试：完整 model 通过，缺任一强制字段、额外字段、非法枚举或小数越界均失败。
- [ ] 写 Rust `CatalogSnapshot` 反序列化测试和 Sidecar 缓存读取测试，确保字段类型与 Backend 一致。
- [ ] 运行 `bash scripts/check-contract-drift.sh`，确认生成物与 Schema 无漂移。
- [ ] 修改 canonical schema 和 Rust Catalog structs；Sidecar 对新 Release 缺字段必须返回 `CATALOG_ROUTING_METADATA_MISSING`。预升级缓存 Release 只允许供旧 Snapshot/旧 Profile 的单候选 `fixed` 兼容路径使用，禁止进入 smart/ensemble，且不得把合成默认值写回缓存。
- [ ] 运行 `bash scripts/generate-contracts.sh`，只保留生成器产生的变更。
- [ ] 运行 `bash scripts/check-contract-drift.sh && uv run --project sidecar pytest tests/integration/test_rust_sidecar_contract.py sidecar/tests/test_runtime_gateway_contract.py sidecar/tests/test_agent_runtime_gateway.py -q`。

## Task 3: 建立 SQLite 路由持久化内核

**Files:**

- Create: `sidecar/ibreeze/persistence/migrations/006_intelligent_routing.sql`
- Create: `sidecar/ibreeze/persistence/migrations/007_routing_capability_tags.sql`
- Modify: `sidecar/ibreeze/persistence/migrations.py`
- Create: `sidecar/ibreeze/routing/__init__.py`
- Create: `sidecar/ibreeze/routing/types.py`
- Create: `sidecar/ibreeze/routing/repository.py`
- Create: `sidecar/tests/test_routing_migration.py`
- Create: `sidecar/tests/test_routing_repository.py`
- Modify: `sidecar/tests/test_migrations.py`
- Modify: `scripts/check_single_writer.py`

**Migration 006 exact changes:**

1. `employee_base_profile_versions` 增加 `routing_policy_json TEXT NOT NULL DEFAULT '{}'`。
2. `execution_snapshots` 增加 `routing_policy_json`、`routing_policy_sha256`、`routing_classifier_version`、`candidate_bindings_json`、`candidate_bindings_sha256`，均允许旧行为空。
3. 创建 `route_decisions`、`route_attempts`、`deployment_health`、`route_outcomes`、`routing_run_controls`，字段、枚举和唯一键严格按设计方案第 17 节。
4. `route_attempts` 额外保存 `run_id`、`execution_snapshot_id`、`candidate_id` 和 `route_role` 的冗余只读索引字段，插入时必须与所属 Decision 一致，以便 Crash Recovery 和 Rust 回调定位。
5. 创建索引：

```sql
CREATE UNIQUE INDEX uq_route_decision_turn ON route_decisions(run_id, turn_index);
CREATE UNIQUE INDEX uq_route_attempt_sequence ON route_attempts(route_decision_id, attempt_sequence);
CREATE UNIQUE INDEX uq_route_attempt_request ON route_attempts(request_id) WHERE request_id IS NOT NULL;
CREATE UNIQUE INDEX uq_route_outcome_source ON route_outcomes(route_decision_id, outcome_type, source_id);
CREATE INDEX ix_route_attempt_active ON route_attempts(run_id, status);
CREATE INDEX ix_deployment_health_bench ON deployment_health(benched_until);
```

6. 为 profile immutable trigger 增加 `routing_policy_json` 同值检查；published/retired version 修改该字段必须中止。

Migration 007 只增加 `employee_task_dispatch_specs.required_capability_tags_json TEXT NOT NULL DEFAULT '[]'` 并校验 JSON 语法。确认事务把 Plan/Department Task 的标签冻结到 eager Run spec 和 deferred dispatch spec；延迟派发运行前必须在应用层严格解析为非空字符串数组或空数组，结构损坏直接使 EmployeeTask 进入 `failed`，不得按对象键或字符串字符迭代放行。

**Exact table columns and checks:**

| 表 | 列定义 |
|---|---|
| `route_decisions` | `id TEXT PK`; `company_id TEXT NOT NULL`; `run_id TEXT NOT NULL`; `turn_index INTEGER >0`; `execution_snapshot_id TEXT NOT NULL`; `routing_mode TEXT CHECK fixed/smart_single/selective_ensemble`; `classifier_version TEXT NOT NULL`; `input_fingerprint TEXT length=64`; `required_tier TEXT CHECK C0..C3`; `confidence REAL 0..1`; `selected_kind TEXT CHECK single/ensemble`; `selected_bindings_json TEXT json_valid`; `aggregator_candidate_id TEXT NULL`; `policy_trail_json TEXT json_valid`; `status TEXT CHECK planned/executing/succeeded/failed/cancelled`; `created_at TEXT NOT NULL`; `completed_at TEXT NULL`; FK `(run_id,company_id)`、`(execution_snapshot_id,company_id)` |
| `route_attempts` | `id TEXT PK`; `route_decision_id TEXT FK`; `run_id TEXT NOT NULL`; `execution_snapshot_id TEXT NOT NULL`; `attempt_sequence INTEGER >0`; `role TEXT CHECK single/proposer/aggregator/fallback`; `candidate_id TEXT NOT NULL`; `provider_release_id TEXT NOT NULL`; `model_binding_id TEXT NOT NULL`; `credential_ref_sha256 TEXT length=64`; `request_id TEXT NULL`; `status TEXT CHECK created/accepted/streaming/succeeded/failed/cancelled/timed_out`; `failure_kind TEXT NULL CHECK` 为 12 个稳定错误之一; `http_status INTEGER NULL 100..599`; 四个时间字段; `latency_ms INTEGER NULL >=0`; 三个 token 字段 `>=0`; `candidate_truncated INTEGER CHECK 0/1` |
| `deployment_health` | `company_id`; `provider_release_id`; `model_binding_id`; `credential_ref_sha256`; `availability_state TEXT CHECK ready/credential_invalid`; `consecutive_strikes INTEGER >=0`; `benched_until TEXT NULL`; `last_failure_kind TEXT NULL`; `last_failure_at TEXT NULL`; `last_success_at TEXT NULL`; `version INTEGER >0`; `updated_at TEXT`; 四元组复合主键 |
| `route_outcomes` | `id TEXT PK`; `route_decision_id TEXT FK`; `outcome_type TEXT CHECK tool_result/verification/artifact/review/task_terminal`; `source_id TEXT NOT NULL`; `score REAL 0..1`; `label TEXT NOT NULL`; `occurred_at TEXT NOT NULL` |
| `routing_run_controls` | `company_id`; `run_id`; `override_mode TEXT NULL CHECK force_fixed/force_single/force_ensemble`; `version INTEGER >0`; `updated_at TEXT`; 复合主键 `(company_id,run_id)` 和复合 FK 到 AgentRun |

Migration 还必须创建 `route_decision_immutable_selection`、`route_attempt_identity_immutable`、`route_attempt_parent_guard` 三个 trigger：Decision 创建后禁止修改分类、输入指纹和选择字段；Attempt 创建后禁止修改 parent/sequence/role/Candidate/Deployment/Credential；Attempt 插入时 parent 的 run/snapshot 必须完全一致，且 Candidate/Role 必须存在于 `selected_bindings_json`。合法状态变化只由 Repository 的带旧状态条件 CAS 执行。

**Required Python types:**

```python
class RoutingMode(StrEnum): FIXED = "fixed"; SMART_SINGLE = "smart_single"; SELECTIVE_ENSEMBLE = "selective_ensemble"
class RouteRole(StrEnum): SINGLE = "single"; PROPOSER = "proposer"; AGGREGATOR = "aggregator"; FALLBACK = "fallback"
class ProviderFailureKind(StrEnum):
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_OVERLOADED = "PROVIDER_OVERLOADED"
    TRANSPORT_TRANSIENT = "TRANSPORT_TRANSIENT"
    TIMEOUT = "TIMEOUT"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    AUTH_INVALID = "AUTH_INVALID"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    INSUFFICIENT_CREDITS = "INSUFFICIENT_CREDITS"
    BAD_REQUEST = "BAD_REQUEST"
    POLICY_REFUSAL = "POLICY_REFUSAL"
    INVALID_RESPONSE = "INVALID_RESPONSE"
@dataclass(frozen=True, slots=True)
class DeploymentKey:
    company_id: str
    provider_release_id: str
    model_binding_id: str
    credential_ref: str
```

- [ ] 写 migration 从 v5 升 v6、重复执行、checksum 篡改、trigger 和 foreign key 测试。
- [ ] 写 Repository 创建 Decision、CAS 状态迁移、Attempt 序号、request id 幂等、Outcome 幂等、health upsert 测试。
- [ ] 写顺序延迟派发冻结 spec 的标签、员工部门/Profile/Catalog/Workspace 失效以及非法标签结构 fail-closed 回归测试。
- [ ] 运行 `uv run --directory sidecar pytest tests/test_routing_migration.py tests/test_routing_repository.py tests/test_migrations.py -q`，确认迁移、Repository 和约束测试通过。
- [ ] 实现 SQL、更新 `MIGRATIONS` 的真实 SHA-256；不得修改历史 migration checksum。
- [ ] Repository 的每个写方法只接收 transaction connection，Service 层通过 WriteQueue 调用。
- [ ] 更新 single-writer 静态检查并运行 `python3 scripts/check_single_writer.py`。
- [ ] 运行本 Task 三个测试文件，要求 statement/branch 均为 100%。

## Task 4: 定义并校验 Profile Routing Policy

**Files:**

- Create: `sidecar/ibreeze/routing/policy.py`
- Create: `sidecar/ibreeze/routing/canonical_json.py`
- Create: `packages/contracts/routing/routing-policy.v1.schema.json`
- Create: `apps/desktop-core/src/broker/credential_index.rs`
- Create: `packages/contracts/security/provider-credentials-index.v1.schema.json`
- Modify: `apps/desktop-core/src/broker/credential.rs`
- Modify: `apps/desktop-core/src/broker/mod.rs`
- Modify: `apps/desktop-core/src/commands.rs`
- Create: `apps/desktop-core/tests/credential_management.rs`
- Create: `packages/rpc-schema/methods/credential.create.request.schema.json`
- Create: `packages/rpc-schema/methods/credential.create.response.schema.json`
- Create: `packages/rpc-schema/methods/credential.list.request.schema.json`
- Create: `packages/rpc-schema/methods/credential.list.response.schema.json`
- Create: `packages/rpc-schema/methods/credential.updateSecret.request.schema.json`
- Create: `packages/rpc-schema/methods/credential.updateSecret.response.schema.json`
- Create: `packages/rpc-schema/methods/credential.probe.request.schema.json`
- Create: `packages/rpc-schema/methods/credential.probe.response.schema.json`
- Create: `packages/rpc-schema/methods/credential.delete.request.schema.json`
- Create: `packages/rpc-schema/methods/credential.delete.response.schema.json`
- Modify: `packages/rpc-schema/reverse-methods.v1.json`
- Modify: `sidecar/ibreeze/profile/service.py`
- Modify: `packages/rpc-schema/methods/profile.createDraft.request.schema.json`
- Modify: `packages/rpc-schema/methods/profile.updateDraft.request.schema.json`
- Modify: `packages/rpc-schema/methods/profile.get.response.schema.json`
- Modify: `packages/rpc-schema/methods/profile.list.response.schema.json`
- Modify: `packages/rpc-schema/methods/profile.validate.response.schema.json`
- Create: `packages/rpc-schema/methods/routing.validatePolicy.request.schema.json`
- Create: `packages/rpc-schema/methods/routing.validatePolicy.response.schema.json`
- Modify: `packages/rpc-schema/registry.v1.json`
- Modify: `packages/rpc-schema/error-codes.v1.json`
- Modify: `sidecar/ibreeze/application/public_rpc.py`
- Modify: `sidecar/ibreeze/rpc/production_server.py`
- Modify: `sidecar/tests/test_profile_service.py`
- Create: `sidecar/tests/test_routing_policy.py`
- Modify: `sidecar/tests/test_public_rpc.py`
- Create: `sidecar/ibreeze/routing/credential_references.py`
- Create: `sidecar/tests/test_credential_references.py`
- Modify: `sidecar/ibreeze/backup/service.py`
- Modify: `sidecar/tests/test_backup_consistency.py`

**Service interface:**

```python
@dataclass(frozen=True, slots=True)
class ValidatedRoutingPolicy:
    canonical_json: str
    sha256: str
    mode: RoutingMode
    anchor_candidate_id: str
    candidates: tuple[CandidatePolicy, ...]
    fallback_order: tuple[str, ...]
    ensemble: EnsemblePolicy

def validate_routing_policy(
    raw: Mapping[str, object],
    *,
    profile_type: str,
    catalog_release: CatalogReleaseView,
) -> ValidatedRoutingPolicy: ...
```

校验错误使用稳定 code：`ROUTING_POLICY_REQUIRED`、`ROUTING_POLICY_INVALID`、`ROUTING_ANCHOR_MISSING`、`ROUTING_CANDIDATE_OUTSIDE_RELEASE`、`ROUTING_CANDIDATE_DUPLICATE`、`ROUTING_ROLE_INSUFFICIENT`、`ROUTING_FALLBACK_INVALID`。响应的 `issues[]` 每项固定为 `{code, json_pointer, message}`。Task 6、8、13 同时把设计方案第 21 节其余路由错误码加入 Registry，禁止延后使用自由文本异常。

**Credential contract:**

公共 Registry 元数据固定为：`credential.create`、`credential.updateSecret`、`credential.probe`、`credential.delete` 均为 `owner=rust_core, kind=write, scope=profile, idempotency_ttl_seconds=86400`；`credential.list` 为 `owner=rust_core, kind=read, scope=profile, ttl=0`。四个 write 必须从 RPC meta 取得 idempotency key，Secret 禁止进入幂等响应缓存键、日志或错误文本；请求规范哈希使用“移除 `secret` 后的规范字段 + `HMAC-SHA256(profile_idempotency_key, secret)`”。32-byte `profile_idempotency_key` 由 Rust 首次创建并只保存在 OS Keychain，不进入 Profile 文件或备份；相同 key/不同 HMAC 返回 `IDEMPOTENCY_CONFLICT`，从而兼顾 24 小时跨重启幂等与 Secret 保密。

- `credential.create` request：`label(1..100),provider_release_id(uuid),auth_type(bearer|x_api_key),secret(1..16384)`；内部经过 `creating`，response 只返回 metadata、`state=unverified,metadata_version=2,active_secret_version=1`。
- `credential.list` request：可选 `provider_release_id`；response `items[]` 不含 Secret，按 `label,credential_ref` 排序。
- `credential.updateSecret` request：`credential_ref,expected_metadata_version,secret`；内部保存 `resume_state` 并经过版本化 `updating`，成功后 metadata 再递增并变为 `unverified`，active secret version +1。Version/state Gate 优先于旧 health，Probe 成功后再清除历史 `credential_invalid`。
- `credential.probe` request：`credential_ref,expected_metadata_version`；只使用 Catalog 固定 Probe，Sidecar `credential.probeSucceeded` 确认后 metadata 才 CAS 为 ready，response 为非敏感 metadata 和 Probe state。
- `credential.delete` request：`credential_ref,expected_metadata_version`；执行设计方案第 9.1 节删除屏障。
- Rust→Sidecar 内部 `credential.getReferences` 返回 `active_profile_version_ids,draft_profile_version_ids,non_terminal_run_ids,total_count`；内部 `credential.probeSucceeded` 携带 Profile scope、Credential Ref hash、Secret Version 和幂等 ID，并清除当前公司该 Profile 内对应 Credential 的全部 invalid health。两者均不进入公共 Registry，ProductionRpcServer 只允许当前认证 Rust IPC Session 调用并等待 WriteQueue commit 后响应。
- reverse `credential.describe` 只返回 `credential_ref,provider_release_id,auth_type,state,metadata_version,active_secret_version`，不返回 Secret。

- [ ] 写设计方案第 9 节每条强制校验的独立测试，包含 1/12/13 candidates 边界。
- [ ] 写 `eligible_roles` 枚举、Anchor 必须同时具备 single/fallback、fallback_order 每项必须具备 fallback 的测试。
- [ ] 写新 Policy 拒绝 `routing_enabled=false` Candidate、旧 fixed 兼容视图可读取但不可发布的测试。
- [ ] 写 Credential create/list/update/delete 的 Keychain mock 测试，断言任何响应、索引和日志均不包含 Secret。
- [ ] 写五个 Credential Registry owner/kind/scope/TTL、write 缺幂等键和同幂等键不同 Secret 返回冲突的测试；不得持久化 Secret 或可离线比对的 Secret hash。
- [ ] 写同 Provider label NFKC+casefold 唯一、跨 Provider 可同名、Provider auth_scheme 与 auth_type 不匹配拒绝的测试。
- [ ] 写 Credential Index Schema 的根 revision、状态条件字段、UUID/时间/版本正反例；Rust 必须使用生成类型或逐字段等价类型，并在读取时拒绝 unknown fields 和非法过渡态。
- [ ] 写索引权限 0600、临时文件 + fsync + atomic rename、metadata 版本冲突、重复 idempotency key、版本化 Keychain account、creating/updating/deleting 恢复矩阵和 metadata/Keychain 任一步失败的补偿测试。
- [ ] 写 create/update 后 unverified、Probe 失败保持 unverified、Sidecar 确认失败保持 unverified、Sidecar 已确认但 metadata CAS 失败仍被 Rust 拒绝、重试 Probe 收敛为 ready 的测试。
- [ ] 写删除屏障：Profile/Draft/非 terminal Run/Rust Lease 任一引用均拒绝；`deleting` 时新 Snapshot 注册拒绝；启动恢复 ready/清理 metadata 两条分支均测试。
- [ ] 写 Credential Version 固定测试：Snapshot 展开当前 version；update 在活跃 Lease 时返回 `CREDENTIAL_IN_USE`；尚未启动的旧 Snapshot version mismatch 进入 `waiting_resource`，不得调用 Provider。
- [ ] 写备份 manifest 排除 `provider-credentials.v1.json` 和 Secret、恢复后缺 Credential 不按 label 自动重绑且 Run 进入 `waiting_resource` 的测试。
- [ ] 写 `credential.describe` Provider mismatch/not-ready/not-found 测试，Profile publish 必须逐 Candidate 调用 metadata 校验而不是读取 Secret。
- [ ] 使用 `packages/contracts/fixtures/routing-canonical-json.v1.json` 写 Sidecar canonicalization 测试；fixture 覆盖中文、转义、键顺序、整数、四位小数字符串和嵌套数组，禁止在路由 JSON 中使用浮点数。
- [ ] 写 Agent CLI 请求携带 routing policy 必须失败的测试。
- [ ] 写既有数据库行和导入旧 Profile 缺 policy 时生成只读单候选 `fixed` 视图的兼容测试；不得回写原行。新的 `profile.createDraft` 在 API Model 未传 policy 时必须返回 `ROUTING_POLICY_REQUIRED`，且至少两个合法 Candidate 才可保存。旧 binding 缺 Provider/Model/Credential 时 `profile.validate` 必须失败而不是生成假 UUID。
- [ ] 更新 RPC schema/registry/error codes 后运行 `bash scripts/generate-contracts.sh`。
- [ ] 修改 Profile service：`routing_policy_json` 与 `runtime_binding_json` 分栏保存；发布时对同一 Catalog Release 做实体解析；canonical JSON 使用 RFC 8785。Public handler 必须在进入 WriteQueue 前逐 Candidate 调用 `credential.describe`，把非敏感 description 作为 preflight 输入传给 transaction；Snapshot 创建和 Rust Lease 注册再次验证当前 state/version，解决发布后的状态变化，不得在 SQLite transaction 内等待 reverse RPC。
- [ ] `profile.list` 每项必须返回 `profile_id,current_version_id,current_version_status,profile_type,name`，不得要求前端从自由结构 versions 数组猜当前版本。
- [ ] 注册 `routing.validatePolicy` 为只读 RPC，不保存输入、不解析 credential 明文。
- [ ] 运行 `cargo nextest run --manifest-path apps/desktop-core/Cargo.toml --test credential_management`。
- [ ] 运行 `uv run --directory sidecar pytest tests/test_routing_policy.py tests/test_credential_references.py tests/test_profile_service.py tests/test_public_rpc.py -q` 和 `bash scripts/check-contract-drift.sh`。

## Task 5: 创建 Execution Snapshot v2 与不可变候选集合

**Files:**

- Create: `sidecar/ibreeze/routing/candidates.py`
- Create: `packages/contracts/routing/candidate-bindings.v2.schema.json`
- Modify: `sidecar/ibreeze/orchestration/run_builder.py`
- Modify: `sidecar/ibreeze/orchestration/confirm_plan.py`
- Modify: `sidecar/ibreeze/runtime/run_executor.py`
- Create: `sidecar/tests/test_routing_candidates.py`
- Modify: `sidecar/tests/test_confirm_plan_transaction.py`
- Modify: `sidecar/tests/test_orchestration.py`
- Modify: `sidecar/tests/test_runtime_service.py`

**Resolver output:**

```python
@dataclass(frozen=True, slots=True)
class CandidateDeployment:
    candidate_id: str
    provider_release_id: str
    provider_key: str
    provider_protocol: str
    model_binding_id: str
    model_id: str
    provider_model_name: str
    credential_ref: str
    credential_secret_version: int
    context_window: int
    max_output_tokens: int
    supports_tools: bool
    supports_streaming: bool
    supports_vision: bool
    routing_tier: int
    quality_prior: Decimal
    tool_reliability_prior: Decimal
    latency_prior_ms: int
    model_family: str
    model_vendor: str
    architecture_class: str
    supports_reasoning: bool
    reasoning_levels: tuple[str, ...]
    eligible_roles: frozenset[RouteRole]
    request_defaults_sha256: str
```

`CandidateResolver.resolve` 只能读取 Profile Version 固定的 `catalog_release_id`、已验签本地 release cache 和 Credential metadata；返回按 `model_binding_id, candidate_id` 排序的 tuple。禁止网络查询中心后台。

- [ ] 写候选展开、缺 model、缺 provider binding、release 混用、disabled candidate、stable canonicalization 测试。
- [ ] 写 `candidate-bindings.v2` Schema 正反例，并让 Snapshot builder 和 Rust fixture 共同消费；字段禁止 `additionalProperties`。
- [ ] 写 Confirm Plan 同一 transaction 同时创建 v2 Snapshot 和 Run 的测试；任一步失败必须全部回滚。
- [ ] 写 Snapshot 哈希篡改导致启动拒绝的测试。
- [ ] 修改 `RunSpec` 增加 `routing_policy_json`、`candidate_bindings_json` 和两个 hash；API Model 必填，CLI 写空值。
- [ ] 修改 `build_run` 在插入 Snapshot 前验证两个 hash，`content_sha256` 必须覆盖旧字段与五个 v2 字段。
- [ ] 修改 `_load_snapshot` 返回 v2 字段；旧 Snapshot 自动构造单候选 `fixed` 视图但不更新数据库。
- [ ] 运行 `bash scripts/generate-contracts.sh` 并执行 contract drift，确保 Candidate Schema 的 Python/TypeScript/Rust 生成物一致。
- [ ] 运行 `uv run --directory sidecar pytest tests/test_routing_candidates.py tests/test_confirm_plan_transaction.py tests/test_orchestration.py tests/test_runtime_service.py -q`。

## Task 6: 在 Rust 建立 Snapshot Authorization Lease

**Files:**

- Create: `apps/desktop-core/src/broker/snapshot_authorization.rs`
- Modify: `apps/desktop-core/src/broker/mod.rs`
- Modify: `apps/desktop-core/src/rpc/reverse.rs`
- Modify: `packages/rpc-schema/reverse-methods.v1.json`
- Modify: `sidecar/ibreeze/runtime/run_executor.py`
- Modify: `sidecar/ibreeze/runtime/transport.py`
- Create: `apps/desktop-core/tests/reverse_broker_contract.rs`
- Create: `apps/desktop-core/tests/snapshot_authorization.rs`
- Modify: `sidecar/tests/test_model_transport_contract.py`
- Modify: `tests/integration/test_rust_sidecar_contract.py`

**New reverse methods:**

- `routing.snapshot.register`：Sidecar 在 Run 开始时注册 `execution_snapshot_id`、`run_id`、规范化 `candidate_bindings_json`、hash 和固定 `run_deadline_at`；deadline 为首次 running 时间加 Profile timeout，禁止续租。
- `routing.decision.register`：Decision `planned` 持久化后注册 Decision ID、turn index、主选择及完整 fallback Candidate/Role 清单。
- `routing.snapshot.revoke`：Run terminal、取消、IPC 断开或 Profile 关闭时撤销。
- `credential.http.start`：增加设计方案第 16 节八个 route 字段；去掉由 Sidecar 决定的 `relative_path`、`protocol` 和任意 model name，Rust 从 Catalog 解析。

**Rust structs:**

```rust
pub struct SnapshotAuthorization {
    pub execution_snapshot_id: Uuid,
    pub run_id: Uuid,
    pub candidate_bindings_json: String,
    pub candidate_bindings_sha256: String,
    pub candidates: Vec<AuthorizedCandidate>,
    pub run_deadline_at: DateTime<Utc>,
}
pub struct AuthorizedCandidate {
    pub candidate_id: Uuid,
    pub provider_release_id: Uuid,
    pub model_binding_id: Uuid,
    pub credential_ref: Uuid,
    pub credential_secret_version: u64,
    pub eligible_roles: BTreeSet<RouteRole>,
    pub request_defaults_sha256: String,
}
```

- [ ] 先写 Snapshot 外 binding、错误 credential、错误 role、错误 run、过期 lease、重复 attempt id、hash 不匹配测试。
- [ ] 写 Provider `deadline_at` 晚于 Run deadline、相同 Snapshot 试图延长 deadline 和 Run deadline 到期后新请求全部拒绝的测试。
- [ ] 写 IPC disconnect/cancel/revoke 后请求被拒绝的测试。
- [ ] 写 Decision 未注册、selection 不含 Candidate、相同 Decision 内容重放和冲突内容重放测试。
- [ ] 使用 Task 2 的 canonicalization fixture 验证 Rust 对 `candidate_bindings_json` 原始 UTF-8 字节验 hash 后再解析；禁止接受结构相同但字节未规范化的 JSON。
- [ ] 写同一 `route_attempt_id` 重放返回同一 accepted/terminal 结果且只触发一次 HTTP 的测试。
- [ ] 实现 `SnapshotAuthorizationStore`；key 为 Snapshot ID，另建 `route_attempt_id -> request_id/terminal` 幂等索引。
- [ ] `ReverseBroker.cancel_all` 必须同时清空 Snapshot leases 和 Attempt 索引。
- [ ] Rust 解析 Provider endpoint、protocol、path、request defaults、model name 后才构造 HTTP；任何 Sidecar 请求体中的 `model` 必须覆盖为 Catalog 值。
- [ ] Rust 将 Candidate `request_defaults_sha256` 与已验签 Catalog Binding 的规范化 defaults 哈希比较；不一致时在 HTTP 发送前拒绝。
- [ ] 运行 `cargo nextest run --manifest-path apps/desktop-core/Cargo.toml --test snapshot_authorization --test reverse_broker_contract`。
- [ ] 运行 `uv run --project sidecar pytest sidecar/tests/test_model_transport_contract.py tests/integration/test_rust_sidecar_contract.py -q`。

## Task 7: 结构化 Provider 错误、Attempt 事件和安全重试

**Files:**

- Modify: `apps/desktop-core/src/broker/http.rs`
- Modify: `apps/desktop-core/src/rpc/reverse.rs`
- Modify: `apps/desktop-core/src/rpc/error.rs`
- Modify: `sidecar/ibreeze/runtime/transport.py`
- Create: `apps/desktop-core/tests/provider_failure_classification.rs`
- Create: `sidecar/tests/test_provider_failures.py`
- Modify: `sidecar/tests/test_model_transport_contract.py`

**Terminal event:**

```json
{
  "request_id": "uuid",
  "route_attempt_id": "uuid",
  "event": "completed|failed|cancelled|timed_out",
  "failure_kind": null,
  "http_status": 200,
  "retry_after_ms": null,
  "timing": {"started_at":"...", "first_event_at":"...", "completed_at":"...", "latency_ms":123},
  "usage": {"prompt_tokens":1, "completion_tokens":2, "total_tokens":3},
  "payload": {}
}
```

`ProviderRequestError` 必须包含 `kind`、`http_status`、`retry_after_ms`、`request_id`、`safe_message`；禁止通过字符串解析决定重试。

ModelTurn 的 `HttpBroker` 只发送一次物理 HTTP 请求并返回结构化错误；不得在 Rust Broker 内部重试，否则会绕过 Sidecar 的 `RouteAttempt` 计数和第 15 节重试表。Credential Probe 不属于 RouteAttempt，可使用单独的探测重试上限。

- [ ] 为设计方案第 15 节 12 个 failure kind 各写 HTTP/transport 映射测试。
- [ ] 写 `Retry-After` 秒和 HTTP-date 两种解析测试，超过 900 秒截断至 900 秒。
- [ ] 写流开始后失败不得透明 fallback、未产生可见内容可 fallback 的测试。
- [ ] Rust 只在安全结构字段返回 Provider body 摘要；日志和 IPC 禁止包含 Authorization 和原始 error body。
- [ ] Sidecar `collect_broker_stream` 由抛 `RuntimeError(str(payload))` 改为构造 `ProviderRequestError`。
- [ ] 运行 `cargo nextest run --manifest-path apps/desktop-core/Cargo.toml --test provider_failure_classification` 和 `uv run --directory sidecar pytest tests/test_provider_failures.py tests/test_model_transport_contract.py -q`。

## Task 8: 实现 RoutingContext、Rules v1、Capability Gate 与单模型评分

**Files:**

- Create: `sidecar/ibreeze/routing/context.py`
- Create: `sidecar/ibreeze/routing/classifier.py`
- Create: `sidecar/ibreeze/routing/config.py`
- Create: `sidecar/ibreeze/routing/health.py`
- Create: `sidecar/ibreeze/routing/engine.py`
- Create: `sidecar/tests/test_routing_context.py`
- Create: `sidecar/tests/test_routing_classifier.py`
- Create: `sidecar/tests/test_routing_config.py`
- Create: `sidecar/tests/test_routing_engine.py`
- Create: `sidecar/tests/test_routing_health.py`

**Pure interfaces:**

```python
class RoutingContextBuilder:
    async def build(self, run: RunView, turn: TurnInput) -> RoutingContext: ...

class RulesV1Classifier:
    version = "rules-v1"
    def classify(self, context: RoutingContext) -> TierDecision: ...

class CapabilityGate:
    def filter(self, context: RoutingContext, tier: TierDecision,
               candidates: tuple[CandidateDeployment, ...],
               role: RouteRole) -> GateResult: ...

class RoutingPolicyEngine:
    def plan(self, context: RoutingContext, tier: TierDecision,
             candidates: tuple[CandidateDeployment, ...],
             health: Mapping[DeploymentKey, HealthState],
             policy: ValidatedRoutingPolicy) -> RoutePlan: ...
```

`RoutingRolloutConfig.from_env()` 只在 Sidecar 启动时读取 `IBREEZE_ROUTING_STAGE`。缺失默认 `observe`，非法值记录一次安全错误并返回 `observe`。公共 RPC 创建的 Context 必须强制 `input_origin=production`；只有 E2E/验收 harness 的内部构造器可设置 `evaluation`。

- [ ] 为 Routing Context 第 11 节所有字段写来源测试；Prompt 只能影响派生特征和 fingerprint，不得持久化正文。
- [ ] 写五个 rollout stage、默认值、非法值、启动后环境变化不生效、公共请求不能伪造 `evaluation` 的测试。
- [ ] 写 `observe` 只执行 Anchor 但记录 rules-v1 建议、`shadow+production` 不增加调用、`shadow+evaluation` 才执行候选、`learning_candidate` 未安装模型时仍由 rules-v1 实际选路的测试。
- [ ] 为第 12.1 节每个阈值写边界前/边界值测试，包含多规则、升一级上限 C3、operator 冲突。
- [ ] 为 capability gate 写 tools/vision/streaming/context/tier/reasoning/role/health 全矩阵。
- [ ] 为 C0-C3 reasoning 映射写测试；不允许低于目标 level。
- [ ] 为评分公式和稳定 tie-break 写精确 Decimal 断言；禁止 binary float 造成平台差异。
- [ ] 为 `fixed`、`smart_single`、Router 异常回 Anchor 和无 eligible candidate 写测试。
- [ ] Health State 使用 deployment tuple + credential hash；实现 strike、bench、重启保留、过期清理、成功复位。
- [ ] 运行 `uv run --directory sidecar pytest tests/test_routing_context.py tests/test_routing_classifier.py tests/test_routing_config.py tests/test_routing_engine.py tests/test_routing_health.py --cov=ibreeze.routing --cov-branch --cov-fail-under=100 -q`。

## Task 9: 实现 Decision/Attempt 生命周期与 RoutingTransport

**Files:**

- Create: `sidecar/ibreeze/routing/service.py`
- Create: `sidecar/ibreeze/routing/transport.py`
- Modify: `sidecar/ibreeze/runtime/model_loop.py`
- Modify: `sidecar/ibreeze/runtime/run_executor.py`
- Modify: `sidecar/ibreeze/runtime/transport.py`
- Modify: `sidecar/ibreeze/runtime/service.py`
- Create: `sidecar/tests/test_routing_service.py`
- Create: `sidecar/tests/test_routing_transport.py`
- Modify: `sidecar/tests/test_runtime_advanced.py`
- Modify: `sidecar/tests/test_runtime_service.py`

**Integration contract:**

`ModelRuntime` 不负责路由，保持每 turn 调用一个 `ModelTransport.complete`。`sidecar/ibreeze/routing/transport.py` 提供名为 `RoutingTransport` 的兼容门面，实际继承并调用 `RoutedModelTransport`；完整实现位于 `sidecar/ibreeze/runtime/transport.py`，避免维护两套路由算法。执行器对 v2 Snapshot 构造该门面，旧 Snapshot 仍走 fixed 兼容路径。每个 turn 执行完整路由：

```python
class RoutingTransport(ModelTransport):
    async def complete(
        self,
        messages: tuple[dict[str, object], ...],
        tool_names: tuple[str, ...],
    ) -> ModelTurn:
        # reserve turn index -> build context -> persist decision ->
        # execute attempts -> persist terminal -> return exactly one ModelTurn
        ...
```

`RoutingService.execute_attempt` 的顺序不可变：

1. 在 WriteQueue transaction 中创建 `route_attempts.created`。
2. 调用 Rust `credential.http.start`，携带相同 Attempt ID。
3. accepted 后 CAS 为 `accepted`，首个 stream event 后 CAS 为 `streaming`。
4. terminal event 后写 usage/timing/failure 并更新 health。
5. 只有 terminal persistence 成功后才把 ModelTurn 返回 ModelRuntime。

- [ ] 写一个 run 连续 3 turn 产生 turn_index 1/2/3 且唯一的测试。
- [ ] 写 transport 两次收到同一消息仍按 turn 序号而非 Prompt hash 去重的测试。
- [ ] 写 Decision/Attempt 合法和非法状态跃迁测试。
- [ ] 写数据库写失败时不得发 Provider 请求、terminal 写失败时不得执行工具的测试。
- [ ] Attempt/Decision/Health 审计写失败必须取消已 accepted 的 Broker 请求并禁止 retry/fallback；不得将持久化错误归类为 ProviderFailureKind。
- [ ] 写 fixed 和 smart_single 实际选择、Attempt role、usage/timing 归档测试。
- [ ] 写 Decision `selected_bindings_json` 在首次 Attempt 前已包含主选择、ensemble roles 和完整有序 fallback chain；`routing.decision.register` 成功后才允许创建 Attempt，运行中不得追加新 Candidate。
- [ ] 写 cancel race：start 前、accepted 后、streaming 后取消均只产生一个 terminal 状态。
- [ ] `run_executor._execute_model` 对 v2 Snapshot 构造 `routing.transport.RoutingTransport`（其真实实现为 `RoutedModelTransport`）；旧 Snapshot 构造兼容 fixed transport，停止直接把单一 binding 传给 `ReverseRpcTransport`。
- [ ] `cancel_model_run` 改为按 run 取消全部 active attempts，不再只存一个 request。
- [ ] 运行 `uv run --directory sidecar pytest tests/test_routing_service.py tests/test_routing_transport.py tests/test_runtime_advanced.py tests/test_runtime_service.py -q`。

## Task 10: 实现 retry、fallback 与 Deployment Health 闭环

**Files:**

- Modify: `sidecar/ibreeze/routing/service.py`
- Modify: `sidecar/ibreeze/routing/health.py`
- Modify: `sidecar/ibreeze/routing/engine.py`
- Create: `sidecar/tests/test_routing_fallback.py`
- Create: `sidecar/tests/test_routing_recovery.py`
- Modify: `sidecar/ibreeze/runtime/recovery.py`
- Modify: `sidecar/ibreeze/application/lifecycle.py`

**Retry planner:**

```python
@dataclass(frozen=True, slots=True)
class RetryDirective:
    retry_same: bool
    max_same_retries: int
    fallback_allowed: bool
    fallback_constraint: Literal["any", "larger_context", "different_credential_or_provider", "none"]
    bench_immediately: bool
    health_strike: bool
```

映射必须逐项等于设计方案第 15 节。Retry count 是同一物理失败后的额外尝试数，不包含第一次调用。每次 retry 都创建新 `route_attempt_id` 和递增 `attempt_sequence`。

- [ ] 写 12 个 failure kind 的 directive 参数化测试。
- [ ] 写 fallback_order 优先，其次 Router 评分稳定排序的测试；已经失败或 benched 的 deployment 不得重复选择。
- [ ] 写 `CONTEXT_OVERFLOW` 只选更大 context、`AUTH_INVALID`/`INSUFFICIENT_CREDITS` 只换 credential/provider、`BAD_REQUEST`/`POLICY_REFUSAL` 立即失败测试。
- [ ] 写可见内容和工具调用后的失败均禁止 retry/fallback 测试。
- [ ] 写 3 strikes bench、Retry-After 当前 Decision 保留重试、deadline 不足跳过等待、最大 900 秒、成功复位、重启清理测试。
- [ ] 写 `AUTH_INVALID` 不增 strike 但标记 `credential_invalid`、Capability Gate 持续排除、显式 probe 成功 CAS 恢复和更换 Credential Ref 不继承旧状态的测试。
- [ ] 启动生命周期在接受 Run 前执行 `cleanup_expired_health` 和 interrupted Decision reconciliation。
- [ ] Recovery 对 `planned` 可安全失败；对 `accepted/streaming` 必须先查询 Rust Attempt 状态，无法证明未发送时只标记 failed，不自动重放。
- [ ] 运行 `uv run --directory sidecar pytest tests/test_routing_fallback.py tests/test_routing_recovery.py -q`。

## Task 11: 实现选择性 Ensemble 的确定性阵容与安全聚合

**Files:**

- Create: `sidecar/ibreeze/routing/ensemble.py`
- Modify: `sidecar/ibreeze/routing/engine.py`
- Modify: `sidecar/ibreeze/routing/transport.py`
- Create: `sidecar/tests/test_routing_ensemble_plan.py`
- Create: `sidecar/tests/test_routing_ensemble_execution.py`
- Modify: `sidecar/tests/test_model_tools.py`

**Planner interface:**

```python
@dataclass(frozen=True, slots=True)
class EnsemblePlan:
    proposers: tuple[PlannedDeployment, ...]
    aggregator: PlannedDeployment
    quorum: int
    proposer_timeout_seconds: int
    aggregator_timeout_seconds: int

class EnsembleExecutor:
    async def execute(
        self,
        decision: RouteDecision,
        plan: EnsemblePlan,
        messages: tuple[dict[str, object], ...],
        tool_schemas: tuple[ToolSchema, ...],
    ) -> ModelTurn: ...
```

**Candidate envelope:**

```json
{
  "candidate_id": "route-attempt-id",
  "role": "anchor|orthogonal_reviewer|strong_critic|fast_sanity",
  "content": "string, max 24000 chars",
  "suggested_tool_calls": [{"name":"string","arguments":{}}],
  "truncated": false
}
```

- [ ] 为第 13 节 6 个触发条件和 6 个禁止条件逐一写测试。
- [ ] 为 Provider/Vendor/Family/Architecture 差异权重和稳定 tie-break 写精确测试。
- [ ] 为 2/3/4 proposer 的默认 quorum 和配置不得降低 quorum 写测试。
- [ ] 按 `estimated_input_tokens + 2000 + max_proposers * 24000` 写 aggregator context 上界边界测试；不足时必须在发出 proposer 请求前降级 single。
- [ ] 写并发完成乱序但 aggregator 输入仍按 plan role 顺序的测试。
- [ ] 写 5 秒 grace、timeout、cancel、retry 和未达 quorum 不调用 aggregator 的虚拟时钟测试。
- [ ] proposer transport 必须使用 `tool_choice=none` 或 Provider 等价禁止机制；返回 tool calls 只进入 `suggested_tool_calls`。
- [ ] aggregator 输入必须使用结构化 envelope，不能把 proposer 内容拼接成 system prompt；工具 schema 只提供给 aggregator。
- [ ] 写 proposer tool call 永不触发 `ModelRuntime` tool，aggregator 合法 tool call 恰好执行一次的端到端单元测试。
- [ ] 写 aggregator invalid response/retry/strong single fallback/fallback chain exhausted 测试。
- [ ] 运行 `uv run --directory sidecar pytest tests/test_routing_ensemble_plan.py tests/test_routing_ensemble_execution.py tests/test_model_tools.py --cov=ibreeze.routing.ensemble --cov-branch --cov-fail-under=100 -q`。

## Task 12: 关联工具、验证、Artifact、Review 与任务 Outcome

**Files:**

- Create: `sidecar/ibreeze/routing/outcomes.py`
- Modify: `sidecar/ibreeze/runtime/model_loop.py`
- Modify: `sidecar/ibreeze/runtime/verification_loop.py`
- Modify: `sidecar/ibreeze/application/review_handlers.py`
- Modify: `sidecar/ibreeze/application/review_aggregation.py`
- Modify: `sidecar/ibreeze/application/completion_handlers.py`
- Modify: `sidecar/ibreeze/artifacts/service.py`
- Create: `sidecar/tests/test_route_outcomes.py`
- Modify: `sidecar/tests/test_application_review_handlers.py`
- Modify: `sidecar/tests/test_completion_handlers.py`

**Attribution rule:**

- Tool result 关联产生该 tool call 的 Decision。
- Verification 关联发起该 verification 的最近一个 Decision；若验证针对 Artifact，则优先使用 Artifact 的 `source_run_id` 最后成功 Decision。
- Review 关联 Artifact 的 `source_run_id` 全部 Decisions，但 score 只写到该 Run 最后一个产生交付内容的 Decision。
- Task terminal 关联该任务所有 Run 的最后成功 Decision；失败且没有成功 Decision 时关联最后失败 Decision。

`RouteOutcomeProjector.append` 必须要求 `source_id` 是稳定业务 UUID 或 `run_id:turn_index`，禁止随机生成。

- [ ] 为设计方案第 19.1 节每条 score/label 写映射测试。
- [ ] 写重复事件、Outbox 重放和 Review 重跑不重复 Outcome 的测试。
- [ ] 写 Artifact superseded 后旧 Outcome 保留，新 Review 只关联新 Artifact 的测试。
- [ ] 写 verifier failure 会使下一 turn `verification_failures` 增加并触发 C3 的闭环测试。
- [ ] 实现本地校准：不足 30 样本返回 0；达到 30 按 purpose bucket 公式计算并 clamp 到 `[-0.20, 0.20]`。
- [ ] 写 prior 0/0.5/1、sample 29/30、不同 purpose、全局回退和 Decimal 精度测试。
- [ ] 运行 `uv run --directory sidecar pytest tests/test_route_outcomes.py tests/test_application_review_handlers.py tests/test_completion_handlers.py -q`。

## Task 13: 增加 Routing 公共 RPC 与错误契约

**Files:**

- Create: `packages/rpc-schema/methods/routing.getRunSummary.request.schema.json`
- Create: `packages/rpc-schema/methods/routing.getRunSummary.response.schema.json`
- Create: `packages/rpc-schema/methods/routing.listDecisions.request.schema.json`
- Create: `packages/rpc-schema/methods/routing.listDecisions.response.schema.json`
- Create: `packages/rpc-schema/methods/routing.getDecision.request.schema.json`
- Create: `packages/rpc-schema/methods/routing.getDecision.response.schema.json`
- Create: `packages/rpc-schema/methods/routing.listDeploymentHealth.request.schema.json`
- Create: `packages/rpc-schema/methods/routing.listDeploymentHealth.response.schema.json`
- Create: `packages/rpc-schema/methods/routing.setRunOverride.request.schema.json`
- Create: `packages/rpc-schema/methods/routing.setRunOverride.response.schema.json`
- Create: `packages/rpc-schema/methods/routing.clearExpiredHealth.request.schema.json`
- Create: `packages/rpc-schema/methods/routing.clearExpiredHealth.response.schema.json`
- Modify: `packages/rpc-schema/registry.v1.json`
- Modify: `packages/rpc-schema/error-codes.v1.json`
- Modify: `sidecar/ibreeze/application/public_rpc.py`
- Create: `sidecar/ibreeze/routing/rpc.py`
- Create: `sidecar/tests/test_routing_rpc.py`
- Modify: `sidecar/tests/test_public_rpc.py`
- Modify: `sidecar/tests/test_schemas.py`

**Method ownership and idempotency:**

`packages/rpc-schema/error-codes.v1.json` 必须一次性加入：`ROUTING_POLICY_REQUIRED`、`ROUTING_POLICY_INVALID`、`ROUTING_ANCHOR_MISSING`、`ROUTING_CANDIDATE_OUTSIDE_RELEASE`、`ROUTING_CANDIDATE_DUPLICATE`、`ROUTING_ROLE_INSUFFICIENT`、`ROUTING_FALLBACK_INVALID`、`ROUTER_NO_ELIGIBLE_CANDIDATE`、`MODEL_CAPABILITY_UNAVAILABLE`、`ROUTING_SNAPSHOT_HASH_MISMATCH`、`ROUTING_SNAPSHOT_NOT_AUTHORIZED`、`ROUTE_DECISION_CONFLICT`、`ROUTE_ATTEMPT_CONFLICT`、`ROUTING_OVERRIDE_NOT_AVAILABLE`、`CREDENTIAL_MISSING`、`CREDENTIAL_NOT_READY`、`CREDENTIAL_IN_USE`、`CREDENTIAL_VERSION_MISMATCH`、`CREDENTIAL_LABEL_DUPLICATE`、`CREDENTIAL_PROVIDER_MISMATCH`、`CREDENTIAL_INDEX_CORRUPT`。每个 RPC 的 `allowed_errors` 只列实际可返回子集，contract test 必须证明实现不会返回 Registry 外错误。

| 方法 | kind | 必填定位字段 | 主要响应 |
|---|---|---|---|
| `routing.validatePolicy` | read | `company_id, profile_type, policy`，并 one-of `profile_version_id/catalog_release_id` | `valid, canonical_sha256, issues` |
| `routing.getRunSummary` | read | `company_id, run_id` | totals、actual models、fallback、usage、latency |
| `routing.listDecisions` | read | `company_id, run_id, cursor, limit` | stable page |
| `routing.getDecision` | read | `company_id, decision_id` | decision、attempts、outcomes |
| `routing.listDeploymentHealth` | read | `company_id, cursor, limit, active_only` | health page |
| `routing.setRunOverride` | write | `company_id, run_id, expected_version, override` | `run_id, override, version` |
| `routing.clearExpiredHealth` | write | `company_id` | `deleted_count` |

`override` 只允许 `force_fixed`、`force_single`、`force_ensemble`、`clear`。无控制行时 `version=0`；第一次 write 必须携带 `expected_version=0` 并插入 version 1，后续用控制行版本 CAS。Override 持续影响设置后创建的所有 Decision，直到 clear 或 Run terminal；不得修改已存在的 Decision。Run terminal、Snapshot 不支持 ensemble 或 rollout stage 低于 selective ensemble 时，`force_ensemble` 返回 `ROUTING_OVERRIDE_NOT_AVAILABLE`；Override 不能绕过 Capability Gate 和 ensemble 禁止条件。`clearExpiredHealth` 只能删除当前公司 `availability_state=ready` 且 `benched_until <= now` 的记录，任何 active bench 或 `credential_invalid` 必须保留。

**Exact response fields:**

- `validatePolicy`: `valid:boolean, canonical_json:string|null, canonical_sha256:string|null, issues:[{code,json_pointer,message}]`；invalid 时两个 canonical 字段均为 null。
- `getRunSummary`: `run_id,routing_mode,rollout_stage,decision_count,single_count,ensemble_count,fallback_hops,total_prompt_tokens,total_completion_tokens,total_tokens,p50_latency_ms,p95_latency_ms,actual_models:[{candidate_id,provider_release_id,model_binding_id,attempt_count,success_count}],control:{override_mode,version}`。
- `listDecisions`: `items:[{decision_id,turn_index,routing_mode,required_tier,confidence,selected_kind,status,created_at,completed_at,actual_candidate_ids}],next_cursor`；排序固定 `turn_index ASC, decision_id ASC`，cursor 编码最后二元组。
- `getDecision`: `decision` 为完整非敏感 Decision 字段；`attempts[]` 含 sequence/role/Candidate/Provider/Model/status/failure/http/timing/usage/truncated；`outcomes[]` 含 type/source/score/label/time。不得返回 input、候选正文、Credential Ref 或 hash 前原值。
- `listDeploymentHealth`: `items:[{provider_release_id,model_binding_id,credential_slot,availability_state,consecutive_strikes,benched_until,last_failure_kind,last_failure_at,last_success_at,version}],next_cursor`；`credential_slot` 为 Credential Ref SHA-256 的前 12 个十六进制字符，仅用于区分同模型的多个本地凭据，不返回 Credential Ref 或完整 hash。
- `setRunOverride`: `run_id,override_mode,version,updated_at`；`clear` 后 override_mode 为 null。
- `clearExpiredHealth`: `deleted_count,completed_at`。

- [ ] 先写每个 schema 的最小合法、缺字段、额外字段、分页边界和 company 隔离测试。
- [ ] 写 write RPC 无 idempotency key、错误 expected_version、terminal run 和重复 key 测试。
- [ ] 实现 `routing/rpc.py`；查询必须 company-scoped，Decision 详情不得返回 credential_ref 原文或候选正文。
- [ ] 修改 registry/error codes，执行 `bash scripts/generate-contracts.sh`。
- [ ] 注册 read/write handler，保证最终注册数与 registry 完全一致。
- [ ] 运行 `uv run --directory sidecar pytest tests/test_routing_rpc.py tests/test_public_rpc.py tests/test_schemas.py -q` 和 `bash scripts/check-contract-drift.sh`。

## Task 14: 实现桌面 Profile 路由配置界面

**Files:**

- Create: `apps/desktop/src/hooks/useRouting.ts`
- Create: `apps/desktop/src/hooks/useCredentials.ts`
- Create: `apps/desktop/src/pages/ProfileRoutingPage.tsx`
- Create: `apps/desktop/src/pages/ProfileRoutingPage.test.tsx`
- Create: `apps/desktop/src/components/CredentialSettings.tsx`
- Create: `apps/desktop/src/components/CredentialSettings.test.tsx`
- Modify: `apps/desktop/src/app/routes.tsx`
- Modify: `apps/desktop/src/components/Layout.tsx`
- Modify: `apps/desktop/src/pages/EmployeePage.tsx`
- Modify: `apps/desktop/src/pages/AgentPage.tsx`
- Create: `apps/desktop/src/pages/AgentPage.test.tsx`
- Modify: `apps/desktop/src/pages/SettingsPage.tsx`
- Modify: `apps/desktop/src/types/index.ts`
- Modify: `apps/desktop/src/shared/queryKeys.ts`

**Route:** `/companies/:companyId/profiles/:profileId/routing`。

**Form behavior:**

1. Profile 类型为 CLI：只显示不可编辑说明，不发送 routing policy。
2. API Model：显示 mode、Anchor、Candidate table、eligible roles、fallback 排序和 ensemble 参数。
3. Candidate 数据只能来自 Profile 固定 Catalog Release 的 `runtime.listAvailableModels`；禁止自由文本输入 ID。
4. 切换 `fixed` 时保留候选草稿但保存请求只启用 Anchor；切回智能模式时用户重新确认启用项。
5. 点击保存前调用 `routing.validatePolicy`；有 issue 时按 `json_pointer` 定位字段并禁止 `profile.updateDraft`。
6. published version 全部只读；用户必须创建新 draft 才能修改。
7. `AgentPage` 增加“职员模型底座”列表，数据来自 `profile.list`，显示 profile type/current version/status；API Model Draft 提供“配置路由”入口，published version 提供“查看路由”入口，CLI 行只显示任务级路由说明。`EmployeePage` 只在能从 profile list 唯一反查 Profile ID 时显示同一入口，禁止把 Version ID 当 Profile ID。
8. Settings 嵌入 `CredentialSettings`：创建/更新 Secret 输入使用 password control，mutation settle 后无条件清空；unverified 只能 Probe/更新/删除，ready 可选入 Candidate，creating/updating/deleting 只显示“恢复中”且禁用操作；删除引用冲突必须显示引用类型和数量。列表只显示 label、Provider、state 和 UUID 后 8 位。

- [ ] 写 CLI/API Model 条件渲染测试。
- [ ] 写 AgentPage 从 Profile ID 导航、EmployeePage Version-to-Profile 唯一映射以及找不到映射时不生成坏链接的测试。
- [ ] 写 Credential Secret 不渲染、不写日志、mutation 成败均清空；Provider 过滤、Probe 状态、version conflict 和 delete references 提示测试。
- [ ] 写 Candidate Credential 下拉只列同 Provider ready 项，禁止自由输入 UUID、unverified/deleting 项不可选的测试。
- [ ] 写 1/12/13 candidates、Anchor 删除、role 不足、fallback 拖动后序列化测试。
- [ ] 写 validate 失败不保存、成功 canonical hash 展示、published 只读测试。
- [ ] 实现 hooks，所有 write mutation 使用 UUID idempotency key 并失效 profile/routing query。
- [ ] 使用统一 `formatBeijingTime` 和 `formatNumber`；不得在页面内重复实现格式器。
- [ ] 运行 `npm --prefix apps/desktop run test -- ProfileRoutingPage.test.tsx AgentPage.test.tsx CredentialSettings.test.tsx && npm --prefix apps/desktop run typecheck && npm --prefix apps/desktop run lint`。

## Task 15: 实现 Run 路由观测、健康与 Override 界面

**Files:**

- Create: `apps/desktop/src/pages/RunRoutingPage.tsx`
- Create: `apps/desktop/src/pages/RunRoutingPage.test.tsx`
- Modify: `apps/desktop/src/pages/TaskDetailPage.tsx`
- Modify: `apps/desktop/src/pages/SettingsPage.tsx`
- Modify: `apps/desktop/src/app/routes.tsx`
- Modify: `apps/desktop/src/hooks/useRouting.ts`
- Modify: `apps/desktop/src/types/index.ts`

**Route:** `/companies/:companyId/runs/:runId/routing`。

页面必须显示：

- Summary：mode、Decision 数、single/ensemble、fallback hops、总 tokens、P50/P95 latency。
- Decision table：turn、tier、confidence、selected kind、requested/actual model、status。
- Detail drawer：policy trail、Attempts、failure kind、usage、timing、Outcomes；不显示 Prompt 和 Credential Ref。
- Override：只对 running/queued Run 显示；明确提示持续影响后续 turn，直到清除或 Run 结束。
- Settings 的 Deployment Health：model/provider、strike、bench 截止、最后成功/失败；只允许清除已过期记录。

- [ ] 写分页、空状态、错误状态、Decision detail 和敏感字段不渲染测试。
- [ ] 写北京时间和最多两位小数展示测试。
- [ ] 写 override optimistic lock、terminal 禁用、成功刷新测试。
- [ ] 写 active bench 无绕过按钮、expired cleanup 行为测试。
- [ ] 运行 `npm --prefix apps/desktop run test -- RunRoutingPage.test.tsx && npm --prefix apps/desktop run typecheck && npm --prefix apps/desktop run lint`。

## Task 16: 建立可观测性、Fake Provider 和跨进程 E2E

**Files:**

- Create: `sidecar/ibreeze/observability/routing.py`
- Modify: `sidecar/ibreeze/observability/health.py`
- Modify: `sidecar/ibreeze/logging_config.py`
- Create: `tests/e2e/fake_provider.py`
- Create: `tests/e2e/test_intelligent_routing.py`
- Create: `packages/contracts/evaluation/routing-golden-task.v1.schema.json`
- Create: `tests/fixtures/routing-golden-tasks.v1.json`
- Create: `tests/fixtures/routing/`（目录内保存 Golden Task 脱敏输入与期望断言文件）
- Create: `sidecar/tests/security/test_routing_redaction.py`
- Modify: `sidecar/tests/test_observability_health.py`
- Modify: `apps/desktop-core/tests/reverse_broker_contract.rs`
- Modify: `scripts/verify-all.sh`

**Fake Provider scenarios:**

`ok_single`、`ok_tool_call`、`rate_limited_then_ok`、`overloaded`、`timeout`、`invalid_json`、`context_overflow`、`auth_invalid`、`stream_then_fail`、`slow_proposer`、`aggregator_invalid_then_ok`。服务必须使用本地测试证书并只绑定 loopback。

- [ ] 为设计方案第 22 节所有 metric name/label 写注册和累加测试。
- [ ] 写日志捕获测试，断言 Prompt、候选正文、API Key、Authorization、credential_ref 原文均不存在。
- [ ] E2E `fixed`：单 Decision、单 Attempt、真实模型为 Anchor。
- [ ] E2E `smart_single`：规则选择、429 fallback、health bench、第二 turn 跳过 benched。
- [ ] E2E `selective_ensemble`：3 proposer/2 quorum/1 aggregator，proposer tool call 不执行，aggregator tool call 执行一次。
- [ ] E2E cancel/crash：所有 attempts terminal，恢复不重复 HTTP。
- [ ] E2E authorization：Snapshot 外 binding、错误 role、错误 credential 被 Rust 拒绝且 Fake Provider 计数为 0。
- [ ] 创建 200 项 Golden Task manifest：C0–C3 各 50 项，每级代码实现、代码 Review、文档/方案、结构化 Schema、工具/故障恢复各 10 项；验证 task_id、输入 fingerprint 不重复，所有 fixture 路径位于 `tests/fixtures/routing/`。
- [ ] Schema 强制每项包含 `task_id,tier,category,run_purpose,input_fixture,required_tools,acceptance,artifact_type,max_runtime_seconds`；`acceptance` 只能使用仓库内命令或结构化断言，禁止人工主观打分。
- [ ] 更新 `run_e2e`：现有 Backend E2E 继续使用 Backend project，`test_intelligent_routing.py` 单独使用 Sidecar project；两组任一失败都使 scope 失败。
- [ ] 运行 `uv run --project sidecar pytest tests/e2e/test_intelligent_routing.py -q` 和 `uv run --directory sidecar pytest tests/security/test_routing_redaction.py tests/test_observability_health.py -q`。

## Task 17: 文档同步、效果验收与全量发布门禁

**Files:**

- Modify: `README.md`
- Modify: `docs/部署文档.md`
- Modify: `docs/设计方案/AI公司桌面应用设计方案.md`
- Modify: `docs/设计方案/AI公司桌面应用-实施计划.md`
- Modify: `docs/设计方案/iBreeze智能聚合路由设计方案.md`（仅当实现发现已核实的契约偏差）
- Create: `docs/使用说明/智能聚合路由使用说明.md`
- Create: `docs/验收报告/智能聚合路由效果验收报告.md`

**Documentation requirements:**

- README：能力边界、三种模式、CLI/API Model 区别、快速验证命令。
- 部署文档：Backend migration 005、Sidecar migration 006/007、Catalog 重新发布、Desktop 升级顺序、回退到 fixed、监控与故障处理。
- 总体设计/实施计划：链接专项设计，更新 Profile/Snapshot/RPC/本地表/UI 清单；不得复制出冲突的第二套字段。
- 使用说明：管理员维护路由元数据、用户配置 Profile、查看 Run、处理 bench 和 override。
- 验收报告：固定 task set、模型池、Provider release、每组样本数、通过率、Review blocker/high、修复轮次、P50/P95 latency、token usage 和原始结果文件 hash。

- [ ] 运行所有专项单元测试，Sidecar `ibreeze.routing` statement/branch 达到 100%，Rust 新授权/分类模块的 `cargo llvm-cov` line/function/region 达到 100%。
- [ ] 执行效果 A/B：Anchor、smart_single、固定 ensemble、selective_ensemble 使用完全相同的 200 项 Golden Task、同一 Catalog Release、同一 Credential 集合和同一 Provider 区域；报告记录 manifest SHA-256。
- [ ] 验证 smart_single 通过率相对 Anchor 下降不超过 1 个百分点。
- [ ] 验证 selective ensemble 在 C3/失败恢复样本通过率提升至少 5 个百分点，或平均修复轮次下降至少 20%。
- [ ] 验证 blocker/high 不上升、工具重复执行为 0、single Router P95 <20ms。
- [ ] 完成文档同步并运行发布清洁扫描，README、部署文档、设计方案和使用说明不得含未完成标记、占位描述或历史迭代说明。
- [ ] 运行 `bash scripts/verify-all.sh --scope contracts`。
- [ ] 运行 `bash scripts/verify-all.sh --scope backend`。
- [ ] 运行 `bash scripts/verify-all.sh --scope sidecar`。
- [ ] 运行 `bash scripts/verify-all.sh --scope desktop`。
- [ ] 运行 `bash scripts/verify-all.sh --scope security`。
- [ ] 运行 `bash scripts/verify-all.sh --scope e2e`。
- [ ] 运行 `bash scripts/verify-all.sh --scope drift`。
- [ ] 最后运行 `bash scripts/verify-all.sh --scope all`；预期 exit code 0、无新增 skip/xfail、无 coverage exclusion、`git diff --check` 通过。

## Completion Checklist

- [ ] Profile Version 固化合法 `routing_policy_json`，旧 profile 有明确 fixed 兼容行为。
- [ ] Execution Snapshot v2 固化完整 Candidate Set 和 hash，Run 中途不读新 Catalog/Profile。
- [ ] Rust 对每个 Attempt 验证 Snapshot、Run、Deployment、Credential、Role 和幂等 ID。
- [ ] API Model 三种路由模式全部通过 unit/integration/E2E；CLI 行为没有改变。
- [ ] proposer 永不执行工具；aggregator 或 single/fallback 的工具调用最多执行一次。
- [ ] 12 类 Provider 错误具有确定 retry/fallback/bench 行为。
- [ ] Crash/cancel/reconnect 不重复 Provider 请求或工具副作用。
- [ ] Decision、Attempt、Health、Outcome、usage、latency 和 Review 可从 Run 完整追踪。
- [ ] 所有 RPC schema、generated types、Backend OpenAPI、UI types 和实现一致。
- [ ] 所有文档与实现一致且不含迭代痕迹、占位描述或未决策项。

## 本次实现状态与验证证据（2026-08-13）

本计划中的代码任务已在当前工作树落地，以下矩阵记录实现路径和可复现证据。Task 1–16 的原始复选框保留为发布门禁清单：它们包含真实 Provider、跨进程 macOS 和覆盖率要求，不能用本地结构测试冒充完成。

| 范围 | 已落地内容 | 当前证据 |
|---|---|---|
| Catalog/契约 | Backend routing metadata、签名 Release 字段、Policy/Candidate v2 Schema、RPC/生成物同步 | `bash scripts/generate-contracts.sh`；`bash scripts/check-contract-drift.sh` 通过 |
| 本地数据 | migration 006/007、Profile Policy、Snapshot v2、Decision/Attempt/Health/Outcome/Override、不可变 Trigger；migration 007 将 Plan/Department Task 的 `required_capability_tags` 冻结到 eager/lazy Run spec | `uv run --directory sidecar pytest tests/test_routing_migration.py tests/test_routing_repository.py -q`；全量 Sidecar 1746 passed |
| Sidecar 路由 | Context（含交付物/能力标签/输入源指纹）、rules-v1、能力门控、Decimal 评分、启动阶段快照、fixed/smart_single/selective_ensemble、observe/shadow 建议、retry/fallback、健康 fail-closed、本地 purpose 校准、effective quality 稳定排序、启动恢复、Attempt 生命周期、proposer 不可执行工具 Schema 和确定性排序 | 路由/Outcome/策略/候选/启动恢复/生命周期/确定性排序/健康恢复/脱敏专项 94 passed；专项 100% 覆盖率仍是发布门禁 |
| Rust Broker | 完整 v2 Candidate 原始 JSON/hash 校验、Snapshot/Decision/Attempt Lease、Credential Version、Catalog-derived protocol/path/model/request defaults、RFC 8785 UTF-16 key canonicalization、错误归一化、旧 fixed 快照兼容和路由字段完整性 fail-closed | `cargo nextest run --offline --no-fail-fast`；191 passed |
| 工具与审计 | proposer tool call envelope 隔离、streaming CAS、稳定 Tool Outcome UUID、Review/Verification/Task Outcome 关联 | Sidecar 全量、脱敏 2 passed |
| UI/公共 RPC | Policy 配置、Run 观测、Health/Override、company-scoped 脱敏查询 | Desktop 151 passed、Admin Web 134 passed、typecheck/lint 通过；Backend 路由相关 44 passed |
| Golden/E2E | C0–C3 各 50 项的 200 项 manifest，结构化 routing E2E 和 redaction E2E | manifest SHA-256 `74fec836f53b0384c7faa361b0628674cc56a84d8724844e49b47e8ebe1f4ac5`；结构 E2E 4 passed |

以下事项仍必须在 staging/发布环境或专项补测后才能把本计划标记为最终交付：真实 Provider 双供应商 ensemble 与故障转移、四组 200 项质量 A/B、跨进程 Rust IPC/TLS、macOS 14/26 Seatbelt、签名公证、升级回滚、Sidecar 总覆盖率 77%、Desktop functions 80%、Admin Web branches 80% 门禁，以及 Sidecar routing statement/branch 与 Rust 新授权模块的专项 100% 覆盖率。当前状态应表述为“代码实现与可运行测试闭环已落地，发布门禁仍待完成”，不得表述为已完成生产效果验收。
