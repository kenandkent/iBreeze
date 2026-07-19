STATUS: PASS

# 摘要

本次架构视角审计了设计方案（AI 公司桌面应用设计方案.md）与实施计划（AI 公司桌面应用-实施计划.md）之间的一致性、模块边界划分、抽象层级、依赖方向以及系统级完整性。由于当前项目尚无任何实体代码（只有一份草案设计方案和一份实施计划），因此这是纯粹的静态审查：比较设计文档与计划文档的匹配度，标记差异、歧义和风险。

总体评定：设计方案质量高，实施计划的映射完整。共发现并确认了 A 类（架构）3 项、B 类（边界/抽象）1 项、C 类（依赖/顺序）3 项问题，合计 7 项。其中新增问题 7 项，未找到原已知 21 条问题列表（本审计 run 对应的制品中未发现问题侧写文件，确认为全新的审查活动）。

# 变更文件

None

# 验证

None

# 产物

- 本报告 (report.md)
- report.issues.json（平行审查 sidecar，包含 lens 标记）

# 问题

## 一、架构级别问题 (A)

### A-1 [有效·新增] Manager Scope 数据结构未在实施计划中显式建模

设计方案 §10.1 定义了 Manager 的两种作用域入口（"直达部门"和"经公司负责人路由"），明确区分 `manager_scope=dept` 和 `manager_scope=company`，并指出相应的 `department_id` 约束。但实施计划 P9-T1 的 `tasks` 表定义只提及 `manager_employee_id/manager_scope`，未给出 `manager_scope` 的枚举值定义和 `department_id` 与 `manager_scope` 的约束关系（dept 时必填、company 时为空）。建议在 P9-T1 中补充 manager_scope 的枚举约束和 `department_id` 的条件 NOT NULL。

### A-2 [有效·新增] Checkpoint p95 < 100ms 与大规模 Workspace 的 context_hash 计算矛盾

设计方案 §4.5 规定 Checkpoint 写入 p95 < 100 ms 作为 release_gate。但 §10.5 的 Checkpoint 定义中包含 `context_hash`，该 hash 需要对整个关联 Workspace 内容做摘要。对于 GitWorktreeWorkspace（潜在的大规模代码仓库），文件 hash 计算很容易超过 100ms。建议在 §7 的 `ResolvedRunConfig` 或 §10.5 中明确采用增量 hash 策略（如记录 Git HEAD commit SHA 作为 context_hash，而非全量扫描），或者将 Checkpoint 拆分为"元数据写入（<100ms）+ 异步 Workspace 校验收敛"两个阶段。

### A-3 [有效·新增] LanceDB/SQLite 双写对账 Worker 缺独立编码任务

设计方案 §9.5 描述了完整的双写一致性策略（generation 切换 + CAS + 后台对账 Worker），但实施计划 Phase 8（特别是 P8-T5）中没有将对账 Worker 列为单独的编码任务，也没有相应的 DoD 和验收标准。当前 P8-T5 只描述了索引切换、双写测试和知识删除，将对账 Worker 的实现隐藏在"索引切换"的附属描述里。建议在 P8-T5 中明确将对账 Worker 的实现作为显式子任务，定义其 DoD 包含"SQLite 期望状态与 LanceDB 实际内容对比修复"。

## 二、边界/抽象级别问题 (B)

### B-1 [有效·新增] SecurityPolicy 对 Capability Engine 和 Workspace 的双向投影缺少矩阵

设计方案 §7 第 7 步要求 Capability Engine 读取 SecurityPolicy 构造 `security_policy` hash，而 §11.3 的 RestrictedWorkspace 同样依赖 SecurityPolicy 的 `effective_allowed_commands` 来构建路径/命令白名单。两个模块共享同一策略但职责不同（Capability Engine 产生运行时约束声明，Workspace 执行路径级限制）。两者之间的投影关系不是正交的——SecurityPolicy 的 `high_risk_actions` 还影响审批流程。建议在 §7 或实施计划 P5-T2 中增加一张"SecurityPolicy 字段投影矩阵"，明确标注每个字段流向哪些下游模块的哪个具体 DTO 字段。

## 三、依赖/顺序级别问题 (C)

### C-1 [有效·新增] Outbox Worker 在 Consumer 未完全注册前的生命周期未定义

P1-T2 实现 Outbox Worker 并在单测中验证了投递逻辑。但 Outbox Worker 在 Phase 1 结束后到 Phase 9 消费者注册完成前（Phase 2-8）如何处理 "pending" 事件未被阐明：
- 若 Worker 持续运行但大多数消费者 handler 尚未注册，投递失败如何记录和重试？
- 若 Worker 暂不启动，pending 事件在 SQLite 中累积是否会导致后续 Phase 9 启动时 Backlog 过多？
实施计划需要在 P1-T2 或 P3-T6 中定义 Outbox Worker 在整个项目早期的运行守卫策略（例如设置 `consumer_name_allowlist`，仅注册已实现的消费者）。

### C-2 [有效·新增] 质量门禁黄金用例空集合缺少填充时间表

P3-T5 的 `run_quality_gate` 定义预留了 Golden Case 接口，但首版为空集合。Phase 13 发布门禁（第 17 节）需要质量门禁真实运行验证内容合规，空集合意味着发布前必须补充真实黄金用例。但实施计划没有任何条目规定"什么时候由谁创建至少 N 条黄金用例"。建议在 P9-T11 或 P13-T4 中增加一个显式子任务，定义 3-5 条 Prompt Asset/Skill/Capability 的黄金用例。

### C-3 [有效·已确认] 测试基础设施和 CI 策略未在实施计划中专题规划

设计方案 §17 定义了详细的质量门禁和安全测试要求，实施计划预期测试文件分布在各个任务的 DoD 中，但缺少一份全项目的测试策略文档（如下），包括：
- 集成测试环境（真实 vs mock）
- 权限逃逸套件的独立 CI 门禁
- 跨服务 REST/RPC 契约测试的编排（如 Backend + Provider + Credential Broker 多模块联调）
- 备份恢复演练的自动化触发时机
当前"每个任务写测试"的方式在高安全关键路径上可能不足，建议在 Phase 0 或 Phase 1 终点加入"测试基础设施"任务（可并行），产出 `docs/测试策略.md` 并建立首次集成测试流水线基线。

# 建议

1. **Checkpoint 增量策略**: 在设计方案 §10.5 和 §4.5 中明确增量 hash 策略（如 Git HEAD SHA 代替全量扫描），确保 p95 < 100ms 的 release_gate 可达成。
2. **Manager Scope 显式建模**: 在实施计划 P9-T1 中将 `manager_scope` 定义为枚举并声明 `department_id` 与它的约束关系。
3. **双写对账 Worker 任务化**: 在 P8-T5 中将对账 Worker 列为显式子任务并定义 DoD。
4. **SecurityPolicy 字段投影矩阵**: 在 P5-T2 中增加 SecurityPolicy 到 Capability Engine / Workspace / 审批流的字段映射表。
5. **黄金用例计划**: 在 P3-T6 或 P9-T11 中分配一个无论谁负责创建至少 5 条真实黄金用例，覆盖常见的 Prompt Injection、密钥泄漏、引用的 Skill 缺失等场景。
6. **Outbox Worker 启动策略**: 在 P1-T2 实现一个基于注册 consumer_name 的 allowlist，防止未实现的消费者导致大量 failed delivery。
7. **测试策略文档**: 在 Phase 0-P1 边界创建 `docs/测试策略.md`，明确集成测试基线、权限逃逸 CI 门禁和备份恢复演练的自动化触发时机。
