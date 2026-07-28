# iBreeze 问题修复记录

> 基于 `docs/review报告/AI公司桌面应用-二次全量复核报告.md` 的修复结果

## 修复摘要

| 问题编号 | 级别 | 描述 | 状态 | 修复方式 |
|---------|------|------|------|---------|
| NEW-P0-01 | P0 | Sidecar 静态检查回归 | **已修复** | 删除未使用的 `time` import；修复 mypy 泛型类型参数缺失 |
| NEW-P0-02 | P0 | CI Policy 测试假通过 | **已修复** | 创建 `test_ci_policy.py` 使用 `git ls-files` 检测；创建 `.github/workflows/ci.yml` |
| CUR-P0-01 | P0 | Broker/Egress NotImplementedError | **部分修复** | Registry、Schema、错误码已定义；UDS 和 Broker 实现需架构重写 |
| CUR-P0-02 | P0 | RPC Schema 空对象 | **已修复** | 21 个空 schema 中 10 个补齐字段、11 个标记为 `maxProperties:0`；创建 Canonical RPC Registry |
| CUR-P0-03 | P0 | Desktop 路由与 RPC | **已修复** | 从 READ_OPERATIONS 删除 Registry 外方法 |
| CUR-P0-04 | P0 | 验证、覆盖率与 CI | **已修复** | 修复 verify-all.sh（工具链、覆盖率阈值 100%）；创建 CI workflow |
| CUR-P0-05 | P0 | 数据库/WriteQueue/Worker 生命周期 | **部分修复** | 添加 OutboxWorker；增强 HealthSnapshot；修复 mypy 类型 |
| CUR-P0-06 | P0 | Admin 认证协议 | **已修复** | 稳定 device_id；修复 Refresh 响应解析；创建认证集成测试 |
| NEW-P1-01 | P1 | Admin Refresh 响应解析 | **已修复** | `apiClient.ts` 使用 `data.data.*` 统一解析 |
| NEW-P1-02 | P1 | tsconfig.tsbuildinfo 被跟踪 | **已修复** | `git rm --cached` 并从 `.gitignore` 忽略 |
| CUR-P1-01 | P1 | CLI Runtime/Seatbelt/Egress | **部分修复** | Registry 定义了 `runtime.process.*` 方法；实现需架构重写 |
| CUR-P1-02 | P1 | Review/Completion 状态机 | **部分修复** | `review.submit` schema 完整定义；Domain Event 注册；状态机实现需架构重写 |
| CUR-P1-03 | P1 | Updater 安全 | **未修复** | 需架构重写第 9 节 |
| CUR-P1-04 | P1 | 生产部署 | **已修复** | 修复 MinIO console-address 端口映射 |
| CUR-P1-05 | P1 | 测试套件漂移 | **已修复** | 创建 E2E 测试 stub；创建 CI Policy 测试；修复 verify-all.sh 根级测试 |
| CUR-P1-06 | P1 | 实时 Health | **已修复** | 修复 Rust `system_health` 硬编码；增强 HealthSnapshot |
| CUR-P2-01 | P2 | 前端包体 | **未修复** | 已有 manualChunks 配置 |
| CUR-P2-02 | P2 | 手工契约副本 | **已修复** | 清理 READ_OPERATIONS；创建 Canonical RPC Registry 替代手工列表 |

## 核心变更

### 新建文件
- `.github/workflows/ci.yml` — CI workflow
- `packages/rpc-schema/registry.v1.json` — 120 个方法的 Canonical RPC Registry
- `packages/rpc-schema/error-codes.v1.json` — 28 个标准化错误码
- `packages/contracts/scripts/validate-registry.mjs` — Registry 验证脚本
- `packages/contracts/domain-events/registry.v1.json` — 44 个 Domain Event 注册
- `sidecar/ibreeze/workers/outbox.py` — OutboxWorker
- `apps/admin-web/src/utils/deviceId.ts` — 稳定设备 ID
- `tests/contract/test_ci_policy.py` — CI Policy 测试
- `tests/functional/test_admin_auth.py` — 认证集成测试
- `tests/e2e/health.spec.ts` — E2E 测试 stub

### 修改文件
- `sidecar/ibreeze/application/app.py` — 修复静态检查、增强 HealthSnapshot、添加 OutboxWorker
- `sidecar/ibreeze/workers/runtime.py` — 修复静态检查
- `apps/admin-web/src/utils/apiClient.ts` — 修复 Refresh 响应解析
- `apps/admin-web/src/pages/LoginPage.tsx` — 使用稳定 device_id
- `apps/desktop/src/shared/rpcClient.ts` — 清理 READ_OPERATIONS
- `scripts/verify-all.sh` — 修复工具链和覆盖率阈值
- `packages/rpc-schema/reverse-methods.v1.json` — 更新为核心架构 11 个方法
- `packages/rpc-schema/methods/*.request.schema.json` — 21 个空 schema 修复
- `.gitignore` — 已包含 tsconfig.tsbuildinfo
- `docker-compose.yml`、`deploy/docker-compose.yml` — MinIO 端口映射
- `apps/desktop-core/src/commands.rs` — 修复 system_health 硬编码
- `README.md`、`docs/部署文档.md`、`docs/用户手册.md` — 文档同步

### 待继续修复（需架构重写）
- CUR-P0-01：Duplex UDS、Credential HTTP Broker、CONNECT Egress（架构重写 Tasks 8-10）
- CUR-P0-05：Persistence Kernel 全面重写（架构重写 Tasks 5-7）
- CUR-P1-01：CLI Runtime/Seatbelt 完整实现（架构重写 Tasks 9-11）
- CUR-P1-02：Review/Completion 状态机完整实现（架构重写 Task 12）
- CUR-P1-03：Updater 安全增强
- CUR-P2-01：前端包体优化
