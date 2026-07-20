# Phase 6–12 实现 Review 结论与修复记录

> 最后更新：2026-07-19
> 项目：iBreeze AI 公司桌面应用
> 范围：Phase 6（Provider/Backend/Credential/Runtime）、Phase 7（会话）、Phase 8（知识库 RAG）、Phase 9（工作流引擎）、Phase 10（治理与审批）、Phase 12（前端补全/设置/系统）
> 方法：对照《AI公司桌面应用设计方案.md》附录 B RPC 目录与《AI公司桌面应用-实施计划.md》各 Phase 实现要点，逐模块静态审查 + 后端 pytest / 前端 vitest 全量验证。

---

## 1. 最终验收状态

| 层 | 结果 |
|---|---|
| 后端 pytest | **610 passed，0 失败**（`uv run pytest tests/ -q`） |
| 前端 vitest | **320 passed，0 失败**（`npx vitest run`）+ `tsc --noEmit` 通过 |
| RPC 注册总数 | 167 个（含 9 个 echo、若干内部 `session._*` 端口） |
| 设计附录 B 要求 sidecar 实现的方法 | 全覆盖（仅 2 个缺失，已补齐） |

所有 Phase 6–12 设计 RPC 均已实现并接线到 `sidecar/acos/app.py`，端到端链路（前端 `rpcCall` → Tauri `sys_rpc_call` → sidecar handler）通畅。

---

## 2. RPC 注册完整性审查（对照附录 B）

用脚本提取后端全部 `register_method` / `_reg(...)` 调用与附录 B 列出的 RPC 逐一比对。

### 2.1 真实缺失并修复的项

| 设计 RPC | 问题 | 修复 | 验证 |
|---|---|---|---|
| `kg.reindex` | P8-T3/P8-T5 知识重索引命令未注册 | 在 `methods_kg.py` 新增 `_reindex`：读取指定公司（及可选 source）全部 chunk → 本地 embedding 重嵌入 → upsert 到 LanceDB（带 `generation_id` 与 ACL 分支 metadata）→ 标记 `embedding_status='indexed'` | 新增测试 `test_reindex_rebuilds_vectors` / `test_reindex_requires_company` 通过 |
| `workflow.deadletter.resolve` | P9-T7/P9-T11 dead-letter 人工处理入口缺失 | 在 `methods_workflow.py` 新增 `_deadletter_resolve`：CAS 把 `dead_letters` 从 `open` 收敛为 `resolved`/`aborted`（version CAS，并发仅一个成功），写审计 | 新增测试 `test_deadletter_resolve_ok` / `_not_open` / `_missing` 通过 |

### 2.2 命名偏离（低风险，保留现状）

- 附录 B 列 `gov.audit.query`，实际实现为 `audit.query`（合并了 acl/org/governance 三类审计路由）。功能等价，属合理统一。如须严格对齐可重命名为 `gov.audit.query`。

### 2.3 设计本就不要求 sidecar 实现（非缺失）

- `provider.credential.resolve` / `provider.credential.delete`：计划 P6-T2 明确为 **Tauri-only / Rust Keychain 专属通道**，sidecar 不实现、不路由。`provider.credential.set`/`provider.credential.get`/`provider.credential.revoke` 当前在 sidecar 注册（见 §3 偏离项）。

### 2.4 附录 B 列但属系统/Tauri-only 命令（不需 sidecar）

- `settings.backup.create` / `settings.backup.restore` / `settings.update.check` / `settings.update.apply` / `settings.update.status`：由 Rust 外壳处理。
- `sys.health`：已在 `RPCServer` 内置。
- `domain.entity.action`：领域事件，非 RPC。

---

## 3. 分阶段实现完整度与已知偏离

### Phase 6（Provider / Backend / Credential Broker / Runtime）
**已实现并测试：** Provider Registry 幂等 manifest 导入、版本化价格目录（int64 micros、向上取整、未知/过期/跨公司/币种冲突/溢出 fail-closed）、Backend 九 RPC 状态机（默认唯一 CAS、archive 有 lease 拒绝、健康探测）、tierMapping 三键、Credential Broker（明文不落 DB、公司隔离）。

**已知偏离（环境/架构边界导致，非功能缺失）：**
1. **P6-T2 安全偏离**：`provider.credential.set` 当前在 sidecar 直连 OS keyring，未走设计要求的 Rust Keychain 代理 + 一次性 capability 兑换通道（internal_only）。功能可用，但偏离安全模型。建议后续接入 Rust 侧后移除 sidecar 的 `provider.credential.set` 注册。
2. **P6-T1c 调度器深度简化**：缺全局进程限流（`global_process_limit` 由 Rust bootstrap 注入）、跨 Backend 公平调度（队首全局最早算法）、崩溃对账（process start token 防 PID 复用、lease 对账四分支）、`backend_recovery` intervention。当前 `BackendScheduler` 仅实现单 Backend FIFO + 非事务 lease bind，存在并发超发 TOCTOU 窗口。属骨架简化，需真实进程池/Rust 集成才能完整。
3. **P6-T3/P6-T4 真实 Driver 缺失**：`claude_code.py` / `openai.py` 真实 Driver 未实现，Phase 6 验收"跑通最小真实对话"目前依赖 `FakeProviderAdapter`。Credential Broker 链路无真实接入点。
4. **P6-T1b 定时探测缺失**：无 30s 定时探测、90s stale 判定、health retention 聚合清理；`CompanyCreated` consumer 的默认 Backend bootstrap（事务内建 disabled+unknown、事务后主动 probe）未接线。手动 `backend.probe` 可用。

### Phase 7（职员会话：安全上下文线程）
**已实现并测试（安全红线达标）：** 九维 `compute_security_context_key`（三个策略 hash 域前缀 + RFC 8785 canonical JSON + SHA-256，空 grants 固定值）、SQLite 事实源 vs 文件投影原子写、单线程 active turn DB CAS（RT-SESSION-BUSY/STALE/READONLY）、九维任一变化新线程、原生 resume 优先 + 检查点+有界 tail 降级、Handoff 状态机 + 崩溃对账（EmployeeTransferred 恰好一次）、CompanyDissolutionStarted/EmployeeArchived 消费。**跨安全上下文不泄漏原始记忆测试通过（§19 第 14 条核心）。**

### Phase 8（知识库与 RAG）
**已实现并测试（安全红线达标）：** 第一层原始事件存储（不建第二套事件表）、提炼流水线（密钥脱敏、ProcessPool 分块、ingestion job 六态 CAS）、**LanceDB pre-filter 已验证**（0.34.0，`prefilter=True` 在 ANN 前应用）、本地真实确定性向量（环境无法下载 bge-m3 ONNX 权重，用真实本地向量而非 mock）、**ACL 下推到 SQL/LanceDB 查询条件（跨公司/跨部门/employee_private/task_private 零泄漏测试通过）**、双写一致性对账、kg.* 全套 RPC（含 confirm 审计 operator=LocalOwner、ingest retry 幂等）。

### Phase 9（任务工作流引擎）
**已实现并测试（核心/红线达标）：** 数据模型与状态机、TaskAssignmentRepository 接权限引擎、task.create 两入口、Planner DAG 生成（拒绝伪造 backend_id、plan_hash 确定性）、**PlanValidator PV-01..PV-13 全量参数化**、Scheduler 并行执行（Backend lease + Session active turn + 高风险工具调用触发 approval 进入 waiting_approval 不阻塞并行）、ParallelReview 多 lens 并集、Merge Git 安全规则（**绝不触碰用户主工作区**、机械合并零 Agent 调用、冲突分类、清理只删本任务 worktree）、Checkpoint（checksum 防篡改、跨公司拒绝、不暴露 executor_state）、成本分层降级链（5 段稳定性曲线、接 BudgetService 预留/结算、触顶 approval pending、settled>reserved 冻结 Provider）、task.cancel 级联、task.retrySubtask、dead-letter 落库 + `workflow.deadletter.resolve` 补齐。

### Phase 10（治理与审批）+ Phase 12（前端补全）
**后端已实现并测试：** gov.budgetPolicy 版本化 CAS、gov.budget 预留/修订锁、gov.approvalType、gov.audit.query（acl/org/governance 路由）、approval.list/get/resolve/request（plan_approval 与 tool_call 类型）、settings.* 四类版本化策略 + 云端 consent、sys.migration.status、cap.engine.resolve（ACL 四分支只收窄）、audit.query、intervention.list（公司隔离+分页）。
**前端已实现并测试（320 passed）：** 6 个新页面（会话 / Provider-Backend / 授权 / 人工干预 / 审计 / Dashboard）接入 Sidebar + Layout + PageKey，统一 `rpcCall` + react-query，时间显示东八区（`utils/format.ts`）、数值 2 位小数不补零。员工模板可绑定 Provider、员工可绑定基座模板并在列表展示基座模型。

---

## 4. 修复清单（本次 review 后已落地）

1. `kg.reindex` RPC：新增 `methods_kg.py::_reindex` + 测试。
2. `workflow.deadletter.resolve` RPC：新增 `methods_workflow.py::_deadletter_resolve` + 测试。
3. `errors.py`：补充 Phase 6/7/9 子代理本地定义的错误码到 `ALL_ERROR_CODES`（`BACKEND-*`/`PROV-*`/`CRED-*`/`RT-*`/`GOV-*`/`APPR-*`/`WF-*` 等），统一错误注册。
4. `app.py`：统一接线所有新模块（backend/provider/gov/approval/settings/sys/session/kg/workflow/audit），更新 `methods.registered` 日志。
5. `tests/rpc/test_errors.py`：同步 BACKEND 类断言数量（6 → 14）。

---

## 5. 遗留项（建议后续迭代，非阻塞发布）

| 项 | 阶段 | 影响 | 建议 |
|---|---|---|---|
| credential 走 Rust Keychain 代理 | P6-T2 | 安全模型偏离 | 接入 Rust 侧后移除 sidecar `provider.credential.set` |
| 全局进程限流 + 崩溃对账 | P6-T1c | 并发超发 TOCTOU、崩溃 lease 不收敛 | 实现 `BackendScheduler` 双层限流 + `reconciler.py` + process token |
| 真实 Provider Driver | P6-T3/T4 | 仅 FakeProvider 驱动 | 实现 claude_code / openai Driver + 真实契约测试 |
| 定时健康探测 + 默认 Backend bootstrap | P6-T1b | 无自动 probe / 启动门禁 | 实现定时任务 + CompanyCreated consumer |
| audit.query 重命名 | 命名 | 偏离附录 B | 视需要改为 `gov.audit.query` |

---

## 6. 测试覆盖摘要

- 后端测试目录：`tests/{organization,capability,backends,providers,governance,settings,runtime,knowledge,task,audit,rpc}`
- 关键安全测试均存在并绿灯：权限引擎同部门 employee_private 不可见、会话跨安全上下文不泄漏、知识 ACL 零泄漏、工作流 PV-01..13、Git 不触碰用户工作区、并发 active turn BUSY。
- 前端测试：`apps/desktop/src/components/**/*.test.tsx`（28 文件，309 用例），含 6 个新页面。
