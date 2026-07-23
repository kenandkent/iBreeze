# iBreeze AI 公司桌面应用实施计划

> **执行方式：** 第三方实施团队按任务依赖逐项执行并以 `- [ ]` 跟踪；任何任务不得跳过失败测试、验证、独立 Review 或阶段出口门禁。

**目标：** 严格按照《AI公司桌面应用设计方案.md》从空代码基线实现可发布的 iBreeze 桌面客户端、Python Sidecar、中心管理后台及其自动化测试、部署和用户文档。

**架构：** 桌面端由 React WebView、Tauri/Rust Core 和唯一 Python Sidecar 组成，全部公司、部门、职员、任务、会话、运行、知识与审计数据保存在本地 Profile。中心后台只负责认证、用户管理和签名发布 Agent、Model、Provider、Skill、兼容规则目录；后台不接收桌面业务数据。所有跨语言边界先定义 JSON Schema/OpenAPI，再生成类型并实现，禁止三端手写同名 DTO。

**技术栈：** React 19、TypeScript 5.7、Vite 6、TanStack Query 5、Zustand 5、Ant Design 5、Tauri 2、Rust 2021、Tokio 1、Python 3.12、Pydantic 2、aiosqlite、LanceDB、ONNX Runtime、FastAPI、SQLAlchemy 2 Async、asyncpg、Alembic、PostgreSQL 16、MinIO、OpenAPI 3.1、JSON-RPC 2.0、JSON Schema 2020-12。

## 全局约束

- 设计方案是功能、字段、状态机、DDL、RPC、REST、安全参数和门禁的唯一事实来源；计划只确定实现顺序、文件归属和验收方法。发现设计缺口时先修改并审核设计方案，禁止在代码中自行补充规则。
- 首发平台固定为 macOS Apple Silicon；CLI Adapter 固定支持 Codex CLI `>=0.144.0 <0.145.0`、Claude Code `>=2.1.0 <2.2.0`、OpenCode `>=1.18.0 <1.19.0`。
- 桌面每个 Profile 只有一个 Python Sidecar 进程；Local Application Service、Orchestration Platform 与 Runtime Gateway 都是该进程内模块。
- 公司是模拟 Agent 工作流，不是真实组织、租户或客户；后台禁止出现公司、部门、职员实例、任务、会话、报告、知识和 Workspace 数据表或 API。
- API Model 是职员模型底座，由 iBreeze Built-in Agent Runtime 驱动完整 Agent Loop；不得实现为简单模型聊天 Adapter。
- 默认权限为当前 Run Workspace 内读写、Workspace 外普通文件只读；其他 Profile、公司、职员私有区、Keychain 和凭据路径不可读；外部写入只允许单目标、单动作、单次审批。
- 不实现预算、费用审批、成本配额、多租户、远程 Agent 执行、普通多模型聊天或后台业务数据同步。
- 所有时间在持久层与协议中使用带 `Z` 的 RFC 3339 UTC；桌面和管理后台统一转换为 `Asia/Shanghai` 展示。无时区字符串按北京时间墙钟时间解释。
- 所有前端数值通过统一格式化器展示，默认最多两位小数且不补零。
- 所有 UUID 由应用层使用 CSPRNG 生成；所有规范 JSON 哈希使用 RFC 8785 + SHA-256；签名使用 Ed25519。
- 手写可执行源码按语言原生可测指标全部达到 100%：TypeScript/TSX 的 statements、branches、functions、lines；Python 的 statements/lines 与 branches；Rust 的 lines、functions、regions。只允许设计方案 K.14 列明的排除项，排除项必须进入 `coverage-exclusions.yml`。
- 每个任务执行 TDD：先提交可复现的失败测试，再做最小实现，最后运行局部测试和受影响的全量测试。禁止先写实现后补测试。
- 每个任务单独提交。提交信息格式固定为 `<type>(<scope>): <结果>`，如 `feat(auth): add refresh token rotation`。不得把互不相关的任务合并进一个提交。
- 每个阶段结束必须由未实现该阶段核心代码的 Reviewer 执行设计一致性 Review；blocker/high 问题清零后才能进入依赖该阶段的任务。
- 实现过程中每次代码修改都同步更新根 `README.md` 和 `docs/部署文档.md`；用户可见行为同步更新 `docs/用户手册.md`。

---

## 1. 计划使用方法与交付规则

### 1.1 任务状态

每个任务只能按以下状态流转：

```text
not_started → test_red → implementing → test_green → reviewing → accepted
                                              └────→ changes_requested → implementing
```

- `test_red` 必须保存失败命令和预期失败原因。
- `test_green` 必须保存局部测试、静态检查和覆盖率结果。
- `reviewing` 必须检查设计章节、公开接口、数据迁移、安全边界和文档同步。
- `accepted` 必须有提交 SHA、测试证据和 Reviewer 名称。

### 1.2 任务完成定义

任一任务只有同时满足以下条件才算完成：

1. 本任务列出的文件、接口和数据库变更已经落地。
2. 所列失败测试先红后绿，且没有删除或弱化断言。
3. 受影响语言的格式化、静态检查和局部覆盖率门禁通过。
4. OpenAPI、JSON Schema、生成 DTO 或迁移文件没有未提交差异。
5. 没有引入设计方案之外的依赖、状态、RPC、REST 或配置项。
6. README、部署文档和用户手册按可观察变化同步更新。
7. 独立 Reviewer 完成 Review，blocker/high 为零。
8. 提交中只包含本任务相关文件。

### 1.3 标准验证命令

各任务按涉及范围运行以下命令；路径不存在表示前置任务未完成，不能跳过：

```bash
cd apps/desktop && npm ci && npm run lint && npm run typecheck && npm run test:coverage
cd apps/admin-web && npm ci && npm run lint && npm run typecheck && npm run test:coverage
cd apps/desktop-core && cargo fmt --check && cargo clippy --all-targets --all-features -- -D warnings
cd apps/desktop-core && cargo nextest run && cargo llvm-cov --all-features --fail-under-lines 100 --fail-under-functions 100 --fail-under-regions 100
cd sidecar && uv sync --frozen && uv run ruff check . && uv run mypy ibreeze
cd sidecar && uv run pytest --cov=ibreeze --cov-branch --cov-fail-under=100
cd apps/backend-api && uv sync --frozen && uv run ruff check . && uv run mypy src
cd apps/backend-api && uv run pytest --cov=ibreeze_backend --cov-branch --cov-fail-under=100
npm --prefix tests/e2e ci && npm --prefix tests/e2e run test
```

### 1.4 计划阶段与依赖

| 阶段 | 内容 | 必须依赖 | 阶段出口 |
|---|---|---|---|
| P0 | 工程、契约、CI 与打包风险验证 | 无 | 四端可构建，契约可生成，Sidecar 可打包 |
| P1 | 中心后台认证、用户与目录发布 | P0 | OpenAPI、PostgreSQL、MinIO 与 Admin API 完整通过 |
| P2 | Rust Core、Keychain、Profile、IPC 与 Catalog Sync | P0、P1 公开契约 | Rust 能安全打开 Profile 并启动 Sidecar |
| P3 | Sidecar 基础设施与本地持久化 | P0、P2 IPC | SQLite 迁移、RPC、事件和幂等可用 |
| P4 | 公司、部门、职员、底座、会话与任务领域 | P3 | 本地核心聚合和状态机通过事务测试 |
| P5 | Agent Runtime Gateway | P2、P3、P4 | 三 CLI 与 API Model 契约全部通过 |
| P6 | Workspace、Artifact、Review 与审批 | P4、P5 | Worktree、CAS、Review 闭环与权限门禁通过 |
| P7 | 公司级和部门级编排 | P4、P5、P6 | 标准软件需求流程可无 UI 完整运行 |
| P8 | 知识、检索、备份与恢复 | P3、P6、P7 | 知识对账与一致备份恢复通过 |
| P9 | 桌面 React UI | P2–P8 稳定 RPC | 全部桌面路由和用户流程 E2E 通过 |
| P10 | 管理后台 React UI | P1 稳定 OpenAPI | 用户、目录、发布和审计 UI 通过 |
| P11 | 可观测性、性能、安全和发布 | 全部 | K.17 最终发布门禁全部通过 |

允许并行：P1 与 P2 的本地壳工作可以在 P0 后并行；P9 只能在对应 RPC 契约冻结后按页面逐步接入；P10 可在各 Admin API 完成后逐模块接入。禁止并行修改同一契约源或同一迁移序列。

---

## 2. 固定工程文件地图

第三方团队必须先创建并持续维护以下边界。未列出的新顶层目录需要先修改设计方案附录 A。

```text
ibreeze/
├─ apps/
│  ├─ desktop/
│  │  ├─ src/app/                 # 路由、Provider、错误边界
│  │  ├─ src/features/            # 按业务能力拆分页面与 hooks
│  │  ├─ src/shared/              # RPC client、格式化、通用组件
│  │  └─ tests/
│  ├─ desktop-core/
│  │  ├─ src/commands/            # 七个 WebView Tauri Command
│  │  ├─ src/ipc/                 # UDS、framing、JSON-RPC
│  │  ├─ src/auth/                # Backend client、JWT、Keychain
│  │  ├─ src/profile/             # Profile discovery 与目录权限
│  │  ├─ src/process/             # Sidecar/CLI 进程监管
│  │  ├─ src/security/            # Grant、Egress、签名、沙箱输入
│  │  └─ tests/
│  ├─ admin-web/
│  │  ├─ src/app/
│  │  ├─ src/features/
│  │  ├─ src/shared/
│  │  └─ tests/
│  └─ backend-api/
│     ├─ src/ibreeze_backend/
│     │  ├─ auth/ users/ catalog/ skills/ compatibility/ releases/
│     │  ├─ api/ db/ storage/ security/ observability/
│     │  └─ main.py
│     ├─ migrations/
│     └─ tests/
├─ sidecar/
│  ├─ ibreeze/
│  │  ├─ application/ orchestration/ runtime/
│  │  ├─ domain/ persistence/ rpc/ events/
│  │  ├─ workspace/ artifacts/ review/ knowledge/ backup/
│  │  └─ main.py
│  ├─ migrations/
│  └─ tests/
├─ packages/
│  ├─ contracts/                  # REST、事件、Artifact、Skill Schema
│  ├─ rpc-schema/                 # 本地 RPC Schema
│  └─ ui/                         # 两个 Web 应用共享的无业务状态组件
├─ tests/
│  ├─ contract/ integration/ e2e/ security/ faults/ performance/ release/
│  └─ fixtures/
├─ deploy/
├─ scripts/
├─ coverage-exclusions.yml
├─ README.md
└─ docs/
```

文件职责要求：领域实体不依赖 RPC、HTTP、React 或 Tauri；Repository 不做状态迁移决策；Command Handler 负责事务、权限、幂等和事件；React 不复制领域实体到 Zustand；Rust 不直接读取业务 SQLite；Sidecar 不直接访问 Keychain 或外网模型 API。

---

## 3. P0：工程、契约、CI 与风险验证

### P0-T01：建立四端工程和锁文件

**依赖：** 无。

**文件：**

- 创建：`apps/desktop/package.json`、`package-lock.json`、`tsconfig.json`、`vite.config.ts`
- 创建：`apps/admin-web/package.json`、`package-lock.json`、`tsconfig.json`、`vite.config.ts`
- 创建：`apps/desktop-core/Cargo.toml`、`Cargo.lock`、`src/main.rs`、`src/lib.rs`
- 创建：`sidecar/pyproject.toml`、`uv.lock`、`ibreeze/main.py`
- 创建：`apps/backend-api/pyproject.toml`、`uv.lock`、`src/ibreeze_backend/main.py`
- 创建：`tests/e2e/package.json`、`tests/e2e/package-lock.json`、`tests/e2e/playwright.config.ts`
- 创建：`.gitignore`、`coverage-exclusions.yml`、`scripts/verify-all.sh`
- 修改：`README.md`、`docs/部署文档.md`

**接口：** 本任务只输出可构建工程，不定义业务 API。依赖版本必须与设计方案 F.1 完全一致。

- [ ] **步骤 1：写工程存在性失败测试**

  在 `tests/contract/test_repository_layout.py` 枚举上述文件，逐项断言存在，并校验五个应用锁文件与E2E测试锁文件已提交。运行：

  ```bash
  python3 -m pytest tests/contract/test_repository_layout.py -v
  ```

  预期：FAIL，报告第一个缺失文件。

- [ ] **步骤 2：创建最小工程入口和依赖锁**

  Python 入口只允许返回版本，不连接数据库：

  ```python
  def build_info() -> dict[str, str]:
      return {"app": "ibreeze", "protocol_version": "1"}
  ```

  Rust `lib.rs` 暴露同一 `PROTOCOL_VERSION: &str = "1"`；两个 React 应用只渲染应用名称和 build version。

- [ ] **步骤 3：安装依赖并生成锁文件**

  ```bash
  cd apps/desktop && npm install
  cd ../admin-web && npm install
  cd ../desktop-core && cargo generate-lockfile
  cd ../../sidecar && uv lock
  cd ../apps/backend-api && uv lock
  cd ../../tests/e2e && npm install
  ```

  预期：六条命令退出码均为 0，锁文件无 `latest` 或 Git branch 依赖。

- [ ] **步骤 4：运行布局和最小构建测试**

  ```bash
  python3 -m pytest tests/contract/test_repository_layout.py -v
  npm --prefix apps/desktop run build
  npm --prefix apps/admin-web run build
  npm --prefix tests/e2e run typecheck
  cargo check --manifest-path apps/desktop-core/Cargo.toml --locked
  uv run --directory sidecar python -c 'from ibreeze.main import build_info; assert build_info()["protocol_version"] == "1"'
  uv run --directory apps/backend-api python -c 'from ibreeze_backend.main import build_info; assert build_info()["protocol_version"] == "1"'
  ```

  预期：全部 PASS。

- [ ] **步骤 5：提交**

  ```bash
  git add apps sidecar tests scripts coverage-exclusions.yml README.md docs/部署文档.md
  git commit -m "chore(repo): initialize ibreeze applications"
  ```

**完成标准：** 干净环境只依赖 Node、Rust 和 `uv` 即可重现全部锁文件构建；没有业务占位接口或未锁定依赖。

### P0-T02：建立 Schema 源、生成器与漂移门禁

**依赖：** P0-T01。

**文件：**

- 创建：`packages/contracts/{events,domain-events,artifacts,skill}/`
- 创建：`packages/contracts/domain-events/registry.v1.json` 及H.4注册表引用的全部v1 payload Schema（含 `knowledge.imported/removed`）
- 创建：`packages/contracts/package.json`、`packages/contracts/package-lock.json`
- 创建：`packages/rpc-schema/methods/`、`packages/rpc-schema/meta.schema.json`、`packages/rpc-schema/ownership.v1.json`
- 创建：`scripts/generate-contracts.sh`、`scripts/check-contract-drift.sh`
- 创建：`scripts/schema-gen-rust/Cargo.toml`、`scripts/schema-gen-rust/Cargo.lock`、`scripts/schema-gen-rust/src/main.rs`
- 创建：`apps/desktop/src/generated/rpc/`
- 创建：`apps/desktop-core/src/generated/`
- 创建：`sidecar/ibreeze/generated/`
- 创建：`apps/admin-web/src/generated/openapi/`
- 创建：`tests/contract/test_schema_catalog.py`

**接口：** JSON Schema dialect 固定为 2020-12；每个 Schema 必须有稳定 `$id`、`title`、`type`、`required` 和 `additionalProperties:false`。生成目标固定为 TypeScript、Pydantic 2 和 Rust Serde。

- [ ] **步骤 1：写失败的 Schema 目录测试**

  测试必须验证 `$schema=https://json-schema.org/draft/2020-12/schema`、重复 `$id`、悬空 `$ref`、未知文件和生成目录是否与源一致。

  ```bash
  python3 -m pytest tests/contract/test_schema_catalog.py -v
  ```

  预期：FAIL，提示 `meta.schema.json` 或注册表不存在。

- [ ] **步骤 2：先实现 RPC meta 和最小 health 契约**

  `meta.schema.json` 固定要求 `trace_id/ipc_session_id/window_session_id/idempotency_key`，其中 `ipc_session_id` 仅Rust本地方法和首次handshake可为null；`ownership.v1.json` 把公开方法精确分配给 `rust_core/sidecar/supervisor_only`，集合必须与J.14及三个Supervisor方法一致且互斥；`reverse-methods.v1.json` 精确登记F.4四个Sidecar→Rust请求和两个通知，并为 `host.externalWrite.execute` 生成严格请求/响应Schema；创建 `system.handshake` 请求/响应Schema及 `system.health` 请求/响应Schema，handshake响应固定五字段ready契约，health response只包含F.5的七个健康字段。

  同时一次性创建H.4完整DomainEvent registry及每个独立payload Schema；目录测试要求registry引用零悬空且集合与H.4逐项相等。后续领域任务只能实现和消费已登记v1事件，不能等到功能阶段再补一个P3运行时所需的Schema。

- [ ] **步骤 3：实现可重复生成脚本**

  ```bash
  npm --prefix packages/contracts ci
  npm exec --prefix packages/contracts -- json2ts -i packages/rpc-schema -o apps/desktop/src/generated/rpc
  uv run --directory sidecar datamodel-codegen --input ../packages/rpc-schema --output ibreeze/generated/rpc.py --output-model-type pydantic_v2.BaseModel
  cargo run --locked --manifest-path scripts/schema-gen-rust/Cargo.toml
  ```

  脚本必须先生成到临时目录，成功后原子替换；失败不得破坏现有生成物。

- [ ] **步骤 4：验证生成确定性**

  连续运行两次 `scripts/generate-contracts.sh`，第二次 `git diff --exit-code` 必须为 0；删除一个 required 字段后 drift 检查必须失败，恢复后再通过。

- [ ] **步骤 5：提交**

  ```bash
  git add packages scripts apps/desktop/src/generated apps/desktop-core/src/generated sidecar/ibreeze/generated tests/contract
  git commit -m "feat(contracts): add generated schema pipeline"
  ```

**完成标准：** CI 能机械阻止手写 DTO 和契约漂移；Schema 编译失败时不会留下半生成文件。

### P0-T03：建立 CI、覆盖率和供应链门禁

**依赖：** P0-T01、P0-T02。

**文件：**

- 创建：`.github/workflows/{contracts,desktop,sidecar,backend,e2e,security,release}.yml`
- 创建：`scripts/check-coverage-exclusions.py`、`scripts/check-lockfiles.sh`
- 修改：各应用测试、lint、typecheck script

**接口：** 所有 job 使用锁文件安装；PR 必须通过 contract drift、格式化、静态检查、单元测试、100% 覆盖率和 secret scan。Release job 只消费已经通过的 commit SHA。

- [ ] **步骤 1：写 CI 配置静态失败测试**

  `tests/contract/test_ci_policy.py` 必须断言每个应用存在 lint/typecheck/test:coverage job，且 workflow 中没有 `continue-on-error:true`、浮动 action tag 或跳过覆盖率参数。

- [ ] **步骤 2：实现矩阵和缓存**

  Node 使用 `npm ci`，Rust 使用 `--locked`，Python 使用 `uv sync --frozen`；缓存 key 必须包含对应锁文件 SHA。

- [ ] **步骤 3：实现覆盖率排除审计**

  `coverage-exclusions.yml` 每项固定含 `path/reason/design_reference/approved_by`；脚本拒绝目录级通配、普通业务分支和空理由。

- [ ] **步骤 4：本地运行 CI 等价命令**

  ```bash
  bash scripts/check-lockfiles.sh
  python3 scripts/check-coverage-exclusions.py
  bash scripts/check-contract-drift.sh
  bash scripts/verify-all.sh
  ```

  预期：全部退出 0；任意移除一个测试 job 时 `test_ci_policy.py` 失败。

- [ ] **步骤 5：提交**

  ```bash
  git add .github scripts tests/contract coverage-exclusions.yml apps sidecar
  git commit -m "ci: enforce contracts tests and coverage"
  ```

**完成标准：** 主分支不能合入生成漂移、未锁依赖、静态检查失败或覆盖率不足的提交。

### P0-T04：验证 Sidecar 打包和内置 Runtime Assets

**依赖：** P0-T01、P0-T03。

**文件：**

- 创建：`sidecar/build/ibreeze-sidecar.spec`
- 创建：`sidecar/ibreeze/runtime_assets.py`
- 创建：`apps/desktop-core/resources/runtime-assets.v1.json`
- 创建：`tests/integration/test_runtime_assets.py`
- 修改：`docs/打包验证记录.md`、`docs/部署文档.md`

**接口：** 安装包必须包含固定 ONNX 模型 `intfloat/multilingual-e5-small`、tokenizer 和 config；manifest 固定相对路径、size、SHA-256。运行时禁止联网下载模型。

- [ ] **步骤 1：写损坏资源失败测试**

  测试覆盖缺文件、size 不符、SHA 不符、路径逃逸和有效 manifest；前四项必须返回稳定诊断代码并拒绝索引。

- [ ] **步骤 2：实现 manifest 校验器和只读映射**

  ```python
  class RuntimeAssetVerifier:
      def verify(self, root: Path, manifest: RuntimeAssetManifest) -> tuple[VerifiedAsset, ...]: ...
  ```

  校验顺序固定为规范路径、普通文件、size、SHA；不得跟随离开资源根的 symlink。

- [ ] **步骤 3：构建 PyInstaller arm64 Sidecar**

  ```bash
  uv run --directory sidecar pyinstaller build/ibreeze-sidecar.spec --clean --noconfirm
  file sidecar/dist/ibreeze-sidecar
  ```

  预期：Mach-O arm64，运行不依赖系统 Python。

- [ ] **步骤 4：真机验证 ONNX 与 LanceDB**

  打包产物必须在无 Python 的干净 macOS arm64 机器完成一次 384 维 embedding 和 LanceDB insert/query；记录输入 SHA、向量维数、命中 id、耗时和产物签名。

- [ ] **步骤 5：提交**

  ```bash
  git add sidecar apps/desktop-core/resources tests/integration docs/打包验证记录.md docs/部署文档.md
  git commit -m "build(sidecar): verify packaged runtime assets"
  ```

**完成标准：** 签名打包环境可真实加载 ONNX、tokenizer、SQLite JSON1/FTS5 和 LanceDB；损坏资源不会降级为联网下载。

### P0 阶段出口

- [ ] 四端从锁文件构建成功。
- [ ] Schema 生成连续两次无差异，故意漂移会阻断。
- [ ] 手写源码覆盖率门禁已经在 CI 生效。
- [ ] Sidecar arm64 打包、ONNX 推理、LanceDB 往返和 SQLite 能力探测有真机证据。
- [ ] 独立 Review 确认实现符合固定进程边界、非目标清单和后台数据边界。

---

## 4. P1：中心后台认证、用户与目录发布

### P1-T01：PostgreSQL、SQLAlchemy 与 Alembic 基线

**依赖：** P0-T01、P0-T03。

**文件：**

- 创建：`apps/backend-api/src/ibreeze_backend/{config.py,db/session.py,db/base.py}`
- 创建：`apps/backend-api/migrations/env.py`
- 创建：`apps/backend-api/migrations/versions/0001_users_tokens_idempotency.py`
- 创建：`apps/backend-api/tests/integration/test_migrations.py`

**接口：** 迁移必须逐字实现设计方案 G.3、G.4；测试数据库固定 PostgreSQL 16 Testcontainer，禁止 SQLite 替代。

- [ ] **步骤 1：写空库升级和重复升级失败测试**

  测试从空库执行 `alembic upgrade head`，断言 users、token family、tokens、idempotency 表、索引和保护管理员 Trigger；初始运行应因迁移不存在而失败。

- [ ] **步骤 2：实现 Async Engine 和迁移**

  Engine 固定 `pool_size=20/max_overflow=20/pool_timeout=10/pool_recycle=1800`，连接设置三个 timeout；API 启动只检查 Alembic head，不自动迁移。

- [ ] **步骤 3：实现默认保护管理员种子**

  迁移用设计方案 G.2 Argon2id 参数创建 `admin/admin123456`，发现同名非保护账号时迁移失败，已存在正确保护账号时幂等通过。

- [ ] **步骤 4：验证迁移**

  ```bash
  uv run --directory apps/backend-api pytest tests/integration/test_migrations.py -v
  uv run --directory apps/backend-api alembic upgrade head
  uv run --directory apps/backend-api alembic check
  ```

  预期：PASS；第二次 upgrade 无 DDL 变化。

- [ ] **步骤 5：提交**

  ```bash
  git add apps/backend-api README.md docs/部署文档.md
  git commit -m "feat(backend-db): add auth schema and migrations"
  ```

**完成标准：** 空库可重复部署，保护管理员约束由数据库和业务层双重执行。

### P1-T02：认证、Token family 和离线票据

**依赖：** P1-T01、P0-T02。

**文件：**

- 创建：`apps/backend-api/src/ibreeze_backend/auth/{models.py,schemas.py,passwords.py,tokens.py,service.py,router.py,keys.py}`
- 创建：`apps/backend-api/tests/auth/{test_register.py,test_login.py,test_refresh.py,test_password.py,test_keys.py}`
- 创建：`apps/backend-api/scripts/export_openapi.py`
- 修改：`packages/contracts/openapi.json`

**产生接口：** 设计方案 G.11 的 11 个认证端点；Access claims 固定含 `pwd_change_required`；应用 normal bundle、受限改密 bundle、管理员 Cookie 三种响应必须是三个显式 Pydantic DTO。

- [ ] **步骤 1：写认证状态矩阵失败测试**

  覆盖注册、重复邮箱、大小写邮箱、错误密码、锁定、disabled、受限改密、normal login、refresh rotation、consumed replay、logout、logout-all、改密撤销和 audience 混用。

- [ ] **步骤 2：实现密码与登录事务**

  ```python
  async def authenticate(credentials: LoginRequest, device_id: UUID, audience: Audience) -> LoginResult: ...
  async def rotate_refresh(raw_token: SecretStr, device_id: UUID) -> SessionBundle: ...
  async def change_password(principal: Principal, request: ChangePasswordRequest) -> SessionBundle | AdminSession: ...
  ```

  用户行和 refresh token 行按 G.5 `SELECT FOR UPDATE`；日志上下文禁止持有原始密码或 Token。

- [ ] **步骤 3：实现 Ed25519 JWT 与签名 keyset**

  Header 只接受 `alg=EdDSA/typ=JWT/kid`；Offline ticket claims 与 F.8 完全一致。Auth keyset 用 Catalog key 对 RFC 8785 字节签名。

- [ ] **步骤 4：实现限速和 Problem Details**

  Nginx 与应用层分别测试 IP 限速、用户失败计数和统一错误映射；登录错误不得区分用户不存在与密码错误。

- [ ] **步骤 5：运行验证**

  ```bash
  uv run --directory apps/backend-api pytest tests/auth -v --cov=ibreeze_backend.auth --cov-branch --cov-fail-under=100
  uv run --directory apps/backend-api python scripts/export_openapi.py
  bash scripts/check-contract-drift.sh
  ```

  预期：全部 PASS，OpenAPI 无未提交漂移。

- [ ] **步骤 6：提交**

  ```bash
  git add apps/backend-api packages/contracts README.md docs/部署文档.md docs/用户手册.md
  git commit -m "feat(auth): implement online and offline sessions"
  ```

**完成标准：** Refresh replay 撤销 family；受限改密登录不能获得 OfflineSessionTicket；管理员与应用 audience 不能混用。

### P1-T03：后台用户管理

**依赖：** P1-T02。

**文件：**

- 创建：`apps/backend-api/src/ibreeze_backend/users/{schemas.py,repository.py,service.py,router.py}`
- 创建：`apps/backend-api/tests/users/test_user_admin.py`

**产生接口：** 设计方案 G.12 全部路由；PATCH 字段白名单按 user_type 分支；DELETE、reset-password、revoke-sessions 都写 admin audit。

- [ ] **步骤 1：写保护管理员和字段矩阵失败测试**

  表驱动覆盖 admin/app_user 创建字段、未知字段、email/username 冲突、乐观锁、保护管理员删除/禁用/改名/改类型、重置密码和会话撤销。

- [ ] **步骤 2：实现 Repository 与 Service**

  Repository 只提供按 version 更新原语；Service 执行字段矩阵、Token 撤销和审计事务，不允许 router 拼业务逻辑。

- [ ] **步骤 3：实现 cursor 列表**

  排序固定 `created_at DESC,id DESC`，filter 只接受 `user_type/status/identifier`，limit 1..200，未知过滤字段 422。

- [ ] **步骤 4：验证并提交**

  ```bash
  uv run --directory apps/backend-api pytest tests/users -v --cov=ibreeze_backend.users --cov-branch --cov-fail-under=100
  git add apps/backend-api packages/contracts docs
  git commit -m "feat(users): add protected user administration"
  ```

**完成标准：** 保护管理员在 API 和数据库层均不可破坏；所有管理写操作可由 request_id 追溯。

### P1-T04：目录实体、版本和兼容规则

**依赖：** P1-T01、P1-T03。

**文件：**

- 创建：`apps/backend-api/migrations/versions/0002_catalog_resources.py`
- 创建：`apps/backend-api/src/ibreeze_backend/catalog/{models.py,schemas.py,repository.py,service.py,validator.py,router.py}`
- 创建：`apps/backend-api/src/ibreeze_backend/compatibility/{schemas.py,evaluator.py,router.py}`
- 创建：`apps/backend-api/tests/catalog/{test_crud.py,test_validation.py,test_immutability.py,test_compatibility.py}`

**产生接口：** 设计方案 G.13 中 Agent、AgentVersion、Model、Provider、两类 ModelBinding、Skill metadata 和 CompatibilityRule 的完整管理路由。状态只允许 `draft → validated → published`。

- [ ] **步骤 1：写目录 DDL 和状态机失败测试**

  测试逐表比对 G.6 列、CHECK、UNIQUE 和 Trigger；验证 published 父资源、子版本及 binding 的 UPDATE/DELETE/INSERT 均由数据库拒绝。

- [ ] **步骤 2：实现 Alembic 迁移与 ORM**

  ORM 字段名、长度和 nullable 必须与 G.6 一致；多态发布引用只在发布 Service 内解析，禁止建立无效通用 ORM 外键。

- [ ] **步骤 3：实现目录校验器**

  ```python
  class CatalogValidator:
      async def validate_revision(self, resource_type: ResourceType, resource_id: UUID) -> ValidationReport: ...
      async def validate_selection(self, selection: CatalogSelection) -> ValidationReport: ...
  ```

  覆盖 SemVer、区间重叠、Agent/Model binding、context window、Provider URL/SSRF、request_defaults、network_domains 和兼容规则引用。

- [ ] **步骤 4：实现草稿复制和乐观锁**

  `revisions` 只复制 published 源；新 revision 从 1 递增，连同子版本及 binding 在单事务复制。PATCH 改发布字段必须退回 draft。

- [ ] **步骤 5：验证**

  ```bash
  uv run --directory apps/backend-api pytest tests/catalog -v --cov=ibreeze_backend.catalog --cov=ibreeze_backend.compatibility --cov-branch --cov-fail-under=100
  uv run --directory apps/backend-api alembic upgrade head
  uv run --directory apps/backend-api alembic check
  ```

  预期：全部 PASS；直接 SQL 修改 published 行失败。

- [ ] **步骤 6：提交**

  ```bash
  git add apps/backend-api packages/contracts docs
  git commit -m "feat(catalog): add versioned resources and compatibility"
  ```

**完成标准：** 管理员只能修改 draft/validated；客户端永远引用具体 revision/version id，不读取 latest draft。

### P1-T05：Skill ZIP 校验、签名和对象存储

**依赖：** P1-T04。

**文件：**

- 创建：`apps/backend-api/src/ibreeze_backend/skills/{manifest.py,archive.py,signing.py,storage.py,service.py,router.py}`
- 创建：`apps/backend-api/src/ibreeze_backend/storage/s3.py`
- 创建：`apps/backend-api/tests/skills/{test_archive.py,test_manifest.py,test_signing.py,test_storage_failure.py}`
- 创建：`tests/fixtures/skills/{valid,traversal,symlink,duplicate,hash_mismatch}/`

**产生接口：** `POST/GET/DELETE /admin/api/v1/skills/{id}/versions` 与公开 package 下载接口。S3 object key 固定为 G.8 格式。

- [ ] **步骤 1：写恶意 ZIP 失败测试**

  覆盖 50 MiB、1000 entry、200 MiB 解压上限、absolute path、`..`、symlink、hardlink、device、重复规范路径、未声明脚本、manifest/file hash 不一致和 ZIP bomb。

- [ ] **步骤 2：实现流式临时文件和 archive 校验**

  读取 ZIP central directory 前先限制上传字节；每个条目逐个统计压缩/解压大小，不把整个包读入内存。任何失败删除 temp file。

- [ ] **步骤 3：实现 manifest schema 与签名**

  使用 `packages/contracts/skill-manifest.v1.schema.json` 校验；按 G.8 生成 `object_sha256/content_sha256` 和 Ed25519 签名输入。私钥只从 `0400` secret file 读取一次并置于零化容器。

- [ ] **步骤 4：实现 S3 两阶段写入与 GC**

  数据库提交失败保留对象供 24 小时 GC；GC 删除前再次查询引用。下载响应固定 `ETag=object_sha256`、`Content-Length` 和 `application/zip`。

- [ ] **步骤 5：用 MinIO Testcontainer 验证**

  ```bash
  uv run --directory apps/backend-api pytest tests/skills -v --cov=ibreeze_backend.skills --cov-branch --cov-fail-under=100
  ```

  预期：有效包上传、下载、重新验签一致；所有恶意 fixture 被明确错误码拒绝。

- [ ] **步骤 6：提交**

  ```bash
  git add apps/backend-api packages/contracts tests/fixtures docs
  git commit -m "feat(skills): validate sign and distribute packages"
  ```

**完成标准：** 无路径逃逸、解压炸弹、未签名包或孤儿数据库引用；对象存储失败不产生已发布版本。

### P1-T06：Catalog Release、Manifest 与紧急禁用

**依赖：** P1-T04、P1-T05。

**文件：**

- 创建：`apps/backend-api/migrations/versions/0003_catalog_releases.py`
- 创建：`apps/backend-api/src/ibreeze_backend/releases/{manifest.py,signing.py,publisher.py,emergency.py,router.py,gc.py}`
- 创建：`apps/backend-api/tests/releases/{test_publish.py,test_concurrency.py,test_manifest.py,test_emergency.py,test_key_rotation.py}`

**产生接口：** G.13 的 manifest、keys、release、resource、目录查询、publish、emergency disable 和 audit API。

- [ ] **步骤 1：写发布原子性与并发失败测试**

  两个并发 publisher 只能取得连续不重复 sequence；在 S3 upload、item insert、父资源 publish、latest pointer 任一步注入失败并断言 G.9 对应事实状态。

- [ ] **步骤 2：实现 RFC 8785 Manifest builder**

  ```python
  async def build_manifest(selection: CatalogSelection, sequence: int) -> SignedManifest: ...
  ```

  输出必须包含 release id/sequence、minimum client version、全量资源 hash、signing key id 和 signature；相同输入字节完全一致。

- [ ] **步骤 3：实现发布事务**

  使用 `pg_advisory_xact_lock(hashtext('catalog-release'))` 与 REPEATABLE READ；严格按 G.9 第 1–9 步执行，不允许 router 分段提交。

- [ ] **步骤 4：实现紧急禁用流**

  sequence 单调，payload schema 固定；客户端状态算法的服务端测试 fixture 必须覆盖 disable、higher enable、lower replay 和不同 resource version。

- [ ] **步骤 5：实现 Catalog keyset 轮换测试**

  验证旧 key 签新 keyset、新旧双签、新 signer release、旧公钥验证历史 release；删除旧公钥必须失败。

- [ ] **步骤 6：验证并提交**

  ```bash
  uv run --directory apps/backend-api pytest tests/releases -v --cov=ibreeze_backend.releases --cov-branch --cov-fail-under=100
  git add apps/backend-api packages/contracts docs
  git commit -m "feat(releases): publish signed catalog snapshots"
  ```

**完成标准：** 已发布 release/item/resource 不可变；S3 latest 指针失败不影响 PostgreSQL 事实；紧急禁用不可回退。

### P1-T07：REST 通用中间件、幂等与审计

**依赖：** P1-T02、P1-T03、P1-T06。

**文件：**

- 创建：`apps/backend-api/src/ibreeze_backend/api/{middleware.py,errors.py,pagination.py,idempotency.py}`
- 创建：`apps/backend-api/src/ibreeze_backend/observability/{audit.py,logging.py,metrics.py}`
- 创建：`apps/backend-api/tests/api/{test_problem_details.py,test_idempotency.py,test_pagination.py,test_redaction.py}`

**接口：** G.10 envelope、RFC 9457、cursor、If-Match、Idempotency-Key 和 request_id 规则。

- [ ] **步骤 1：写横切行为失败测试**

  对一个代表性 GET/PATCH/POST/DELETE 测试 content type、request id、字段错误、未知异常脱敏、cursor 篡改、同 key 同请求重放、同 key 异请求冲突和 processing 超时。

- [ ] **步骤 2：实现 middleware 顺序**

  顺序固定为 request id → access log context → auth → rate limit → idempotency → router → problem mapping → metrics；密码和 Token 路由不得进入响应缓存。

- [ ] **步骤 3：实现 admin audit append-only writer**

  Audit 与业务事务同 session 提交；before/after 先执行字段白名单和正文清除。未知异常只记录脱敏堆栈，不进入 HTTP body。

- [ ] **步骤 4：验证并提交**

  ```bash
  uv run --directory apps/backend-api pytest tests/api -v --cov=ibreeze_backend.api --cov=ibreeze_backend.observability --cov-branch --cov-fail-under=100
  git add apps/backend-api docs
  git commit -m "feat(backend-api): enforce transport and audit policy"
  ```

**完成标准：** 所有后台路由行为一致；敏感认证响应不被缓存或记录；未知错误不泄露 SQL、路径或堆栈。

### P1-T08：后台健康、容器与部署基线

**依赖：** P1-T01–P1-T07。

**文件：**

- 创建：`deploy/compose.yml`、`deploy/.env.example`、`deploy/nginx.conf`
- 创建：`apps/backend-api/Dockerfile`、`apps/admin-web/Dockerfile`
- 创建：`apps/backend-api/src/ibreeze_backend/api/health.py`
- 创建：`tests/integration/test_backend_compose.py`
- 修改：`docs/部署文档.md`

**产生接口：** `/health/live`、`/health/ready`、私网 `/metrics`；生产容器约束完全采用 K.10–K.12。

- [ ] **步骤 1：写健康矩阵失败测试**

  分别断开 PostgreSQL、设置错误 Alembic head、移除 bucket、破坏 Auth/Catalog key pair、删除保护管理员；ready 必须 503 且仅返回稳定组件码。

- [ ] **步骤 2：实现容器与 Nginx**

  镜像使用 immutable digest、non-root、read-only rootfs、cap_drop ALL；只 Nginx 暴露 443，metrics 不发布宿主端口。

- [ ] **步骤 3：实现迁移 Job 和备份顺序**

  Compose API 不自动迁移；部署脚本按数据库备份 → Alembic Job → API ready → Web → Nginx 切换 → 冒烟执行。

- [ ] **步骤 4：运行集成验证**

  ```bash
  docker compose -f deploy/compose.yml config
  python3 -m pytest tests/integration/test_backend_compose.py -v
  ```

  预期：配置无未解析变量，健康故障矩阵全部 PASS。

- [ ] **步骤 5：提交**

  ```bash
  git add deploy apps/backend-api apps/admin-web tests/integration docs/部署文档.md README.md
  git commit -m "build(backend): add hardened compose deployment"
  ```

**完成标准：** 中心后台可独立部署，且数据库中不存在任何桌面业务表。

### P1 阶段出口

- [ ] 所有 G.11–G.13 REST 端点进入 OpenAPI 且 Schemathesis 无未处理 5xx。
- [ ] PostgreSQL 迁移从空库和上一 migration head 均可升级。
- [ ] 保护管理员、Token replay、published immutability、Skill 恶意包和发布并发测试通过。
- [ ] Docker Compose 冷启动后 live/ready/登录/目录/Skill 冒烟通过。
- [ ] 数据库 Schema 审核确认没有 company/department/employee/task/conversation/workspace 表。

---

## 5. P2：Rust Desktop Core、Profile、IPC 与目录同步

### P2-T01：Tauri 壳、Capability 与七个 Command

**依赖：** P0-T01、P0-T03。

**文件：**

- 创建：`apps/desktop-core/tauri.conf.json`、`capabilities/main.json`
- 创建：`apps/desktop-core/src/commands/{rpc.rs,workspace.rs,external.rs,diagnostics.rs,updater.rs,mod.rs}`
- 创建：`apps/desktop-core/tests/capabilities.rs`

**产生接口：** K.9 的七个自定义 Command；WebView 不获得外部写执行、shell、fs、http、process、clipboard-write 或原生 updater 插件权限。

- [ ] **步骤 1：写 capability 失败测试**

  解析 Tauri capability JSON，断言命令集合精确等于七项；发现任何外部写执行Command、多一项或通配permission必须失败。

- [ ] **步骤 2：实现最小 Command 路由**

  每个Command先验证 `window_session_id` 和主窗口label。`rpc_request`读取生成的 `ownership.v1.json`：`rust_core` 方法调用Rust handler，`sidecar` 方法仅在Profile已打开且IPC session有效时转发UDS，`supervisor_only` 方法拒绝WebView；其余Command再转交对应service。本任务使用 `NotInitialized` 内部错误，不创建业务假响应。

- [ ] **步骤 3：应用生产 CSP**

  CSP 必须逐项等于 K.9；构建测试解析最终配置，拒绝 `unsafe-eval`、`*` 和任意网络 origin。

- [ ] **步骤 4：验证并提交**

  ```bash
  cargo nextest run --manifest-path apps/desktop-core/Cargo.toml --test capabilities
  cargo clippy --manifest-path apps/desktop-core/Cargo.toml --all-targets -- -D warnings
  git add apps/desktop-core docs
  git commit -m "feat(desktop-core): restrict tauri command surface"
  ```

**完成标准：** WebView 无法绕过 Rust 直接访问系统资源或后台 HTTP。

### P2-T02：Profile 发现、目录权限与 Keychain session bundle

**依赖：** P2-T01、P1-T02 契约。

**文件：**

- 创建：`apps/desktop-core/src/profile/{origin.rs,metadata.rs,layout.rs,mod.rs}`
- 创建：`apps/desktop-core/src/auth/{keychain.rs,session_bundle.rs,offline_ticket.rs}`
- 创建：`apps/desktop-core/tests/{profile_security.rs,keychain_rotation.rs,offline_ticket.rs}`

**产生接口：** `ProfileLocator::from_identity(canonical_origin, app_user_id)`、`SessionBundleStore::{load,replace,delete}`、`OfflineTicketVerifier::verify`。

- [ ] **步骤 1：写 origin 与目录逃逸失败测试**

  覆盖 userinfo/path/query/fragment、Unicode domain、默认端口、HTTP 非开发 origin、目录 basename 篡改、meta id 不一致和宽权限修复。

- [ ] **步骤 2：实现 canonical origin 和 directory id**

  按 F.9 使用 `lowercase-base32(SHA-256(origin || 0x00 || app_user_id))`，不截断；禁止调用方提供目录名。

- [ ] **步骤 3：实现 profile-meta 原子更新**

  先写同目录 temp、`sync_all`、chmod 0600、rename、fsync parent；读取只用于发现，打开 Profile 后必须由 Sidecar 再比对 local_profile。

- [ ] **步骤 4：实现单 Keychain item 轮换**

  value 固定为 F.9 五字段 JSON；先从Keychain读取并验证旧bundle，旧值损坏立即报 `KEYCHAIN_BUNDLE_CORRUPT`；再验证新bundle并执行一次 `SecItemUpdate` 或首次 `SecItemAdd`。调用失败后必须重新读取Keychain：等于旧值/仍不存在则返回原错误，等于新值则按响应丢失后的成功处理，第三种值或损坏JSON返回同一损坏错误且禁止打开Profile；不得以写前内存副本代替读回。在线签发的新bundle最终未确认保存时，使用内存Access Token最佳努力撤销新family后zeroize。测试覆盖旧值、新值、缺失值和损坏值四种读回分支、撤销成功/网络失败、signed-out `auth.logout` 仅清除本次损坏item的恢复路径。

- [ ] **步骤 5：实现 Offline Ticket 校验**

  校验 alg/kid/signature/issuer/audience/sub/device/origin/iat/exp 和 60 秒 skew；公钥缺失、过期或 Catalog keyset 签名无效返回 `OFFLINE_TICKET_INVALID`。

- [ ] **步骤 6：验证并提交**

  ```bash
  cargo nextest run --manifest-path apps/desktop-core/Cargo.toml profile_security keychain_rotation offline_ticket
  git add apps/desktop-core README.md docs/用户手册.md
  git commit -m "feat(profile): add isolated profile and keychain sessions"
  ```

**完成标准：** 不读取业务 SQLite即可安全列出离线 Profile；Token 明文不进入数据库、WebView或日志。

### P2-T03：Sidecar Supervisor、UDS framing 与握手

**依赖：** P2-T01、P2-T02、P0-T02。

**文件：**

- 创建：`apps/desktop-core/src/process/{sidecar.rs,registry.rs,signals.rs}`
- 创建：`apps/desktop-core/src/ipc/{framing.rs,client.rs,handshake.rs,router.rs}`
- 创建：`apps/desktop-core/tests/{framing.rs,handshake.rs,supervisor.rs}`
- 创建：`tests/fixtures/fake-sidecar/`

**产生接口：** F.3–F.5 的 Sidecar 生命周期和 `system.handshake/health/shutdown`；4-byte big-endian frame；单连接、单对象、16 MiB 上限。

- [ ] **步骤 1：写恶意 frame 与握手失败测试**

  覆盖 0 长度、16 MiB+1、截断、非法 UTF-8、顶层数组、batch JSON-RPC、错误 nonce、proof replay、第二连接、旧 ipc session，以及handshake初始化10分钟超时；超时测试使用fake clock且断言Sidecar进程组被清理。

- [ ] **步骤 2：实现启动协议**

  Rust 创建 0700 run dir、0600 socket、32-byte startup token，经 stdin 写 base64 一次后关闭；Sidecar proof 按 F.3 HMAC 公式校验。fake-sidecar严格实现握手响应 `{ipc_session_id,protocol_version,profile_status:'ready',database_status:'ready',migration_version}` 和F.5 health枚举，用于先验证Rust监督逻辑；P3-T01/P3-T02必须由真实数据库实现同一契约。

- [ ] **步骤 3：实现心跳和重启限流**

  5 秒 health、3 秒 timeout、连续 3 次 lost、60 秒最多重启 3 次；第 4 次进入 diagnostics。测试使用 fake clock，不能 sleep 真实 60 秒。

- [ ] **步骤 4：实现进程组清理**

  正常 shutdown 等 10 秒，随后 SIGTERM 5 秒、SIGKILL；启动恢复时校验 PID、PGID、start time 和 executable path，防止 PID reuse。

- [ ] **步骤 5：验证并提交**

  ```bash
  cargo nextest run --manifest-path apps/desktop-core/Cargo.toml framing handshake supervisor
  git add apps/desktop-core tests/fixtures docs/部署文档.md
  git commit -m "feat(ipc): supervise authenticated sidecar channel"
  ```

**完成标准：** Sidecar 丢失后不会遗留 CLI 进程组；伪造/重放握手和恶意 frame 被拒绝且不崩溃。

### P2-T04：Backend HTTP Client、认证刷新与 Profile 打开

**依赖：** P2-T02、P2-T03、P1-T02。

**文件：**

- 创建：`apps/desktop-core/src/auth/{backend_client.rs,refresh.rs,login.rs}`
- 创建：`apps/desktop-core/src/auth/local_rpc.rs`
- 创建：`apps/desktop-core/src/profile/open.rs`
- 创建：`apps/desktop-core/tests/{backend_client.rs,auth_flow.rs}`
- 创建：`apps/desktop-core/tests/auth_local_rpc.rs`

**产生接口：** J.14八个Rust本地方法 `backend.validateOrigin`、`auth.register`、`auth.login`、`auth.changePassword`、`auth.logout`、`auth.listOfflineProfiles`、`auth.openProfile`、`auth.closeProfile`；F.7 timeout/redirect/body上限；只有完整认证与Profile校验成功后才启动Sidecar。

- [ ] **步骤 1：写 HTTP 安全失败测试**

  覆盖非 HTTPS、跨 origin redirect、4 次 redirect、16 MiB+1 body、connect timeout、request timeout、错误 audience 和 Token refresh 只尝试一次。

- [ ] **步骤 2：实现 reqwest client**

  使用 Rust 内存 Access Token；Refresh/Offline bundle 只由 Keychain service 获取。错误响应按 Problem Details code 映射，不以 message 做判断。

- [ ] **步骤 3：实现Rust本地RPC与所有权门禁**

  八个方法逐字采用J.14 params/response；密码字段使用 `secrecy::SecretString` 并在请求完成后zeroize。Rust本地写方法只在内存合并同key的in-flight请求，完成即删除key和结果，禁止写入Sidecar幂等表或缓存Token响应。测试证明这些方法不进入UDS，Sidecar方法在未打开Profile时返回 `STATE_TRANSITION_INVALID`，Supervisor方法返回 `METHOD_NOT_ALLOWED`。

- [ ] **步骤 4：实现登录状态机**

  ```text
  signed_out → authenticating → password_change_required | catalog_syncing
  catalog_syncing → online_profile_open | failed
  signed_out → offline_verifying → offline_profile_open | failed
  ```

  受限登录Refresh只在zeroize内存。顺序固定为REST认证/Refresh→响应与票据验证→单次Keychain更新及故障后读回确认→Catalog同步验签→Profile meta原子更新→启动Sidecar→握手确认数据库/迁移/local_profile均ready→首次health为healthy；任何失败关闭Sidecar且不返回opened。P2任务以严格fake-sidecar完成Rust状态机契约测试；P3阶段出口必须再以真实Sidecar重复同一测试，生产构建不得用fake实现返回opened。

- [ ] **步骤 5：实现退出与关闭差异**

  `auth.closeProfile`只关闭Sidecar与内存Access Token并保留bundle；`auth.logout`先关闭Profile，再在线撤销family并删除bundle。离线logout删除bundle并返回 `revoked_family=false`，UI展示远端未即时撤销。

- [ ] **步骤 6：验证并提交**

  ```bash
  cargo nextest run --manifest-path apps/desktop-core/Cargo.toml backend_client auth_flow auth_local_rpc
  git add apps/desktop-core docs/用户手册.md README.md
  git commit -m "feat(auth-client): open online and offline profiles"
  ```

**完成标准：** 后台在线时不能主动离线；Refresh失败退出在线态但不删除本地业务数据；Rust本地方法不出现在Sidecar请求日志；本任务证明Rust侧协议，真实Sidecar的Profile ready集成门禁在P3阶段出口完成。

### P2-T05：Catalog 下载、签名校验与原子缓存交付

**依赖：** P2-T04、P1-T06。

**文件：**

- 创建：`apps/desktop-core/src/security/{catalog_keys.rs,catalog_verify.rs}`
- 创建：`apps/desktop-core/src/auth/catalog_client.rs`
- 创建：`apps/desktop-core/tests/{catalog_verify.rs,catalog_sync.rs}`
- 创建：`tests/fixtures/catalog/`

**产生接口：** Rust 验签后的 `VerifiedCatalogRelease`，只允许该类型进入 Sidecar `catalog.sync`；普通 JSON 不得构造此类型。

- [ ] **步骤 1：写签名和回滚失败测试**

  fixture 覆盖未知 key、篡改 canonical bytes、资源 hash 错、父子引用错、低 sequence、最低客户端过高、紧急禁用回退和旧 key 验历史 release。

- [ ] **步骤 2：实现 trust keyset 轮换**

  新 keyset 至少一个签名由已信任 key 验证；新增 key 原子缓存，retired key 永不删除。

- [ ] **步骤 3：实现 manifest/resource 流式下载**

  限制普通 body 16 MiB；Skill 使用 10 分钟流式路径。先验 manifest 签名，再按 id/hash 下载资源，全部通过才构造 Verified 类型。

- [ ] **步骤 4：将已验证目录发送 Sidecar**

  `catalog.sync` 请求含 release id/sequence、manifest path、resource directory 和 Rust verification receipt SHA；Sidecar仍需二次验证本地文件 hash 和关系。

- [ ] **步骤 5：验证并提交**

  ```bash
  cargo nextest run --manifest-path apps/desktop-core/Cargo.toml catalog_verify catalog_sync
  git add apps/desktop-core tests/fixtures docs
  git commit -m "feat(catalog-client): verify signed catalog releases"
  ```

**完成标准：** 任何网络失败或验证失败保留上一 active release；前端和 Sidecar看不到未验签目录。

### P2-T06：Workspace Grant、只读选择器与外部动作

**依赖：** P2-T01、P2-T02。

**文件：**

- 创建：`apps/desktop-core/src/security/{bookmarks.rs,path_policy.rs,external_write.rs}`
- 创建：`apps/desktop-core/src/commands/{workspace.rs,external.rs}`（`external.rs`仅实现只读系统打开 `external_open`）
- 创建：`apps/desktop-core/src/ipc/reverse/external_write.rs`
- 创建：`apps/desktop-core/tests/{path_policy.rs,external_write.rs}`

**产生接口：** `workspace_select` 返回 opaque grant id；`readonly_file_select` 返回只读 grant；F.4内部反向RPC `host.externalWrite.execute`，不注册WebView Command。

- [ ] **步骤 1：写路径与 symlink 攻击失败测试**

  覆盖其他 Profile/公司/职员、`.ssh/.gnupg/.aws/.kube/Keychains`、file credential、symlink swap、case normalization、同路径跨公司 active grant、grant stale、响应丢失后同approval重试以及目标处于第三种状态时拒绝。

- [ ] **步骤 2：实现 Security Scoped Bookmark 生命周期**

  Bookmark 原始字节只由 Rust 保管；Sidecar只得到 grant id和规范路径。每次使用重新 resolve并比对 file id，stale 时拒绝运行。

- [ ] **步骤 3：实现单次外部写执行器**

  严格校验 F.4 params、当前 `ipc_session_id`、operation、canonical target、old hash、staging相对路径/new content hash/size和expiry；为单一目标生成临时Seatbelt权限。执行后先销毁staging和临时权限，再返回绑定全部字段的receipt及RFC8785 SHA-256；Rust不读取SQLite、不改变approval状态，Sidecar在P6-T05校验receipt后消费。

- [ ] **步骤 4：验证并提交**

  ```bash
  cargo nextest run --manifest-path apps/desktop-core/Cargo.toml path_policy external_write
  git add apps/desktop-core docs/用户手册.md
  git commit -m "feat(workspace): enforce grants and one-shot writes"
  ```

**完成标准：** WebView、Sidecar 和模型均不能用任意绝对路径伪造授权；审批不可重复消费。

### P2-T07：CLI Egress Broker 与 Credential HTTP Broker

**依赖：** P2-T03、P2-T05。

**文件：**

- 创建：`apps/desktop-core/src/security/{egress_proxy.rs,domain_policy.rs,credential_broker.rs}`
- 创建：`apps/desktop-core/tests/{egress_proxy.rs,credential_broker.rs,ssrf.rs}`

**产生接口：** 每 Run loopback CONNECT proxy；Sidecar 反向 RPC 只允许 `credential.http.start/cancel/probe`、`host.externalWrite.execute` 和两个 process notification，集合逐字来自 `reverse-methods.v1.json`。

- [ ] **步骤 1：写代理绕过和 SSRF 失败测试**

  覆盖无 auth、错误 token、非 CONNECT、80/其他端口、IP literal、跨域、通配多 label、DNS rebinding、private/loopback/link-local、61 次/分钟和第 33 个并发 tunnel。

- [ ] **步骤 2：实现 per-run CONNECT proxy**

  `EgressLease` 固定包含 run id、port、zeroizing token、normalized allowlist 和 cancel handle；关闭时停止 listener、关闭 tunnels、清零 token。

- [ ] **步骤 3：实现 Credential Broker**

  Sidecar请求只含 credential_ref、已验签 Provider id/version、relative path、非认证 headers 和 body。Rust 校验 catalog、从 Keychain取 key、注入 auth、执行 HTTPS，再分 chunk 返还。

- [ ] **步骤 4：真实 CLI 代理兼容探测**

  对锁定的三种 CLI 验证登录探测、模型调用和原生恢复均只通过代理；任一 CLI 忽略 proxy env 时该版本 range 必须 unavailable，禁止放开公网。

- [ ] **步骤 5：验证并提交**

  ```bash
  cargo nextest run --manifest-path apps/desktop-core/Cargo.toml egress_proxy credential_broker ssrf
  git add apps/desktop-core tests/security docs/部署文档.md
  git commit -m "feat(security): broker cli and model network access"
  ```

**完成标准：** CLI 沙箱直接出站失败；Credential 明文只在 Rust 零化内存中短暂存在。

### P2-T08：Updater、诊断导出与桌面打包骨架

**依赖：** P2-T01–P2-T07、P0-T04。

**文件：**

- 创建：`apps/desktop-core/src/updater/{manifest.rs,policy.rs,install.rs}`
- 创建：`apps/desktop-core/src/diagnostics/{bundle.rs,redact.rs}`
- 创建：`apps/desktop-core/tests/{updater.rs,diagnostics.rs}`
- 修改：`apps/desktop-core/tauri.conf.json`

**接口：** K.10.1 更新门禁；诊断包默认本地生成，不上传。

- [ ] **步骤 1：写更新前置条件失败测试**

  active Run、pending approval、最近备份失败、Tauri signature失败、Apple signature失败任一存在时不得安装。

- [ ] **步骤 2：实现更新状态机与恢复入口**

  首次启动 30 秒内 protocol/migration/health 失败进入 recovery，不自动数据库降级；只提供缓存安装包重装与备份恢复。

- [ ] **步骤 3：实现诊断脱敏**

  固定移除 password/authorization/cookie/token/api_key/credential/prompt/message body/绝对 Profile path；测试用 canary secret 断言压缩包不存在原文。

- [ ] **步骤 4：验证并提交**

  ```bash
  cargo nextest run --manifest-path apps/desktop-core/Cargo.toml updater diagnostics
  git add apps/desktop-core docs
  git commit -m "feat(desktop-core): add safe updates and diagnostics"
  ```

**完成标准：** 更新不能在活跃执行中安装；诊断导出无敏感正文且不会自动发送。

### P2 阶段出口

- [ ] 七个WebView Command、八个Rust本地认证/Profile RPC、CSP、window session、Profile、Keychain、Offline Ticket 和 UDS 安全测试通过。
- [ ] Catalog 签名/回滚、Grant/symlink、Egress/SSRF 和 Credential canary 测试通过。
- [ ] Sidecar crash、CLI 进程组清理和 updater 恢复路径通过 fault injection。
- [ ] Rust 手写代码 100% 覆盖，`cargo clippy -D warnings` 通过。

---

## 6. P3：Sidecar 基础设施与本地持久化

### P3-T01：SQLite 固定运行时、迁移与 Profile 打开

**依赖：** P0-T04、P2-T03。

**文件：**

- 创建：`sidecar/ibreeze/persistence/{connection.py,migrator.py,write_queue.py,profile.py}`
- 创建：`sidecar/migrations/20260722000100_profile_catalog.sql`
- 创建：`sidecar/tests/persistence/{test_connection.py,test_migrator.py,test_profile.py}`

**产生接口：** `ProfileDatabase.open(path, identity)`、单写队列、8 读连接池、H.1 migration state machine。

- [ ] **步骤 1：写 SQLite 能力和迁移故障测试**

  覆盖版本不在 `>=3.45,<3.46`、foreign_keys off、缺 JSON1/FTS5、migration hash drift、running 中断、事务 B 失败、pre-upgrade backup失败和 foreign_key_check失败；连接创建、归还、借出时逐次断言 `defer_foreign_keys=0`，注入泄漏时必须回滚、丢弃连接并降级health。

- [ ] **步骤 2：实现连接初始化**

  每连接执行 H.1 PRAGMA；写连接额外 wal_autocheckpoint，单写队列容量固定32并在满时背压。Profile identity 必须与 local_profile 完全匹配；只有迁移完成、identity一致、写队列可接收命令时数据库状态才为ready。

- [ ] **步骤 3：实现三事务迁移器**

  ```python
  async def apply_migration(db: Connection, migration: Migration) -> MigrationResult: ...
  ```

  A 写 running，B `BEGIN IMMEDIATE` 执行与 FK check，C 仅在失败时写 failed；已完成 hash变化拒绝启动。

- [ ] **步骤 4：实现单写协程和优雅 checkpoint**

  写命令全部进入容量32的 bounded asyncio.Queue；退出先拒绝新写、等待当前事务、执行 WAL TRUNCATE。

- [ ] **步骤 5：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/persistence -v --cov=ibreeze.persistence --cov-branch --cov-fail-under=100
  git add sidecar docs/部署文档.md
  git commit -m "feat(sidecar-db): add profile migrations and write queue"
  ```

**完成标准：** migration 中断可安全重跑；不兼容 SQLite 或损坏 Profile 不会被静默打开。

### P3-T02：JSON-RPC Server、Schema 校验与公开方法注册

**依赖：** P3-T01、P0-T02、P2-T03。

**文件：**

- 创建：`sidecar/ibreeze/rpc/{server.py,framing.py,registry.py,context.py,errors.py,schema.py}`
- 创建：`sidecar/tests/rpc/{test_protocol.py,test_registry.py,test_schema.py,test_direction.py}`

**产生接口：** J.14中 `sidecar` 所有权的公开方法注册表；F.3–F.5三个 `supervisor_only` 方法；反向调用白名单。`rust_core` 方法不得在Sidecar注册。

- [ ] **步骤 1：写协议与方法注册失败测试**

  从 `ownership.v1.json` 断言Sidecar registry与 `sidecar` 集合精确一致，并断言所有Rust本地方法缺席；未知方法、方向错误、缺meta、写方法缺idempotency、读方法带key、Schema extra field全部失败。

- [ ] **步骤 2：实现 request pipeline**

  顺序固定 frame parse → JSON-RPC parse → meta/session → method/direction → request schema → command/query dispatch → response schema → frame write。

  `system.handshake` 必须等待P3-T01的ProfileDatabase达到ready并完成identity校验，才返回 `{ipc_session_id,protocol_version,profile_status:'ready',database_status:'ready',migration_version}`；`system.health.database_status`只允许 `ready/migrating/failed`。数据库初始化失败时握手失败并退出，不能仅凭UDS可连接返回ready。

- [ ] **步骤 3：实现错误映射**

  协议错误用标准 code；领域错误统一 `-32000` 与 20 节稳定 code；未知异常只回 `INTERNAL_ERROR/trace_id`。

- [ ] **步骤 4：实现 cursor HMAC**

  cursor 编码排序字段/id并用 Profile随机 key签名；跨 method/company/filter复用统一返回 `VALIDATION_FAILED`。`EVENT_SEQUENCE_INVALID` 只用于 `event.replay` 的未来、缺口或非法 sequence。

- [ ] **步骤 5：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/rpc -v --cov=ibreeze.rpc --cov-branch --cov-fail-under=100
  git add sidecar packages/rpc-schema
  git commit -m "feat(rpc): enforce generated local contracts"
  ```

**完成标准：** WebView不能调用内部编排方法；所有响应在出站前再次通过生成 Schema。

### P3-T03：DomainEvent、Outbox、事件补拉与幂等

**依赖：** P3-T01、P3-T02。

**文件：**

- 创建：`sidecar/migrations/20260722000200_events_idempotency.sql`
- 创建：`sidecar/ibreeze/events/{registry.py,writer.py,outbox.py,replay.py}`
- 创建：`sidecar/ibreeze/application/idempotency.py`
- 创建：`sidecar/tests/fixtures/sqlite_company_parent.py`
- 创建：`sidecar/tests/events/{test_atomicity.py,test_outbox.py,test_replay.py,test_idempotency.py}`

**产生接口：** H.4 DomainEvent registry、projection offset、outbox、rpc_idempotency；`event.subscribe/replay`。Conversation事实与消息投影分别由 P4-T01、P4-T03 创建。

- [ ] **步骤 1：写原子性和重放失败测试**

  P3 单元测试数据库在运行正式 migration 后，通过 `sqlite_company_parent.py` 额外创建仅含 `id PRIMARY KEY` 的测试父表并插入 fixture company；该表只存在于测试连接，禁止进入 migration 或运行包。在 aggregate update、domain event、projection offset、outbox、idempotency result 各边界注入异常，事务后必须全有或全无。同 key异 payload必须 conflict。

- [ ] **步骤 2：实现注册事件 writer**

  未在 `packages/contracts/domain-events/registry.v1.json` 注册或 payload不合 Schema的事件禁止写入；payload不得含 prompt/token/完整正文。

- [ ] **步骤 3：实现 Outbox dispatcher**

  每项至少一次投递，consumer按 event id幂等；指数退避有上限，永久失败进入 diagnostics但不删除事实事件。

- [ ] **步骤 4：实现 replay 与压缩 marker**

  cursor签名、未来 sequence、gap、compacted range按 J.12；本任务实现replay识别marker及连续区间语义，不执行压缩或删除。transcript生成、marker提交和delta删除的唯一实现归属为P5-T07 `event_compactor.py`。

- [ ] **步骤 5：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/events -v --cov=ibreeze.events --cov=ibreeze.application.idempotency --cov-branch --cov-fail-under=100
  git add sidecar packages/contracts
  git commit -m "feat(events): add transactional events and replay"
  ```

**完成标准：** 崩溃不会产生无事件状态或无状态事件；事件补拉可识别压缩区间且不误报丢失。

### P3-T04：Catalog Cache、Skill 安装与底座版本存储

**依赖：** P3-T01、P3-T03、P2-T05。

**文件：**

- 创建：`sidecar/migrations/20260722000300_profiles_catalog_cache.sql`
- 创建：`sidecar/ibreeze/application/catalog/{cache.py,sync.py,skills.py,availability.py}`
- 创建：`sidecar/ibreeze/domain/profiles/{entities.py,service.py,repository.py}`
- 创建：`sidecar/tests/catalog/{test_sync.py,test_skill_install.py,test_profile_versions.py}`

**产生接口：** H.2 表及 `profile.*`、`catalog.*` RPC。

- [ ] **步骤 1：写目录原子切换和底座不可变失败测试**

  staging任何校验失败不影响 active；低 sequence拒绝；底座版本引用不存在的 catalog release 由外键拒绝；published profile content/binding修改由 Trigger拒绝；retire守卫按 9.2。

- [ ] **步骤 2：实现 cache sync**

  二次验证 manifest/resource hash、引用和 compatibility后，单事务旧 active→retired、新 staging→active；至少保留 active+最近2 retired。

- [ ] **步骤 3：实现 Skill 安装删除**

  流式复制、fsync、atomic rename后才写 installed；remove先检查 profile/snapshot/run引用，再删文件，文件失败保留DB。

- [ ] **步骤 4：实现 Profile draft/publish/retire**

  publish单事务同步 name/description/current_version/version；runtime_binding与skill lock来自当前已验签 release，不接受前端任意 catalog JSON。

- [ ] **步骤 5：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/catalog -v --cov=ibreeze.application.catalog --cov=ibreeze.domain.profiles --cov-branch --cov-fail-under=100
  git add sidecar packages/rpc-schema docs/用户手册.md
  git commit -m "feat(profiles): cache catalog and publish employee bases"
  ```

**完成标准：** 已发布底座和绑定不可变；损坏/禁用 Skill 不能进入新的 ExecutionSnapshot。

### P3-T05：本地审计、日志和设置

**依赖：** P3-T01–P3-T04。

**文件：**

- 创建：`sidecar/migrations/20260722000400_audit_settings.sql`
- 创建：`sidecar/ibreeze/application/{audit.py,settings.py}`
- 创建：`sidecar/ibreeze/observability/{logging.py,redaction.py}`
- 创建：`sidecar/tests/observability/{test_audit.py,test_redaction.py,test_settings.py}`

**产生接口：** `settings.get/update`；append-only audit_logs；20 MiB×10、1..365天日志策略。

- [ ] **步骤 1：写 canary 脱敏和审计不可变测试**

  复用 P3-T03 的测试父表 fixture；以每个敏感字段名和正文 canary 写日志/审计，断言输出不存在原文；直接 UPDATE/DELETE audit失败；存在 `company_id` 时孤儿公司引用必须被外键拒绝，system级 `company_id=null` 仍可写入。

- [ ] **步骤 2：实现 structlog processor链**

  固定字段 `timestamp/level/event/trace_id/company_id/task_id/run_id/code`；清除敏感 key和消息正文，绝对 Profile path改为相对标识。

- [ ] **步骤 3：实现设置乐观锁**

  只允许 CLI concurrency 1..16、retention 1..365；更新 version CAS，新的 concurrency只影响未租约任务。

- [ ] **步骤 4：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/observability -v --cov=ibreeze.application.audit --cov=ibreeze.application.settings --cov=ibreeze.observability --cov-branch --cov-fail-under=100
  git add sidecar packages/rpc-schema docs
  git commit -m "feat(sidecar): add audit logging and settings"
  ```

**完成标准：** 本地可追溯但不保存敏感正文；设置只有设计允许的两项。

### P3 阶段出口

- [ ] 设计方案 H.1、H.2、H.4 中事件/Outbox/offset/idempotency子集及 H.14 DDL 可在空 SQLite 执行，所有 FK check为零；公司级写入测试使用明确隔离的最小父表 fixture。
- [ ] 使用真实Sidecar重复P2-T04在线、离线和改密后的Profile打开集成测试；只有握手数据库ready且首次health healthy时Rust才返回opened，fake-sidecar不得进入生产构建。
- [ ] RPC 方法集合、Schema、方向和错误码契约测试通过。
- [ ] 事务 fault injection、Outbox重放、catalog原子切换、Skill损坏和审计脱敏测试通过。
- [ ] Sidecar 基础模块 100% 覆盖且无直接外网/Keychain访问代码。

---

## 7. P4：本地公司、部门、职员、会话与任务领域

### P4-T01：公司、部门与原子初始化骨架

**依赖：** P3-T01、P3-T03、P3-T04。

**文件：**

- 创建：`sidecar/migrations/20260722000500_company_bootstrap.sql`
- 创建：`sidecar/ibreeze/domain/company/{entities.py,commands.py,repository.py,service.py}`
- 创建：`sidecar/ibreeze/domain/company/bootstrap.py`
- 创建：`sidecar/ibreeze/domain/department/{entities.py,responsibilities.py,repository.py,service.py}`
- 创建：`sidecar/ibreeze/domain/employee/{entities.py,repository.py}`
- 创建：`sidecar/ibreeze/domain/conversation/{entities.py,repository.py}`
- 创建：`sidecar/tests/domain/{test_company.py,test_department.py,test_responsibility_graph.py}`

**产生接口：** `company.create/get/list/update/archive`、`department.create/get/list/update/archive/setLeader`、responsibility CRUD。

- [x] **步骤 1：写六项公司创建不变量失败测试**

  对 H.5 每个插入点注入异常，断言不存在部分 Company、Office、GM Employee 或 Conversation。成功后逐项验证六项不变量。

- [x] **步骤 2：实现可原子启动的 DDL 与组合外键**

  同一迁移逐字实现 H.3 的 company/department/revision/responsibility/employee 表以及 H.4 的 `conversations` 表、唯一索引和不可变 Trigger；`conversation_messages` 留给 P4-T03。所有 company scope 引用使用组合 FK，确保空库在本任务结束时已经具备执行 H.5 事务所需的全部表。

- [x] **步骤 3：实现 Company 创建事务**

  命令只接受 E.3 字段；服务端生成七个 UUID（Company、CompanyRevision、Office、OfficeRevision、GM Employee、公司会话、办公室会话）。只在该 `BEGIN IMMEDIATE` 创建事务内设置 `defer_foreign_keys=ON`，通过bootstrap repository按H.5固定顺序写入并提交 `company.created`；提交和每条回滚路径都读取并断言已恢复OFF。部门创建采用相同限定；测试向其他Command注入deferred设置，必须被连接归还守卫发现并丢弃，不能污染下一事务。

- [ ] **步骤 4：实现 Revision 更新与职责 DAG**

  名称统一 NFKC/trim/空白折叠/lowercase；update用 expected_version并生成 Revision。职责边增删后执行拓扑排序，有环返回 `RESPONSIBILITY_CYCLE`。

- [ ] **步骤 5：实现归档守卫**

  普通部门、总经理办公室和公司分别按 K.4检查非终态任务、Run、审批；归档事务级联状态但不删除历史，禁止恢复 RPC。

- [ ] **步骤 6：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/domain/test_company.py tests/domain/test_department.py tests/domain/test_responsibility_graph.py -v --cov=ibreeze.domain.company --cov=ibreeze.domain.department --cov-branch --cov-fail-under=100
  git add sidecar packages/rpc-schema docs/用户手册.md
  git commit -m "feat(company): add simulated companies and departments"
  ```

**完成标准：** 公司创建原子、职责无环、Revision不可变、总经理办公室不能被破坏。

### P4-T02：职员实例、负责人和调岗

**依赖：** P4-T01、P3-T04。

**文件：**

- 修改：`sidecar/ibreeze/domain/employee/{entities.py,repository.py}`
- 创建：`sidecar/ibreeze/domain/employee/{service.py,availability_rules.py}`
- 创建：`sidecar/tests/domain/test_employee.py`

**产生接口：** `employee.create/get/list/updateStatus/updateDisplayName/updateBaseProfile/transfer` 和 leader切换内部服务。

- [ ] **步骤 1：写角色与 active assignment 失败测试**

  覆盖同部门名称冲突、跨公司/部门、未发布底座、总经理调岗/停用/改角色、active assignment调岗、leader切换和旧负责人任务快照不漂移。

- [ ] **步骤 2：实现 Employee Service**

  `workflow_role` 只允许三值；所有更新CAS version并写 event。调岗只更新未来任务归属，禁止修改旧 ExecutionSnapshot。

- [ ] **步骤 3：实现 setLeader单事务**

  锁部门、旧 leader、目标 employee；更新两个 role和 department指针/version，写 `department.leader_changed`。目标等于当前按幂等成功。

- [ ] **步骤 4：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/domain/test_employee.py -v --cov=ibreeze.domain.employee --cov-branch --cov-fail-under=100
  git add sidecar packages/rpc-schema docs
  git commit -m "feat(employee): manage local agent employees"
  ```

**完成标准：** 总经理和办公室 leader 永远是同一 active Employee；任务快照不随职员配置更新漂移。

### P4-T03：会话与消息投影基础

**依赖：** P4-T01、P4-T02、P3-T03。

**文件：**

- 创建：`sidecar/migrations/20260722000600_local_domain_runtime_parents.sql`
- 修改：`sidecar/ibreeze/domain/conversation/{entities.py,repository.py}`
- 创建：`sidecar/ibreeze/domain/conversation/{projection.py,service.py}`
- 创建：`sidecar/tests/domain/test_conversations.py`

**产生接口：** `conversation.getCompany/getDepartment/listMessages`；领域事件到 `conversation_messages` 的可重建投影和内部 append 接口。

- [ ] **步骤 1：写投影与隔离失败测试**

  覆盖公司/部门会话类型、跨公司 id 统一 not found、发送者职员同公司、重复 source event 幂等和乱序 projection offset 拒绝。

- [ ] **步骤 2：创建无缺失父表的本地域骨架迁移**

  同一迁移按附录分组且只创建以下表：H.4 的 `conversation_messages`；H.6 的 `company_tasks/company_plan_versions/task_context_snapshots/department_tasks/department_task_dependencies/employee_tasks/employee_availability_snapshots/execution_snapshots`；H.11 的 `agent_runs` 核心表；H.11 Workspace父表 `workspace_grants/task_workspaces`。此归组是 SQLite 的运行要求：message 的可空 `task_id`、ExecutionSnapshot 的可空 `task_workspace_id` 仍要求父表已经存在。P4-T04、P5-T01、P6-T01 分别实现任务、Runtime、Workspace业务，不得再次创建这些表；`agent_run_events/checkpoints/tool_executions/human_approvals/verification_results` 明确由008迁移创建。迁移完成后立即执行 `foreign_key_check`，并实际插入 `task_id=null` 的消息和 `task_workspace_id=null` 的非代码 ExecutionSnapshot 验证父表闭环。

- [ ] **步骤 3：实现消息投影**

  领域事件保存事实，conversation_messages是可重建投影。删除并重建投影后消息 id、顺序、发送者和内容哈希不变；本阶段写 `task_id=null` 的初始化/普通投影 fixture，P4-T04 补齐任务关联重建测试。

- [ ] **步骤 4：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/domain/test_conversations.py -v --cov=ibreeze.domain.conversation --cov-branch --cov-fail-under=100
  git add sidecar packages/rpc-schema docs/用户手册.md
  git commit -m "feat(conversation): add durable message projections"
  ```

**完成标准：** 公司初始化后的两个会话可立即读取；消息投影可重建且不成为状态事实来源。

### P4-T04：任务、Plan、Snapshot 与四类状态机

**依赖：** P4-T03。

**文件：**

- 使用：P4-T03 已创建的 `20260722000600_local_domain_runtime_parents.sql`，本任务不新增迁移
- 创建：`sidecar/ibreeze/domain/tasks/{entities.py,state.py,repository.py,service.py,plans.py,snapshots.py}`
- 创建：`sidecar/ibreeze/application/task_intake.py`
- 创建：`sidecar/tests/tasks/{test_schema.py,test_state_machines.py,test_plan_versions.py,test_snapshots.py,test_task_intake.py}`

**产生接口：** `conversation.submitUserMessage`、`task.confirmPlan/requestPlanRevision/rejectPlan/pause/resume/cancel/get/list/getGraph/getEvidence`；submit DTO 固定含互斥的 `target_task_id/supersedes_task_id`；H.6和H.7完整状态。

- [ ] **步骤 1：把迁移表转为参数化失败测试**

  测试遍历设计方案 H.7 每个允许边和所有未列边；允许边还要覆盖业务guard，未列边必须 `STATE_TRANSITION_INVALID`。显式断言 `submitted` 不能越过 `peer_reviewing` 直接进入 changes_requested/accepted。

- [ ] **步骤 2：验证并映射 H.6 DDL 与不可变 Trigger**

  对 P4-T03 迁移中的 company task、plan version、context snapshot、department task/dependency、employee task、availability、execution snapshot 建立Repository映射和Schema测试；逐项核对H.6列、组合外键、CHECK与不可变Trigger，覆盖 EmployeeTask `standard/merge` kind 且禁止其他值，禁止以第二个迁移修补遗漏。H.11 `agent_runs` 核心表只作为 PlanVersion/Queue 的持久化父表，Gateway逻辑仍由P5-T01实现。

- [ ] **步骤 3：实现唯一状态迁移入口**

  ```python
  async def transition(aggregate: StatefulAggregate, target: State, expected_version: int, reason: TransitionReason) -> StatefulAggregate: ...
  ```

  Repository禁止公开任意 status update；等待态在同一UPDATE写/清 resume_state。

- [ ] **步骤 4：实现 PlanVersion与确认事务**

  确认同时校验 plan id/version/hash、PlanValidator receipt和current awaiting版本，创建 DepartmentTask、Dependencies、TaskContextSnapshot并进入approved；任一步失败全部回滚。

- [ ] **步骤 5：实现用户输入事务**

  `conversation.submitUserMessage` 在一个 `BEGIN IMMEDIATE` 中写 user message event、projection、CompanyTask draft或目标任务修订、`user_message_event_id` 和 outbox。普通输入创建新 draft；target只允许 awaiting/revision_requested并复用任务；supersedes只允许同公司 cancelled/failed；approved任务修改被拒；跨公司 id统一 not found。响应逐字为 `{message_id,company_task_id,task_status,intake_mode,analysis_queued:true}`：新建/重发为draft，计划修改为revision_requested；不得返回尚未由Outbox创建的run_id。Schema和测试覆盖三种intake_mode及异步任务事件获取Run。

- [ ] **步骤 6：实现 Snapshot get-or-create**

  prospective RFC8785 hash必须等于ExecutionSnapshot content hash；Context/Availability/Execution Snapshot 的 catalog release 必须存在，Run创建断言两个snapshot的employee/company/work_item一致且availability未过期。

- [ ] **步骤 7：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/tasks -v --cov=ibreeze.domain.tasks --cov-branch --cov-fail-under=100
  git add sidecar packages/rpc-schema packages/contracts
  git commit -m "feat(tasks): add plans snapshots and state machines"
  ```

**完成标准：** 任何状态只能沿H.7迁移；确认后的Plan、Context和ExecutionSnapshot不可变。

### P4-T05：Runtime Queue、Lease 与公平调度基础

**依赖：** P4-T04、P3-T01。

**文件：**

- 创建：`sidecar/migrations/20260722000700_runtime_queue.sql`
- 创建：`sidecar/ibreeze/runtime/{queue.py,leases.py,scheduler.py,limits.py}`
- 创建：`sidecar/tests/runtime/{test_queue.py,test_leases.py,test_fairness.py}`

**产生接口：** H.10 Queue/Lease；purpose映射、四级优先级、company fairness、global/employee/conversation slots。

- [ ] **步骤 1：写并发租约失败测试**

  100个并发acquire对同一queue只能1个成功；lease过期可回收，旧holder续租/完成失败；conversation和employee不能超槽；不存在的company不能写入fairness/queue/lease，lease的company必须与queue三列组合外键一致。knowledge queue即使 `run_id=null` 也必须受直接company FK约束。

- [ ] **步骤 2：实现单事务 acquire**

  使用 `BEGIN IMMEDIATE` 同时取得queue、global、employee、conversation slot并更新fairness；任一步不足不留下部分lease。

- [ ] **步骤 3：实现确定性优先级**

  priority按H.10；同级先最久未调度company，再queued_at/id。knowledge只占ProcessPool slot且run_id为空。

- [ ] **步骤 4：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/runtime/test_queue.py tests/runtime/test_leases.py tests/runtime/test_fairness.py -v --cov=ibreeze.runtime.queue --cov=ibreeze.runtime.leases --cov=ibreeze.runtime.scheduler --cov-branch --cov-fail-under=100
  git add sidecar
  git commit -m "feat(runtime): add fair durable scheduler"
  ```

**完成标准：** 多公司不会饥饿；同职员和同会话不会并发执行两个active turn。

### P4 阶段出口

- [ ] H.3–H.7、H.10以及H.11的AgentRun/Workspace父表全部列、组合FK、Trigger和状态边测试通过。
- [ ] 公司/部门/职员/会话/任务所有公开RPC成功、错误、幂等和跨公司测试通过。
- [ ] fault injection证明公司创建、用户消息、计划确认、leader切换和snapshot创建原子。
- [ ] 无Repository提供任意status更新或跨公司裸id查询。

---

## 8. P5：Agent Runtime Gateway

### P5-T01：Runtime Gateway、AgentRun 与标准事件

**依赖：** P4-T04、P4-T05、P2-T03、P2-T07。

**文件：**

- 创建：`sidecar/migrations/20260722000800_runtime_foundation.sql`
- 创建：`sidecar/ibreeze/runtime/{gateway.py,process_supervisor.py,event_normalizer.py,run_repository.py}`
- 创建：`sidecar/ibreeze/artifacts/{model.py,cas.py,runtime_sink.py}`
- 创建：`sidecar/tests/runtime/{test_gateway.py,test_run_state.py,test_events.py,test_process_supervisor.py,test_runtime_artifact_sink.py}`

**产生接口：** I.1四个入口；使用 P4-T04 已创建的 H.11 AgentRun 核心表，并创建 RunEvent/Checkpoint/ToolExecution/VerificationResult/HumanApproval存储表及 H.12 `artifacts` 核心表；提供仅供 Runtime 写 diagnostic/log/transcript/checkpoint 等证据的不可变 CAS sink；14.6标准事件。HumanApproval决策服务和完整Artifact领域分别由P6-T05、P6-T03实现。

- [ ] **步骤 1：写 Gateway边界失败测试**

  静态扫描禁止runtime外调用`asyncio.create_subprocess_exec`或模型HTTP；start缺snapshot、过期availability、hash不一致、非法purpose均失败；Runtime Foundation迁移逐字创建H.11运行子表/HumanApproval及H.12 Artifact核心表、任务索引和不可变Trigger，验证可写Artifact、VerificationResult、ToolExecution和pending HumanApproval且不存在缺失父表，直接UPDATE/DELETE Artifact必须失败。

- [ ] **步骤 2：实现 Run创建和状态迁移**

  AgentRunSpec先过E.8 Schema；持久化run_spec canonical JSON/hash、`department_task_id/work_item_id` 可索引列、两个 snapshot id 和 conversation。按 E.8/H.11 校验 company_plan/summary→CompanyTask、interactive_turn→Conversation、task_execution→standard EmployeeTask、merge→merge EmployeeTask、review→ReviewAssignment、verification→Artifact、repair→ReviewIssue；P5单元测试对尚由009迁移创建的ReviewAssignment/ReviewIssue使用Repository fake，P6-T04必须补真实SQLite集成测试。运行状态只用H.7表。

- [ ] **步骤 3：实现进程登记通知**

  spawn后立即存PID/PGID/start time并通知Rust；退出通知含exit/signal/hash。Rust拒绝登记时立刻终止Run进程组。

- [ ] **步骤 4：实现事件归一化**

  每Run sequence从1递增；native raw只存脱敏JSON；payload过1MiB通过 runtime CAS sink 写不可变 Artifact 引用。sink只接受固定 Runtime 证据类型，执行 temp→hash→fsync→rename→DB insert，并复用 P6-T03 将扩展的同一 CAS 实现；unknown native event映射diagnostic，不破坏sequence。

- [ ] **步骤 5：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/runtime/test_gateway.py tests/runtime/test_run_state.py tests/runtime/test_events.py tests/runtime/test_process_supervisor.py tests/runtime/test_runtime_artifact_sink.py -v --cov=ibreeze.runtime --cov=ibreeze.artifacts --cov-branch --cov-fail-under=100
  git add sidecar packages/contracts packages/rpc-schema
  git commit -m "feat(runtime): add durable agent run gateway"
  ```

**完成标准：** 所有Agent执行经过唯一Gateway；状态、进程和事件可在崩溃后对账。

### P5-T02：Codex CLI Adapter

**依赖：** P5-T01、P2-T07。

**文件：**

- 创建：`sidecar/ibreeze/runtime/cli_adapters/codex.py`
- 创建：`sidecar/tests/runtime/adapters/{test_codex_argv.py,test_codex_events.py,test_codex_resume.py}`
- 创建：`tests/fixtures/cli/codex/`

**产生接口：** `AgentAdapter` I.4实现，registry key=`codex_cli`。

- [ ] **步骤 1：写argv精确比较失败测试**

  首次、resume、非Git三种期望数组逐元素比较；禁止dangerous bypass、add-dir、任意用户config；Prompt只经stdin。

- [ ] **步骤 2：实现probe与版本门禁**

  解析`codex-cli 0.144.x`，login status失败标auth unavailable；范围外返回`AGENT_VERSION_INCOMPATIBLE`。

- [ ] **步骤 3：实现JSONL解析**

  fake CLI分块输出、4MiB行、malformed line、native session、tool/model/final/error事件；final与last-message SHA不一致返回`ADAPTER_RESULT_MISMATCH`。

- [ ] **步骤 4：真实契约冒烟**

  在受控测试仓库通过Egress+Seatbelt执行只读问答、workspace写任务、resume和cancel；保存版本与事件fixture，不保存prompt正文。

- [ ] **步骤 5：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/runtime/adapters/test_codex_argv.py tests/runtime/adapters/test_codex_events.py tests/runtime/adapters/test_codex_resume.py -v --cov=ibreeze.runtime.cli_adapters.codex --cov-branch --cov-fail-under=100
  git add sidecar tests/fixtures/cli docs/Runtime选型记录.md
  git commit -m "feat(runtime): add codex cli adapter"
  ```

**完成标准：** 锁定Codex版本完成首次、恢复、取消与结果一致性测试，不能绕过代理或Seatbelt。

### P5-T03：Claude Code Adapter

**依赖：** P5-T01、P2-T07。

**文件：** `sidecar/ibreeze/runtime/cli_adapters/claude_code.py`、`sidecar/tests/runtime/adapters/test_claude_argv.py`、`sidecar/tests/runtime/adapters/test_claude_events.py`、`sidecar/tests/runtime/adapters/test_claude_resume.py`、`tests/fixtures/cli/claude/`。

**产生接口：** `AgentAdapter` I.5实现，registry key=`claude_code`。

- [ ] **步骤 1：测试精确argv和禁用项**：断言print/stream-json/safe-mode/strict-mcp/empty setting sources/dontAsk/allowedTools/session-id；禁止continue、dangerously-skip、max-budget。
- [ ] **步骤 2：实现version/auth probe和stream-json stdin/stdout**：输入每turn都是合法stream event，partial合并不重复文本。
- [ ] **步骤 3：实现resume和错误归一化**：只用`--resume id`，认证、限流、工具拒绝、模型错误进入稳定event/failure_code。
- [ ] **步骤 4：运行fake与真实契约**：

  ```bash
  uv run --directory sidecar pytest tests/runtime/adapters/test_claude_argv.py tests/runtime/adapters/test_claude_events.py tests/runtime/adapters/test_claude_resume.py -v --cov=ibreeze.runtime.cli_adapters.claude_code --cov-branch --cov-fail-under=100
  ```

- [ ] **步骤 5：提交**：`git commit -m "feat(runtime): add claude code adapter"`。

**完成标准：** safe mode下不加载用户插件、Hook、CLAUDE.md、MCP或自动记忆；Skill只由Context Engine注入。

### P5-T04：OpenCode Adapter

**依赖：** P5-T01、P2-T07。

**文件：** `sidecar/ibreeze/runtime/cli_adapters/opencode.py`、`sidecar/tests/runtime/adapters/test_opencode_argv.py`、`sidecar/tests/runtime/adapters/test_opencode_events.py`、`sidecar/tests/runtime/adapters/test_opencode_resume.py`、`tests/fixtures/cli/opencode/`。

**产生接口：** `AgentAdapter` I.6实现，registry key=`opencode`。

- [ ] **步骤 1：测试精确argv**：pure/json/model/agent build/dir/auto/file/message；resume只追加session；禁止share/attach/fixed port。
- [ ] **步骤 2：实现task.md安全生命周期**：0600、Run结束删除、诊断和备份不包含；路径只能RUN_TEMP。
- [ ] **步骤 3：实现raw JSON event parser与session恢复**：错误行、stderr、cancel、exit状态和最终内容全部覆盖。
- [ ] **步骤 4：运行fake与真实契约**：

  ```bash
  uv run --directory sidecar pytest tests/runtime/adapters/test_opencode_argv.py tests/runtime/adapters/test_opencode_events.py tests/runtime/adapters/test_opencode_resume.py -v --cov=ibreeze.runtime.cli_adapters.opencode --cov-branch --cov-fail-under=100
  ```

- [ ] **步骤 5：提交**：`git commit -m "feat(runtime): add opencode adapter"`。

**完成标准：** `--auto`只在Seatbelt和Egress探测成功后启用；任务文件不残留。

### P5-T05：ModelTransport 与 Built-in Agent Loop

**依赖：** P5-T01、P2-T07、P3-T04。

**文件：**

- 创建：`sidecar/ibreeze/runtime/model_runtime/{agent_loop.py,protocol.py,stream.py,limits.py}`
- 创建：`sidecar/ibreeze/runtime/model_runtime/transports/{openai_responses.py,anthropic_messages.py,openai_chat.py}`
- 创建：`sidecar/tests/runtime/model_runtime/{test_transports.py,test_agent_loop.py,test_stream_recovery.py}`

**产生接口：** I.10三协议；I.11完整loop；所有HTTP通过Rust Credential Broker。

- [ ] **步骤 1：写三协议fixture测试**

  覆盖文本、tool call、多tool、usage、SSE分块、invalid JSON、断流、429 retry-after、401/403、context overflow和unsupported tool。

- [ ] **步骤 2：实现统一ModelEvent**

  Transport只做协议转换，不执行工具或loop；同一语义事件在三协议输出一致的`model.output.delta/tool.call/usage/error`。

- [ ] **步骤 3：实现Agent Loop状态机**

  固定步骤context→model→tool validation→permission→execute→result→model，最多50 tool calls、5修复loops；达到上限`RUN_LIMIT_REACHED`。

- [ ] **步骤 4：实现断流决策**

  未产生tool/side effect可按相同idempotency重试；已发生不确定外部副作用进入`RUN_RECOVERY_UNCERTAIN`，禁止自动重放。

- [ ] **步骤 5：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/runtime/model_runtime -v --cov=ibreeze.runtime.model_runtime --cov-branch --cov-fail-under=100
  git add sidecar tests/fixtures docs
  git commit -m "feat(runtime): add builtin api model agent loop"
  ```

**完成标准：** API Model能完整执行工具任务，不存在“直接请求模型并返回文本”的捷径。

### P5-T06：Tool Registry、Permission Gateway 与Seatbelt生成

**依赖：** P5-T05、P2-T06、P2-T07。

**文件：**

- 创建：`sidecar/ibreeze/runtime/tools/{registry.py,files.py,search.py,shell.py,artifacts.py,knowledge.py}`
- 创建：`sidecar/ibreeze/runtime/{permission_gateway.py,seatbelt.py}`
- 创建：`packages/contracts/approvals/external-write-target.v1.schema.json`
- 创建：`sidecar/tests/security/{test_tool_schemas.py,test_permissions.py,test_seatbelt.py,test_external_write.py}`

**产生接口：** I.12工具集合；purpose权限缩减；I.8 SBPL模板；I.13审批。

- [ ] **步骤 1：写每个工具Schema和边界失败测试**

  未知字段、绝对/逃逸路径、depth>5、>5000条、输出>1MiB、shell字符串拼接、只读purpose写工具和外部写无审批均失败。

- [ ] **步骤 2：实现Registry与参数数组执行**

  每个工具固定name/input schema/output schema/risk/required capability；shell只接受`argv:string[]`和cwd grant，不接受shell text。

- [ ] **步骤 3：实现purpose ToolPolicy**

  interactive/company_plan/review/summary移除workspace写工具；verification只运行snapshot锁定命令；外部写只创建 H.11 pending HumanApproval并停止执行，决策、Rust receipt和消费由P6-T05实现。

- [ ] **步骤 4：实现并实测SBPL**

  使用设计方案I.8模板，变量realpath+转义；启动时探测 `/usr/bin/sandbox-exec` 及最小allow/deny/代理用例，任一失败则所有CLI职员unavailable。普通CI用fake执行器覆盖模板、转义和拒绝路径；发布门禁必须在最低与最高受支持macOS版本的真实机器上实际尝试读其他profile/credential、写外部、直连公网和fork逃逸，不能降为可选nightly任务。没有满足版本矩阵的真实runner时禁止发布，但不影响API Model职员使用Built-in Runtime。

- [ ] **步骤 5：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/security/test_tool_schemas.py tests/security/test_permissions.py tests/security/test_seatbelt.py tests/security/test_external_write.py -v --cov=ibreeze.runtime.tools --cov=ibreeze.runtime.permission_gateway --cov=ibreeze.runtime.seatbelt --cov-branch --cov-fail-under=100
  git add sidecar packages/contracts tests/security docs
  git commit -m "feat(runtime): enforce tools sandbox and approvals"
  ```

**完成标准：** 模型不能获得未在ExecutionSnapshot中的工具、路径或网络域名；外部写审批只消费一次。

### P5-T07：Context Engine、Token容量与Checkpoint恢复

**依赖：** P5-T01、P5-T05、P5-T06。

**文件：**

- 创建：`sidecar/ibreeze/runtime/{context_engine.py,token_budget.py,checkpoint.py,recovery.py,event_compactor.py}`
- 创建：`packages/contracts/approvals/uncertain-recovery-target.v1.schema.json`
- 创建：`sidecar/tests/runtime/{test_context.py,test_token_budget.py,test_checkpoint.py,test_recovery.py,test_event_compactor.py}`

**产生接口：** I.14Context容量、I.15Checkpoint、16章Context Pack与恢复。

- [ ] **步骤 1：写Context隔离和容量失败测试**

  其他公司/任务/职员引用不可进入；system/skill/目标不可截断；四种tokenizer和byte upper bound有golden fixture；必需内容超限返回指定错误。

- [ ] **步骤 2：实现优先级组装和摘要**

  固定顺序系统/安全→目标验收→最近8组→直接artifact→历史知识；摘要只尝试1次并输出固定schema，失败确定性保留最近内容。

- [ ] **步骤 3：实现Checkpoint存储**

  每边界RFC8785 JSON→zstd3→SHA；≤1MiB DB blob，否则temp+fsync+rename。读取先验hash和schema。

- [ ] **步骤 4：实现恢复决策表**

  completed工具不重放，未开始重做，started只读重做，写/副作用不确定按I.13 Schema创建 `action=retry_once` approval；CLI native session失败才用transcript+checkpoint新session。

- [ ] **步骤 5：实现Run事件压缩器**

  后台扫描完成满24小时的Run，严格按J.12把连续 `model.output.delta` 合成为transcript Artifact，在同一写事务追加覆盖区间和Artifact hash绑定的 `model.output.compacted` marker；只有marker提交后才删除被覆盖delta，其他事件永不删除。崩溃注入覆盖Artifact写前、Artifact写后、marker提交前后和delta删除前后，重复运行必须得到同一覆盖结果且 `event.replay` 无sequence缺口。

- [ ] **步骤 6：验证并提交**

  ```bash
  uv run --directory sidecar pytest tests/runtime/test_context.py tests/runtime/test_token_budget.py tests/runtime/test_checkpoint.py tests/runtime/test_recovery.py tests/runtime/test_event_compactor.py -v --cov=ibreeze.runtime.context_engine --cov=ibreeze.runtime.token_budget --cov=ibreeze.runtime.checkpoint --cov=ibreeze.runtime.recovery --cov=ibreeze.runtime.event_compactor --cov-branch --cov-fail-under=100
  git add sidecar packages/contracts
  git commit -m "feat(runtime): add context checkpoints and recovery"
  ```

**完成标准：** Context不可跨公司；恢复不会重复未知副作用；Checkpoint损坏明确失败。

### P5 阶段出口

- [ ] 三CLI锁定版本在fake和真实环境完成probe/start/resume/cancel/event/result契约。
- [ ] API Model三协议、tools、repair loop、断流和Credential Broker集成通过。
- [ ] Seatbelt、Egress、敏感路径、purpose只读和外部审批安全测试通过。
- [ ] Run crash/restart/checkpoint/native session恢复矩阵通过。
- [ ] Runtime Artifact sink、VerificationResult、ToolExecution和pending HumanApproval可在008正式Schema上持久化，不依赖尚未执行的迁移。

---

## 9. P6：Workspace、Artifact、Review 与审批闭环

### P6-T01：Workspace Grant 与TaskWorkspace领域

**依赖：** P4-T04、P2-T06、P5-T06。

**文件：**

- 创建：`sidecar/migrations/20260722000900_workspace_artifacts.sql`
- 创建：`sidecar/ibreeze/workspace/{grants.py,task_workspace.py,repository_probe.py}`
- 修改：`sidecar/ibreeze/domain/tasks/service.py`
- 创建：`sidecar/tests/workspace/{test_grants.py,test_task_workspace.py,test_repository_probe.py,test_plan_confirmation.py}`

**产生接口：** `workspace.get/apply/abandon/cleanupTask`；J.1准入；使用 P4-T03 已创建的 H.11 grant/workspace表，本任务的009迁移创建P6后续任务所需的Artifact扩展与Review表。

- [ ] **步骤 1：写仓库准入失败测试**：非git、detached、dirty、merge/rebase/cherry-pick、路径已被其他公司active grant、bookmark stale和HEAD变化全部进入`waiting_resource`且不修改仓库。
- [ ] **步骤 2：接入计划确认编排并创建TaskWorkspace**：扩展 P4-T04 的确认 Application Service；代码项目在确认事务中锁定 grant/root/baseline/user branch，预生成 integration branch/path 并创建 TaskWorkspace，repository_root只能来自Rust grant。任一 Workspace 写入或 Plan 确认写入失败时整笔回滚；非代码任务不创建 Git TaskWorkspace，仍执行 H.8 的领域确认事务。
- [ ] **步骤 3：实现Workspace状态机**：只允许preparing→active→ready_to_apply→applied或abandoned；cleanup仅终态且无active Run。
- [ ] **步骤 4：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/workspace/test_grants.py tests/workspace/test_task_workspace.py tests/workspace/test_repository_probe.py -v --cov=ibreeze.workspace --cov-branch --cov-fail-under=100
  git add sidecar packages/rpc-schema docs
  git commit -m "feat(workspace): lock task repositories and baselines"
  ```

**完成标准：** iBreeze不自动stash/reset/checkout用户文件；所有代码任务有不可漂移baseline。

### P6-T02：受管Worktree、职员分支与合并

**依赖：** P6-T01、P5-T06。

**文件：**

- 创建：`sidecar/ibreeze/workspace/{git.py,worktrees.py,merge.py,apply.py}`
- 创建：`sidecar/tests/workspace/{test_worktrees.py,test_merge.py,test_apply.py}`

**产生接口：** J.2/J.3分支命名、worktree校验、integration merge、用户apply和人工合并计划Artifact。

- [ ] **步骤 1：写碰撞和漂移失败测试**：branch/path已存在但ref、HEAD、baseline任一不符必须拒绝；禁止`-B/--force`。
- [ ] **步骤 2：实现参数数组Git执行器**：所有命令固定argv和cwd，不经shell；记录stdout/stderr hash、exit和trace。
- [ ] **步骤 3：实现职员到integration合并**：按计划依赖顺序，`--no-ff --no-commit`，冲突回滚本次merge并产出Artifact，不覆盖别的worktree。
- [ ] **步骤 4：实现apply二次校验**：用户worktree必须clean、branch相同、HEAD=baseline；否则只生成manual plan。成功质量门禁后提交固定message。
- [ ] **步骤 5：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/workspace/test_worktrees.py tests/workspace/test_merge.py tests/workspace/test_apply.py -v --cov=ibreeze.workspace --cov-branch --cov-fail-under=100
  git add sidecar docs/用户手册.md
  git commit -m "feat(workspace): manage isolated git worktrees"
  ```

**完成标准：** 并行职员不写同一目录；任何用户仓库漂移均转人工计划而非强制覆盖。

### P6-T03：Artifact CAS、版本链与文档Workspace

**依赖：** P6-T01、P3-T01。

**文件：**

- 修改：`sidecar/ibreeze/artifacts/{model.py,cas.py}`
- 创建：`sidecar/ibreeze/artifacts/{manifest.py,service.py,document_workspace.py}`
- 创建：`sidecar/tests/artifacts/{test_cas.py,test_manifest.py,test_versions.py,test_document_workspace.py}`

**产生接口：** `artifact.list/getSnapshot`；在 P5-T01 Runtime CAS sink 上补齐 J.4/J.5 通用 CAS、manifest、版本链和贡献者；H.12 Artifact扩展表。

- [ ] **步骤 1：写CAS损坏和路径失败测试**：错误hash、size、symlink、absolute relative_path、`..`、mode异常、同hash并发写、孤儿temp和supersedes环；P5 Runtime sink创建的历史对象必须仍可由通用Service读取和验证。
- [ ] **步骤 2：扩展统一CAS写入器**：复用 P5-T01 已实现的 stream→temp→hash→fsync→rename 原语，增加通用Artifact类型、manifest和并发入口；CAS key只由SHA决定，已有对象需重验size和抽样hash，不盲信存在，禁止另建第二套对象存储实现。
- [ ] **步骤 3：实现Artifact事务**：DB row、contributors、manifest、outbox同事务；正式Artifact不可更新，修复创建新id/supersedes。
- [ ] **步骤 4：实现文档Workspace**：非Git任务在受管目录按Artifact版本工作，apply通过Rust单次外部写或用户导出，不直接覆盖任意路径。
- [ ] **步骤 5：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/artifacts -v --cov=ibreeze.artifacts --cov-branch --cov-fail-under=100
  git add sidecar packages/contracts packages/rpc-schema
  git commit -m "feat(artifacts): add immutable content addressed outputs"
  ```

**完成标准：** 每个交付物可按hash重放和验证；修复保留旧快照与贡献者。

### P6-T04：Review分配、报告和Issue状态机

**依赖：** P6-T03、P4-T02、P4-T04、P5-T01。

**文件：**

- 创建：`sidecar/ibreeze/review/{assignment.py,service.py,issues.py,reports.py}`
- 创建：`sidecar/tests/review/{test_assignment.py,test_reports.py,test_issues.py,test_stale.py}`

**产生接口：** `review.submit/listIssues/rerun/resolveIssue`；H.12 Review表和状态；11.6/E.9报告。

- [ ] **步骤 1：写Reviewer池矩阵失败测试**：贡献者排除、参与职员池、leader fallback、唯一贡献者无peer、关键Artifact最多2人、department report公司级池、final report不递归review。
- [ ] **步骤 2：实现确定性分配**：按当前负载、最后分配时间、employee id排序；eligible为空将任务置waiting_resource。
- [ ] **步骤 3：实现Report与Run引用校验**：reviewer run employee/purpose、artifact hash、report artifact type/creator全部匹配；使用009正式Schema集成验证 review→ReviewAssignment、repair→ReviewIssue，verification→Artifact及merge→merge EmployeeTask 的同公司/同任务链映射，替换P5-T01的Repository fake；否则拒绝。
- [ ] **步骤 4：实现Issue状态机**：blocker/high不能rejected；medium/low需理由；resolved→verified→closed，Artifact新版本使旧assignment stale。
- [ ] **步骤 5：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/review -v --cov=ibreeze.review --cov-branch --cov-fail-under=100
  git add sidecar packages/contracts packages/rpc-schema docs/用户手册.md
  git commit -m "feat(review): add cross employee review closure"
  ```

**完成标准：** 无职员Review自己的贡献；任务完成前所有blocker/high closed且证据有效。

### P6-T05：HumanApproval 与不确定副作用处理

**依赖：** P5-T06、P6-T01、P4-T04。

**文件：**

- 创建：`sidecar/ibreeze/application/approvals/{service.py,repository.py,expiry.py}`
- 创建：`sidecar/tests/approvals/{test_lifecycle.py,test_target_change.py,test_recovery.py}`

**产生接口：** `approval.listPending/resolve`；使用 P5-T01 已创建的 H.11 HumanApproval存储表，实现I.13一次性审批完整生命周期。

- [ ] **步骤 1：写生命周期失败测试**：唯一允许边为 pending→allowed/denied/expired、allowed→consumed/expired，denied/expired/consumed均为终态；覆盖重复resolve、allowed执行pending重试、响应丢失后目标已达成的receipt重建、过期allow、跨公司、非owner、target hash改变和旧expected_version失败。
- [ ] **步骤 2：实现审批创建**：只由Permission Gateway/Recovery创建，target_json分别通过I.13两个固定Schema并存canonical hash；前端不能任意创建。
- [ ] **步骤 3：实现外部写resolve与Rust握手**：数据库allowed后请求Rust执行；外部写ToolExecution必须记录同Run、同target hash的`approval_id`，其他工具不得绑定审批。只有Rust返回目标、动作、result state和receipt hash均匹配的receipt，才在同一事务完成ToolExecution并把allowed审批置consumed；无receipt保持allowed且`listPending.execution_pending=true`，重复相同allow只走F.4幂等重试。
- [ ] **步骤 4：实现不确定恢复与expiry决策**：不确定恢复allow在单一事务为同input hash创建唯一一次新ToolExecution、消费审批并把Run转retrying，deny/expired不重放并把Run置failed。外部写pending过期直接reject并恢复；allowed过期前先用F.4只读对账，目标已达成则consume，仍为old state才expired并恢复，第三种状态保持ToolExecution uncertain并把Run置failed。
- [ ] **步骤 5：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/approvals -v --cov=ibreeze.application.approvals --cov-branch --cov-fail-under=100
  git add sidecar packages/rpc-schema
  git commit -m "feat(approvals): close one-shot human decisions"
  ```

**完成标准：** 外部写和不确定恢复都由用户逐次决定；批准不能变成目录永久授权。

### P6 阶段出口

- [ ] Git clean/dirty/branch/HEAD/worktree碰撞/merge冲突/apply漂移矩阵通过。
- [ ] CAS损坏、Artifact版本链、贡献者、Review自审和Issue闭环测试通过。
- [ ] 外部写symlink swap、hash变化、过期和重复消费测试通过。
- [ ] blocker/high Review问题存在时所有完成路径都被阻断。

---

## 10. P7：Agent Orchestration Platform

### P7-T01：Company Plan Schema、生成和PlanValidator

**依赖：** P4-T04、P5-T07、P6-T01、P6-T04。

**文件：**

- 创建：`packages/contracts/company-plan.schema.json`
- 创建：`sidecar/ibreeze/orchestration/{plan_generator.py,plan_validator.py,department_matcher.py}`
- 创建：`sidecar/tests/orchestration/{test_plan_schema.py,test_plan_validator.py,test_department_matcher.py}`

**产生接口：** E.6 CompanyPlan；PV-001..PV-011；H.8评分算法。

- [ ] **步骤 1：为11条规则逐条写失败fixture**：每个fixture只违反一条并断言对应rule id；同时测试多个错误排序稳定。
- [ ] **步骤 2：实现Plan生成Run**：只用GM employee、company_plan purpose、只读Workspace、公司介绍与全部active部门Revision；模型格式错误最多两次修复。
- [ ] **步骤 3：实现评分与候选**：40/30/20/10公式、阈值60、tie按created_at/id；候选外部门仅GM office temporary flag。
- [ ] **步骤 4：实现确认receipt**：Validator输出plan id/version/hash/rule version/result hash；confirm必须验证receipt与当前Plan完全一致。
- [ ] **步骤 5：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/orchestration/test_plan_schema.py tests/orchestration/test_plan_validator.py tests/orchestration/test_department_matcher.py -v --cov=ibreeze.orchestration.plan_generator --cov=ibreeze.orchestration.plan_validator --cov=ibreeze.orchestration.department_matcher --cov-branch --cov-fail-under=100
  git add sidecar packages/contracts
  git commit -m "feat(orchestration): generate and validate company plans"
  ```

**完成标准：** 未确认前只运行只读company_plan；任何不可执行计划不能进入awaiting confirmation。

### P7-T02：职员可用性探测与替换

**依赖：** P7-T01、P5全部、P4-T02。

**文件：**

- 创建：`sidecar/ibreeze/orchestration/{availability.py,replacement.py}`
- 创建：`sidecar/tests/orchestration/{test_availability.py,test_replacement.py}`

**产生接口：** `departmentTask.checkResources/replaceEmployee`；E.7/H.6 AvailabilitySnapshot。

- [ ] **步骤 1：写七项探测矩阵**：employee/department、agent/provider auth、model/skill/runtime、package、workspace/tool、slot、health逐项失败；过5分钟重探。
- [ ] **步骤 2：实现prospective config hash**：从锁定catalog/profile/company/department/workspace/tool/verification构建RFC8785 bytes；probe结果和evidence refs写不可变snapshot。
- [ ] **步骤 3：实现replaceEmployee**：只允许同部门active且能力覆盖；旧未运行EmployeeTask cancelled，新建task/snapshots；改变目标/权限/交付物/门禁时拒绝并要求取消重发。
- [ ] **步骤 4：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/orchestration/test_availability.py tests/orchestration/test_replacement.py -v --cov=ibreeze.orchestration.availability --cov=ibreeze.orchestration.replacement --cov-branch --cov-fail-under=100
  git add sidecar packages/rpc-schema
  git commit -m "feat(orchestration): probe and replace task employees"
  ```

**完成标准：** 任何Run启动前有未过期available snapshot；替换不修改旧证据。

### P7-T03：部门分析、协作策略与职员任务

**依赖：** P7-T02、P6-T02、P6-T04。

**文件：**

- 创建：`sidecar/ibreeze/orchestration/{department_flow.py,collaboration.py,assignment.py}`
- 创建：`sidecar/tests/orchestration/{test_department_flow.py,test_collaboration.py}`

**产生接口：** 11.5四种策略；DepartmentTask从checking_resources到completed的内部编排。

- [ ] **步骤 1：写四策略计划fixture**：independent drafts、section partition、primary peer review、sequential refinement分别断言EmployeeTask依赖、Workspace和Artifact输入。
- [ ] **步骤 2：实现leader interactive turn**：负责人也先探测并用只读interactive Run分析；输出策略必须过Schema且引用同部门候选。
- [ ] **步骤 3：原子创建EmployeeTask与ExecutionSnapshot**：全部候选可用后单事务插入；任何一人失败不创建部分子任务。
- [ ] **步骤 4：实现阶段推进guard**：全部required EmployeeTask accepted且Review blocker清零才允许DepartmentTask completed。
- [ ] **步骤 5：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/orchestration/test_department_flow.py tests/orchestration/test_collaboration.py -v --cov=ibreeze.orchestration.department_flow --cov=ibreeze.orchestration.collaboration --cov=ibreeze.orchestration.assignment --cov-branch --cov-fail-under=100
  git add sidecar
  git commit -m "feat(orchestration): coordinate department employees"
  ```

**完成标准：** 多Agent协作使用隔离Workspace和不可变输入；参与职员自动进入Review池。

### P7-T04：标准软件需求工作流模板

**依赖：** P7-T03。

**文件：**

- 创建：`sidecar/resources/workflow-templates/software_requirement_delivery.v1.json`
- 创建：`sidecar/ibreeze/orchestration/workflow_templates.py`
- 创建：`sidecar/tests/orchestration/test_software_workflow.py`

**产生接口：** H.9七阶段DAG与12章完成门禁。

- [ ] **步骤 1：写模板hash和DAG失败测试**：阶段键、responsibility、依赖必须精确匹配H.9；删边、加边、成环或改hash失败。
- [ ] **步骤 2：实现职责匹配实例化**：不按部门显示名；每stage选择评分合格部门并把模板SHA写Plan Snapshot。
- [ ] **步骤 3：实现阶段质量门禁**：架构三文档、开发代码+单测、独立测试用例、首轮问题、修复+全review、终轮回归、GM终审逐项需Artifact/Report evidence。
- [ ] **步骤 4：无UI端到端运行fixture**：fake adapters执行完整DAG，断言implementation与test_design并行，后续严格依赖。
- [ ] **步骤 5：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/orchestration/test_software_workflow.py -v --cov=ibreeze.orchestration.workflow_templates --cov-branch --cov-fail-under=100
  git add sidecar packages/contracts
  git commit -m "feat(workflows): add software delivery lifecycle"
  ```

**完成标准：** 标准研发任务可机械走完用户要求的架构、开发、测试、修复、终测和总经理闭环。

### P7-T05：部门报告、公司级Review、返工与最终报告

**依赖：** P7-T03、P7-T04、P6-T04。

**文件：**

- 创建：`sidecar/ibreeze/orchestration/{reports.py,rework.py,final_review.py}`
- 创建：`sidecar/tests/orchestration/{test_reports.py,test_rework.py,test_final_review.py}`

**产生接口：** department report、company-level report Review、GM final report；11.7规则。

- [ ] **步骤 1：写报告证据完整性失败测试**：缺deliverable、verification、review round、closed issue、risk、evidence任一失败。
- [ ] **步骤 2：实现部门报告公司级池**：GM Employee未出现在该报告的 `artifact_contributors` 时必选；仅执行review Run或提交ReviewReport不算贡献。再加GM office当前任务参与职员至最多2人，所有Artifact贡献者均排除；通过后投影到company conversation。
- [ ] **步骤 3：实现返工任务**：每个跨部门问题有owner department/employee、acceptance和source evidence；沿原Plan边界，不静默改目标。
- [ ] **步骤 4：实现最终报告guard**：全部department report通过、blocker/high closed、验收有证据、workspace ready；final report不再递归Review。
- [ ] **步骤 5：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/orchestration/test_reports.py tests/orchestration/test_rework.py tests/orchestration/test_final_review.py -v --cov=ibreeze.orchestration.reports --cov=ibreeze.orchestration.rework --cov=ibreeze.orchestration.final_review --cov-branch --cov-fail-under=100
  git add sidecar packages/contracts docs/用户手册.md
  git commit -m "feat(orchestration): close reports rework and final review"
  ```

**完成标准：** CompanyTask completed前证据链完整；总经理最终报告可追溯所有部门产物与问题。

### P7 阶段出口

- [ ] PV-001..PV-011、评分、Plan确认hash和未确认只读门禁全部通过。
- [ ] 七项可用性、四协作策略、Review分配和替换守卫全部通过。
- [ ] fake Agent无UI完整运行标准软件需求DAG，所有阶段证据齐全。
- [ ] 返工和最终报告不能绕过blocker/high或验收证据。

---

## 11. P8：知识、检索、备份与恢复

### P8-T01：知识Schema、导入、权限与访问日志

**依赖：** P3-T01、P4-T04、P6-T03。

**文件：**

- 创建：`sidecar/migrations/20260722001000_knowledge_backup.sql`
- 创建：`sidecar/ibreeze/knowledge/{model.py,importer.py,permissions.py,chunking.py}`
- 使用：P0-T02 已创建的 `packages/contracts/domain-events/{knowledge.imported.v1.schema.json,knowledge.removed.v1.schema.json}`
- 创建：`sidecar/tests/knowledge/{test_import.py,test_permissions.py,test_chunking.py}`

**产生接口：** `knowledge.import/remove/list`；H.13知识表与access logs；J.6分块与检索权限候选集合。`knowledge.search` 由P8-T02在这些权限原语上实现。

- [ ] **步骤 1：写权限与来源约束失败测试**：用相同关键词植入其他company/department/task/private employee数据，搜索候选阶段就不得出现，不允许模型后过滤；覆盖 scope 字段组合、跨公司引用、Artifact与消息事件来源二选一，以及消息投影重建后知识来源仍稳定。
- [ ] **步骤 2：实现import与chunking**：Markdown/text/code/JSON/YAML按J.6固定token和overlap；每chunk保存 source Artifact id 或 append-only `source_message_event_id`、hash、visibility和scope，禁止引用可重建的 `conversation_messages.id` 作为长期事实。每个新chunk写 `aggregate_type=knowledge_item/version=1` 的 `knowledge.imported`，且导入事实、事件和至少一个 `knowledge.index.requested` Outbox必须在同一事务提交；事件payload不得含正文。
- [ ] **步骤 3：实现remove**：每个待删除item先以原version+1写 `knowledge.removed` 再删除，删除事实、事件与相同索引Outbox必须同事务；历史access log只保留query hash和引用，不保留query原文。测试证明提交失败三者全无、重复Outbox按event id幂等。
- [ ] **步骤 4：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/knowledge/test_import.py tests/knowledge/test_permissions.py tests/knowledge/test_chunking.py -v --cov=ibreeze.knowledge --cov-branch --cov-fail-under=100
  git add sidecar packages/rpc-schema
  git commit -m "feat(knowledge): import scoped local knowledge"
  ```

**完成标准：** 检索前权限过滤可由测试证明；知识原文不进入审计和日志。

### P8-T02：ONNX Embedding、FTS5、LanceDB与混合检索

**依赖：** P8-T01、P0-T04、P4-T05。

**文件：**

- 创建：`sidecar/ibreeze/knowledge/{embedding.py,fts.py,lance.py,hybrid.py,generations.py,index_worker.py}`
- 创建：`sidecar/tests/knowledge/{test_embedding.py,test_hybrid.py,test_generations.py,test_index_worker.py}`

**产生接口：** `knowledge.search`；384维E5 embedding；BM25 top50 + cosine top50 + RRF k=60 + dedupe + top12。

- [ ] **步骤 1：写golden embedding与RRF测试**：固定文本hash对应向量维度/有限值/近似hash；固定rank列表得到精确RRF顺序。
- [ ] **步骤 2：实现ProcessPool embedding与批量写入**：主event loop不运行ONNX；资源先验manifest/hash，只读加载；失败进入diagnostics。ProcessPool结果最多累计128条后向容量32的单写队列提交一个批次事务，满时await背压；1万条fixture断言提交批次数不超过 `ceil(10000/128)`，禁止逐条或旁路写入。
- [ ] **步骤 3：实现内部索引Worker、generation构建和原子激活**：Outbox按company合并提交H.10 `knowledge_index`内部任务，不创建AgentRun。同公司单active任务抓取最新知识事件sequence（从未有知识事件时为0）和完整id/hash快照，FTS行与Lance向量均写新generation id；building完成后再次比对快照、最新sequence、384维和数量，全部一致才在一个事务更新知识行generation引用并切换active/retired。有变化则failed、清理building数据并合并重排，旧active继续服务；切换后的旧generation由幂等清理器删除，崩溃重跑。空集合也激活空generation；孤儿或跨公司 generation 必须由外键/服务双重拒绝。
- [ ] **步骤 4：实现hybrid search**：先读取公司active generation；SQLite权限集合确定后，FTS/Lance都同时按该generation id和候选白名单过滤，禁止混读building/retired代际；写knowledge_access_logs候选顺序、命中顺序和Context hash。测试在building、切换提交和旧数据清理失败三个时点并发查询，结果只能来自完整旧代或完整新代。
- [ ] **步骤 5：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/knowledge/test_embedding.py tests/knowledge/test_hybrid.py tests/knowledge/test_generations.py tests/knowledge/test_index_worker.py -v --cov=ibreeze.knowledge --cov-branch --cov-fail-under=100
  git add sidecar tests/fixtures
  git commit -m "feat(knowledge): add local hybrid retrieval"
  ```

**完成标准：** 1万条fixture检索满足K.16；Lance损坏可从SQLite重建且不影响业务事实。

### P8-T03：一致备份、保留与恢复

**依赖：** P8-T02、P3-T05、P6-T03。

**文件：**

- 创建：`sidecar/ibreeze/backup/{manifest.py,create.py,restore.py,retention.py}`
- 创建：`sidecar/tests/backup/{test_create.py,test_restore.py,test_corruption.py,test_retention.py}`
- 创建：`tests/fixtures/backups/`

**产生接口：** `backup.create/restore/list`；J.9/J.10；H.13.1记录。

- [ ] **步骤 1：写备份边界失败测试**：当前写事务超10秒、CAS缺失、hash错、路径逃逸、symlink、tampered manifest、SQLite corruption、migration失败和磁盘不足。
- [ ] **步骤 2：实现snapshot barrier**：暂停新写、等当前事务、SQLite Online Backup、收集被引用CAS/catalog/skill locks、manifest SHA、tar.zst temp+fsync+rename。
- [ ] **步骤 3：实现严格排除**：测试备份包不存在Keychain/CLI state/API key/log/temp worktree/外部仓库；代码变化只以Artifact patch/commit证据存在。
- [ ] **步骤 4：实现staging restore**：完整校验→migrate→FK/integrity→Artifact refs→重建FTS/Lance→grants stale→原子目录切换；任何失败保持active原Profile。
- [ ] **步骤 5：实现保留**：自动备份按日历周归档，保留最近7个日备份和4个周备份；手动备份不自动清理。删除仅针对已解析、校验属于当前Profile backup root且status=completed的自动备份，遵循H.13.1失败恢复状态。
- [ ] **步骤 6：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/backup -v --cov=ibreeze.backup --cov-branch --cov-fail-under=100
  git add sidecar tests/fixtures/backups docs/用户手册.md docs/部署文档.md
  git commit -m "feat(backup): add consistent local backup and restore"
  ```

**完成标准：** 随机中断每个恢复步骤都不破坏原Profile；恢复后必须重授权Workspace和重新探测Agent/Provider。

### P8-T04：启动对账与恢复编排

**依赖：** P5-T07、P8-T03、P4-T05。

**文件：**

- 创建：`sidecar/ibreeze/application/startup_reconciliation.py`
- 创建：`sidecar/tests/recovery/{test_startup.py,test_run_recovery.py,test_process_reconciliation.py}`

**产生接口：** 21.2六步启动对账；`run.resume`恢复门禁。

- [ ] **步骤 1：生成崩溃点fixture**：queued/probing/starting/running/tool started/tool completed/verifying/waiting approval/Sidecar lost/Rust lost各一份。
- [ ] **步骤 2：实现对账顺序**：migration/files→nonterminal runs→PID/native session/checkpoint→retrying或waiting approval→projection rebuild→knowledge generation对账→scheduler enable。知识对账逐公司检查无active、null generation引用、active水位落后最新 `knowledge.imported/removed`、id/hash集合不一致及building超1小时；任一成立按P8-T02合并排队全量重建，包括删除最后一条后的空generation。
- [ ] **步骤 3：禁止启动期间新写**：对账完成前公开写RPC返回固定unavailable；读health显示recovery phase和进度，不显示敏感路径。
- [ ] **步骤 4：验证并提交**：

  ```bash
  uv run --directory sidecar pytest tests/recovery -v --cov=ibreeze.application.startup_reconciliation --cov-branch --cov-fail-under=100
  git add sidecar docs/用户手册.md
  git commit -m "feat(recovery): reconcile runs after restart"
  ```

**完成标准：** 确定性步骤自动恢复，不确定副作用请求人工批准，旧PID不会误杀无关进程。

### P8 阶段出口

- [ ] 知识权限预过滤、RRF、generation对账和1万条性能门禁通过。
- [ ] 备份敏感数据排除、损坏检测、staging restore、grant stale和原子切换通过。
- [ ] 每个关键崩溃点都有恢复期望，fault injection结果一致。
- [ ] Profile恢复后SQLite FK/integrity、Artifact引用和Lance generation全部一致。

---

## 12. P9：桌面 React UI

### P9-T01：应用壳、路由、状态边界与RPC Client

**依赖：** P2-T01、P3-T02；接入页面前对应RPC必须accepted。

**文件：**

- 创建：`apps/desktop/src/app/{router.tsx,providers.tsx,error-boundary.tsx,layout.tsx}`
- 创建：`apps/desktop/src/shared/rpc/{client.ts,errors.ts,query-keys.ts,event-sync.ts}`
- 创建：`apps/desktop/src/shared/format/{time.ts,number.ts}`
- 创建：`apps/desktop/src/store/ui-store.ts`
- 创建：`apps/desktop/tests/{router.test.tsx,state-boundary.test.ts,time.test.ts,number.test.ts}`

**产生接口：** K.1全部路由；J.13 TanStack Query/Zustand边界；Asia/Shanghai和数值格式化器。

- [ ] **步骤 1：写路由和状态边界失败测试**

  未登录只能访问auth/offline；登录后URL company与Query数据不一致拒绝；Zustand state snapshot不得出现company/department/employee/task/run实体字段。

- [ ] **步骤 2：实现RPC Client**

  所有调用通过Tauri `rpc_request`；写请求生成并在用户显式重试时复用idempotency key；前端只按`error.data.code`分支。

- [ ] **步骤 3：实现事件同步**

  按scope保存last sequence；跳号暂停实时应用并调用event.replay；compacted marker覆盖range后恢复。未知事件只触发事实query刷新。

- [ ] **步骤 4：实现统一格式化**

  时间测试覆盖Z、offset、无时区和夏令时宿主；数值覆盖0、整数、1.2、1.234、NaN/null。组件禁止直接`new Date(...).toLocaleString()`或原始小数输出。

- [ ] **步骤 5：验证并提交**

  ```bash
  npm --prefix apps/desktop run test -- router.test.tsx state-boundary.test.ts time.test.ts number.test.ts
  npm --prefix apps/desktop run typecheck
  git add apps/desktop packages/ui docs/用户手册.md
  git commit -m "feat(desktop-ui): add routed rpc application shell"
  ```

**完成标准：** 页面无直接HTTP/文件/Keychain访问；事实状态唯一存TanStack Query，UI瞬态才进Zustand。

### P9-T02：Server、登录、注册、改密与离线解锁

**依赖：** P9-T01、P2-T04、P2-T05。

**文件：**

- 创建：`apps/desktop/src/features/auth/{server-page.tsx,login-page.tsx,register-page.tsx,password-change-page.tsx,offline-page.tsx,schemas.ts}`
- 创建：`apps/desktop/tests/auth/server-page.test.tsx`
- 创建：`apps/desktop/tests/auth/login-page.test.tsx`
- 创建：`apps/desktop/tests/auth/register-page.test.tsx`
- 创建：`apps/desktop/tests/auth/password-change-page.test.tsx`
- 创建：`apps/desktop/tests/auth/offline-page.test.tsx`
- 创建：`tests/e2e/auth.spec.ts`

**页面契约：** K.2全部行为；注册confirm只客户端发送前校验，REST request不含confirm；受限改密不打开Profile。

- [ ] **步骤 1：写表单与导航失败测试**：非法origin、HTTP生产、邮箱trim/lowercase、8/128密码、confirm不一致、重复邮箱、must-change、离线票据过期、Keychain拒绝和目录sync fallback。
- [ ] **步骤 2：实现Server页**：保存前只调用`/health/ready`经Rust；错误显示稳定component code，不展示连接串。
- [ ] **步骤 3：实现认证页**：提交期间禁重复；register成功预填login；must-change路由锁定；成功后目录sync再open Profile。
- [ ] **步骤 4：实现Offline页**：只显示verified meta的masked identifier；无密码输入；离线banner常驻，网络恢复立即refresh。
- [ ] **步骤 5：Playwright/Tauri E2E并提交**：

  ```bash
  npm --prefix apps/desktop run test -- auth
  npm --prefix tests/e2e run test -- auth.spec.ts
  git add apps/desktop tests/e2e docs/用户手册.md
  git commit -m "feat(desktop-ui): add secure authentication flows"
  ```

**完成标准：** 注册、登录、强制改密、online refresh、logout和offline unlock全部通过真实Rust边界E2E。

### P9-T03：首次向导、底座与Skill页面

**依赖：** P9-T02、P3-T04、P4-T01。

**文件：**

- 创建：`apps/desktop/src/features/onboarding/onboarding-wizard.tsx`
- 创建：`apps/desktop/src/features/onboarding/agent-provider-step.tsx`
- 创建：`apps/desktop/src/features/onboarding/gm-profile-step.tsx`
- 创建：`apps/desktop/src/features/onboarding/company-step.tsx`
- 创建：`apps/desktop/src/features/onboarding/department-template-step.tsx`
- 创建：`apps/desktop/src/features/profiles/profiles-page.tsx`
- 创建：`apps/desktop/src/features/profiles/profile-editor.tsx`
- 创建：`apps/desktop/src/features/skills/skills-page.tsx`
- 创建：`apps/desktop/src/features/skills/skill-detail.tsx`
- 创建：`apps/desktop/tests/onboarding/onboarding-wizard.test.tsx`
- 创建：`apps/desktop/tests/profiles/profile-editor.test.tsx`
- 创建：`apps/desktop/tests/skills/skills-page.test.tsx`
- 创建：`tests/e2e/onboarding.spec.ts`
- 创建：`tests/e2e/profiles.spec.ts`

**页面契约：** K.3五步向导；E.5底座表单；Agent CLI/API Model显式二选一；Skill compatibility/install/publish/retire。

- [ ] **步骤 1：写向导恢复失败测试**：每步独立提交后关闭重开，从第一个未完成步骤恢复；无published GM base时company create禁用。
- [ ] **步骤 2：实现底座draft editor**：只展示当前verified catalog；Agent选择agent/model，API选择provider/model/credential ref；系统prompt、capabilities、tools、skills、timeout/retry严格校验。
- [ ] **步骤 3：实现Skill状态**：清楚区分catalog available、installed、disabled、corrupt、incompatible；删除被引用Skill显示稳定阻断原因。
- [ ] **步骤 4：实现publish/retire确认**：publish展示canonical hash和锁定版本；retire列出active employee引用，不能通过前端隐藏绕过服务端。
- [ ] **步骤 5：验证并提交**：

  ```bash
  npm --prefix apps/desktop run test -- onboarding profiles skills
  npm --prefix tests/e2e run test -- onboarding.spec.ts profiles.spec.ts
  git add apps/desktop tests/e2e docs/用户手册.md
  git commit -m "feat(desktop-ui): add onboarding profiles and skills"
  ```

**完成标准：** 用户无需理解底层JSON即可创建两类底座，UI不能构造未发布或不兼容绑定。

### P9-T04：公司、部门、职员与职责流转页面

**依赖：** P9-T01、P4-T01、P4-T02。

**文件：**

- 创建：`apps/desktop/src/features/companies/company-list-page.tsx`
- 创建：`apps/desktop/src/features/companies/company-overview-page.tsx`
- 创建：`apps/desktop/src/features/companies/company-form.tsx`
- 创建：`apps/desktop/src/features/departments/departments-page.tsx`
- 创建：`apps/desktop/src/features/departments/department-form.tsx`
- 创建：`apps/desktop/src/features/departments/responsibility-graph.tsx`
- 创建：`apps/desktop/src/features/employees/employees-page.tsx`
- 创建：`apps/desktop/src/features/employees/employee-form.tsx`
- 创建：`apps/desktop/tests/companies/company-form.test.tsx`
- 创建：`apps/desktop/tests/companies/company-overview.test.tsx`
- 创建：`apps/desktop/tests/departments/department-form.test.tsx`
- 创建：`apps/desktop/tests/departments/responsibility-graph.test.tsx`
- 创建：`apps/desktop/tests/employees/employee-form.test.tsx`
- 创建：`tests/e2e/company-management.spec.ts`

**页面契约：** K.4；公司介绍/业务流转必填；部门职能/结构化职责；leader/employee；模板仅显式创建普通部门。

- [ ] **步骤 1：写字段、scope和乐观锁测试**：1/100、1/20000、1/10000边界、同名、跨company URL、409 refresh、不自动覆盖用户输入。
- [ ] **步骤 2：实现Company list/detail/form**：显示GM office、流转、可用性和任务；edit展示Revision diff并提示只影响新任务。
- [ ] **步骤 3：实现Department DAG editor**：添加边即时前端检测环，但保存仍由Sidecar验证；职责字段不能只用自然语言代替结构化项。
- [ ] **步骤 4：实现Employee管理**：同部门显示名、base version、status、workflow role；active assignment时禁调岗/停用并展示任务引用。
- [ ] **步骤 5：实现归档确认**：列出非终态阻断；GM office无归档按钮；archived只读。
- [ ] **步骤 6：验证并提交**：

  ```bash
  npm --prefix apps/desktop run test -- companies departments employees
  npm --prefix tests/e2e run test -- company-management.spec.ts
  git add apps/desktop tests/e2e docs/用户手册.md
  git commit -m "feat(desktop-ui): manage companies departments employees"
  ```

**完成标准：** UI完整表达模拟公司工作流且不出现租户/真实组织概念。

### P9-T05：公司会话、部门会话与Plan确认

**依赖：** P9-T04、P4-T03、P7-T01。

**文件：**

- 创建：`apps/desktop/src/features/conversations/{company-page.tsx,department-page.tsx,message-list.tsx,composer.tsx,plan-card.tsx,event-timeline.tsx}`
- 创建：`apps/desktop/tests/conversations/company-page.test.tsx`
- 创建：`apps/desktop/tests/conversations/department-page.test.tsx`
- 创建：`apps/desktop/tests/conversations/composer.test.tsx`
- 创建：`apps/desktop/tests/conversations/plan-card.test.tsx`
- 创建：`apps/desktop/tests/conversations/event-timeline.test.tsx`
- 创建：`tests/e2e/plan-confirmation.spec.ts`

**页面契约：** K.5；公司输入→GM分析→Plan卡；确认/要求修改/拒绝；部门显示分析、资源、分派、Artifact、Review、修复、复测和报告。

- [ ] **步骤 1：写消息意图和并发Plan测试**：普通composer两nullable；plan card revision带target id；approved无修改；cancelled重发带supersedes；确认前重新fetch hash，409只刷新不重试。
- [ ] **步骤 2：实现虚拟消息列表和Artifact refs**：按sequence稳定渲染，employee display name为主，agent/model只在run drawer。
- [ ] **步骤 3：实现Plan card**：展示需求理解、部门DAG、deliverables、acceptance、权限和资源风险；按钮操作复用idempotency key。
- [ ] **步骤 4：实现Department conversation**：resource failure提供recheck/replace/report GM；不提供独立Reviewer配置。
- [ ] **步骤 5：验证并提交**：

  ```bash
  npm --prefix apps/desktop run test -- conversations
  npm --prefix tests/e2e run test -- plan-confirmation.spec.ts
  git add apps/desktop tests/e2e docs/用户手册.md
  git commit -m "feat(desktop-ui): add hierarchical task conversations"
  ```

**完成标准：** 用户不确认Plan时看不到部门执行；消息跳号和Plan冲突不会产生重复任务。

### P9-T06：任务、Runtime、Review、审批与Workspace应用

**依赖：** P9-T05、P5、P6、P7。

**文件：**

- 创建：`apps/desktop/src/features/tasks/task-list-page.tsx`
- 创建：`apps/desktop/src/features/tasks/task-detail-page.tsx`
- 创建：`apps/desktop/src/features/tasks/task-graph.tsx`
- 创建：`apps/desktop/src/features/runtime/runtime-page.tsx`
- 创建：`apps/desktop/src/features/runtime/run-detail-drawer.tsx`
- 创建：`apps/desktop/src/features/review/review-issues-panel.tsx`
- 创建：`apps/desktop/src/features/approvals/approval-list.tsx`
- 创建：`apps/desktop/src/features/workspace/workspace-apply-panel.tsx`
- 创建：`apps/desktop/tests/tasks/task-detail-page.test.tsx`
- 创建：`apps/desktop/tests/tasks/task-graph.test.tsx`
- 创建：`apps/desktop/tests/runtime/run-detail-drawer.test.tsx`
- 创建：`apps/desktop/tests/review/review-issues-panel.test.tsx`
- 创建：`apps/desktop/tests/approvals/approval-list.test.tsx`
- 创建：`apps/desktop/tests/workspace/workspace-apply-panel.test.tsx`
- 创建：`tests/e2e/task-runtime-review.spec.ts`
- 创建：`tests/e2e/workspace-apply.spec.ts`

**页面契约：** K.6全部字段与按钮；Run timeline、queue/lease/PID/checkpoint；ReviewIssue闭环；one-shot approval；apply/abandon/cleanup。

- [ ] **步骤 1：写状态按钮矩阵**：从H.7机器可读状态表生成每状态可见操作，UI不展示非法transition；服务端拒绝仍按code刷新。
- [ ] **步骤 2：实现任务DAG和证据页**：Department/Employee状态、Artifact版本、Review round、Verification和Evidence可逐级跳转。
- [ ] **步骤 3：实现Runtime详情**：事件sequence、native session、process、attempt、exit/failure、checkpoint；cancel必填reason，resume只在可恢复状态。
- [ ] **步骤 4：实现Review和Approval**：Issue显示severity/owner/evidence/expected/actual/solution；Approval显示规范路径、动作、old hash、new摘要、expiry，只能本次或拒绝。
- [ ] **步骤 5：实现Workspace应用**：完成后展示baseline/integration/diff；二次确认apply目标；只有applied/abandoned且无active Run显示cleanup。
- [ ] **步骤 6：验证并提交**：

  ```bash
  npm --prefix apps/desktop run test -- tasks runtime review approvals workspace
  npm --prefix tests/e2e run test -- task-runtime-review.spec.ts workspace-apply.spec.ts
  git add apps/desktop tests/e2e docs/用户手册.md
  git commit -m "feat(desktop-ui): expose task runtime and review evidence"
  ```

**完成标准：** 用户能观察和控制完整任务闭环，但不能从UI跳过状态机、权限或Review门禁。

### P9-T07：设置与诊断中的知识、备份和更新操作

**依赖：** P9-T01、P8、P2-T08、P3-T05。

**文件：**

- 创建：`apps/desktop/src/features/settings/settings-page.tsx`
- 创建：`apps/desktop/src/features/settings/knowledge-panel.tsx`
- 创建：`apps/desktop/src/features/settings/backup-panel.tsx`
- 创建：`apps/desktop/src/features/diagnostics/diagnostics-page.tsx`
- 创建：`apps/desktop/src/features/diagnostics/updater-panel.tsx`
- 创建：`apps/desktop/tests/settings/settings-page.test.tsx`
- 创建：`apps/desktop/tests/settings/knowledge-panel.test.tsx`
- 创建：`apps/desktop/tests/settings/backup-panel.test.tsx`
- 创建：`apps/desktop/tests/diagnostics/diagnostics-page.test.tsx`
- 创建：`apps/desktop/tests/diagnostics/updater-panel.test.tsx`
- 创建：`tests/e2e/backup-restore.spec.ts`
- 创建：`tests/e2e/settings.spec.ts`

**路由约束：** 知识、备份和更新不新增独立路由。知识源与备份作为 `/settings` 的操作面板；诊断导出和更新作为 `/diagnostics` 的操作面板。设置表单仍只有 K.6 指定的 CLI 全局并发与日志保留天数两个可写配置。

- [ ] **步骤 1：写设置边界测试**：配置表单只含两项，范围与默认精确；Backend origin不在settings；expected_version冲突刷新；三个操作面板不写入settings表。
- [ ] **步骤 2：实现知识操作面板**：import使用Rust只读选择器；展示visibility/source/hash/status；search结果显示citation和scope，不显示其他company候选。
- [ ] **步骤 3：实现备份操作面板**：create/list/restore状态、破坏警告、恢复期间全局只读；成功后要求grant/agent/provider重新检查。
- [ ] **步骤 4：实现诊断与更新面板**：诊断导出路径由Rust返回；update precondition逐项展示；失败进入恢复说明，不承诺自动降级DB。
- [ ] **步骤 5：验证并提交**：

  ```bash
  npm --prefix apps/desktop run test -- settings-page knowledge-panel backup-panel diagnostics-page updater-panel
  npm --prefix tests/e2e run test -- backup-restore.spec.ts settings.spec.ts
  git add apps/desktop tests/e2e docs/用户手册.md
  git commit -m "feat(desktop-ui): add settings recovery and diagnostics"
  ```

**完成标准：** 所有K.1桌面路由有可用页面、空态、loading、错误和权限态。

### P9 阶段出口

- [ ] K.1–K.6所有路由和行为有组件测试与Tauri E2E。
- [ ] 所有时间和数值通过统一formatter，静态扫描无直接原始格式化。
- [ ] React UI无HTTP、filesystem、Keychain、CLI直接调用。
- [ ] 桌面手写TypeScript 100%覆盖，真实用户主链路E2E通过。

---

## 13. P10：管理后台 React UI

### P10-T01：Admin应用壳、认证与OpenAPI Client

**依赖：** P1-T02、P1-T07、P0-T02。

**文件：**

- 创建：`apps/admin-web/src/app/{router.tsx,providers.tsx,layout.tsx}`
- 创建：`apps/admin-web/src/shared/api/{client.ts,errors.ts,query-keys.ts}`
- 创建：`apps/admin-web/src/features/auth/login-page.tsx`
- 创建：`apps/admin-web/src/features/auth/change-initial-password-page.tsx`
- 创建：`apps/admin-web/src/features/auth/auth-guard.tsx`
- 创建：`apps/admin-web/tests/auth/login-page.test.tsx`
- 创建：`apps/admin-web/tests/auth/change-initial-password-page.test.tsx`
- 创建：`apps/admin-web/tests/auth/auth-guard.test.tsx`

- [ ] **步骤 1：写token存储失败测试**：Access只在React memory；刷新依赖HttpOnly Cookie；localStorage/sessionStorage/IndexedDB均无token。
- [ ] **步骤 2：实现admin login/refresh/logout**：must-change只可改密/logout；401只refresh一次；audience错误退出。
- [ ] **步骤 3：实现路由守卫和统一Problem Details**：字段错误定位，409刷新，写请求不自动重试。
- [ ] **步骤 4：验证并提交**：

  ```bash
  npm --prefix apps/admin-web run test -- auth
  npm --prefix apps/admin-web run typecheck
  git add apps/admin-web docs/用户手册.md
  git commit -m "feat(admin-ui): add secure admin shell"
  ```

**完成标准：** 默认管理员首次只能改密；浏览器持久存储无认证Token。

### P10-T02：用户管理页面

**依赖：** P10-T01、P1-T03。

**文件：** `apps/admin-web/src/features/users/users-page.tsx`、`apps/admin-web/src/features/users/user-form.tsx`、`apps/admin-web/src/features/users/reset-password-dialog.tsx`、`apps/admin-web/src/features/users/revoke-sessions-dialog.tsx`、`apps/admin-web/tests/users/users-page.test.tsx`、`apps/admin-web/tests/users/user-form.test.tsx`、`apps/admin-web/tests/users/protected-admin.test.tsx`、`tests/e2e/admin-users.spec.ts`。

- [ ] **步骤 1：写字段矩阵与保护按钮测试**：两种用户create字段、筛选/cursor、PATCH字段、reset/revoke；protected admin不渲染删除/禁用/改名/改类型。
- [ ] **步骤 2：实现列表、表单和确认对话框**：密码只在submit内存；成功立即清空；不回显hash/失败计数/token。
- [ ] **步骤 3：实现409和错误处理**：version冲突关闭提交态、刷新事实、保留非敏感表单字段。
- [ ] **步骤 4：验证并提交**：

  ```bash
  npm --prefix apps/admin-web run test -- users
  npm --prefix tests/e2e run test -- admin-users.spec.ts
  git add apps/admin-web tests/e2e docs/用户手册.md
  git commit -m "feat(admin-ui): manage admin and application users"
  ```

**完成标准：** 两类用户管理完整，保护管理员操作在UI和API均被阻断。

### P10-T03：Agent、Model、Provider、Skill与兼容规则页面

**依赖：** P10-T01、P1-T04、P1-T05。

**文件：**

- 创建：`apps/admin-web/src/features/agents/agents-page.tsx`
- 创建：`apps/admin-web/src/features/agents/agent-editor.tsx`
- 创建：`apps/admin-web/src/features/models/models-page.tsx`
- 创建：`apps/admin-web/src/features/models/model-editor.tsx`
- 创建：`apps/admin-web/src/features/providers/providers-page.tsx`
- 创建：`apps/admin-web/src/features/providers/provider-editor.tsx`
- 创建：`apps/admin-web/src/features/skills/skills-page.tsx`
- 创建：`apps/admin-web/src/features/skills/skill-editor.tsx`
- 创建：`apps/admin-web/src/features/compatibility/compatibility-page.tsx`
- 创建：`apps/admin-web/src/features/compatibility/compatibility-editor.tsx`
- 创建：`apps/admin-web/src/features/catalog/validation-report.tsx`
- 创建：`apps/admin-web/tests/catalog/resource-state.test.tsx`
- 创建：`apps/admin-web/tests/catalog/agent-bindings.test.tsx`
- 创建：`apps/admin-web/tests/catalog/provider-bindings.test.tsx`
- 创建：`apps/admin-web/tests/catalog/skill-upload.test.tsx`
- 创建：`apps/admin-web/tests/catalog/compatibility.test.tsx`
- 创建：`tests/e2e/admin-catalog.spec.ts`
- 创建：`tests/e2e/admin-skill.spec.ts`

- [ ] **步骤 1：写状态和字段测试**：draft可编辑、validated字段变更退draft、published只读并可clone；Agent versions、两类bindings、Skill multipart和compatibility均有边界测试。
- [ ] **步骤 2：实现目录编辑器**：版本范围、platform、probe argv、network domains、context/tool/vision能力采用结构化控件，不允许自然语言代替。
- [ ] **步骤 3：实现Skill上传报告**：显示object/content hash、signing key、manifest字段和具体校验问题；不得在浏览器解压作为安全依据。
- [ ] **步骤 4：实现validation report**：按resource/rule id定位字段和关联资源；只有后端validated状态可进入release selection。
- [ ] **步骤 5：验证并提交**：

  ```bash
  npm --prefix apps/admin-web run test -- catalog
  npm --prefix tests/e2e run test -- admin-catalog.spec.ts admin-skill.spec.ts
  git add apps/admin-web tests/e2e docs/用户手册.md
  git commit -m "feat(admin-ui): edit versioned global catalog"
  ```

**完成标准：** Admin UI覆盖G.13每个管理路由且不能编辑published资源。

### P10-T04：目录发布、紧急禁用、审计与仪表盘

**依赖：** P10-T03、P1-T06、P1-T07。

**文件：** `apps/admin-web/src/features/releases/releases-page.tsx`、`apps/admin-web/src/features/releases/release-confirm-dialog.tsx`、`apps/admin-web/src/features/emergency-disables/emergency-disables-page.tsx`、`apps/admin-web/src/features/audit/audit-page.tsx`、`apps/admin-web/src/features/dashboard/dashboard-page.tsx`、`apps/admin-web/tests/releases/release-confirm.test.tsx`、`apps/admin-web/tests/releases/emergency-disable.test.tsx`、`apps/admin-web/tests/audit/audit-page.test.tsx`、`apps/admin-web/tests/dashboard/dashboard-page.test.tsx`、`tests/e2e/admin-release.spec.ts`。

- [ ] **步骤 1：写发布二次确认测试**：必须展示sequence、resource count、minimum client、manifest SHA；内容变化后旧确认失效。
- [ ] **步骤 2：实现release selection和publish进度**：只选validated；失败显示阶段和request id，不自行重试写请求。
- [ ] **步骤 3：实现emergency disable**：resource/version/action/reason结构化；enable必须更高sequence；历史只读。
- [ ] **步骤 4：实现审计和dashboard**：cursor/filter，before/after脱敏；dashboard只含后台auth/catalog/skill/health，不出现桌面公司任务指标。
- [ ] **步骤 5：验证并提交**：

  ```bash
  npm --prefix apps/admin-web run test -- releases audit
  npm --prefix tests/e2e run test -- admin-release.spec.ts
  git add apps/admin-web tests/e2e docs/用户手册.md
  git commit -m "feat(admin-ui): publish catalog and inspect audit"
  ```

**完成标准：** K.7所有后台路由完成；仪表盘不暗示后台持有桌面业务数据。

### P10 阶段出口

- [ ] 管理后台全部路由、字段矩阵、状态和错误策略有测试。
- [ ] OpenAPI生成client无手写重复DTO且drift为零。
- [ ] 浏览器安全测试确认无Token持久化、敏感响应缓存或published编辑。
- [ ] Admin Web手写TypeScript 100%覆盖。

---

## 14. P11：可观测性、安全、性能、打包与正式发布

### P11-T01：可观测性、日志脱敏与保留策略

**依赖：** P1、P2、P3、P5、P7全部完成。

**文件：**

- 修改：`apps/backend-api/src/ibreeze_backend/observability/metrics.py`
- 修改：`apps/backend-api/src/ibreeze_backend/observability/logging.py`
- 创建：`sidecar/ibreeze/observability/metrics.py`
- 修改：`sidecar/ibreeze/observability/logging.py`
- 创建：`apps/desktop-core/src/observability.rs`
- 创建：`apps/backend-api/tests/observability/test_metrics.py`
- 创建：`apps/backend-api/tests/observability/test_logging.py`
- 创建：`sidecar/tests/observability/test_metrics.py`
- 创建：`sidecar/tests/observability/test_logging.py`
- 创建：`tests/security/test_log_redaction.py`
- 创建：`tests/integration/test_observability.py`

**固定指标字典：** Counter后缀 `_total`，Gauge不加后缀，Histogram后缀 `_seconds/_bytes`。延迟桶固定为 `0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2.5,5,10,30` 秒；未经设计变更不得增加动态标签。

| 位置 | 指标 | 类型 | 允许标签 |
|---|---|---|---|
| Backend | `ibreeze_backend_http_requests_total` | Counter | `route,method,status_class` |
| Backend | `ibreeze_backend_http_request_duration_seconds` | Histogram | `route,method` |
| Backend | `ibreeze_backend_auth_attempts_total` | Counter | `audience,result` |
| Backend | `ibreeze_backend_auth_locked_users` | Gauge | 无 |
| Backend | `ibreeze_backend_catalog_publish_total` | Counter | `result` |
| Backend | `ibreeze_backend_catalog_publish_duration_seconds` | Histogram | 无 |
| Backend | `ibreeze_backend_skill_upload_bytes` | Histogram | `result` |
| Backend | `ibreeze_backend_postgres_pool_connections` | Gauge | `state` |
| Backend | `ibreeze_backend_s3_operations_total` | Counter | `operation,result` |
| Local | `ibreeze_runtime_runs_total` | Counter | `purpose,adapter,result` |
| Local | `ibreeze_runtime_active_runs` | Gauge | `purpose` |
| Local | `ibreeze_runtime_queue_depth` | Gauge | `priority` |
| Local | `ibreeze_sidecar_restarts_total` | Counter | `reason` |
| Local | `ibreeze_checkpoints_total` | Counter | `result` |
| Local | `ibreeze_recovery_decisions_total` | Counter | `decision` |
| Local | `ibreeze_adapter_events_total` | Counter | `adapter,event_type` |
| Local | `ibreeze_knowledge_search_duration_seconds` | Histogram | `mode` |

- [ ] **步骤 1：定义指标字典**：实现设计方案 K.12–K.13 指定的后台和本地指标；每个指标固定名称、类型、单位、标签集合，禁止把 `user_id`、`company_id`、`task_id`、prompt、路径作为高基数标签。
- [ ] **步骤 2：统一结构化日志**：后台、Rust Core、Sidecar均输出 `timestamp/level/component/request_id/run_id/event_type/error_code`；字段缺失写 `null`，禁止各进程自定义同义字段。
- [ ] **步骤 3：实现脱敏器**：对password、token、API key、Authorization、credential handle值和敏感路径执行键名与模式双重脱敏；测试日志、崩溃报告和审计导出均复用同一规则集。
- [ ] **步骤 4：实现本地日志滚动与清理**：单文件达到20 MiB轮换，最多10个文件；保留天数读取Profile设置 `1..365`（默认30），数量或天数任一超限即删除最旧日志；清理器不删除审计、业务事件、Artifact或恢复检查点。
- [ ] **步骤 5：实现后台指标端点**：仅在管理网络暴露 `/metrics`；不得把桌面公司、任务和会话数据上报后台。
- [ ] **步骤 6：验证并提交**：

  ```bash
  uv run --directory apps/backend-api pytest tests/observability/test_metrics.py tests/observability/test_logging.py -v --cov=ibreeze_backend.observability --cov-branch --cov-fail-under=100
  uv run --directory sidecar pytest tests/observability/test_metrics.py tests/observability/test_logging.py -v --cov=ibreeze.observability --cov-branch --cov-fail-under=100
  python3 -m pytest tests/integration/test_observability.py tests/security/test_log_redaction.py -v
  cargo nextest run --manifest-path apps/desktop-core/Cargo.toml observability
  git add apps tests docs/部署文档.md docs/用户手册.md
  git commit -m "feat(observability): add bounded metrics and redacted logs"
  ```

**完成标准：** 指标可用于定位故障，任何日志、指标和崩溃报告都不含凭据或用户业务正文。

### P11-T02：契约、集成与故障注入测试

**依赖：** P11-T01。

**文件：**

- 创建：`tests/contract/test_openapi_contract.py`
- 创建：`tests/contract/test_rpc_contract.py`
- 创建：`tests/contract/test_json_schema_compatibility.py`
- 创建：`tests/integration/test_postgres_minio_catalog.py`
- 创建：`tests/integration/test_backend_data_boundary.py`
- 创建：`tests/integration/test_sidecar_core_restart.py`
- 创建：`tests/integration/test_outbox_recovery.py`
- 创建：`tests/faults/test_failure_matrix.py`

- [ ] **步骤 1：锁定OpenAPI**：从运行中的Backend导出OpenAPI，与仓库快照和生成client进行diff；使用Schemathesis覆盖所有后台路由的合法、边界与错误响应。
- [ ] **步骤 2：锁定RPC**：逐一发送 J.14 namespace 的合法请求、缺字段、未知字段、错误类型和超时请求；断言统一envelope、错误码、request id和schema version。
- [ ] **步骤 3：锁定Schema兼容性**：为Event、TaskPlan、Report、Review、Catalog snapshot保存golden payload；新增字段必须可选，删除/改义必须提升major且由迁移任务处理。
- [ ] **步骤 4：使用真实依赖集成**：Testcontainers启动PostgreSQL和MinIO，验证目录发布事务、ZIP对象、签名清单和孤儿对象回收，不以mock替代存储语义。
- [ ] **步骤 5：执行进程与存储故障注入**：覆盖Backend断网、Sidecar崩溃、Core重启、SQLite写失败、磁盘空间不足、CLI无输出超时、事件重复/乱序和outbox发送中断；逐项断言设计方案 21.1–21.2 的恢复状态。
- [ ] **步骤 6：验证并提交**：

  ```bash
  python3 -m pytest tests/contract tests/integration tests/faults -v
  npm --prefix packages/contracts run check-generated
  git add tests packages/contracts docs/部署文档.md
  git commit -m "test(system): lock contracts and failure recovery"
  ```

**完成标准：** 契约漂移在CI中失败；设计方案21章每类故障均有自动化测试和唯一恢复动作。

### P11-T03：安全验证与供应链审计

**依赖：** P11-T02。

**文件：**

- 创建：`tests/security/test_auth_boundaries.py`
- 创建：`tests/security/test_company_isolation.py`
- 创建：`tests/security/test_catalog_signature.py`
- 创建：`tests/security/test_skill_zip_safety.py`
- 创建：`tests/security/test_workspace_boundary.py`
- 创建：`tests/security/test_egress_policy.py`
- 创建：`tests/security/test_credential_broker.py`
- 创建：`tests/security/test_process_environment.py`

- [ ] **步骤 1：认证边界测试**：覆盖用户枚举、弱口令、token过期/撤销、refresh重放、管理员与应用用户跨域、protected admin保护、离线宽限到期。
- [ ] **步骤 2：本地隔离测试**：尝试跨company读取Conversation、Task、Artifact、Knowledge和cursor；尝试通过伪造ID、过滤器或导入包绕过隔离，均必须返回固定错误且写审计。
- [ ] **步骤 3：供应链测试**：目录清单、Skill ZIP、runtime asset任一字节改变必须验签失败；ZIP Slip、symlink、重复文件、压缩炸弹、未声明文件和hash不一致必须拒绝。
- [ ] **步骤 4：沙箱与网络测试**：验证工作区内读写、工作区外只读、敏感目录禁止、域名白名单、DNS重绑定/IP直连/重定向越界拒绝；每次拒绝写 `permission.denied`。
- [ ] **步骤 5：凭据测试**：API key不得进入SQLite、环境变量、命令行、事件或日志；CLI subprocess环境使用allowlist；credential broker只向授权adapter和run返回一次性能力。
- [ ] **步骤 6：依赖审计**：执行 `cargo audit`、`pip-audit`、`npm audit --audit-level=high`、SBOM生成和许可证检查；高危漏洞或禁用许可证阻断发布。
- [ ] **步骤 7：验证并提交**：

  ```bash
  python3 -m pytest tests/security -v
  cargo audit --file apps/desktop-core/Cargo.lock
  uv export --project apps/backend-api --frozen --no-dev --format requirements-txt | pip-audit -r /dev/stdin
  uv export --project sidecar --frozen --no-dev --format requirements-txt | pip-audit -r /dev/stdin
  npm --prefix apps/desktop audit --audit-level=high
  npm --prefix apps/admin-web audit --audit-level=high
  npm --prefix packages/contracts audit --audit-level=high
  npm --prefix tests/e2e audit --audit-level=high
  git add tests .github docs/部署文档.md
  git commit -m "test(security): verify trust boundaries and supply chain"
  ```

**完成标准：** K.13威胁模型每个边界均有自动化攻击用例；高危安全问题为零。

### P11-T04：端到端业务流程验收

**依赖：** P9、P10、P11-T03。

**文件：**

- 创建：`tests/e2e/app-registration.spec.ts`
- 创建：`tests/e2e/admin-catalog-release.spec.ts`
- 修改：`tests/e2e/onboarding.spec.ts`
- 创建：`tests/e2e/software-delivery.spec.ts`
- 创建：`tests/e2e/rework-and-review.spec.ts`
- 创建：`tests/e2e/offline-recovery.spec.ts`
- 修改：`tests/e2e/backup-restore.spec.ts`
- 创建：`tests/e2e/fixtures/software-project.ts`

- [ ] **步骤 1：固定验收fixture**：建立一个应用用户、一个目录版本、Codex/Claude Code/OpenCode三类Agent、一个API Model、一家公司、总经理办公室/架构部/开发部/测试部和可用职员；fixture不得依赖开发者本机账户。
- [ ] **步骤 2：验收注册到目录同步**：注册、登录、管理员查看用户、发布目录、客户端验签应用、创建Profile、安装/探测CLI或使用测试adapter。
- [ ] **步骤 3：验收标准研发流**：用户在公司会话提需求；总经理生成结构化方案；用户确认；架构部产出需求/设计/计划；开发部实现与单测；测试部并行写用例并测试；开发部返修；测试部回归；总经理终审和汇总。
- [ ] **步骤 4：验收多Agent协作**：同一Subtask至少两个不同Agent/Model职员分别执行与互审；报告必须可追溯到run、input artifact、output artifact、review issue和处理决策。
- [ ] **步骤 5：验收异常闭环**：覆盖职员不可用替补、拒绝方案后修订、审批过期、CLI中断恢复、离线宽限、目录紧急禁用、合并冲突人工裁决。
- [ ] **步骤 6：验收备份恢复**：在流程中途备份，删除测试Profile后恢复；恢复后event seq、task状态、CAS引用和知识索引一致，运行中任务按策略标记中断而非静默继续。
- [ ] **步骤 7：验证并提交**：

  ```bash
  npm --prefix tests/e2e run test -- app-registration.spec.ts admin-catalog-release.spec.ts onboarding.spec.ts software-delivery.spec.ts rework-and-review.spec.ts offline-recovery.spec.ts backup-restore.spec.ts
  git add tests/e2e docs/用户手册.md
  git commit -m "test(e2e): verify complete company delivery workflow"
  ```

**完成标准：** 设计方案第27章全部功能验收项可由独立环境重复执行，不依赖人工修改数据库或内部状态。

### P11-T05：性能基线与容量门禁

**依赖：** P11-T04。

**文件：**

- 创建：`tests/performance/fixtures.py`
- 创建：`tests/performance/test_startup.py`
- 创建：`tests/performance/test_event_ingestion.py`
- 创建：`tests/performance/test_task_list.py`
- 创建：`tests/performance/test_knowledge_search.py`
- 创建：`tests/performance/test_run_recovery.py`
- 创建：`tests/performance/test_backend_catalog.py`
- 创建：`scripts/run-performance-gate.sh`

- [ ] **步骤 1：固定基线与fixture**：桌面runner固定Apple M1/8 Core/16GB/空闲且接交流电；后台固定4 vCPU/8GB API、4 vCPU/8GB PostgreSQL和1Gbps MinIO。创建1GB Profile DB、100家公司、1万任务；知识集1万个384维条目；Catalog manifest固定10 MiB。所有fixture使用固定seed并校验生成后hash。
- [ ] **步骤 2：固定采样程序**：每项先预热5次，再独立执行3轮、每轮30个样本；每轮分别计算p95，任一轮超限即失败；报告同时保存P50/P95/P99、错误数、硬件和系统版本。
- [ ] **步骤 3：测量五项桌面硬门禁**：Rust spawn到`system.health=healthy`的Sidecar冷启动p95<3s；`task.list`首屏50条UDS往返p95<50ms；SQLite commit到React Query observer收到目标sequence p95<100ms；J.7检索前12条p95<500ms；10个queued/running Run对账p95<10s。每轮同时采集 `write_queue_depth` 的最大值和背压等待时间，深度大于固定容量32直接判为实现违约；知识构建不得通过旁路写入换取性能。
- [ ] **步骤 4：测量两项后台硬门禁**：10 MiB已发布manifest从API收请求到body完成p95<200ms；100并发连接持续60秒，以1:1:1:1:1读取manifest和四类目录列表，错误率必须为0且p95<500ms。
- [ ] **步骤 5：记录非阻断外部指标**：真实CLI启动、原生session恢复和API Provider模型响应仅记录分位数；不混入七项硬门禁，但其参数构造、事件解析、超时和恢复决策仍由单元/契约测试阻断。
- [ ] **步骤 6：输出与执行门禁**：结果写 `artifacts/performance/report.json`；报告逐项包含fixture hash、起止点、三轮样本、阈值和判定，不允许通过提高阈值消除回归。
- [ ] **步骤 7：验证并提交**：

  ```bash
  bash scripts/run-performance-gate.sh
  git add tests/performance scripts .github docs/部署文档.md
  git commit -m "test(performance): enforce deterministic capacity gates"
  ```

**完成标准：** K.16每项指标有固定fixture、计算口径、阈值和CI结果；本地与外部网络指标已分离。

### P11-T06：macOS打包、签名、公证与更新演练

**依赖：** P11-T05、P2-T08。

**文件：**

- 修改：`apps/desktop-core/tauri.conf.json`
- 创建：`apps/desktop-core/entitlements.plist`
- 创建：`scripts/build-desktop-release.sh`
- 创建：`scripts/notarize-desktop.sh`
- 创建：`scripts/verify-desktop-bundle.sh`
- 创建：`tests/release/test_desktop_bundle.py`

- [ ] **步骤 1：锁定bundle布局**：Tauri主程序、Sidecar arm64 binary、migration、schemas和runtime assets进入设计方案 K.9 固定打包流程；缺失、重复或hash不一致立即失败。
- [ ] **步骤 2：配置macOS能力**：entitlements只声明实现所需能力；Hardened Runtime启用；CSP禁止远程脚本、`eval`和未声明连接源。
- [ ] **步骤 3：构建Apple Silicon产物**：在arm64 runner构建PyInstaller Sidecar、Rust Core和Tauri bundle；运行 `codesign --verify --deep --strict` 和Gatekeeper检查。
- [ ] **步骤 4：签名与公证**：密钥仅来自CI secret；提交Apple notarization并staple；构建日志脱敏且不保存证书明文。
- [ ] **步骤 5：更新/回退演练**：生成签名更新manifest，从前一稳定版本升级；模拟下载损坏、签名错误、启动失败和健康检查失败，验证自动保留旧版本并可回退。
- [ ] **步骤 6：净机验证**：在无Python、Node和CLI的干净macOS VM启动；Sidecar必须由内置runtime运行；未安装Agent显示可修复状态，不导致应用崩溃。
- [ ] **步骤 7：验证并提交**：

  ```bash
  bash scripts/build-desktop-release.sh
  bash scripts/verify-desktop-bundle.sh
  python3 -m pytest tests/release/test_desktop_bundle.py -v
  git add apps/desktop scripts tests/release docs/部署文档.md
  git commit -m "build(desktop): package notarized recoverable release"
  ```

**完成标准：** Apple Silicon macOS安装包在净机可启动、可更新、可回退，且不依赖系统Python。

### P11-T07：中心后台生产部署与灾备演练

**依赖：** P11-T05、P1-T08。

**文件：**

- 修改：`deploy/compose.yml`
- 修改：`deploy/nginx.conf`
- 修改：`deploy/.env.example`
- 创建：`scripts/backup-backend.sh`
- 创建：`scripts/restore-backend.sh`
- 创建：`tests/release/test_backend_deployment.py`

- [ ] **步骤 1：构建不可变镜像**：固定digest、非root运行、只读根文件系统、独立临时卷；镜像包含migration但启动进程不自动越权修改schema。
- [ ] **步骤 2：配置TLS和网络**：Nginx 1.27按 K.10 终止TLS并配置固定安全头、认证限流和52 MiB请求上限；宿主只映射443，PostgreSQL、MinIO和metrics处于内部网络；对象桶禁止匿名访问。
- [ ] **步骤 3：配置生产变量**：`env.example`只给变量名与生成说明；JWT/refresh pepper、目录签名私钥、PostgreSQL和MinIO密钥不得提供默认生产值。
- [ ] **步骤 4：实现备份**：一致性备份PostgreSQL、MinIO对象和目录签名元数据；生成manifest、hash和时间点；备份加密并写到独立存储。
- [ ] **步骤 5：实现恢复演练**：在空环境恢复，执行migration检查，验证最新目录release清单、ZIP对象hash、用户登录和审计连续性；记录RPO/RTO实测值。
- [ ] **步骤 6：验证并提交**：

  ```bash
  docker compose -f deploy/compose.yml config
  python3 -m pytest tests/release/test_backend_deployment.py -v
  git add deploy scripts tests/release docs/部署文档.md
  git commit -m "ops(backend): provide hardened deployment and restore drill"
  ```

**完成标准：** 新环境可按文档部署和恢复；桌面业务数据不进入后台备份。

### P11-T08：最终文档、可追溯性与交付门禁

**依赖：** P11-T01至P11-T07。

**文件：** `README.md`、`docs/部署文档.md`、`docs/用户手册.md`、`docs/API文档.md`、`docs/故障排查手册.md`、`docs/安全与隐私说明.md`、`docs/设计方案/AI公司桌面应用设计方案.md`、本实施计划。

- [ ] **步骤 1：同步公共文档**：README给出开发入口和仓库结构；部署文档覆盖后台、桌面签名、公证、升级、备份恢复；用户手册覆盖全部路由和异常恢复。
- [ ] **步骤 2：生成API文档**：OpenAPI和RPC Schema生成可阅读文档；每个方法包含权限、请求、响应、错误码、幂等、分页和事件副作用。
- [ ] **步骤 3：编写故障排查手册**：按症状→诊断数据→安全恢复动作组织，覆盖设计方案20章错误码和21章恢复流程；禁止建议手工编辑SQLite作为常规修复。
- [ ] **步骤 4：编写安全与隐私说明**：明确中心后台与本地数据边界、凭据保存、CLI权限、外联策略、日志保留、备份内容和用户删除行为。
- [ ] **步骤 5：执行追踪检查**：设计方案每个验收项映射到本计划任务、实现文件和自动化测试；本计划所有任务必须为完成状态或阻断发布，不允许以延期事项关闭。
- [ ] **步骤 6：执行交付清洁检查**：实现并运行 `scripts/check-release-hygiene.py`，阻断未完成标记、仅测试用生产入口、无所有者的功能开关和失效文档引用；领域Review实体、测试与正式状态说明不属于清理对象。
- [ ] **步骤 7：运行最终门禁**：

  ```bash
  bash scripts/verify-all.sh
  python3 scripts/check-release-hygiene.py
  git diff --check
  git status --short
  ```

- [ ] **步骤 8：提交最终交付**：仅在第17章门禁全部通过后执行。

  ```bash
  git add README.md docs apps packages tests deploy scripts .github
  git commit -m "docs(release): finalize implementation and operations handoff"
  ```

**完成标准：** 第三方仅凭设计方案、实施计划、README和部署/使用/API文档即可构建、测试、部署、运维和排障；文档与实现不存在未解释差异。

### P11 阶段出口

- [ ] 功能、契约、集成、E2E、安全、故障、性能和发布测试全部通过。
- [ ] Rust、Python、手写TypeScript单元测试覆盖率均为100%，且没有扩大排除范围规避覆盖。
- [ ] macOS安装包、后台镜像、SBOM、签名、公证、更新manifest和备份恢复报告齐全。
- [ ] 设计方案第27章验收项和 K.17 发布清单全部满足。

---

## 15. 设计验收项到实现任务的追踪矩阵

以下编号对应设计方案第27章；任何一行缺少实现任务或测试即禁止发布。

| 验收编号 | 可观察结果 | 主实现任务 | 强制验收测试 |
|---|---|---|---|
| AC-01 | 应用用户用邮箱、密码和确认密码无验证码注册，并出现在后台用户列表 | P1-T02、P1-T03、P9-T02、P10-T02 | `apps/backend-api/tests/auth/test_register.py`、`tests/e2e/app-registration.spec.ts` |
| AC-02 | 管理员只能由后台用户管理模块创建和管理 | P1-T03、P10-T02 | `apps/backend-api/tests/users/test_user_admin.py`、`tests/e2e/admin-users.spec.ts` |
| AC-03 | 默认 `admin/admin123456` 首次登录必须改密且不可删除 | P1-T01、P1-T02、P1-T03、P10-T01、P10-T02 | `apps/backend-api/tests/auth/test_password.py`、`tests/e2e/admin-users.spec.ts` |
| AC-04 | 后台发布Agent、Model、Provider、Skill和兼容规则目录 | P1-T04至P1-T06、P10-T03、P10-T04 | `apps/backend-api/tests/releases/test_publish.py`、`tests/e2e/admin-catalog-release.spec.ts` |
| AC-05 | 客户端只接受签名有效的新目录，离线使用上一有效目录 | P2-T05、P3-T04 | `apps/desktop-core/tests/catalog_sync.rs`、`sidecar/tests/catalog/test_sync.py`、`tests/e2e/offline-recovery.spec.ts` |
| AC-06 | 后台数据库和API不保存任何本地业务数据 | P1-T01、P1-T08、P11-T07 | `tests/integration/test_backend_data_boundary.py`、`tests/release/test_backend_deployment.py` |
| AC-07 | 用户可创建多个相互隔离的本地公司 | P4-T01、P9-T04 | `sidecar/tests/domain/test_company.py`、`tests/security/test_company_isolation.py` |
| AC-08 | 公司创建原子生成办公室、总经理、公司会话和办公室部门会话 | P4-T01、P4-T02、P4-T03 | `sidecar/tests/domain/test_company.py`、`tests/faults/test_failure_matrix.py` |
| AC-09 | 公司新增和编辑包含介绍及内部业务流转说明 | P4-T01、P9-T04 | `sidecar/tests/domain/test_company.py`、`tests/e2e/company-management.spec.ts` |
| AC-10 | 部门新增和编辑包含部门职能说明 | P4-T01、P9-T04 | `sidecar/tests/domain/test_department.py`、`tests/e2e/company-management.spec.ts` |
| AC-11 | 总经理计划使用公司介绍、部门职能和结构化职责 | P7-T01 | `sidecar/tests/orchestration/test_department_matcher.py`、`tests/e2e/software-delivery.spec.ts` |
| AC-12 | 未确认时只运行只读company_plan，不创建可执行部门任务或其他purpose Run | P4-T04、P7-T01、P9-T05 | `sidecar/tests/orchestration/test_plan_validator.py`、`tests/e2e/plan-confirmation.spec.ts` |
| AC-13 | 部门执行前检查全部参与职员实际可用性 | P7-T02、P7-T03 | `sidecar/tests/orchestration/test_availability.py`、`tests/e2e/rework-and-review.spec.ts` |
| AC-14 | 职员底座支持agent_cli、api_model和版本化Skill绑定 | P3-T04、P4-T02、P9-T03 | `sidecar/tests/catalog/test_profile_versions.py`、`tests/e2e/profiles.spec.ts` |
| AC-15 | Codex CLI、Claude Code和OpenCode通过统一Gateway执行任务 | P5-T01至P5-T04 | `sidecar/tests/runtime/test_gateway.py`及三类Adapter测试、真实CLI发布冒烟 |
| AC-16 | API Model由Built-in Agent Runtime驱动完整Agent Loop | P5-T05 | `sidecar/tests/runtime/model_runtime/test_agent_loop.py`、`sidecar/tests/runtime/model_runtime/test_transports.py` |
| AC-17 | 同一任务由多个不同Agent协作产出并交叉Review | P7-T03、P6-T04 | `sidecar/tests/orchestration/test_collaboration.py`、`tests/e2e/software-delivery.spec.ts` |
| AC-18 | 参与职员自动进入Review池且不能Review自己的产物 | P6-T04、P7-T03 | `sidecar/tests/review/test_assignment.py`、`sidecar/tests/orchestration/test_collaboration.py` |
| AC-19 | 软件需求完成架构、开发、首测、修复、终测和总经理终审 | P7-T04、P7-T05 | `sidecar/tests/orchestration/test_software_workflow.py`、`tests/e2e/software-delivery.spec.ts` |
| AC-20 | Workspace内读写、外部普通文件只读、越界写逐目标批准 | P2-T06、P5-T06、P6-T01、P6-T05 | `tests/security/test_workspace_boundary.py`、`sidecar/tests/approvals/test_target_change.py` |
| AC-21 | 不同公司、其他职员私有执行区和其他本地用户数据不可访问 | P2-T02、P4、P6-T01 | `tests/security/test_company_isolation.py`、`tests/security/test_workspace_boundary.py` |
| AC-22 | Agent崩溃或应用重启恢复确定性步骤，不重放不确定副作用 | P3-T03、P5-T07、P8-T04、P11-T02 | `sidecar/tests/runtime/test_recovery.py`、`tests/faults/test_failure_matrix.py` |
| AC-23 | 部门和最终报告追溯产物、测试、Review、修复与复测证据 | P6-T03、P6-T04、P7-T05 | `sidecar/tests/orchestration/test_reports.py`、`sidecar/tests/orchestration/test_final_review.py` |
| AC-24 | CLI不能绕过每Run Egress Broker，未声明域名必须失败 | P2-T07、P5-T06 | `apps/desktop-core/tests/egress_proxy.rs`、`tests/security/test_egress_policy.py` |
| AC-25 | Refresh Token与OfflineSessionTicket在单个Keychain bundle原子轮换且明文不可见 | P2-T02、P2-T04 | `apps/desktop-core/tests/keychain_rotation.rs`、`apps/desktop-core/tests/auth_flow.rs` |

---

## 16. RPC Namespace 责任矩阵

RPC方法以设计方案 J.14 为唯一契约来源；下表规定实现归属，避免相邻阶段重复定义。

| Namespace | 所有者与实现任务 | Desktop调用/UI任务 | 固定方法与重点行为 |
|---|---|---|---|
| `backend.*` | Rust Core，P2-T04 | P9-T02 | `validateOrigin`；规范化Origin并通过ready后保存 |
| `auth.*` | Rust Core，P2-T02、P2-T04 | P9-T02 | `auth.register`、`auth.login`、`auth.changePassword`、`auth.logout`、`auth.listOfflineProfiles`、`auth.openProfile`、`auth.closeProfile`；密码、bundle、目录同步与Profile生命周期 |
| `company.*` | P4-T01 | P9-T04 | `create/get/list/update/archive`；原子初始化、Revision、归档守卫 |
| `department.*` | P4-T01、P4-T02 | P9-T04 | CRUD、`setLeader`、`responsibility.*`；职责DAG、负责人不变量 |
| `employee.*` | P4-T02 | P9-T04 | create/get/list、状态/名称/底座更新、transfer；active assignment守卫 |
| `profile.*` | P3-T04 | P9-T03 | draft CRUD、Skill绑定、validate、publish、retire；版本不可变 |
| `conversation.*` | P4-T03、P4-T04 | P9-T05 | P4-T03实现公司/部门会话和消息列表，P4-T04实现submit任务入口；任务意图、事务原子性和公司隔离 |
| `task.*` | P4-T04 | P9-T05、P9-T06 | Plan确认/修订/拒绝、pause/resume/cancel、get/list/graph/evidence |
| `departmentTask.*` | P7-T02、P7-T05 | P9-T05、P9-T06 | checkResources、replaceEmployee、getReport；可用性和证据报告 |
| `runtime.*` | P5-T01至P5-T05、P7-T02 | P9-T03、P9-T06 | probeAgent/probeProvider、listAvailableModels/getStatus |
| `run.*` | P5-T01、P5-T07、P8-T04 | P9-T06 | cancel/resume/get/list/listEvents；checkpoint恢复和不确定副作用 |
| `approval.*` | P6-T05 | P9-T06 | listPending/resolve；target hash、TTL、一次性消费 |
| `artifact.*` | P6-T03 | P9-T06 | list/getSnapshot；CAS、版本链和贡献者谱系 |
| `workspace.*` | P6-T01、P6-T02 | P9-T06 | get/apply/abandon/cleanupTask；baseline、漂移和清理守卫 |
| `review.*` | P6-T04、P7-T05 | P9-T06 | submit/listIssues/rerun/resolveIssue；自审排除和Issue闭环 |
| `catalog.*` | P3-T04 | P2-T05、P9-T03 | sync、release/Agent/Model/Skill查询、Skill安装删除和cache校验 |
| `knowledge.*` | P8-T01、P8-T02 | P9-T07 | import/remove/list/search；权限先过滤和引用证据 |
| `backup.*` | P8-T03 | P9-T07 | create/restore/list；staging恢复和完整性校验 |
| `settings.*` | P3-T05 | P9-T07 | get/update；仅允许并发度和日志保留两个typed setting |
| `event.*` | P3-T03 | P9-T01 | subscribe/replay；sequence、gap、压缩marker和补拉 |
| `system.*` | Supervisor专用，P2-T03、P3-T02、P8-T04 | WebView不可调用 | handshake/health/shutdown仅限Rust与Sidecar监督通道 |

所有Namespace均必须满足：

1. 请求固定包含 `jsonrpc/id/method/params/meta`；`meta` 只含 `trace_id/ipc_session_id/window_session_id/idempotency_key`。仅Rust本地方法和首次handshake允许 `ipc_session_id=null`；Profile由当前Sidecar进程绑定，不在请求中任意指定。
2. params与响应均通过对应方法的JSON Schema；公司作用域方法按 J.14 携带 `company_id`，未知字段拒绝，不静默忽略拼写错误。
3. 读方法 `meta.idempotency_key=null`；写方法必须使用UUID。Rust本地写只合并in-flight请求且不缓存敏感响应；Sidecar写按J.14保留期限保存结果。只有 `update/resolve` 类方法必须带 `expected_version`。
4. 列表cursor与method、profile、company、filter hash绑定；不匹配统一返回 `VALIDATION_FAILED`。`EVENT_SEQUENCE_INVALID`只用于事件续传序号非法。
5. 长任务先返回受理结果，再通过事件流报告状态；不得保持RPC连接等待Agent完成。

---

## 17. 中心后台 REST 责任矩阵

| 路由域 | 后端实现 | Admin Web | Desktop | 契约重点 |
|---|---|---|---|---|
| `/api/v1/auth/*` | P1-T02 | 不可调用 | P2-T04、P9-T02 | 应用注册/登录、bundle轮换、撤销、离线票据和keys |
| `/admin/api/v1/auth/*` | P1-T02 | P10-T01 | 不可调用 | HttpOnly refresh Cookie、内存Access Token、强制改密 |
| `/admin/api/v1/users*` | P1-T03 | P10-T02 | 不可调用 | 两类字段矩阵、protected admin、If-Match和审计 |
| `/api/v1/catalog/manifest`、`/keys`、`/releases/{id}`、`/releases/{id}/resources/{type}` | P1-T06 | 不可调用 | P2-T05 | sequence、manifest、signature、resource hash、minimum client |
| `/api/v1/catalog/agents`、`/agents/{agent_id}/models` | P1-T04、P1-T06 | 不可调用 | P2-T05 | 只读当前published release，不读取draft |
| `/api/v1/catalog/providers`、`/providers/{provider_id}/models` | P1-T04、P1-T06 | 不可调用 | P2-T05 | Provider、Model binding、外联域名和credential schema |
| `/api/v1/catalog/skills`、`/skills/{skill_id}/versions/{version}/package` | P1-T05、P1-T06 | 不可调用 | P2-T05 | Skill metadata/package、流式下载与客户端验签 |
| `/api/v1/catalog/compatibility` | P1-T04、P1-T06 | 不可调用 | P2-T05 | platform、版本范围和组合约束 |
| `/api/v1/catalog/emergency-disables/latest` | P1-T06 | 不可调用 | P2-T05 | 单调sequence、禁用优先、不可回退 |
| `/admin/api/v1/{agents,models,providers,skills,compatibility-rules}*` | P1-T04、P1-T05 | P10-T03 | 不可调用 | draft/validated/published、revision、version、binding、multipart |
| `/admin/api/v1/catalog/*`、`/admin/api/v1/emergency-disables` | P1-T06 | P10-T04 | 不可调用 | selection校验、发布事务、紧急禁用 |
| `/admin/api/v1/audit-logs` | P1-T07 | P10-T04 | 不可调用 | before/after脱敏、cursor、actor/action/resource |
| `/health/live`、`/health/ready` | P1-T08 | P10-T04仪表盘读取 | P2-T04诊断读取 | live不访问依赖；ready检查PG/MinIO/签名配置 |

禁止增加公司、部门、职员实例、会话、任务、运行、Artifact或本地知识REST路由；这些数据只能经本地RPC访问。

---

## 18. 数据库迁移执行顺序与所有权

### 18.1 中心后台 PostgreSQL

| Revision | 创建内容 | 所属任务 |
|---|---|---|
| `0001_users_tokens_idempotency.py` | users、refresh token family、login failures、idempotency、protected admin seed | P1-T01、P1-T02、P1-T03 |
| `0002_catalog_resources.py` | Agent/Model/Provider/Skill/Compatibility、versions、bindings、validation reports | P1-T04、P1-T05 |
| `0003_catalog_releases.py` | releases、release resources、emergency disables和admin audit | P1-T06、P1-T07 |

规则：Alembic revision只前进；每次部署先备份再执行 `alembic upgrade head`；失败保持旧应用运行；生产禁止自动downgrade。

### 18.2 本地 SQLite

| 文件 | 创建内容 | 所属任务 |
|---|---|---|
| `20260722000100_profile_catalog.sql` | Profile identity、migration元数据以及目录基础引用 | P3-T01 |
| `20260722000200_events_idempotency.sql` | DomainEvent、Outbox、projection offset与RPC幂等；不创建Conversation或message投影 | P3-T03 |
| `20260722000300_profiles_catalog_cache.sql` | Catalog cache、Skill安装状态、职员底座及版本绑定 | P3-T04 |
| `20260722000400_audit_settings.sql` | append-only本地审计与typed settings | P3-T05 |
| `20260722000500_company_bootstrap.sql` | Company、Department、Revision、职责、Employee基础实例与Company/Department Conversation | P4-T01、P4-T02 |
| `20260722000600_local_domain_runtime_parents.sql` | `conversation_messages`；H.6的八张任务/Plan/Snapshot表；`agent_runs`核心；`workspace_grants/task_workspaces`父表，具体表名以P4-T03固定清单为准 | P4-T03、P4-T04、P5-T01、P6-T01 |
| `20260722000700_runtime_queue.sql` | durable queue、lease、slot与fairness状态 | P4-T05 |
| `20260722000800_runtime_foundation.sql` | RunEvent、Checkpoint、ToolExecution、VerificationResult、HumanApproval存储及Artifact核心表；AgentRun核心表已在006迁移创建 | P5-T01、P5-T07、P5-T06 |
| `20260722000900_workspace_artifacts.sql` | Artifact贡献者/版本服务与Review表；复用006的Workspace表和008的Artifact/HumanApproval核心表 | P6-T01至P6-T05 |
| `20260722001000_knowledge_backup.sql` | Knowledge、索引generation/access log、backup/restore记录 | P8-T01至P8-T04 |

迁移实现必须遵守项目 `AGENTS.md` 的SQLite幂等规则。新表和索引使用 `IF NOT EXISTS`；新增列先由迁移runner检查 `PRAGMA table_info`；迁移记录hash，已执行同名文件hash变化立即停止。v1只创建本设计定义的Profile schema；外部数据进入Profile必须经过显式导入器，不能隐式猜测字段。

---

## 19. 测试分层、覆盖率与执行环境

### 19.1 测试分层

| 层级 | 目标 | 外部依赖 | 何时运行 |
|---|---|---|---|
| Unit | 单个状态机、validator、parser、service和React组件 | 全部使用内存fake | 每个PR |
| Contract | JSON Schema、RPC envelope、OpenAPI和生成client一致性 | 启动最小服务 | 每个PR |
| Integration | SQLite、PostgreSQL、MinIO、进程监督、CLI parser | Testcontainers/临时目录/测试二进制 | 每个PR |
| E2E | 真实桌面UI、后台UI和完整业务流 | 打包应用+真实服务+确定性adapter | 合并前与nightly |
| Real Adapter | 真实Codex/Claude Code/OpenCode已安装版本 | 隔离测试账户，不使用个人配置 | nightly与发布候选 |
| Security/Fault | 攻击面和恢复语义 | 隔离网络、故障注入代理 | 合并前与发布候选 |
| Performance | K.16确定性容量和延迟 | 固定macOS runner | nightly与发布候选 |
| Release | 签名、公证、净机、升级回退、后台恢复 | 干净VM和预发布环境 | 发布候选 |

### 19.2 100%单元测试覆盖定义

1. Rust以 `cargo llvm-cov --manifest-path apps/desktop-core/Cargo.toml --all-features --fail-under-lines 100 --fail-under-functions 100 --fail-under-regions 100` 为准。
2. Python以 `pytest --cov-branch --cov-fail-under=100` 为准；Backend和Sidecar分别计算后再汇总。
3. 手写TypeScript/TSX以Vitest/Istanbul的statements、branches、functions、lines四项100%为准。
4. 只允许排除生成代码、第三方vendor、声明文件、migration SQL和不可执行的Tauri生成胶水；排除清单固定在根配置，变更必须由安全与测试review批准。
5. E2E、集成、真实CLI和性能测试不计入单元覆盖率数字，但都是发布硬门禁。
6. 不允许通过 `pragma: no cover`、`istanbul ignore` 或死分支制造100%；必要的平台分支由相应平台runner覆盖。

### 19.3 根验证脚本固定顺序

`scripts/verify-all.sh` 必须按以下顺序执行并在首个失败处返回非零：

```bash
npm --prefix packages/contracts run lint
npm --prefix packages/contracts run check-generated
cargo fmt --manifest-path apps/desktop-core/Cargo.toml --all -- --check
cargo clippy --manifest-path apps/desktop-core/Cargo.toml --all-targets --all-features -- -D warnings
cargo nextest run --manifest-path apps/desktop-core/Cargo.toml --all-features
cargo llvm-cov --manifest-path apps/desktop-core/Cargo.toml --all-features --fail-under-lines 100 --fail-under-functions 100 --fail-under-regions 100
uv run --directory apps/backend-api ruff check src tests
uv run --directory apps/backend-api mypy src
uv run --directory apps/backend-api pytest --cov=ibreeze_backend --cov-branch --cov-fail-under=100
uv run --directory sidecar ruff check ibreeze tests
uv run --directory sidecar mypy ibreeze
uv run --directory sidecar pytest --cov=ibreeze --cov-branch --cov-fail-under=100
npm --prefix apps/desktop run lint
npm --prefix apps/desktop run typecheck
npm --prefix apps/desktop run test:coverage
npm --prefix apps/admin-web run lint
npm --prefix apps/admin-web run typecheck
npm --prefix apps/admin-web run test:coverage
python3 -m pytest tests/contract tests/integration tests/security tests/faults -v
npm --prefix tests/e2e run test
bash scripts/run-performance-gate.sh
git diff --check
```

---

## 20. 固定技术决策与风险处置

本章内容是执行约束，不是开放选型；第三方不得在实现中替换而不先修改并批准设计方案。

| 主题 | 固定决策 | 触发风险时的处置 |
|---|---|---|
| 桌面壳 | Tauri 2 + Rust Core + React | capability无法满足时先提供最小复现和威胁分析，禁止切Electron绕过 |
| Sidecar | Python 3.12 standalone arm64 binary | 打包失败先缩减依赖或修复recipe，禁止要求用户安装Python |
| 本地数据库 | 每Profile单SQLite，WAL | 写竞争先收敛为单写队列，禁止迁移到后台数据库 |
| 向量检索 | LanceDB，本地持久化；FTS5并存 | 索引损坏从source/chunk重建，禁止以向量库为事实源 |
| 中心后台 | FastAPI + PostgreSQL + MinIO | 容量问题水平扩展无状态API，禁止上传桌面业务数据缓解 |
| 桌面通信 | Rust监督Sidecar，UDS framed JSON-RPC + event replay | Sidecar异常按supervisor策略重启，禁止开放TCP端口 |
| 运行时 | CLI Adapter + API Model Agent Loop统一Gateway | 上游CLI变化只改对应adapter/parser，禁止把条件散到编排层 |
| 凭据 | Keychain + Rust Credential Broker | Keychain不可用时阻断依赖凭据的执行并提示修复，禁止降级明文 |
| 沙箱 | macOS Seatbelt + 应用层路径/网络双重校验 | Seatbelt能力变化时默认拒绝并出诊断，禁止扩大默认权限 |
| Git隔离 | 每Subtask独立worktree，WorkspaceService合并 | 非Git目录使用快照工作区，不得直接并发修改原目录 |
| 目录供应链 | manifest签名 + object/content hash + ZIP安全校验 | 验签/校验失败继续使用最后可信快照并告警，禁止忽略错误 |
| 更新 | 签名manifest + 健康检查 + 保留旧版本 | 新版失败自动回退；数据库只采用前向兼容迁移 |

---

## 21. 最终发布清单

以下项目全部勾选后才能生成正式版本号和发布说明：

### 21.1 功能与数据边界

- [ ] 设计方案第27章 AC-01至AC-25全部通过并有可定位测试报告。
- [ ] 中心后台数据库、对象存储、日志和指标均不含公司、部门实例、职员实例、会话、任务、运行、Artifact和本地知识正文。
- [ ] 默认公司研发流、通用公司流和多Agent协作流均完成E2E。

### 21.2 质量与安全

- [ ] 所有语言100%单元覆盖且排除项未扩大。
- [ ] lint、typecheck、静态分析、契约、集成、E2E、真实Adapter、故障、安全和性能测试全部通过。
- [ ] 高危/严重依赖漏洞为零；SBOM和许可证清单已生成。
- [ ] 凭据、日志、路径、网络、ZIP、目录签名和公司隔离安全用例全部通过。

### 21.3 发布与运维

- [ ] macOS Apple Silicon签名、公证、staple和净机验证通过。
- [ ] 从前一稳定版升级、失败回退、目录紧急禁用和离线宽限演练通过。
- [ ] 后台生产部署、数据库迁移、MinIO访问、备份与空环境恢复演练通过。
- [ ] 指标、日志、审计、诊断包和告警规则可用且脱敏。

### 21.4 文档与交接

- [ ] README、部署文档、用户手册、API文档、故障排查、安全隐私说明与当前实现一致。
- [ ] OpenAPI、RPC、JSON Schema、迁移表和路由表均由CI验证无漂移。
- [ ] 本计划所有任务状态、commit和测试证据可追溯，发布清洁检查无阻断项。
- [ ] 第三方已在无口头补充的情况下按文档完成一次构建、部署、首次使用、业务流和恢复演练。

---

## 22. 第三方交付物目录

实施团队最终必须交付以下不可缺项；文件名可增加版本号，但职责不得合并后遗漏。

1. **源代码**：`apps/desktop`、`apps/desktop-core`、`sidecar`、`apps/backend-api`、`apps/admin-web`、`packages/contracts`、`packages/rpc-schema`、`packages/ui`。
2. **自动化测试**：各应用单元测试，以及 `tests/contract`、`tests/integration`、`tests/e2e`、`tests/security`、`tests/faults`、`tests/performance`、`tests/release`。
3. **构建与部署**：CI工作流、锁文件、容器定义、macOS签名/公证脚本、更新manifest生成器、后台部署定义。
4. **数据演进**：完整Alembic revisions、SQLite migrations、schema版本策略、备份与恢复脚本。
5. **契约产物**：OpenAPI、RPC Schema、事件/计划/报告/Review/Catalog JSON Schema、生成client和golden fixtures。
6. **发布产物**：公证后的macOS安装包、Backend/Admin镜像digest、SBOM、许可证清单、签名目录清单和校验值。
7. **质量证据**：100%覆盖率报告、静态分析、E2E、真实Adapter、安全、故障、性能、升级回退和灾备报告。
8. **交付文档**：README、部署文档、用户手册、API文档、故障排查手册、安全与隐私说明、设计方案和本实施计划。

交付验收人按第21章逐项签署；任何只存在于演示环境、个人机器、聊天记录或口头说明中的配置与操作均视为未交付。
