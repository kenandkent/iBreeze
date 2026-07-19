# AI 公司桌面应用 实施计划文档

> 本文档依据《AI公司桌面应用设计方案.md》（以下简称"设计方案"）编写，是面向**第三方开发团队**的详细实施计划。每个任务给出确切文件路径、需要实现的接口/字段（引用设计方案章节，不重复定义，避免两份文档漂移）、测试用例与验收标准（Definition of Done）。设计方案是唯一的接口/数据事实来源；本计划只负责"先做什么、怎么切任务、如何验收"。

## 0. 如何使用本计划

- **前置阅读**：开工前必须完整读一遍设计方案的 §1–§13（领域与架构）与附录 A（代码结构）、附录 B（API 目录）。本计划里的每个任务只给"这一步要做什么"，字段/接口/状态机的**权威定义**永远在设计方案里，本计划不重复摘抄完整字段列表，只在关键处提示"对照设计方案 §X"。
- **任务编号**：`P<阶段号>-T<任务号>`，如 `P3-T2`。任务之间的"依赖"字段指向其他任务编号，必须先完成依赖任务才能开始。
- **文件路径**：全部位于设计方案《附录 A》约定的包边界内；本计划可在对应子包下细化 `service`、审计或测试文件，新增 RPC handler 时必须同步更新 `coverage.yaml`。
- **测试优先**：每个任务的"测试"小节列出必须写的测试文件与关键用例。涉及安全/一致性的任务（权限、能力不可变、会话隔离、幂等恢复）测试用例是**强制项**，不是建议项。
- **提交粒度**：一个任务对应一个或多个小提交，提交信息用 `<phase>: <task 简述>`，例如 `P4: implement permission_engine.compute_scope with structured predicate`。
- **验收标准（DoD）**：每个任务的 DoD 明确、可判定；阶段末尾的"阶段验收"把 DoD 汇总映射到设计方案 §19 的验收标准编号，方便第三方自查是否达标。
- **RPC 任务完成规则**：凡任务实现附录 B 方法，该任务的 DoD 自动包含第 6 节对应行列出的 handler 和成功/失败契约测试；状态迁移方法还必须覆盖非法前态与并发 CAS。契约测试文件即为该任务交付物，不能推迟到前端阶段补写；责任人为第 1.1 节对应 Phase 主责，备份人负责交叉复核。

---

## 1. 总体阶段与时间线

按 5 人团队规划 25 周功能基线（6 人团队可压缩为 24 周），并为跨模块集成、真机兼容与缺陷修复预留第 26–29 周缓冲，共 14 个阶段。部分阶段沿三条轨道并行推进：**组织/能力/权限**、**知识/运行时**、**桌面壳/前端**，在 Phase 9 任务工作流引擎处收拢汇合。

| 阶段 | 名称 | 依赖 | 建议周期 | 可并行轨道 |
|---|---|---|---|---|
| Phase 0 | 工程初始化、打包验证与 Runtime 选型 | — | 第 1–2 周 | 全员 |
| Phase 1 | 跨领域契约基础设施 | P0 | 第 2–3 周 | 轨道 A |
| Phase 2 | 组织基础（Company/Department） | P1 | 第 3–4 周 | 轨道 A |
| Phase 3 | 能力系统（Skill/PromptAsset/Capability） | P1 | 第 4–7 周 | 轨道 A |
| Phase 4 | 职员与权限（Employee/Permission Engine） | P2, P3 | 第 7–9 周 | 轨道 A |
| Phase 5 | Capability Engine 装配器 | P3, P4 | 第 9–10 周 | 轨道 A |
| Phase 6 | Provider、公司级本机 Backend、Credential Broker 与 Agent Runtime 骨架 | P1；Backend 任务另依赖 P2-T1 | 第 3–7 周 | 轨道 B（与 P2/P3 并行） |
| Phase 7 | 职员会话：安全上下文线程 | P4, P6 | 第 10–12 周 | 轨道 B |
| Phase 8 | 知识库与 RAG | P1, P3, P4, P6 | 第 8–13 周 | 轨道 B（与 P4/P5 尾段并行） |
| Phase 9 | 任务工作流引擎 | P5, P6, P7；P9-T10 另依赖 P8 | 第 12–19 周；第 12–13 周先完成 T1/T1a/T1b | 全员收拢 |
| Phase 10 | 治理：预算/审批 | P3(Tool Binding)、P7(会话状态)、P9-T1/T1b | 第 13 周先行 | 完成后才可开始 P9-T5 |
| Phase 11 | 可观测性与读模型 | P1, P9 | 第 19–21 周 | 轨道 A |
| Phase 12 | 前端 UI | P1（契约冻结后逐步接入） | 第 2–22 周，贯穿 | 轨道 C（全程并行） |
| Phase 13 | 质量门禁与发布加固 | 全部，含 P8 的双写一致性对账 | 第 21–25 周（功能基线）+ 第 26–29 周（仅集成/修复缓冲） | 全员 |

**交付切线**：

- 发布基线：公司隔离与 ACL、Claude Code CLI + OpenAI API Driver、Credential Broker、公司级 `local_process` Backend 的配置/持久化 lease 调度/健康检查/管理界面、九维会话安全上下文、单机任务闭环、Git/通用文件 Workspace、知识检索与引用、备份恢复、更新事务回退、安全/权限/恢复/契约测试和签名公证；不得因进度削减。
- 弹性范围：额外 Provider Driver、复杂组织图交互、额外观测图表、非必要批量体验和 UI 动效；进度不足时通过 feature flag 关闭，不阻塞发布基线。
- 容量约束：5 人场景第 1–25 周、6 人场景第 1–24 周的人员排期最多使用总人周的 85%，其余容量用于集成返工、人员不可用和真机差异；第 26–29 周不承诺新增功能。
- Go/No-Go：Phase 0 必须完成打包与 Runtime 选型；Phase 6 必须完成 P6-T3 的 Claude Code CLI Driver 与 P6-T4 的 OpenAI API Driver，并分别跑通真实调用契约，同时跑通本机 Backend 调度/恢复；Phase 9 必须跑通含知识固化的任务闭环；Phase 13 必须通过安全、恢复、更新回退和签名门禁。未达标时先关闭弹性范围，不压缩质量门禁。

**关键路径提示**：
- Phase 0 的打包验证（PyInstaller + native 依赖，含真实 ONNX 推理与 LanceDB 读写）与 Runtime 选型 Spike（OpenHands SDK 是否内嵌进某个 Provider Driver）是设计方案 §1、§4.4 明确点名的最高风险项，**必须第一、二周就跑通/决策完毕**，不能拖到后期。
- Phase 9（任务工作流引擎）是复杂度最高、耗时最长的阶段，建议投入最多人力并尽量提前完成其依赖（P5/P6/P7）。
- Phase 9-T1/T1b 先提供 task/approval schema 与 repository；Phase 10 的审批基础设施（P10-T1）随后完成，并必须早于 Phase 9 的 Worker Execute（P9-T5）接入 Tool Binding 四步校验链，不能等到 Phase 9 收尾才做。
- Phase 8 的知识提炼（P8-T2）需要调用 Provider，因此依赖 Phase 6，不能仅依赖 P1/P3/P4。

### 1.1 人员席位、主备责任与容量基线

人员以稳定席位而非具体姓名排期；项目启动时必须在排期系统中把姓名绑定到席位，人员变化只能换绑定，不能让责任空缺。

| 席位 | 主技能与主责 | 必须能备份 |
|---|---|---|
| A | Tauri/Rust、打包、更新、桌面集成 | B 的 IPC 安全；E 的前端接入 |
| B | Sidecar 平台、SQLite/迁移、身份与安全 | A 的 Supervisor；C 的权限引擎 |
| C | 组织、Capability、ACL | B 的数据层；E 的 PlanValidator |
| D | Provider、Credential 客户端、Knowledge/RAG | B 的备份恢复；E 的成本结算 |
| E | Workflow、会话、前端、QA 自动化 | C 的组织状态机；A 的发布门禁 |
| F（第 6 人，可选） | 专职前端、真机 QA、发布工程 | A/E；5 人场景由 A 与 E 分担本席位工作 |

| Phase | 乐观 / 基准 / 悲观 人周 | 主责 | 备份 | 并行上限与技能约束 |
|---|---:|---|---|---|
| P0 | 4.8 / 6 / 7 | A、B | D | 最多 3 人；签名/Runtime/native 依赖必须 A+B 共同复核 |
| P1 | 6 / 7.5 / 8.75 | B | A、C | 最多 2 人；事件、幂等、备份迁移不得由互不知情的分支独立冻结 |
| P2 | 4 / 5 / 5.83 | C | B | 最多 2 人；组织状态机与闭包表同一 owner |
| P3 | 5.6 / 7 / 8.17 | C | E | 最多 2 人；发布状态机由单一 owner 维护 |
| P4 | 6.4 / 8 / 9.33 | C、B | E | 最多 3 人；Permission Engine 与组织写事务联审 |
| P5 | 3.2 / 4 / 4.67 | C | D | 最多 2 人；必须等 P4 ACL 契约冻结 |
| P6 | 8.8 / 11 / 12.83 | D、A、E | B | 最多 3 人；Backend lease 与 Broker Rust/Python 两端分别做并发/安全联审 |
| P7 | 4.8 / 6 / 7 | E、D | B | 最多 2 人；会话事实与文件投影不能拆成不同事实源 |
| P8 | 8 / 10 / 11.67 | D | B、C | 最多 3 人；预过滤验证未通过前不得并行扩展检索 UI |
| P9 | 13.6 / 17 / 19.83 | E | C、D | 最多 4 人；generation/run/assignment repository 先于执行器并行开发 |
| P10 | 4 / 5 / 5.83 | B | E | 最多 2 人；P10-T1 必须先于 P9-T5 |
| P11 | 3.2 / 4 / 4.67 | B、E | D | 最多 2 人；读模型不拥有业务写入 |
| P12 | 8 / 10 / 11.67 | A、E（或 F） | C | 最多 3 人；只消费冻结的 rpc-schema |
| P13 | 4 / 5 / 5.83 | E、A（或 F） | B、D | 最多 4 人；测试 owner 不得是被测安全模块的唯一实现者 |
| **合计** | **84.4 / 105.5 / 123.08** |  |  |  |

任务级基准人周如下；每个任务的 optimistic=`0.8×基准值`，pessimistic=`7/6×基准值`，并继承上表主责/备份与原任务“依赖”。容量计算保留精确值，排期界面可显示两位小数但不得逐任务向上取整后再声称仍符合汇总；显示舍入差额计入 15% 非计划容量。该公式保证任务明细与 Phase 汇总可机械复算。

```text
P0:  T1=.5 T2=1 T3=1 T4=2 T5=1.5
P1:  T1=.5 T2=1.25 T3=1 T4=1 T4b=1.75 T5=.75 T6=.75 T7=.5
P2:  T1=2.25 T2=2.75
P3:  T1=.75 T2=.75 T3=1 T4=1 T5=1.25 T6=1.25 T7=1
P4:  T1=.75 T2=1.5 T2a=1 T3=2 T4=1 T5=1.75
P5:  T1=1.5 T2=2.5
P6:  T1=.75 T1a=1.25 T1b=1.5 T1c=1.5 T2=1.5 T3=1.25 T4=1.25 T5=1 T6=1
P7:  T1=1.25 T2=1 T3=1 T4=1.75 T5=1
P8:  T1=1.25 T2=2 T3=2.25 T4=2 T4a=1.25 T5=1.25
P9:  T1=1 T1a=1 T1b=1.75 T2=1 T3=1.5 T4=1.25 T5=2 T6=1 T7=1.5 T8=1.5 T9=1.25 T10=1 T11=1.25
P10: T1=2.75 T2=.75 T3=1.5
P11: T1=1.5 T2=2.5
P12: T1=1.5 T2=.75 T3=1 T4=1 T5=1.25 T6=1.25 T7=.75 T8=1.5 T9=1
P13: T1=1 T2=1.25 T3=.75 T4=.5 T4b=.75 T5=.75
```

容量校验：5 人 × 25 周 × 85%=106.25 人周，可覆盖 105.5 人周基准；A–E 每席位的 25 周计划上限均为 21.25 人周。6 人 × 24 周 × 85%=122.4 人周，105.5 人周基线占该可排容量的 86.2%（占 144 总人周的 73.3%），可在 24 周完成功能基线。5 人 × 29 周 × 85%=123.25 人周，可覆盖 123.08 人周悲观总量，因此第 26–29 周只能吸收估算偏差、人员不可用和集成修复，不能预排新增功能。每周由排期工具校验单席位承诺不超过 0.85 人周、主责与备份不能同时承担同一高风险步骤；超载时按“额外 Provider Driver → 复杂组织图交互 → 额外观测图表 → 非必要批量体验/UI 动效”顺序关闭弹性范围。

关键路径为 `P0 → P1/P2-T1 → P6-T1b/T1c → P3/P4 → P5/P7/P8 → P9-T1/T1a/T1b → P10-T1 → P9-T5..T11 → P11/P12 收口 → P13`。P0/P6/P9/P13 各设 Go/No-Go；主责请假超过 1 周时由表中备份接管，若备份也不可用则冻结该链路的新功能并消耗缓冲，不允许以删除隔离、审计、备份、恢复或安全测试换工期。

---

## Phase 0：工程初始化、打包验证与 Runtime 选型

**目标**：搭好 monorepo 骨架，验证 Tauri↔Sidecar 能通信、能打包签名并真实跑通本地推理/向量读写，决定 OpenHands SDK 的使用边界——这四件事是后续一切工作的地基，任何一件卡住都需要重新评估技术路线。

### P0-T1：Monorepo 骨架
**文件**：按设计方案附录 A 创建完整目录骨架（含包声明与可启动的最小模块），初始化：
- `apps/desktop/src-tauri/Cargo.toml`（Tauri 2 项目）
- `apps/desktop/src/`（Vite + React + TypeScript 项目，接入 Zustand/TanStack Query/React Flow/Monaco）
- `sidecar/pyproject.toml`（Python 3.12+，用 `uv` 管理依赖）
- `packages/rpc-schema/`（JSON Schema 契约源，先放一个最小 schema）、`packages/rpc-types/`（生成产物目录，先放空 `index.ts`）
- 根目录 `README.md`、`.gitignore`、`docs/`（放入设计方案与本计划）

**测试**：无（脚手架任务）。
**DoD**：`cd apps/desktop && npm run dev` 能起前端；`cd sidecar && uv run python -m acos.app` 能完成配置校验、输出结构化启动/退出日志并无报错退出；仓库通过 `git init` 纳入版本管理并提交初始骨架。

### P0-T2：Sidecar 最小 JSON-RPC 回环
**文件**：
- 创建 `sidecar/acos/app.py`、`sidecar/acos/rpc/server.py`
- 创建 `apps/desktop/src-tauri/src/rpc_client.rs`、`apps/desktop/src-tauri/src/main.rs`

**实现要点**（对照设计方案 §4.1、§4.2）：
- Sidecar 监听 Unix Domain Socket，实现首个正式方法 `sys.health`（对照附录 B.6）；本阶段至少返回 RPC 组件的真实状态，后续组件按同一 schema 扩展。
- 消息 framing 用 NDJSON（每行一个 JSON 对象，带 `type: request|response|notify`），为后续流式通知（附录 B.7）打基础，本阶段先只用 `request`/`response` 两种类型。
- Rust 侧 `rpc_client.rs` 实现 JSON-RPC 2.0 客户端，能连接 UDS 并调用 `sys.health`。
- 所有请求/响应携带 `trace_id` 字段（哪怕暂时不使用也要携带，为 P1 打基础）。

**测试**：
- `sidecar/tests/rpc/test_server_smoke.py`：起 server，用测试客户端连接调用 `sys.health`，断言返回 `status: healthy`。
- Rust 侧 `apps/desktop/src-tauri/src/rpc_client.rs` 内 `#[test]`：起一个测试用 UDS server（可用 sidecar 测试脚本或 mock），断言客户端能收到响应。

**DoD**：从 Tauri app 界面（哪怕是一个按钮）点击后能显示 Sidecar 返回的健康状态。

### P0-T3：Sidecar 生命周期管理（Supervisor）
**文件**：`apps/desktop/src-tauri/src/supervisor.rs`

**实现要点**（对照 §4.3、§4.2——生命周期接口只需 `Initialize/Start/Stop/Dispose/HealthCheck`，不实现 `Pause/Resume`，见 §18 非目标）：
- App 启动时拉起 Sidecar 子进程，传入 socket 路径与数据目录；等待就绪心跳，超时重试，超上限提示用户。
- 心跳检测（周期可配置，先用 5s）；崩溃自动重启，限流（同一分钟内重启超过 3 次则停止自动重启并显示告警）。
- App 退出时优雅关闭：发送 stop 信号，等待有限时间后强杀。

**测试**：
- 手动测试脚本 `scripts/test_supervisor_crash.sh`：故意 kill -9 sidecar 进程，观察 Tauri 日志里出现自动重启记录。
- Rust 单测覆盖限流逻辑：连续 4 次"崩溃"信号在 60 秒内触发，断言第 4 次不再自动重启且触发告警回调。

**DoD**：手动杀死 Sidecar 进程后，`sidecar_restart_ready_time` 达到 §4.5 的 release_gate 目标（< 3s，只算进程重启到能接受 RPC，不含任务恢复）；连续崩溃后应用明确提示用户而不是无限重启。

### P0-T4：打包、签名公证验证与真实推理/向量读写验证（本阶段最高优先级）
**文件**：
- `sidecar/build/pyinstaller.spec`
- `apps/desktop/src-tauri/tauri.conf.json`（签名/公证配置）
- `docs/打包验证记录.md`（记录验证过程与踩坑，供团队复用）

**实现要点**（对照 §4.4、§4.7、§19 第 11 条——**不能只验证打包体积/能否启动，必须验证真实功能**）：
1. 用 PyInstaller 把 `sidecar/acos/app.py` 打包成单一可执行文件，显式对 ONNX Runtime / LanceDB / tokenizers 做 `--collect-all`。
2. 在打包出的签名应用内，使用固定的小型测试模型真实跑通一次 ONNX 推理和一次 LanceDB 的 create/insert/query 往返——只验证"能打包、能启动"不够，必须证明 native 依赖在签名沙箱环境下真的可加载、可执行，这是本方案落地风险最高的环节。
3. 验证本地 embedding 模型权重的下载/校验/断点续传路径（模型不随可执行文件分发，见 §4.4）：模拟磁盘空间不足、下载中断、checksum 不匹配三种失败场景，确认都有明确的失败提示而不是静默卡死。
4. 验证打包产物在**一台没有装 Python 的干净 macOS arm64 机器**上能独立运行。
5. 验证 Tauri 应用签名 + 公证流程能跑通（哪怕用临时开发者证书）。

**测试**：无自动化测试（这是环境验证任务），但必须产出 `docs/打包验证记录.md`，记录：
- 打包命令与产物大小
- ONNX 推理与 LanceDB 读写的实测结果（不是"应该能跑"，是"跑了，结果是什么"）
- 模型下载失败场景的实测截图/日志
- 在干净机器上的运行结果
- 遇到的 native 依赖加载问题与解决方式、签名公证的命令与结果

**DoD**：一份签名公证过的 `.app` 在全新 macOS arm64 环境（无 Python、无开发工具）双击可打开，能通过 UI 触发 `sys.health`，且能真实完成一次 ONNX 推理与一次 LanceDB 读写往返。**这个 DoD 不达成，不允许进入 Phase 1。**

### P0-T5：Runtime 选型 Spike（OpenHands SDK 的使用边界）
**文件**：`docs/Runtime选型记录.md`

**实现要点**（对照设计方案 §1、§11.1 的契约边界；**这是决策任务，不是编码任务**）：本方案的 Agent Runtime / ProviderAdapter / Workspace / Employee 会话是自研契约，OpenHands SDK 至多作为某个代码类 CLI Provider Driver 的内部实现细节。本任务要在写 Phase 6 的 Provider Driver 代码之前，花 2–3 天做选型验证并产出一份决策记录：
1. 尝试用 OpenHands SDK 包一层，验证它的 Agent/Tool/Sandbox 抽象能否在不破坏我们自己 `ProviderAdapter` 契约（§11.2）的前提下，实现 CLI Provider 包装、原生会话恢复、事件流式输出、取消、Workspace 挂载、工具调用这六项能力。
2. 产出映射表：哪些能力可以直接复用 SDK、哪些需要包装适配、哪些必须完全自研。
3. 若验证失败（SDK 的对象模型与我们的契约冲突过大，适配成本高于自研），**明确决定不使用 OpenHands SDK**，Phase 6 的 CLI Provider Driver 全部自研；决策记录必须是可直接执行的终局结论。
4. 本任务必须在第 2 周结束前完成评审并形成“使用/不使用/部分使用”的唯一结论；若届时 Spike 尚不能证明 SDK 路径可行，默认结论为“不使用、按自研契约实现”，不得继续占用 Phase 6 关键路径。后续如要改判只能走正式 ADR，不阻塞既定 Driver 开发。

**测试**：无（决策任务）。
**DoD**：第 2 周结束前 `docs/Runtime选型记录.md` 产出明确结论（用/不用/部分用+映射表）；未按期证明可行即记录自研结论，团队据此在 Phase 6 落地，不允许 Phase 6 开工时这个问题还悬而未决。

### 阶段验收（Phase 0）
对应设计方案 §19 第 11 条的打包与真实功能验证子集（完整第 11 条要到 Phase 13 才能全部满足，此处验收打包链路与 native 依赖真实可用，且 Runtime 选型已有明确结论）。

---

## Phase 1：跨领域契约基础设施

**目标**：把设计方案 §5 定义的横切规范代码化——所有后续模块都要用这些基础设施，必须先建好。

### P1-T1：统一错误码
**文件**：`sidecar/acos/rpc/errors.py`

**实现要点**（对照 §5.1）：
- 定义 `AcosError` 基类：`code, message, cause, suggestion, trace_id`。
- 按模块前缀定义错误码常量：`ORG_*`、`CAP_*`、`WF_*`、`RT_*`、`PROV_*`、`BACKEND_*`、`KG_*`、`GOV_*`、`SYS_*`（对照 §5.1 给出的示例逐条建常量，后续模块开发时按需补充新码，但前缀分类不能破）。常量列表以设计方案附录 C 为准，首版实现附录 C 各领域小节末尾列出的核心错误码子集（约 30 个，包括但不限于：`ORG-VALIDATION`、`ORG-NOT-FOUND`、`ORG-STATE-INVALID`、`ORG-PERM-DENIED`、`ORG-DEPT-CYCLE`、`ORG-COMPANY-DISSOLVED`、`CAP-VALIDATION`、`CAP-VERSION-IMMUTABLE`、`CAP-SNAPSHOT-CHECKSUM-MISMATCH`、`CAP-QUALITY-GATE-FAILED`、`ASSET-CROSS-COMPANY-REF-DENIED`、`TEMPLATE-CROSS-COMPANY-DENIED`、`WF-BUDGET-EXCEEDED`、`WF-FIX-MAX-ROUNDS`、`RT-SESSION-BUSY`、`RT-SESSION-STALE`、`RT-SESSION-READONLY`、`RT-RESUME-FAILED`、`PROV-UNAVAILABLE`、`PROV-AUTH-INVALID`、`PROV-BUDGET-FROZEN`、`BACKEND-UNAVAILABLE`、`BACKEND-CAPACITY-FULL`、`BACKEND-DRAINING`、`BACKEND-PATH-DENIED`、`BACKEND-RECOVERY-UNSAFE`、`BACKEND-QUEUE-TIMEOUT`、`KG-EXTRACT-FAILED`、`KG-EMBED-VERSION-MISMATCH`、`KG-CLOUD-CONSENT-REQUIRED`、`GOV-APPROVAL-REJECTED`、`GOV-BUDGET-CURRENCY-INVALID`、`GOV-BUDGET-LIMIT-INVALID`、`GOV-BUDGET-POLICY-INVALID`、`SYS-INTERNAL`、`SYS-OPTIMISTIC-LOCK-CONFLICT`、`SYS-IDEMPOTENCY-CONFLICT`、`SYS-MIGRATION-FAILED`、`SYS-BACKUP-IN-PROGRESS`、`SYS-BACKUP-QUIESCE-TIMEOUT`、`SYS-BACKUP-INCOMPATIBLE`、`SYS-BACKUP-INCONSISTENT`、`SYS-BACKUP-NOT-FOUND`、`SYS-UPDATE-FAILED`、`SYS-UPDATE-SIGNATURE-INVALID`、`SYS-BOOTSTRAP-ROOT-INVALID`），后续 Phase 按需补充新码。
- RPC 层统一异常处理：任何 `AcosError` 抛出后被 `rpc/server.py` 捕获并序列化为标准错误响应。

**测试**：`sidecar/tests/rpc/test_errors.py`
- 测试任意方法抛 `AcosError(code="ORG-PERM-DENIED", ...)` 后，RPC 响应体符合 `{code,message,cause,suggestion,trace_id}` 结构。
- 测试 `BACKEND-UNAVAILABLE/BACKEND-RECOVERY-UNSAFE/BACKEND-QUEUE-TIMEOUT` 等 Backend 错误同样通过统一序列化，不被误归类为 Provider 或 Runtime 错误。
- 测试未预期的 Python 异常（非 AcosError）被兜底捕获，转成 `SYS-INTERNAL` 错误码而不是让进程崩溃或把 stack trace 泄露给客户端。

**DoD**：任意 RPC 方法内抛出业务异常，客户端收到的都是结构化错误，不会看到裸 Python traceback。

### P1-T2：领域事件（不可变）与 Outbox 投递状态
**文件**：
- `sidecar/acos/events/models.py`（事件信封结构）
- `sidecar/acos/events/outbox.py`（Outbox 消费）
- `sidecar/migrations/0001_domain_events.sql`

**实现要点**（对照 §5.2——**`domain_events` 与投递状态是两张表，不要合一**）：
- `domain_events` 表：`event_id, company_id, event_type, aggregate_type, aggregate_id, aggregate_version, task_id?, employee_id?, run_id?, occurred_at, trace_id, actor_type, actor_id, payload, metadata`，只有 insert，不提供 update/delete；所有读模型先按不可变 `company_id` 过滤，不依赖解析 payload。
- `outbox_deliveries` 表：`delivery_id, event_id(FK), consumer_name, status(pending|delivered|failed), attempt_count, next_retry_at, last_error`。
- 提供 `emit_event(session, company_id, event_type, aggregate_ref, scope_ref, payload, actor_context)`：**必须在调用方的同一数据库事务内写入 `domain_events` 与初始 `outbox_deliveries`**。`scope_ref` 提供 task/employee/run 维度；`actor_context` 只接受服务端解析的 LocalOwner、活动 assignment 或 system 身份。
- Outbox Worker（`sidecar/acos/events/outbox.py` 内 `OutboxWorker` 类）：轮询 `outbox_deliveries` 中 `pending`/可重试的 `failed` 行，按 `(event_id, consumer_name)` 幂等消费，只更新 `outbox_deliveries`，不改写 `domain_events`。
- 注册设计方案 §5.2 的全部具名事件。建立 `organization_transition_event_map`，CI 校验公司、部门、领导、汇报关系、职员和授权的每个状态转换都映射唯一事件类型；业务阶段逐项实现同事务写入。

**测试**：`sidecar/tests/events/test_outbox.py`
- 测试 `emit_event` 在事务回滚时，`domain_events` 与 `outbox_deliveries` 都不会残留（事务原子性）。
- 测试 Outbox Worker 对同一 `(event_id, consumer_name)` 重复投递时只处理一次（幂等），且 `domain_events` 本身从未被修改。
- 测试事件信封缺 `company_id/trace_id/actor` 时拒绝写入；按 company/task/employee/run 查询不读取其他公司的记录。

**DoD**：能在一个事务内写业务表 + 写 `domain_events` + 写初始 `outbox_deliveries`，事务提交后 Outbox Worker 能在后台消费到该事件；杀掉 Worker 重启后不会重复处理已消费事件。

### P1-T3：RPC 契约中间件（trace_id / 幂等键 / 流式 framing）
**文件**：`sidecar/acos/rpc/server.py`（在 P0-T2 基础上扩展）、`sidecar/acos/rpc/idempotency.py`、`sidecar/acos/rpc/streaming.py`、`sidecar/migrations/0001b_rpc_idempotency.sql`

**实现要点**（对照 §5.3、§4.1、附录 B.7）：
- 每个请求若未带 `trace_id` 则服务端生成一个，全链路日志都带上它。
- `packages/rpc-schema` 中每个方法强制声明 `is_write`、`retry_failed` 与幂等保留窗口，禁止根据方法名猜测。写方法要求 `idempotency_key`；`rpc_idempotency_records` 保存 `company_id, actor_type, actor_id, method, idempotency_key, request_hash, status(processing|succeeded|failed), response_ref?, error_ref?, created_at, updated_at, expires_at, version`，唯一键为 `(company_id, actor_type, actor_id, method, idempotency_key)`。去除 trace_id 后规范化 DTO 计算 request hash：同键同 hash 重放原结果/错误或返回同一 processing operation，同键不同 hash 抛 `SYS-IDEMPOTENCY-CONFLICT`；失败后的同 key 重试严格服从方法 schema 并用 CAS 重新占有。
- DTO 与实体解耦：`sidecar/acos/rpc/dto.py` 里请求/响应模型由 `packages/rpc-schema` 生成（不手写），不直接暴露 ORM 实体。
- 把设计方案附录 B.0 的 `PageRequest/Page<T>`、过滤 DTO 与 `TranscriptRange` 落入 JSON Schema；集合方法统一默认 50/上限 200 的签名 opaque cursor，transcript 默认 100/上限 500 且按 sequence 升序。游标绑定 method/company/subject/filter_hash/sort_key，篡改、跨主体或更换 filters 后复用统一返回 `SYS-PAGE-CURSOR-INVALID`；所有 DTO `additionalProperties=false`。
- 流式通知：`stream_id` 由服务端分配。流式请求先返回 `stream_started{stream_id,aggregate_type,aggregate_id}`；`session.sendMessage` 每个 turn 新建 stream，后台 topic 由 Rust 建内部订阅时按 `(IPC session,topic,aggregate_id)` 建 stream。每条 `notify` 带从 1 开始的单调 `sequence`；补发必须带原 stream_id + resume_from_sequence，且只在同一已认证 IPC 会话、同一 Sidecar 进程和 1000 条/5 分钟缓冲内有效，否则返回 gap 并由客户端刷新事实查询 RPC。客户端不得创建、跨请求复用或拼接 stream_id。
- 按设计方案 §4.1 实现 logical IPC session resume：握手 nonce 用后失效，Rust 内存持有的 session id + resume MAC 仅在 Rust/Sidecar 均未重启时可于传输断开后 5 分钟内恢复同一 session。session 恢复窗口与单 stream 的 1000 条/5 分钟缓冲是独立且必须同时满足的门禁；恢复 session 后目标 sequence 已淘汰仍返回 gap，缓冲仍在但进程/session 已变化也返回 gap。任一进程重启、超时或 MAC 错误必须新建 session，resume MAC 不暴露给 WebView。

**测试**：`sidecar/tests/rpc/test_idempotency.py`、`sidecar/tests/rpc/test_streaming.py`
- 测试同一 `idempotency_key` 调用两次某个写方法，第二次不重复执行副作用，且返回值与第一次一致。
- 测试不同 `idempotency_key` 的两次调用各自正常执行。
- 测试公司 A/B 使用同一 key 不共享记录；同公司不同 actor 不共享；同键不同 payload 被拒绝；并发相同请求只有一个执行者；窗口过期按 schema 重新执行但旧审计仍可查。
- 对 `retry_failed=false` 的方法验证 failed 结果只能重放；对 `retry_failed=true` 的方法验证仅同一 request hash 可 CAS 重新占有，旧执行者不能覆盖新结果。
- 测试流式通知的 `sequence` 单调递增；测试断线重连带 `resume_from_sequence` 能补发缓冲内的事件；测试超出缓冲范围返回 `gap` 标记。
- 测试客户端伪造/跨 aggregate/跨 IPC 会话复用 stream_id 被拒；`session.sendMessage` 的 stream_id 与服务端生成的 session_turn_id 一一对应，Sidecar 重启后旧 stream 返回 gap。
- 测试瞬时 UDS 断开后 5 分钟内由 Rust 恢复 logical session 可补发；超时、MAC 篡改、Rust/Sidecar 任一重启均不可恢复旧 session。
- 分页契约测试覆盖默认/上下界、稳定排序不重不漏、篡改 cursor、跨公司/主体/方法复用、更换 filters 后复用与未知过滤字段；均必须按规范拒绝，不静默降级。

**DoD**：对任意写类 RPC 方法重放同一请求不会产生重复副作用；流式通知具备断线重连补发能力。

### P1-T4：持久化通用列与迁移框架
**文件**：
- `sidecar/acos/store/base_model.py`（通用列 mixin：`created_at, updated_at, version, deleted_at, deleted_by, delete_reason`）
- `sidecar/acos/store/append_only.py`（不可变记录基类：主键 + created_at/occurred_at，不暴露 update/delete）
- `sidecar/acos/store/migrator.py`（Forward-only 迁移执行器）
- `sidecar/migrations/`（迁移脚本目录，含迁移版本表 `schema_migrations`）

**实现要点**（对照 §5.4、§17——**迁移策略是"生产只前向 + 升级前自动备份"，不是"每个迁移都要能 down 回滚生产数据"**）：
- 可变聚合/资源表通过 base model mixin 带通用列；`domain_events/conversation_events/provider_model_prices/backend_health_checks/backend_health_daily/五类业务审计/usage_records/evidence ledger` 使用 append-only 基类，不带 `updated_at/version/deleted_*` 且 repository 不暴露 update/delete。P1-T5 先建 ACL/知识访问/知识治理/组织四类基础审计，`backend_change_audit` 随 P6-T1b 建立但复用同一基类；Backend 健康表只允许 P6-T1b 先聚合校验后的 7/90 天受控清理。`outbox_deliveries/rpc_idempotency_records/approvals/backend_queue_entries/backend_leases` 是可变状态表，使用 CAS version，但不得软删其引用的事实。
- 乐观锁：更新操作用 `WHERE version = ?` 模式，未命中则抛 `SYS-OPTIMISTIC-LOCK-CONFLICT`。
- 软删除：删除操作只置 `deleted_at/deleted_by/delete_reason`，查询默认过滤已删除记录（除非显式 `include_deleted=True`）。
- 迁移器：**生产环境执行迁移前自动调用 P1-T4b 的 `backup.create_snapshot()` 做一次跨存储一致快照**，迁移失败则从该快照恢复，不依赖迁移脚本自带的 `down`。`down` 脚本只在开发阶段、迁移尚未随任何版本发布前使用，一旦随版本发布就不再允许被回滚。迁移脚本本身要求幂等（重复执行同一已应用迁移是 no-op）。

**测试**：`sidecar/tests/store/test_migrator.py`、`test_optimistic_lock.py`、`test_soft_delete.py`
- 迁移：对一批迁移脚本执行 up 全部成功，重复执行验证幂等（不报错、不重复建表）。
- 迁移前自动调用快照（用 P1-T4b 的 fake/mock 快照函数验证调用发生，真实备份恢复演练在 P1-T4b 与 P13-T4）。
- 乐观锁：并发场景模拟——两个"并发"更新持有同一旧 `version`，第一个成功，第二个应收到冲突错误。
- 软删除：删除记录后默认查询查不到，`include_deleted=True` 能查到且 `deleted_at` 非空。
- append-only：静态检查与 repository 测试确认业务连接没有 update/delete API，直接 SQL 更新/删除由 authorizer/trigger 测试拒绝；只有 P11-T2 的最小权限 RetentionCompactor 可在“日聚合 + compaction manifest + root/计数校验”同事务后删除无引用 allow 明细，失败时源记录原样保留。
- 另两个最小权限删除入口仅为 P6 健康记录受控聚合清理与 P8 LocalOwner 合规硬删除。P8 删除内容型事件/派生行前同事务写不含正文的 HardDeletionPerformed + governance audit（source ids/计数/hash/reason）；通用 repository、RPC 条件或任意 SQL 仍无 delete 权限。

**DoD**：`acos-migrate up` 命令可用且生产路径下自动调用备份快照；任意业务表的更新在并发冲突下能被正确拦截。

### P1-T4b：跨存储一致备份快照（snapshot barrier + manifest + 加密 + 保留/删除）
**文件**：
- `sidecar/acos/store/backup.py`（`create_snapshot()` / `restore_snapshot()` / `list_snapshots()` / `delete_snapshot()`）
- `apps/desktop/src-tauri/src/backup.rs`（DEK 的 envelope encryption：生成随机数据密钥，用 Keychain 主密钥包装后随 manifest 存放）
- `sidecar/migrations/0002c_snapshot_epochs_backups.sql`（`snapshot_epochs/backup_manifests`）

**实现要点**（对照 §4.7——**核心是跨存储一致，必须按顺序执行每一步，不能省略 barrier 或 manifest**）：
- **冻结（barrier）**：`create_snapshot()` 开始时置一个共享写门禁拒绝新写入（新写入请求报 `SYS-BACKUP-IN-PROGRESS`，短暂重试而不是直接失败），暂停领取新的 outbox delivery，要求 active turn 在安全边界落 Checkpoint 后暂停，并等待当前数据库事务、delivery 与投影写入在有界超时内完成。任一 writer 未 quiesce 则报 `SYS-BACKUP-QUIESCE-TIMEOUT`、解除门禁并放弃本次快照，禁止一边继续写一边打包。
- **记录 `snapshot_epoch`**：严格建立设计方案 §4.7 的 `snapshot_epochs(snapshot_epoch,state,sqlite_event_watermark,outbox_delivery_watermark,lancedb_generation_map_json,session_watermarks_json,barrier_started_at,captured_at?,failure_code?)` 与 `backup_manifests(backup_id,snapshot_epoch,kind,app_version,schema_version,archive_path,manifest_sha256,encrypted_archive_sha256,wrapped_dek,file_count,total_bytes,status,created_at,completed_at?,deleted_at?,delete_reason?)`；epoch 用 AUTOINCREMENT 且永不复用，manifest 对 epoch 唯一。SQLite 用在线备份 API 生成快照文件；LanceDB 按 company_id 稳定排序记录所有当前 active generation 为 `[{company_id,generation_id}]`（尚无索引的公司省略，之后的新写入走 COW 进入下一代）；遍历 `session_threads` 按 company/employee/security_context 稳定顺序记录每条线程的 `last_checkpoint_offset`。
- **解冻**：清除冻结标志，恢复正常写入。
- **打包**：把 SQLite 快照文件、LanceDB 各公司的固定 generation 数据文件、会话文件目录一起打包，写入 manifest（JSON）：`{app_version, schema_version, snapshot_epoch, lancedb_generations:[{company_id,generation_id}], files:[{path,sha256}], session_watermarks:[{company_id,employee_id,security_context_key,last_checkpoint_offset}]}`。只有 epoch=ready、归档与 manifest hash 都持久化后 manifest 才 CAS 为 available；creating/failed 临时文件不出现在 list/restore。
- **加密**：调用 Rust 侧 `backup.rs` 生成随机 DEK，对打包好的归档文件加密；DEK 用 Keychain 主密钥包装后与 manifest 一起存放；备份目录权限收紧为仅当前系统用户可读。
- **恢复**：`restore_snapshot(backup_id)` 参数校验：backup_id 必须指向 `backup_manifests` 中 `status=available` 且 `deleted_at IS NULL` 的记录；不存在、已删除或 status 非 available 时返回 `SYS-BACKUP-NOT-FOUND`。校验通过后：先用 DEK（经 Keychain 主密钥解包）解密归档，离线校验 manifest 的每个文件 hash 与 `schema_version` 兼容性 → 停止 Sidecar 写入 → 仅替换 manifest 列出的 SQLite/LanceDB/会话投影业务根，显式排除 Rust `system/`、Keychain 与更新 journal → 重启 Sidecar → 跑跨存储 reconciler（校验 SQLite/LanceDB/会话文件的 watermark 都对应 manifest 里记录的同一个 `snapshot_epoch`）→ 通过才开放写入；不通过报 `SYS-BACKUP-INCONSISTENT` 并自动回退到恢复前自动生成的那份快照。
- **保留与删除**：默认保留最近 5 份且不超过 30 天，超出自动清理（后台定时任务）；`delete_snapshot(backup_id)` 物理删除归档文件+manifest；提供"立即删除全部历史备份"的批量接口。

**测试**：`sidecar/tests/store/test_backup.py`
- 备份期间持续对 SQLite/会话线程发起并发写入，验证这些写入在冻结窗口内被短暂拒绝重试，冻结解除后能成功写入，且没有写入落在被打包的快照范围之外又被误算入 manifest。
- 构造无法在期限内暂停的 active turn/current transaction，验证快照失败、未生成可见 backup manifest、门禁最终解除且原业务继续运行。
- 恢复后 SQLite/LanceDB/会话文件的 watermark 一致性测试（构造三者故意不一致的历史归档，验证 reconciler 能检测并拒绝，报 `SYS-BACKUP-INCONSISTENT`）。
- 篡改检测：手工改动归档内一个文件字节，恢复时应因 hash 不匹配被拒绝。
- 加密：验证归档文件本身不可被不知道 DEK 的进程直接读出有效内容；删除/损坏 Keychain 主密钥后无法解密任何历史备份。
- 保留策略：连续生成超过 5 份或超过 30 天窗口的备份，验证自动清理只保留符合策略的部分。
- 完整备份恢复演练：用带真实数据的副本执行"备份 → 迁移 → 模拟迁移失败 → 从备份恢复 → 校验数据完整"，测试文件为 `test_backup_restore.py`。

**DoD**：Sidecar 内部 quiesce/snapshot/restore/delete service 可供 Rust 编排；备份是可验证的跨存储一致快照（有 manifest 且恢复后 reconciler 校验通过）；加密/保留/删除策略均有测试覆盖。`settings.backup.*` Tauri-only command 在 P12-T9 完成组合与注册。

### P1-T5：审计表
**文件**：
- `sidecar/acos/organization/audit.py`
- `sidecar/migrations/0002_audit_tables.sql`
- `sidecar/acos/knowledge/access_log.py`
- `sidecar/acos/knowledge/governance_audit.py`
- `sidecar/acos/organization/audit_retention.py`

**实现要点**（对照 §5.5——应用层不可篡改，不代表能抵御拥有本机管理员权限的攻击者，代码与文档都不应做超出这个范围的承诺）：
- `acl_audit_log`：`id, subject, company_id, resource_type, resource_id, action, decision, matched_rule, scope_hash, trace_id, timestamp`，只提供 insert 接口。索引 `(subject, timestamp)`、`(resource_type, resource_id, timestamp)` 与 `(decision, timestamp)`。
- `knowledge_access_logs`：`id, company_id, operator?, subject, action(search|list|get|citation|context_pack), query_hash, scope_hash, result_knowledge_ids(JSON), result_count, decision, matched_rules(JSON), trace_id, timestamp`；UI view-as 同时记录 LocalOwner operator 与 employee subject。
- `knowledge_governance_audit`：`id, company_id, resource_type, resource_id, action, before_snapshot, after_snapshot, operator, reason, trace_id, timestamp`，只提供 insert 接口。
- `org_change_audit`：`id, company_id, aggregate_type, aggregate_id, action, before_snapshot, after_snapshot, operator, reason, trace_id, timestamp`，索引 `(company_id,timestamp)` 与 `(company_id,aggregate_type,aggregate_id,timestamp)`，同样只提供 insert。
- `audit_record_refs`：append-only 引用边 `ref_id,company_id,audit_table,audit_id,ref_type(evidence|citation|checkpoint|incident),ref_id_value,created_at`。证据/引用/Checkpoint/incident 创建时必须同事务插入；RetentionCompactor 只通过该表的 `NOT EXISTS` 反连接判定“无引用”，禁止扫描任意 JSON 猜测。
- 保留策略：两张访问日志的 deny 明细默认不过期；allow 明细保留 90 天后由每日生命周期 Worker 调用幂等压缩任务聚合为日统计，幂等键为 `(log_type, company_id, date)`，聚合前后计数守恒。`knowledge_governance_audit` 与 `org_change_audit` 明细长期保留。
- 提供 `write_acl_audit(...)`、`write_knowledge_access(...)`、`write_knowledge_governance_audit(...)` 与 `write_org_change_audit(...)`；`operator` 只接受服务端确定的身份（见 P1-T6）。

**测试**：`sidecar/tests/organization/test_audit.py`、`sidecar/tests/knowledge/test_governance_audit.py`
- 测试写入后无法通过任何暴露的接口修改或删除审计记录（代码里根本不提供该能力）。
- 测试索引存在（可用 EXPLAIN QUERY PLAN 断言查询走了索引，避免全表扫描）。
- `acl_audit_log` 缺少 resource/action 时拒绝写入；`knowledge_access_logs.result_knowledge_ids` 与最终返回结果完全一致。
- 知识删除/拒绝/确认/重试分别产生不可修改的 `knowledge_governance_audit`，operator、resource、before/after 与实际变更一致。
- allow 明细压缩重复执行幂等、计数守恒且不删除 deny 明细。

**DoD**：审计写入函数就位，没有任何路径可以修改/删除已写入的审计记录。

### P1-T6：本地身份主体（LocalOwnerPrincipal）
**文件**：
- `sidecar/acos/organization/principal.py`
- `sidecar/migrations/0002b_local_owner.sql`

**实现要点**（对照 §5.6——**解决"actor/operator/approved_by 字段该填什么、不能让客户端随便声明"的问题**）：
- `local_owner` 表本机唯一一行：`owner_id`（首次启动生成的 UUID）、`display_name`、`created_at`。
- 提供 `get_local_owner() -> LocalOwnerPrincipal` 单例访问函数，首次调用时若表为空则创建。
- 提供 `resolve_actor(context)` 辅助函数：UI 发起的管理操作（发布、调岗、审批、创建公司等）返回 `LocalOwnerPrincipal.id`；Agent 执行任务过程中产生的事件返回当前 `task_node.assignee_employee_id`。所有需要 `actor`/`operator`/`approved_by` 的写路径（P1-T2 的 `emit_event`、P1-T5 的审计写入函数）都通过这个函数取值，**RPC 层不接受把这些字段作为客户端可传入的参数**——如果某个 DTO 定义里出现了 `actor`/`operator` 作为入参字段，视为设计缺陷，需要在 code review 阶段拦下。

**测试**：`sidecar/tests/organization/test_principal.py`
- 首次调用 `get_local_owner()` 创建唯一记录，第二次调用返回同一 `owner_id`（不重复创建）。
- 静态检查（代码扫描）：`packages/rpc-schema` 里任何写方法的请求 DTO 不包含 `actor`/`operator`/`approved_by` 字段。

**DoD**：本机身份主体机制就位；后续所有阶段的事件/审计写入都通过 `resolve_actor`，不接受客户端自称身份。

### P1-T7：跨领域 HumanIntervention 基础表与 Repository

**文件**：`sidecar/acos/interventions/models.py`、`sidecar/acos/interventions/repository.py`、`sidecar/migrations/0002d_human_interventions.sql`、`sidecar/tests/interventions/test_repository.py`

**实现要点**（对照设计方案 §5.7/§10.2.2）：
- 提前建立 `human_interventions`，字段为 `intervention_id/company_id/task_id?/node_id?/run_id?/subtype/target_ref/status/allowed_actions/resolution_ref?/resolved_at?/resolved_by?/trace_id/version`；subtype 固定为 `approval|manual_task|dead_letter|employee_drain|company_dissolution|backend_recovery`，`task_id/node_id/run_id` 是可空 opaque UUID，不对尚未创建的未来表声明悬空 FK。`resolved_by` 由服务端主体解析注入。
- repository 提供 `create_or_get_open(company_id, subtype, target_ref, ...)`、`get/list` 与 `resolve_cas(expected_version, resolution_ref)`；用部分唯一约束保证同一 `(company_id,subtype,target_ref)` 最多一个 open 项，所有查询先按 company_id 隔离。
- repository 不解释 `allowed_actions`、不执行领域副作用。P2/P4/P6/P9/P10 的领域服务负责校验动作、完成自身事务后才 CAS 关闭 intervention；P11 只读聚合，UI 不直写。

**测试**：open 唯一、跨公司不可见、`task_id=NULL` 可用、并发 resolve 仅一个成功、重复 create 返回同一 open 项、已关闭后可为新的目标版本创建新项；未知 subtype、客户端直接修改 allowed_actions/status 均拒绝。

**DoD**：Phase 2 的 company_dissolution、Phase 4 的 employee_drain、Phase 6 的 backend_recovery 无需等待 Workflow migration 即可持久化，且领域状态机仍由各自 owner 控制。

### 阶段验收（Phase 1）
支撑设计方案 §19 第 21、22 条（幂等/可审计/可从 Checkpoint 恢复的基础设施部分，含 `actor` 字段服务端注入）。此时应有：错误码体系、事件与 Outbox 投递分离、迁移+备份框架、审计表、本地身份主体、跨领域 HumanIntervention repository 全部有单测覆盖且可独立运行。

---

## Phase 2：组织基础（Company / Department）

**目标**：落地公司/部门的数据模型与闭包表，这是权限体系的地基。**注意引导顺序**：创建公司时职员体系尚不存在，不能要求"创建即有负责人"，本阶段两个任务的顺序和边界因此做了调整。

### P2-T1：Company 模型、默认策略与解散协调器
**文件**：
- `sidecar/acos/organization/models.py`（新增 `Company`）
- `sidecar/acos/organization/service.py`（`start_company_dissolution` / `complete_company_dissolution`）
- `sidecar/acos/organization/dissolution.py`
- `sidecar/migrations/0003_companies_and_policies.sql`

**依赖**：P1-T7（跨领域 HumanIntervention repository）。

**实现要点**（对照 §6.1）：
- Company 状态为 `initializing|active|dissolving|dissolved`；迁移同时建立设计方案 §6.1 完整定义的版本化 `knowledge_policies/embedding_policies/security_policies`，落默认值、单 active/版本唯一约束和 company pointer，并在 company 行保存 `default_provider_policy={free:ProviderModelRef|null,standard:ProviderModelRef|null,premium:ProviderModelRef|null}`（`ProviderModelRef={provider_id,model}`，三键必有）与设计方案定义的 `default_budget_policy` JSON。Embedding active_generation_id 初始为 NULL，首次索引切换后设置。首版不另建 `provider_policies/budget_default_policies` 表，使 bootstrap 不依赖尚未实现的业务服务且与设计方案 §6.1/§15 一致；通用 `org.company.update` 不得修改这两类策略，必须走 `provider.tierMapping.update` 或 `settings.budgetDefault.update` 的专用校验与审计。SecurityPolicy v1 只由 bootstrap 创建，不暴露公共修改 RPC。
- `start_company_dissolution` 用 CAS 把 active 公司转为 dissolving，同事务写 `CompanyDissolutionStarted`、组织审计和各消费者 delivery；dissolving 后新任务/会话/Provider 调用/知识摄取/配置等业务写统一拒绝，只保留按公司隔离的只读/审计及 LocalOwner 的 `workflow.companyDissolution.resolve`、`workflow.backendRecovery.resolve` 两个收敛命令。例外命令只能处理该公司的 open intervention，不能创建新业务执行。
- `dissolution.py` 按 Organization/Task/Session/Knowledge/Provider/Backend 六个 consumer watermark 对账，全部成功后才由 `complete_company_dissolution` 转 dissolved 并写 `CompanyDissolved`；失败项创建 `company_dissolution` intervention。各消费者分别在 P4-T2、P9-T10、P7-T5、P8-T5、P6-T5、P6-T1b/T1c 实现，P13-T2 做故障恢复联调。
- `workflow.companyDissolution.resolve` 只允许 LocalOwner 对 open 的 `company_dissolution` intervention 执行 `retry_failed_consumers`；服务端依据已持久化 watermark 只重投未完成 consumer delivery，以 intervention version CAS 和 delivery 唯一键防止并发/重复重试，成功收敛后关闭 intervention。详情查看复用 `workflow.humanIntervention.list`，不另造无审计的写入口；该类 intervention 允许 `task_id=NULL`。
- `org.company.update` 是直接编辑命令，必须携带 expected_version 并返回新 version；与 tier mapping/budget default 等公司行 JSON 更新共享 Company CAS，冲突返回 `SYS-OPTIMISTIC-LOCK-CONFLICT`，禁止最后写入者静默覆盖。

**测试**：`sidecar/tests/organization/test_company.py`
- 状态转换只允许 `initializing→active→dissolving→dissolved`；非法跳转被拒。
- bootstrap 原子创建三类默认策略和两项公司行内默认配置；默认预算负数、未知 on_budget_exceeded 或试图通过 `org.company.update` 绕过专用策略命令均被拒绝。
- 两个客户端用同一 company expected_version 更新时只有一个成功；tier mapping/budget default 更新后，持旧 Company version 的 company.update 也必须冲突。
- start dissolution 后先保持 dissolving；只有六个测试 consumer watermark 完成才转 dissolved 并写唯一 `CompanyDissolved`。
- 构造部分消费者失败且 `task_id=NULL` 的 intervention：非 LocalOwner、已关闭项和跨公司请求被拒；重试只重投失败消费者，并发重复请求只产生一次有效 delivery，全部 watermark 收敛后唯一关闭 intervention 并完成解散。
- dissolving 状态下普通业务写、Backend 配置/probe 均拒绝；只读审计可用，且既有 backend_recovery 可安全 resolve 并释放确认已退出的 lease，随后 Backend watermark 和公司解散可收敛。
- 已解散公司不能再创建新部门/职员（调用应报 `ORG-COMPANY-DISSOLVED`）。

**DoD**：公司状态机、默认策略表、解散协调器和故障恢复测试可用；`org.company.create/activate` 的跨表事务在 P2-T2/P4-T2 完成，`org.company.dissolve` 已进入可恢复流程，`workflow.companyDissolution.resolve` 有权限、CAS、成功和失败契约测试。

### P2-T2：Department 树 + 闭包表（含根部门创建）
**文件**：
- `sidecar/acos/organization/models.py`（新增 `Department`）
- `sidecar/acos/organization/closure.py`
- `sidecar/migrations/0004_departments.sql`

**实现要点**（对照 §6.2，**本任务是全方案安全性的关键基础，务必对照测试用例逐条验证**）：
- `department_closure(company_id, ancestor_department_id, descendant_department_id, depth)`。
- 闭包表维护**必须在与部门增删移动同一事务内完成**：
  - 新增部门：插入自身到自身（depth=0），并为所有祖先插入到该新部门的闭包行（depth = 祖先到父节点深度 + 1）。
  - 移动子树：先删除该子树所有节点与其"旧祖先集合"的闭包行，再按新父节点重新插入。
  - 移动前必须校验：目标新父节点不是待移动节点自身或其后代（否则成环），违反抛 `ORG-DEPT-CYCLE`。
- 提供查询函数：`get_descendants(department_id)`、`get_ancestors(department_id)`，均基于闭包表一次查询完成，不递归遍历。
- 在 `organization/service.py` 实现可重入 `create_company`：Path Broker 先在应用数据根目录预留空 workspace，随后单个 SQLite 事务创建 initializing Company、根部门、三类默认策略、`CompanyCreated`、初始 deliveries 和 `org_change_audit`；失败只清理本次预留的空目录。幂等重放返回同一 company，不产生第二个根部门或策略。
- `department.leader_employee_id` 是领导关系事实源；`org.department.setLeader` 同事务同步派生 employee_type、审计和 `DepartmentLeaderChanged`。领导转岗/暂停/归档必须提供合格替补。
- `org.department.update` 的直接 patch 必须携带 expected_version、返回新 version；名称/说明/职责的并发编辑只允许一个 CAS 成功。
- 实现 `freeze/unfreeze/archive` 状态机；frozen/archived 部门不能接收新任务或新分派，Phase 9 的 PV-12 复用同一校验函数。

**测试**：`sidecar/tests/organization/test_closure.py`（**强制覆盖以下场景**）
- 创建公司后自动有一个根部门，`company.root_department_id` 指向它。
- 建一个 3 层部门树（A→B→C），验证 `get_descendants(A)` 返回 `{A,B,C}`，`get_ancestors(C)` 返回 `{A,B,C}`。
- 把 B 移动到另一个顶层部门 D 下，验证闭包表更新后 A 不再是 B/C 的祖先，D 变为祖先。
- 尝试把 A 移动到其后代 C 下面，断言抛出 `ORG-DEPT-CYCLE`，且闭包表未被破坏性修改（事务回滚验证）。
- 部门归档（`status=archived`）后不能再被指定为新部门的父节点。
- bootstrap 任一步失败均不留下 company/root/policy 半成品；相同幂等 key 并发创建只生成一套数据。
- setLeader 覆盖跨公司、非 active 职员、无替补领导离岗、并发设置和事务回滚；freeze 后 PV-12 组织状态查询返回不可分派。

**DoD**：`org.company.create` 与部门 CRUD/move/setLeader/freeze/unfreeze/archive 全部可用；bootstrap 原子性、闭包、领导唯一事实源和部门状态测试全绿。

### 阶段验收（Phase 2）
支撑 §19 第 22 条（部门移动防成环、公司创建不要求预先存在负责人）的组织侧部分。

---

## Phase 3：能力系统（Skill / Prompt Asset / Capability）

**目标**：落地能力资产化的核心——Skill、Prompt Asset、Tool Binding、Capability 及其版本发布状态机、快照锁文件、质量门禁。此阶段不依赖 Employee，可与 Phase 2 并行。

**任务顺序说明**：质量门禁（校验快照 checksum、依赖 Resolve）依赖快照能力，快照依赖 Capability 模型，发布状态机的"publish 前必过质量门禁"这条集成逻辑必须在快照与质量门禁都就位后才能接线——因此本阶段任务顺序是"模型 → 快照 → 质量门禁 → 状态机集成"，不是先写状态机再补依赖。

### P3-T1：Skill 与 Prompt Asset 模型
**文件**：
- `sidecar/acos/capability/models.py`（`Skill`, `SkillVersion`, `PromptAsset`, `PromptAssetVersion`）
- `sidecar/acos/capability/skill_service.py`
- `sidecar/acos/capability/prompt_service.py`
- `sidecar/migrations/0005_skills_prompts.sql`

**实现要点**（对照 §6.3、§6.4——本任务只建模型与基础 CRUD，`status` 字段先只支持 `draft`，发布流程留给 P3-T6）：
- Skill 字段：`skill_id, company_scope(global|company), company_id(NULLABLE), name, prompt_asset_id, prompt_asset_version, tool_bindings(JSON), knowledge_refs(JSON), input_schema, output_schema, checksum, version, status`。约束：`company_scope=global ⟺ company_id IS NULL`，`company_scope=company ⟺ company_id NOT NULL`，建表时加 CHECK 约束，插入/更新违反直接由数据库拒绝。
- Prompt Asset 字段：`prompt_asset_id, company_scope, company_id(NULLABLE), name, segments{system,developer,user_template,tool_instructions,output_contract}, variables[], context_slots[], checksum, version, status`。约束同上。
- `checksum` 用内容的确定性序列化（如排序后的 JSON）做 SHA-256，任何字段变化 checksum 必变——这是 P3-T3 快照校验的基础，务必现在就做对。
- Skill 创建时必须引用一个**已发布**（`published`）的 Prompt Asset 版本，否则报 `CAP-VALIDATION`（本阶段"已发布"校验先写好判断逻辑，真正能达到 `published` 状态要等 P3-T6 状态机集成完成，可先用测试夹具直接把数据库状态设为 `published` 来验证本任务的校验逻辑）。
- **跨公司引用校验**（对照设计方案 §6.5 的"跨公司引用约束"）：Skill 引用的 `prompt_asset_id` 必须满足"该 Prompt Asset 为 `global`，或其 `company_id` 与该 Skill 的 `company_id` 相同"，否则报 `ASSET-CROSS-COMPANY-REF-DENIED`；此校验独立于状态机校验，P3-T1 阶段就要写好（不等 P3-T6）。
- Skill 与 Prompt Asset 都实现 create/saveDraft/list/get/version.list/createVersion 基础 service；更新既有 draft 的 saveDraft 必须携带 expected_version 并返回新 version，创建不需要期望版本；`createVersion` 从指定基线复制内容、版本号单调递增且新版本恒为 `draft`。submitReview/publish/archive 由 P3-T6 的通用状态机接线。

**测试**：`sidecar/tests/capability/test_skill.py`、`test_prompt_asset.py`
- 创建 Prompt Asset，校验 `variables` 里声明为 `required` 的变量在装配时（Phase 5 会用到，这里只测 Prompt Asset 自身的 schema 校验）缺失会报错。
- 创建 Skill 引用一个 `draft` 状态的 Prompt Asset，断言失败并报正确错误码。
- 修改任意字段后 `checksum` 必须变化（用两次创建对比断言）。
- `company_scope=global` 但传入非空 `company_id` 应被 CHECK 约束拒绝；反之 `company_scope=company` 但 `company_id` 为空同样拒绝。
- 公司 A 的 Skill 引用公司 B 的 company 域 Prompt Asset 应报 `ASSET-CROSS-COMPANY-REF-DENIED`；引用一个 `global` Prompt Asset 应成功。
- Skill/Prompt Asset 的版本列表按版本号稳定排序；并发 `createVersion` 不产生重复版本号；新版本不修改已发布基线内容。
- 两个相同 expected_version 的 saveDraft 并发提交只有一个成功，失败方得到 `SYS-OPTIMISTIC-LOCK-CONFLICT` 且不会覆盖胜者内容；Skill、Prompt Asset 各覆盖一次。

**DoD**：Skill/Prompt Asset 数据模型、字段校验与跨公司引用校验就位。

### P3-T2：Capability 模型
**文件**：`sidecar/acos/capability/models.py`（新增 `Capability`, `CapabilityVersion`）、`sidecar/acos/capability/service.py`、`sidecar/migrations/0006_capabilities.sql`

**实现要点**（对照 §6.5）：
- Capability 字段按设计方案 §6.5 建立；`skill_set` 不另存可漂移 JSON，而由 `skill_bindings(binding_id,capability_id,capability_version,ordinal,skill_id,skill_version,skill_version_checksum,created_at)` 按 ordinal 投影。迁移落实两组唯一约束、连续 ordinal、具体不可变版本 FK 与 checksum 校验，Capability 进入 review 后 bindings 不可修改。
- `cost_policy.stability_level` 超出 1–10 范围在创建时报 `CAP-VALIDATION`。
- `skill_set` 引用的每个 Skill 版本此时可以是 `draft`（P3-T1 阶段还没有发布流程），真正"必须引用已发布版本"的约束在 P3-T6 状态机集成时才生效。
- **跨公司引用校验**：`skill_set` 中每个 `skill_id` 必须满足"该 Skill 为 `global`，或其 `company_id` 与该 Capability 的 `company_id` 相同"，否则报 `ASSET-CROSS-COMPANY-REF-DENIED`。
- 实现 Capability 的 create/saveDraft/list/get/version.list/createVersion 基础 service；更新既有 draft 的 saveDraft 必须携带 expected_version 并返回新 version，版本创建规则与 P3-T1 一致，submitReview/publish/deprecate/archive 在 P3-T6 接线。

**测试**：`sidecar/tests/capability/test_capability.py`
- `stability_level=0` 或 `11` 创建应报 `CAP-VALIDATION`。
- `skill_set` 引用不存在的 `skill_id` 应报错。
- 公司 A 的 Capability 引用公司 B 的 company 域 Skill 应报 `ASSET-CROSS-COMPANY-REF-DENIED`。
- 重复 ordinal、重复 skill version、断号、checksum 不符和 review 后修改 binding 均被拒绝；按 ordinal 读取的 skill_set 与快照依赖顺序一致。
- 非法 source category、空 visibility scope 和把 source category 当作 ACL 级别的输入均被 schema 拒绝。
- Capability saveDraft 并发 CAS 只有一个成功，失败方不能部分改写 skill_bindings。

**DoD**：Capability 数据模型、字段校验与跨公司引用校验就位。

### P3-T3：Capability 快照与锁文件
**文件**：`sidecar/acos/capability/snapshot.py`、`sidecar/acos/capability/models.py`、`sidecar/migrations/0006b_capability_snapshots.sql`

**实现要点**（对照 §6.8）：
- `build_snapshot(capability_id, version)` 伪代码：
  ```text
  1. 加载 CapabilityVersion（status 必须为 published）
  2. 按 ordinal 从 skill_bindings 加载所有 binding
  3. 对每个 binding：
     a. 加载 SkillVersion（用 binding.skill_id + binding.skill_version）
     b. 验证 skill_version_checksum == 当前 SkillVersion.checksum（不一致 → CAP-SNAPSHOT-CHECKSUM-MISMATCH）
     c. 从 SkillVersion.prompt_asset_id + prompt_asset_version 加载 PromptAssetVersion
     d. 验证 PromptAssetVersion.checksum 与 SkillVersion 中记录的 prompt_asset_checksum 一致
  4. 构建 dependency_tree = [{skill_id, skill_version, skill_checksum, prompt_asset_id, prompt_asset_version, prompt_asset_checksum, ordinal}, ...]
  5. 计算 snapshot_checksum = SHA256(canonical_json({capability_id, capability_version, dependency_tree, published_at}))
  6. 返回 lock = {capability_id, capability_version, dependency_tree, snapshot_checksum, published_at}
  ```
- `snapshot_json` 存储的就是上述 lock 本身（即 `{capability_id, capability_version, dependency_tree, snapshot_checksum, published_at}`），`dependency_tree` 列冗余存储同一数组（便于直接查询依赖关系而无需解析 JSON）。两者内容一致，`dependency_tree` 是 `snapshot_json` 的一个字段投影。
- 把完整 snapshot 与 lock 持久化到 `capability_snapshots(snapshot_id, capability_id, capability_version, snapshot_json, dependency_tree, snapshot_checksum, created_at)`；同一内容 checksum 唯一，历史 run 只引用 snapshot id/checksum，不复制可变 Capability 行。
- 装配/恢复时校验：对 `dependency_tree` 里每个条目逐条比对其 `skill_checksum`/`prompt_asset_checksum` 与当前数据库中对应版本的实际 checksum，任一条不一致即抛 `CAP-SNAPSHOT-CHECKSUM-MISMATCH`（这是防御性校验，用于检测数据损坏或误操作——Skill/Prompt Asset 一旦发布不可变，理论上锁文件应永久有效）。

**测试**：`sidecar/tests/capability/test_snapshot.py`
- 构建一个引用 2 个 Skill 的 Capability，`build_snapshot` 后校验 `dependency_tree` 包含两条记录且 checksum 与 Skill 自身记录一致。
- 直接改数据库里某个 Skill 的 checksum 字段（模拟数据损坏），重新校验快照应检测出 `CAP-SNAPSHOT-CHECKSUM-MISMATCH`。

**DoD**：`cap.snapshot.build`（附录 B.2）可用；快照校验能真实检测出不一致。

### P3-T4：Tool Binding 四步校验链（骨架）
**文件**：`sidecar/acos/capability/tool_binding.py`

**实现要点**（对照 §6.6，**这是安全关键路径**）：
- Tool Binding 结构：`tool_name, entrypoint, required_permissions[], param_whitelist, sandbox{filesystem,network,process,env,mcp_endpoint}, timeout, retry_policy, checksum`。
- 实现 `validate_tool_call(employee, workspace, capability_snapshot, tool_call)` 函数，严格按四步顺序校验，**任一步失败立即返回对应错误码并写 `acl_audit_log`**：
  1. ACL 校验（调用 Phase 4 的 permission_engine，此处先定义接口签名，Phase 4 完成后接线）
  2. Workspace 校验（目标路径经统一路径 broker，见 Phase 9-T5；此处先 mock）
  3. Capability 校验（该职员能力快照的 `skill_set` 是否确实包含此工具）
  4. Runtime Policy 校验（是否高风险命令需要人工审批，含计算 `tool_call_hash`——Phase 10 才有真实审批流程，此处先返回"需要审批"的布尔标记 + hash）
- 路径相关校验统一走 canonical-path 解析（拒绝 symlink 越界与 `../` 穿越），本阶段先实现路径 broker 的核心函数（无需依赖真实 Workspace 分类，Phase 9 接线）。
- 本阶段先把该函数的**结构与单元可测性**做对（每一步都是可独立 mock 的子函数），后续阶段依赖它但不需要重写它。

**测试**：`sidecar/tests/capability/test_tool_binding.py`
- 分别 mock 四个校验子步骤中的每一步失败，断言函数在该步骤即返回、不再继续往后校验（保证顺序正确）。
- 路径 broker 测试：构造一个指向 Workspace 外部的 symlink，断言被拒绝。
- 全部通过时返回允许执行的结果，含 `tool_call_hash`。

**DoD**：四步校验链函数骨架就位、顺序正确、任一步失败即短路返回，供后续阶段接线真实实现。

### P3-T5：能力发版质量门禁
**文件**：`sidecar/acos/capability/quality_gate.py`

**实现要点**（对照 §17"能力发版质量门禁"，依赖 P3-T3 的快照能力）：
- `run_quality_gate(entity_type, entity_id, version)`：
  1. Manifest/Schema 校验（字段完整性、JSON Schema 合法）
  2. 依赖 Resolve（Skill 引用的 Prompt Asset 版本必须存在且已发布；Capability 引用的 Skill 版本同理）
  3. checksum/依赖锁校验：Prompt Asset 重算自身 checksum；Skill 重算自身 checksum 并核对锁定 Prompt Asset 版本/checksum；Capability 才调用 P3-T3 的 `build_snapshot` 重算完整 dependency tree 与 snapshot checksum。禁止对三类实体无差别调用只接受 Capability 的接口。
  4. Golden Case（预留接口，允许配置若干"输入→期望输出"对，首版可以是空集合，允许通过）
  5. Prompt Injection / Secret Leakage 静态检测（对 Prompt Asset 的静态文本段做正则/关键词扫描，检测明显的密钥格式或"忽略之前的指令"类注入模式；这是**启发式检测**，不是完备防护，需在代码注释中说明局限）
- 任一步失败，`publish()` 调用应被阻止并返回 `CAP-QUALITY-GATE-FAILED`，附带具体失败的检查项。

**测试**：`sidecar/tests/capability/test_quality_gate.py`
- 构造一个引用了未发布 Skill 版本的 Capability，断言质量门禁在"依赖 Resolve"步骤失败。
- 构造一个 checksum 被篡改的场景，断言门禁能检测出来。
- Prompt Asset、Skill、Capability 分别覆盖自身 checksum、直接依赖锁和完整快照校验路径，错误实体类型不能误调 `build_snapshot`。
- 构造一个 Prompt Asset 里含疑似密钥格式字符串的场景，断言被标记。

**DoD**：质量门禁函数就位，五类检查均有对应测试；尚未接入 `publish()`（下一任务接线）。

### P3-T6：通用发布状态机 + Publish 集成
**文件**：`sidecar/acos/capability/versioning.py`

**实现要点**（对照 §6.7，**Skill / Prompt Asset / Capability 三者共用同一状态机实现，不要各写一套；本任务把前五个任务串成一条完整的发布链路**）：
- 状态：`draft → review → published → deprecated → archived`，且**必须先 `submit_review` 进 `review`，再 `publish`**，不存在 `draft` 直接到 `published` 的路径。
- `published` 后内容不可变：任何试图修改已发布版本的写操作抛 `CAP-VERSION-IMMUTABLE`；需要变更必须创建新版本（`version + 1`，初始状态 `draft`）。
- 提供通用函数：`submit_review(entity_type, entity_id, version)`、`publish(entity_type, entity_id, version)`（**内部先调 P3-T5 的 `run_quality_gate`，通过才真正把状态改为 `published`**）、`deprecate(...)`、`archive(...)`。
- Skill、Prompt Asset、Capability 的 `deprecate` 都必须发各自具名事件；`archive` 只接受 `deprecated`，三类资产的 RPC 不得出现绕过弃用兼容期的直接归档路径。
- `publish` 成功后，P3-T1/T2 的"引用必须已发布"校验立即生效。

**测试**：`sidecar/tests/capability/test_versioning.py`
- 断言 `draft` 状态调用 `publish` 直接失败（必须先 `submit_review`）。
- 断言质量门禁未通过时 `publish` 失败且状态仍为 `review`。
- 断言 `published` 版本调用任何修改内容的接口都抛 `CAP-VERSION-IMMUTABLE`。
- 三类资产分别验证 `published→deprecated→archived`、弃用事件唯一、`published→archived` 被拒绝，并覆盖并发 deprecate/archive 的 CAS。
- 端到端：创建 Prompt Asset → 走完整发布流程 → 创建引用它的 Skill → 走完整发布流程 → 创建引用该 Skill 的 Capability → 走完整发布流程，全程无需绕过任何一步。

**DoD**：三类实体（Skill/PromptAsset/Capability）复用同一状态机模块，`publish` 强制经过质量门禁；附录 B.2 的三类实体 CRUD、版本与发布 RPC 均可用，端到端发布链路测试通过。

### P3-T7：能力度量（只读）
**文件**：`sidecar/acos/capability/metrics.py`、`sidecar/migrations/0007_capability_metrics.sql`

**实现要点**（对照 §13）：
- `capability_metrics` 表：按 `capability_id, capability_version` 聚合 `success_rate, avg_cost, review_pass_rate, avg_downgrade_count, over_budget_rate, avg_duration`。
- 本阶段建表、只读 `cap.metrics.get` 与 `CapabilityMetricsAggregator`；聚合器订阅 `TaskCompleted/ReviewCompleted` delivery，以 `(event_id,consumer_name)` 幂等增量更新，另每 15 分钟按已结算 usage/evidence 重算脏 capability 作为对账。P3 用 fixtures 测试，P9-T10 注册真实 producer，P11-T2 注册 worker 生命周期；请求路径绝不实时聚合。
- **明确不做**：任何基于该表自动修改 Capability 配置或触发自动发版的逻辑——代码里不应存在这样的调用路径，review 时需专门检查这一点。

**测试**：`sidecar/tests/capability/test_metrics.py`
- 断言 `cap.metrics.get` 对不存在数据的能力返回空/零值而不报错。
- 静态检查测试：`metrics.py` 模块不 import 任何 `versioning.py` 或 `models.py` 的写操作函数——防止后续有人"顺手"加上自动改能力的代码。
- Phase 9/11 联调验证 TaskCompleted/ReviewCompleted 重放不重复计数，15 分钟对账可修复一次故意漏投的增量结果。

**DoD**：只读接口可用；有测试守住"度量不能反向改能力"这条设计红线。

### 阶段验收（Phase 3）
对应 §19 第 19、20 条：能力/技能/Prompt Asset 可创建、版本化、快照；`publish` 强制经过质量门禁；published 不可改；度量只读不自动改配置。

---

## Phase 4：职员与权限（Employee / Permission Engine）

**目标**：落地职员实例、权限引擎与审计，是安全边界的核心阶段。依赖 Phase 2（部门）与 Phase 3（能力快照）。

### P4-T1：EmployeeTemplate
**文件**：
- `sidecar/acos/organization/models.py`（新增 `EmployeeTemplate`）
- `sidecar/acos/organization/template_service.py`
- `sidecar/migrations/0008_employee_templates.sql`

**实现要点**（对照 §6.9）：
- 字段：`template_id, template_scope(global|company), company_id(NULLABLE), provider_type, provider_id, model, capability_id, capability_version, capability_snapshot, default_role, version, status(draft|active|archived)`。约束同 P3-T1：`template_scope=global ⟺ company_id IS NULL`。状态只允许 `draft→active→archived` 或 `draft→archived`。
- `org.template.saveDraft` 以可选 template_id/expected_version 创建或 CAS 保存 draft；`org.template.create` 无 draft_id 时创建 active，有 draft_id 时完整校验后原地 CAS 激活；`update` 只修改 active 的新建职员默认值，`archive` 可终止 draft/active，两者均必须带 expected_version。只有 active 模板可实例化 Employee。
- 创建模板时必须引用一个**已发布**的 Capability 版本，调用 Phase 3 的 `build_snapshot` 生成并保存 `capability_snapshot`（含 lock）。引用未发布版本报 `CAP-VALIDATION`。
- **跨公司复用校验**：`template_scope=global` 的模板只能引用 `company_scope=global` 的 Capability，否则报 `TEMPLATE-CROSS-COMPANY-DENIED`；`template_scope=company` 的模板可引用本公司 `company_id` 一致的 Capability，或任意 `global` Capability。
- 用模板实例化 Employee 时（P4-T2 消费本任务产出）校验 `template.company_id IS NULL OR template.company_id == 目标 company_id`，不满足报 `TEMPLATE-CROSS-COMPANY-DENIED`。
- `default_role` 必填、trim 后 1–100 字符；它是 P4-T2 创建 Employee 时 `role_name` 的唯一默认来源。模板后续修改不得回填既有职员。

**测试**：`sidecar/tests/organization/test_employee_template.py`
- 引用已发布 Capability 创建模板成功，`capability_snapshot` 非空且包含正确的 lock 结构。
- 引用 `draft`/`review` 状态的 Capability 创建模板应失败。
- `template_scope=global` 引用一个 `company_scope=company` 的 Capability 应报 `TEMPLATE-CROSS-COMPANY-DENIED`。
- 用公司 A 的 `template_scope=company` 模板在公司 B 实例化 Employee 应报 `TEMPLATE-CROSS-COMPANY-DENIED`。
- 空/超长 default_role 拒绝；合法模板实例化后 `employee.role_name == template.default_role`，修改模板后既有职员 role_name 不变。
- 覆盖 saveDraft 新建/更新 CAS、create 直接激活/从 draft 原地激活、草稿不可实例化、active 更新不回填既有 Employee、draft/active 归档与 archived 不可复活；并发 CAS 只有一方成功。

**DoD**：`org.template.*` 全部 handler 与 `test_template_rpc.py` 可用，快照生成正确串联 Phase 3。

### P4-T2：Employee 模型、状态机与汇报链闭包表
**文件**：
- `sidecar/acos/organization/models.py`（新增 `Employee`）
- `sidecar/acos/organization/reporting_closure.py`
- `sidecar/migrations/0009_employees.sql`

**实现要点**（对照 §6.10——**`reports_to_employee_id` 表达个人汇报链，与部门层级是两个不同关系，需要独立的闭包表，不能复用 `department_closure` 近似**）：
- Employee 字段：`employee_id, company_id, department_id, template_id, capability_snapshot, name, role_name, employee_type(company_leader|department_leader|employee), reports_to_employee_id, provider_override, model_override, model_tier_override, stability_level, responsibilities, authority_level, knowledge_access_level, status, session_transfer_state(none|transfer_requested|transferring|needs_repair), primary_session_thread_id`。
- `employee_reporting_closure(...)` 只能由 `org.employee.setManager` 更新；同事务维护闭包、写 `EmployeeManagerChanged` 与 `org_change_audit`，校验双方同公司、未归档并防环。
- `department.leader_employee_id` 是领导事实源；普通 `org.employee.create` 在服务端把 `employee_type` 固定初始化为 `employee`，请求 DTO 和模板都不含该字段。之后它仅由根/普通部门领导关系派生，通用 update/create 不能直接写；领导转岗、暂停或归档前必须通过 P2-T2 的 setLeader 原子指定替补。
- 状态机：`created→onboarding→active↔suspended→archived`；实现 `activate/suspend/resume/archive` 的前态校验和事件/审计。
- suspend/archive 调用 P4-T5 的 Employee Drain：先以 CAS 阻断新 assignment/turn；有 active assignment/turn 时持久化 operation=suspend|archive 的 drain，并向既有 run 签发只允许推进到安全 checkpoint/当前不可中断调用终点的服务端 drain token，不能开启下一次 Provider 调用。archive 仅在 drain 清空后转 archived；resume 要求没有 open drain。无活动工作时允许同事务完成。
- 创建职员时从模板的 `capability_snapshot`（含 `cost_policy`）物化 `model_tier_override` 初值与 `stability_level` 初值为职员自己的独立列（允许后续覆盖）。
- 创建职员时同事务把 `template.default_role` 物化到 `employee.role_name`；`org.employee.create` 不接受 role_name，v1 的通用 update 也不能隐式修改它。`EmployeeSummary/EmployeeDetail` 必须返回 role_name，`EmployeeFilters.role_name` 做 trim 后精确/规范化文本过滤，通用 `text` 同时搜索 name 与 role_name。
- `org.employee.update` 的直接 patch 必须携带 expected_version 并返回新 version；并发职责/权限级别/模型档位/稳定性编辑只允许一个 CAS 成功。
- `primary_session_thread_id` 初始为空（惰性创建，Phase 7 实现）；`session_transfer_state` 初始为 `none`。
- 实现 `org.company.activate(company_id, leader{name,template_id})`：通过 `BackendBootstrapGate` domain port 校验默认映射唯一且目标为 enabled + fresh healthy，再以单事务创建首任 Employee、回填根部门 leader、同步派生 employee_type、转 active，并写 `EmployeeCreated/DepartmentLeaderChanged/CompanyActivated` 与组织审计；未就绪返回 `BACKEND-UNAVAILABLE` 且不留下半状态。P4 以 fake port 完成组织域单测，P6-T1b 提供真实 adapter 和跨模块契约测试；普通 `org.employee.create` 只接受 active 公司。并发激活只有一个 CAS 成功。
- 实现 CompanyDissolutionStarted 的 Organization consumer：先把 open Employee Drain 标为 `aborted_by_dissolution` 并终结对应 intervention；同一事务清空全部 department leader 关系、把未归档职员的 employee_type 重新派生为 employee，再幂等归档部门/职员并上报 watermark。审计 before snapshot 保留原领导身份；Session consumer 独立归档线程。
- 提供 `get_org_graph(company_id)` 查询：一次返回部门闭包、负责人、职员汇报线及负责人缺失/汇报环异常标记，供 `org.graph.get` 使用；只返回通过公司隔离校验的数据。

**测试**：`sidecar/tests/organization/test_employee.py`、`sidecar/tests/organization/test_reporting_closure.py`
- 创建请求即使通过额外 JSON 字段尝试传入 employee_type/role_name 也因 `additionalProperties=false` 被拒绝；正常创建固定得到 `employee_type=employee` 和模板 role_name，列表/详情/role_name 过滤契约一致。
- 创建职员后能从模板正确带入初始 `stability_level`（默认 5，若模板未设则用 5）。
- `org.company.activate` 在 Backend bootstrap 未完成、默认不唯一或不健康时失败且不写 leader/active；bootstrap 就绪时公司、leader、派生类型、三类事件和审计同事务，并发激活只有一个成功。
- 非法状态转换（如 `archived → active`）应被拒绝。
- `stability_level` 设置为 0 或 11 应报 `ORG-VALIDATION`。
- 汇报链闭包：构造 3 级汇报链（组员→组长→部门负责人），验证 `get_reporting_superiors` 能查到全部上级；尝试把某人设为自己下级的上级，断言抛 `ORG-REPORTING-CYCLE`。
- suspended→resume 成功，archived→resume 拒绝；领导无替补暂停/归档拒绝；解散 consumer 中 open drain 只终结一次，重放不重复归档或发 watermark。
- 有活动节点时 suspend 返回 drain_id 且不再接收新工作；archive 保持 suspended 直至 drain 完成，重启后续跑；open drain 时 resume 被拒绝。
- `org.graph.get` 返回完整部门树、负责人和汇报线；跨公司查询被拒绝，负责人缺失时返回可定位的异常标记。

**DoD**：`org.company.activate`、Employee CRUD/activate/suspend/resume/archive/setManager 与 `org.graph.get` 可用；领导事实源、公司激活、汇报闭包和解散消费均有事务测试。

### P4-T2a：职员能力升级事务

**文件**：`sidecar/acos/organization/service.py`（`upgrade_employee_capability`）、`sidecar/tests/organization/test_employee_capability_upgrade.py`

**实现要点**（对照设计方案 §6.10）：

- `upgrade_employee_capability(employee_id, capability_id, target_version, reason)` 校验目标版本为 `published`、公司 scope 兼容，并通过 Phase 3 的 `build_snapshot` 重建和校验 lock/checksum。
- 单个 SQLite 事务内按 Employee `version` 做 CAS：替换 `capability_snapshot`，更新由能力提供且未被用户显式覆盖的 `model_tier_override/stability_level`，写 before/after `org_change_audit`，并写 `EmployeeCapabilityUpgraded` 到 `domain_events/outbox_deliveries`。任一步失败全部回滚。
- 已开始的 `task_run` 继续使用 run 创建时锁定的 `capability_snapshot_checksum`；升级只影响之后创建的 run。
- Phase 7 的事件消费者把旧通用线程置 `dormant` 并清空 `primary_session_thread_id`；下一次通用对话按新安全上下文惰性创建线程。事件消费使用 event id 幂等。

**测试**：

- 未发布版本、跨公司私有 Capability、checksum 错误均拒绝，Employee 不发生部分更新。
- 两个并发升级只有一个 CAS 成功，失败方收到 `SYS-OPTIMISTIC-LOCK-CONFLICT`。
- 成功升级后快照、物化字段、审计、事件具有同一 `trace_id`；运行中的 task run 仍保持旧 checksum，新 run 使用新 checksum。
- Phase 7 联调验证旧通用线程转 dormant、pointer 清空，下一次通用对话创建新线程且不带旧 transcript。

**DoD**：`org.employee.upgradeCapability` 后端命令、事务、事件、审计与会话轮换全部可用，UI 不承担任何拼装写逻辑。

### P4-T3：Permission Engine（结构化 scope 与具体资源鉴权）
**文件**：`sidecar/acos/organization/permission_engine.py`

**实现要点**（对照 §8.1–§8.3，**这是整套方案安全性的核心——权限判定结果必须是按可见性等级分支的结构化谓词，不能拍扁成"部门集合 ∩ 可见性列表"的交集，否则 `employee_private`/`task_private` 会被错误放宽成"部门内任何人可见"**）：
- `compute_scope(company_id, employee_id, task_id=None) -> AuthorizedScope`（**纯函数，无副作用，不写审计**）：
  ```text
  AuthorizedScope = {
    company_id,
    visible_department_ids: [department_id],        # 8.2 有效可读部门集合（company_leader 时已是
                                                       all_departments(company_id)）∪ 8.4 临时授权部门
    managed_department_ids: [department_id],         # 仅本人实际领导的部门及后代；普通职员为空
    visible_task_ids: [task_id],                     # 本人活动 assignment ∪ managed_department_ids 内任务 ∪
                                                       # 根部门 leader 可见的 company-scope 任务 ∪ 有效 task grant
    own_employee_id: employee_id,
    private_visible_employee_ids: [employee_id],     # managed_employee_ids（本人是其部门负责人，来自部门
                                                       闭包表：该部门及下级部门全部职员）∪
                                                       reporting_subordinate_ids（来自 P4-T2 的
                                                       employee_reporting_closure）——两个不同来源的并集
  }
  ```
  `company` 级判定**不需要单独字段**：`visibility=='company'` 的条目对任何该公司在职职员恒可读，判定条件只是"目标条目的 `company_id` 与 `AuthorizedScope.company_id` 一致"（公司隔离已经保证这一点，不需要 `employee_type` 判断）——不要引入一个只对 `company_leader` 为真的布尔位来控制这一分支，那会把"全公司可见"错误地收窄成"只有公司负责人可见"。四个字段各自独立求解，**不允许**把 `visible_department_ids` 拿去套用在 `employee_private`/`task_private` 条目上做近似判断。
- `authorize(company_id, employee_id, resource_ref, action, task_id=None) -> AuthorizationDecision`：调用 `compute_scope(...)` 后对具体 resource/action 求值，写完整 `acl_audit_log` 并返回 `allow|deny + matched_rule`。工具、Workspace、组织资源和单条知识详情必须使用该函数；业务代码不得直接拿 `compute_scope` 访问资源。
- `org.permission.resolve` 只用于 LocalOwner 诊断；知识 search/list/get/citation/Context Pack 统一由 P8 的 `query_with_audit` 写 `knowledge_access_logs`。
- 冲突消解优先级（v1）：`Temporary Grant(access_grants，未过期) > Inherited(部门闭包继承/汇报链/本人资源) > Default Deny`——**不实现 Explicit Deny/Allow**（v1 没有对应的数据表和真实场景，见设计方案 §18 非目标；若后续要加，需先建 `acl_rules` 表再插入这个优先级链条）。
- `visible_department_ids` 由职员当前部门与领导关系计算；`managed_department_ids` 只由 `department.leader_employee_id` 与闭包表计算。先定义 `TaskAssignmentRepository.list_active_task_ids(employee_id)`、`TaskRepository.list_by_managed_department_ids(ids)` 与 `list_company_scope_tasks_for_root_leader` protocol，P9-T1a 接入真实实现。

**测试**：`sidecar/tests/organization/test_permission_engine.py`（**逐条覆盖，缺一不可，这是全项目测试密度最高的一个文件**）
- 普通职员只能读自己部门（`visible_department_ids` 只含自己部门）。
- 部门负责人能读自己部门+全部下级部门（构造 3 层部门树验证）。
- 公司负责人 `visible_department_ids` 覆盖全公司所有部门（`all_departments(company_id)`）。
- 任意 active 职员对 `visibility=='company'` 的条目都可读（不要求 `employee_type=company_leader`）；跨公司职员对该条目不可读。
- 普通职员读平级部门 → deny，读上级部门 → deny。
- **核心断言**：构造同部门两名普通职员 A、B，A 的 `employee_private` 条目对 B **不在** `AuthorizedScope` 允许范围内（即 B 的 `private_visible_employee_ids` 不包含 A），即使 A、B 同部门——必须通过。
- **核心断言**：构造"组员→组长→部门负责人"三级汇报链，验证组长与部门负责人的 `private_visible_employee_ids` 都包含组员（分别来自汇报链闭包与部门闭包两个不同来源），但平级的另一个组长不包含。
- **核心断言**：非任务参与者对该任务的 `task_private` 范围不可达，即使该职员与任务参与者同部门。
- **数据库集成断言**：普通职员与任务同部门但无 assignment 时 deny；部门 leader 通过 managed department allow；公司根 leader 对 company-scope allow；调岗/关闭最后一条 assignment 后立即 deny。
- **核心断言（依赖 P9-T1a，先用 repository mock 驱动，P9 完成后换真实数据重跑）**：任务所在部门的负责人、及公司负责人，即使不是该任务的 `task_assignments` 参与者，也能通过 `visible_task_ids` 读到该任务的 `task_private` 条目；平级部门的负责人不能。
- 有效的 `access_grants`（未过期）能把对应部门/任务并入 `visible_department_ids`/`visible_task_ids`。
- 已过期的 `access_grants` 不生效。
- 对同一 scope 中两个不同资源分别调用 `authorize`，验证产生一条 allow、一条 deny，日志的 resource/action/matched_rule 与实际结果一致；直接调用 `compute_scope` 不产生访问审计。
- 两次相同参数的调用不共享任何缓存状态（mock 检测 DB 查询次数一致，证明没有走缓存分支）。

**DoD**：以上全部测试通过；`org.permission.resolve` 返回结构化 `AuthorizedScope + scope_hash`；所有具体资源判定均通过 `authorize` 留下字段完整的 `acl_audit_log`。

### P4-T4：临时跨部门授权（access_grants）
**文件**：
- `sidecar/acos/organization/models.py`（新增 `AccessGrant`）
- `sidecar/acos/organization/grant_service.py`
- `sidecar/migrations/0010_access_grants.sql`

**实现要点**（对照 §8.4）：
- 字段：`grant_id, company_id, employee_id, target_type(department|task), target_id, permission(department_read|task_read), status(active|revoked|expired), expires_at, approved_by, revoked_at, version`；CHECK 保证 target/permission 匹配且只有一个目标。
- 创建时校验 grantee/目标同公司、未归档、`expires_at > now`；撤销用 version CAS；过期即时不生效并由后台幂等标记 expired。
- `approved_by` 取值来自 P1-T6 的 `resolve_actor`，不接受客户端传参。
- 创建/撤销均发对应事件（`AccessGranted`/`AccessRevoked`）并写 `org_change_audit`。

**测试**：`sidecar/tests/organization/test_access_grants.py`
- 创建授权后 `compute_scope` 结果的对应分支包含该部门/任务（与 P4-T3 联调测试）。
- 撤销后立即失效（无需等到 `expires_at`）。
- 创建/撤销都产生对应事件与审计记录。
- 双目标、无目标、permission/target 不匹配、跨公司、过去过期时间、已归档目标均拒绝；并发撤销只有一个状态跃迁。

**DoD**：`org.grant.create` / `org.grant.revoke` / `org.grant.list`（附录 B.1）可用，且与 Permission Engine 联调测试通过。

### P4-T5：Employee Drain 与职员调岗（组织侧事务 + Handoff 触发点）
**文件**：`sidecar/acos/organization/employee_drain_service.py`（`start_drain` / `transfer_employee` / drain reconciler）、`sidecar/acos/organization/employee_drain_repository.py`、`sidecar/migrations/0009b_employee_drains.sql`

**实现要点**（对照 §11.4 的"排空后调岗"规则，**本任务做组织侧的排空状态机 + 切换短事务，会话线程的实际归档/重建在 Phase 7；Handoff 的范围只影响职员的通用会话线程，不是该职员全部历史会话**）：
- `transfer_employee(employee_id, new_department_id, reason)`：
  1. **排空阶段**：短事务把 `employee.session_transfer_state` 置 `transfer_requested`（该状态下不可分配新任务，`employee.department_id` **暂不更新**）、创建 operation=transfer drain，写 `EmployeeDrainStarted/EmployeeTransferStarted`（都只表示流程已启动）、写 `org_change_audit`，提交。
  2. 后台排空：加载步骤 1 已创建的 `employee_drain_items`；每行有独立 `drain_item_id`，`drain_id` 只作为一次操作的分组键，`UNIQUE(drain_id,assignment_id)`，同组 company/employee/operation/target_department 一致。本任务提供真实 `EmployeeDrainRepository` 与迁移，`TaskAssignmentRepository` 仍以 protocol + fake 开发，P9-T1a 接入真实 assignment adapter。协调器查询该职员 active assignments，逐条等待对应节点到达终态后精确关闭；同一协调器也消费 P4-T2 的 suspend/archive drain。排空超时值默认 10 分钟（`drain_timeout_seconds=600`），可通过公司级配置调整；超时不自动强制推进节点状态，而是按设计方案 §10.2.2 为整个 drain_id 创建/复用唯一一条 `employee_drain` HumanIntervention，target_ref 固定为 `employee_drain:<drain_id>`，并把 intervention_id 写到仍 waiting 的 items；不是每个 item 各建一条。人工可 wait（延长排空期限）或对指定阻塞 node reassign；全部 item 收敛且领域后继动作完成后才关闭 intervention。
  3. **切换阶段**：排空完成后，短事务把 `session_transfer_state` 置 `transferring`、更新 `employee.department_id`，提交。
  4. 通过显式 `EmployeeDrainRuntimePort` 调用 P7：P7-T4 实现 transfer Handoff，P7-T5 实现 suspend/archive/resume 线程生命周期 ACK；端口未完整注册时有活动工作的 drain 路径不进入 RPC registry，不保留空实现。Handoff 归档旧通用线程、创建新投影并以 staging+原子 rename 落盘。
  5. Handoff 成功后事务性写 pointer、置 `none` 和 `EmployeeDrainCompleted/EmployeeTransferred`；对账不确定则置 `needs_repair` 并写 `EmployeeDrainNeedsRepair/EmployeeTransferNeedsRepair` 与 intervention。suspend/archive operation 也必须以 DrainCompleted 或 DrainNeedsRepair 唯一收敛。

**测试**：`sidecar/tests/organization/test_employee_drain.py`、`sidecar/tests/organization/test_employee_drain_rpc.py`、`sidecar/tests/organization/test_transfer.py`
- 排空阶段的短事务：`session_transfer_state=transfer_requested`、事件、审计三者原子，且此时 `employee.department_id` 未变。
- `session_transfer_state ∈ {transfer_requested, transferring}` 期间调用"分配任务"应报错（此断言在 Phase 9 才能真正验证分配逻辑，本阶段先测状态字段本身能被正确读取）。
- 用真实 SQLite EmployeeDrainRepository + 内存 fake TaskAssignmentRepository 构造 active assignment，验证排空逻辑在对应节点未到终态前不会推进；P9-T1a 完成后同一 assignment 契约测试切到真实 SQLite adapter 重跑。
- 排空超时后验证干预条目已持久化；P11 验证 `HumanIntervention` 视图可查询，P12-T8 验证 UI 展示与处理。
- transfer/suspend/archive 三种 operation 共享同一 drain repository 与 CAS；最终只执行各自后继动作，重放不串操作。

**DoD**：Employee Drain 自身事实和 intervention 已在 P4 使用真实 SQLite 持久化并按精确 assignment 工作；只有 P7 注册完整 `EmployeeDrainRuntimePort` 且 P9-T1a 提供真实 TaskAssignment adapter 后，`org.employee.transfer` 与有活动工作的 suspend/archive 才进入 registry；完整链路由 P7-T4/T5、P9-T11、P13-T2 联调验收。

### 阶段验收（Phase 4）
对应 §19 第 3、4、7、14、19 条中组织/权限/Employee Drain/能力升级部分。**这是全项目安全性测试最密集的阶段，不建议压缩测试时间，尤其 P4-T3 的"同部门 employee_private 不可见"这条断言是全方案安全性的核心验证点。**

---

## Phase 5：Capability Engine 装配器

**目标**：把职员能力快照装配成一次 Agent 运行所需的具体参数，依赖 Phase 3（能力快照）与 Phase 4（权限引擎）。

### P5-T1：Context Pipeline 与 ContextBuilder
**文件**：`sidecar/acos/capability/context_builder.py`

**实现要点**（对照 §7 的 Context Pipeline 固定顺序）：
- 唯一的 `ContextBuilder.build(employee, task_context, capability_snapshot, retrieved_knowledge)` 按固定序拼装：`Employee Identity → Workflow Context → Capability Context → Retrieved Knowledge → Runtime Variables → User Input`。
- `retrieved_knowledge` 参数本阶段先接受 mock 输入（Phase 8 完成后才有真实检索结果），保证顺序装配逻辑本身可独立测试。
- **约束**：不允许在 `context_builder.py` 之外的任何地方拼装最终上下文——review 时需检查 Agent Runtime/Provider 代码里没有另起一套上下文拼接逻辑。

**测试**：`sidecar/tests/capability/test_context_builder.py`
- 给定各段输入，断言输出的上下文严格按六段固定顺序排列。
- 缺少必需字段时报错而不是静默跳过。

**DoD**：`ContextBuilder` 单元可测、顺序正确。

### P5-T2：Capability Engine 主装配流程
**文件**：`sidecar/acos/capability/engine.py`

**实现要点**（对照 §7 的固定装配步骤，**第 3 步的知识范围求交必须按 `AuthorizedScope` 的分支结构逐一收窄，不能拍扁**）：
```text
0. 校验 capability.lock 的 snapshot_checksum 与各依赖 checksum（复用 P3-T3）
1. system_prompt ← identity + 各 skill 的 Prompt Asset 段，校验 variables 齐备
2. tool_set      ← skill_set 的 tool_bindings 并集，交给 P3-T4 的四步校验链在实际调用时收紧
3. knowledge_scope ← capability.visibility_scope 与 AuthorizedScope 逐分支求交，再把
   source_categories 映射为 KnowledgeDocument.source_category 过滤；两维正交且都只能收窄
4. model_tier    ← cost_policy.default_model_tier（可被 employee.model_tier_override / 任务级覆盖）
5. review_spec   ← review_policy
6. decision_limits ← decision_policy
7. security_policy ← 按 §6.1 将 active SecurityPolicy 与 Tool Binding 解析为
   effective_allowed_commands/denied/high-risk/approval 规则
8. backend_requirements ← Workspace/Tool Binding/security_level 所需能力；只产出要求，
   不在 Capability Engine 选择 Backend 或取得 lease
```
产出设计方案 §7 的版本化 `ResolvedRunConfig` 数据类，逐字段实现 identity、tool_set、四分支 knowledge_scope、model、六段 context_sections、workspace、security_policy、review_spec、decision_limits、backend_requirements 与 config_hash；数组稳定排序、null 显式化，按 RFC 8785 canonical JSON + 域前缀计算 SHA-256。运行时 `model.model_id` 必须逐字复制所选 `provider_models.model`（即 `ProviderModelRef.model`/Provider RPC `model`），不得另造内部模型别名或主键。不得用未声明的 dict 让跨模块自行猜字段。

**测试**：`sidecar/tests/capability/test_engine.py`（**重点测试第 3 步的"按分支只收窄不扩大"**）
- 能力 `knowledge_scope` 只声明 `{department: true}`（不含 `company`），即使该职员对 `company` 级条目本来可读，断言最终 `ResolvedRunConfig.knowledge_scope` 不含 `company` 分支（能力主动收窄同样生效，即便职员权限本身覆盖更宽）。
- 反过来：能力 `knowledge_scope` 只声明 `{task: true}`，即使该职员 `AuthorizedScope` 覆盖全公司，最终范围也只到 `task` 分支。
- **核心断言**：能力声明 `{employee: true}`，验证最终范围只包含 `own_employee_id` 与 `private_visible_employee_ids`（若该职员是上级/部门负责人），不会因为职员的 `visible_department_ids` 很宽就连带把整个部门的 `employee_private` 条目都打开。
- `snapshot_checksum` 不一致时装配应中止并报 `CAP-SNAPSHOT-CHECKSUM-MISMATCH`。
- 覆盖优先级测试：`employee.model_tier_override` 存在时优先于 `capability.cost_policy.default_model_tier`。
- Workspace 类型字段使用第 11.3 节枚举，Backend required_capabilities 字段只使用执行原语，两组枚举分属不同字段：Local/Task/Restricted→agent_runtime+filesystem_io，GitWorktree 另加 git_cli，ReadOnly→agent_runtime+readonly_io。验证同快照同上下文输出和 config_hash 稳定，且装配过程不查询 Backend 健康、不占并发槽。
- 选定模型后断言 `ResolvedRunConfig.model.model_id == provider_models.model == ProviderModelRef.model`；传入档位名、`latest` 或内部数据库行 ID 代替具体 model 字符串时装配失败。
- SecurityPolicy 分别覆盖 inherit/restrict 模式、ToolBinding 交集、denied 减集与空结果 fail-closed；仅改 policy_version/effective command/high-risk/approval 任一字段均改变 config_hash 与 security_policy_hash。

**DoD**：`cap.engine.resolve` 单元测试覆盖四种可见性和六类来源类别，证明任何组合都只收窄 ACL。

### 阶段验收（Phase 5）
对应 §19 第 7、19 条中"knowledge_scope 恒受结构化 ACL 约束"部分。至此，Phase 2–5（轨道 A）应可交付一个完整可测的"组织+能力+权限"内核，尚不涉及真实 Agent 执行。

---

## Phase 6：Provider、公司级本机 Backend、Credential Broker 与 Agent Runtime 骨架

**目标**：落地统一 Provider 适配层、公司级 `local_process` Backend、持久化 lease 调度、跨进程凭据代理与 Agent Runtime 接口骨架。Provider/Runtime 依赖 Phase 0/1；Backend 另依赖 P2-T1，可与 Phase 2–5 其余任务并行开发（轨道 B）。

### P6-T1：ProviderAdapter 抽象与 RuntimeEvent
**文件**：
- `sidecar/acos/providers/base.py`（`ProviderAdapter` 抽象基类）
- `sidecar/acos/runtime/models.py`（`RuntimeEvent` 统一结构）

**实现要点**（对照 §11.1、§11.2——Agent Runtime 与 ProviderAdapter 是本方案自研契约，Phase 0-T5 的选型结论只影响某个 Driver 内部是否用 OpenHands SDK，不改变这一层的接口）：
- `ProviderAdapter` 抽象方法：`checkAvailability() -> AvailabilityStatus`、`capabilities() -> ProviderCapabilities`、`createSession(config) -> Session`、`send(session, message, stream) -> AsyncIterator[RuntimeEvent] | Result`、`cancel(run_id)`、`resume(checkpoint) -> Session`、`collectUsage(run_id) -> UsageRecord`、`healthCheck() -> HealthStatus`。
- `RuntimeEvent` 字段含 `company_id/department_id/employee_id/task_id/conversation_id/run_id/trace_id` + 事件类型与 payload。
- **约束**：任何 Provider 实现的 `send()` 都必须把底层原始输出（CLI 的 stdout/退出码、API 的 SSE chunk）翻译成统一 `RuntimeEvent`，不允许把 provider 专有格式泄露给上层。

**测试**：`sidecar/tests/providers/test_base.py`
- 用一个 `FakeProviderAdapter`（测试替身，不调真实 CLI/API）验证抽象接口的每个方法签名可被正确调用与 mock。

**DoD**：抽象接口与 `RuntimeEvent` 定义就位，作为后续所有 Provider 实现与 Agent Runtime 的统一契约。

### P6-T1a：Provider Registry 与版本化价格目录

**文件**：`sidecar/acos/providers/registry.py`、`sidecar/acos/providers/pricing.py`、`sidecar/migrations/0010b_provider_registry_pricing.sql`

**实现要点**：建立 `providers/provider_models/provider_model_prices/provider_budget_freezes`，字段严格采用设计方案 §6.11。`providers` 是全局 Driver 注册表；内置 Driver 随包提供带 manifest_version/hash 的只读 `provider-models.json`，首次初始化/升级按 `(provider_id,model,owner_company_id IS NULL)` 幂等导入静态能力；probe 只更新公司级 Availability，不改能力。v1 manifest 至少登记一个已通过发布候选环境真实契约测试的 OpenAI chat 模型，`model` 必须是 Provider API 接受的完整具体 ID，禁止 `latest`/档位名/漂移别名；修改模型 ID 必须提升 manifest 版本并重跑真实 API 契约测试。OpenAI-Compatible 由 `provider.pricingPolicy.update` 同时接收必填 model_spec，并在同事务按 `(owner_company_id,provider_id,model)` 登记当前公司的私有静态能力与新价格版本。价格按 `(company_id,provider_id,model,currency,effective_at)` 追加，input/output/cache 使用“每百万 token 的 int64 micros”，tool 使用固定 int64 micros，禁止 binary float；source 来自请求，`verified_at` 只由服务端在校验并落库时写当前 UTC，DTO 禁止传入，历史版本禁止覆盖。`resolve_price(company_id,...)` 对未知、过期、跨公司、币种冲突、负数或溢出 fail-closed，run 固化 pricing_version_id。`provider.model.list` 必须接收 company_id，只合并全局内置模型与该公司私有模型。Provider 计价异常由结算服务内部按 `(company_id,provider_id)` 创建唯一 active hard-budget freeze，固化 trigger_run_id/evidence_hash；不提供人工 create RPC，同 run 重放不重复创建，冻结期间硬预算选择返回 `PROV-BUDGET-FROZEN`。解除只能由 LocalOwner 调 `provider.budgetFreeze.clear`，在重新 probe/验价/验硬上限后带 1..1000 字符 clear_reason 把 `active→cleared` CAS 清除并审计；新违约建新行，不复活历史 freeze。`provider.tierMapping.update` 携带 expected_company_version，只替换 `default_provider_policy` 的一个 tier，并以 Company CAS 验证/回写完整 `{free,standard,premium}` 三键 schema与新 company_version。

**测试**：`sidecar/tests/providers/test_pricing.py`、`test_provider_rpc.py` 覆盖价格生效边界、历史版本复算、未知/过期/币种冲突、自定义价格跨公司隔离、负数/溢出拒绝、整数向上取整不低估最坏成本；请求伪造 verified_at 因 schema 拒绝，正常写入时间由服务端 clock 注入。冻结后仅阻断对应公司硬预算调用；公共 RPC registry 不存在 freeze create，同 run 重放不重复建 freeze，同公司/Provider 并发违约只有一条 active，证据字段不可改，clear_reason 空/超长被拒，cleared 不复活；签名 manifest hash 篡改、缺少具体 OpenAI 模型 ID、出现 `latest`/档位别名、模型 ID 变更但 manifest_version 不变均阻断发布，probe 不改写静态能力；非 LocalOwner、跨公司、仍不满足硬上限或无同币种有效价格的解除请求均失败，并发解除只成功一次且只产生一组解冻审计/事件。tier mapping 覆盖三键初始 null、逐 tier 更新、跨公司/未知模型拒绝、完整 JSON round-trip，以及两个相同 expected_company_version 并发更新只有一个成功。

**DoD**：Provider/model/price/freeze 均有持久化事实源；v1 签名 manifest 固定了至少一个已通过真实契约测试的具体 OpenAI chat 模型 ID；`provider.list/model.list/pricingPolicy.update/budgetFreeze.clear` handler 和契约测试可用，历史 run 可按 pricing_version_id 复算，冻结只能在安全条件重新校验通过后审计解除。

### P6-T1b：公司级 local_process Backend Registry、生命周期与健康检查

**文件**：
- `sidecar/acos/backends/models.py`
- `sidecar/acos/backends/service.py`
- `sidecar/acos/backends/health.py`
- `sidecar/migrations/0010c_backends.sql`

**依赖**：P1-T2/T3/T5（事件、幂等、审计）、P2-T1（公司生命周期）。

**实现要点**（对照设计方案 §6.11/§15/附录 B）：
- 建立 `backends/company_backend_defaults/backend_health_checks/backend_health_daily/backend_queue_entries/backend_leases/backend_change_audit`。默认关系只存在于 company_backend_defaults；queue/lease 的 run_id/session_turn_id 用 CHECK 保证二选一和活动唯一。Backend v1 只接受 local_process+policy_only。`backends.capabilities`（执行原语）、`provider_models.supports`（模型能力）和 `backends.workspace_types`（Workspace 类型）使用三套互不兼容的枚举；Workspace 映射严格按设计方案 §6.11。RestrictedWorkspace 依赖 filesystem_io，其路径 allowlist 来自 ResolvedRunConfig.workspace，命令 allowlist 来自解析后的 SecurityPolicy。可信数据根由 Rust 在认证 bootstrap 消息注入；Python Sidecar 的唯一 `runtime/path_broker.py` 在每次启动/bootstrap 重新 canonicalize。注入根不存在/非目录/含 symlink/所有权权限错误/无法证明位于应用私有根时以 `SYS-BOOTSTRAP-ROOT-INVALID` 阻止 Initialize 与业务 RPC；单次业务路径越根、跨公司或 symlink 逃逸返回 `BACKEND-PATH-DENIED`，不使进程降级运行。Rust 不实现第二套 broker，业务配置不能注入 executable/env/公司外路径。
- lifecycle 只允许 `enabled→draining→disabled→enabled` 与 `disabled→archived`；首个 Backend 在默认映射缺失时原子补为默认，`backend.setDefault` 用映射行 version CAS 保证恰好一个非 archived 默认。默认项不能 drain/archive，除非先原子切换默认；归档不物理删除历史引用。drain 同事务取消 waiting entries：session turn 可保留 queued_at 重入新默认，task node 因 Backend 已进入 plan_hash 必须返回 BACKEND-DRAINING 等待 retry/replan，公司解散不重排。name/concurrency_limit 可在线 CAS 更新且 limit∈`1..global_process_limit`；workspace_root/capabilities/workspace_types 仅 disabled+无 held lease 可改，改后健康置 unknown。canonical workspace_root 在同公司不得相同或父子重叠。
- queue 的 `wait_reason` 固定为 `NULL|backend_capacity|global_capacity|unhealthy`，`cancel_reason` 固定为 `deadline|backend_draining|request_cancelled|company_dissolution`；initial/leased reason 必须为 NULL，cancelled 必须有 cancel_reason，run/turn 二选一。
- `CompanyCreated` consumer 幂等执行 `ensure_default_local_backend(company_id)`：事务内创建 disabled+unknown Backend/default mapping；默认声明 agent_runtime/filesystem_io/readonly_io + TaskWorkspace/ReadOnlyWorkspace/RestrictedWorkspace，只有受信任 Git 预检成功才成对加入 git_cli/GitWorktreeWorkspace。事务后主动 probe，基础能力 healthy 才 CAS enable；其余激活门禁、失败诊断与 dissolution watermark 按设计方案 §6.11 实现。
- `LocalBackendHealthProbe` 在 Sidecar 启动时检查所有非 archived Backend，配置变更/手动调用时检查目标 Backend；30 秒定时任务只检查 enabled/draining，disabled 在 enable 前主动 probe，archived 不再探测。单次 3 秒超时，检查 workspace 可写、受控 worker handshake、进程池；声明 `git_cli` 时还执行受控 Git 可用性检查并写 `git_cli_ok`，未声明时为 NULL；不检查 Provider 网络。超过 90 秒为 stale。探测结果带 trigger/operator append 到 `backend_health_checks`，只有状态变化才写 `BackendHealthChanged`；`backend.enable` 必须先得到 healthy。每日 retention job 只处理已结束的 UTC 日，按 Backend/day 幂等写唯一且不可变的 `backend_health_daily`、校验 `source_count`，不聚合仍增长的当日窗口；再删超过 7 天的未变化 healthy 原始记录，失败/degraded/unavailable/timeout 原始记录保留 90 天。
- 实现 `backend.list/get/create/update/setDefault/enable/drain/archive/probe` 九个 Registry/Health RPC；管理写方法只接受 initializing/active 公司并注入 LocalOwner，dissolving 时仅内部 dissolution consumer 可 drain/disable，dissolved 全拒绝；list/get 在 dissolving/dissolved 按公司隔离只读开放。全部写方法带 request hash 幂等并写 `backend_change_audit`/具名事件。update 降低并发不杀已有 lease；draining 最后一个 lease 释放后自动 disabled。包含真实容量/队列位置的 `backend.checkAvailability` 最终 handler 归 P6-T1c。每次 lifecycle 状态变更（enable/drain/disable/archive/setDefault）和 probe 结果变化（healthy/degraded/unavailable/unknown 切换）时发送 `notify.backendStatus` 通知，携带 Backend id、新状态、health summary 与 held/limit 计数。

**测试**：`sidecar/tests/backends/test_registry.py`、`test_health.py`、`test_backend_rpc.py`
- 默认唯一、跨公司读写/默认切换拒绝、非法状态跃迁、默认/有 lease 归档拒绝、CAS 冲突、重复 idempotency key 与不同 payload、workspace 越界、未知 type/security_level、把 Provider supports 值写进 Backend capabilities（或反向混写）、未知 workspace_types 均覆盖；git_cli 与 GitWorktreeWorkspace 必须成对，Git 预检失败时默认 Backend 仍可凭文件/只读基础能力 healthy，但 Git 任务被拒。
- 启动/bootstrap 根不存在、非目录、symlink、所有权/权限错误和大小写 canonical form 不一致逐项验证 Initialize fail-closed；正常根下单次跨公司/越界请求只失败该请求。重启后重新注入必须再次校验，不复用上次内存判定。
- 在线改 name/降并发不杀现有 lease；enabled 时改 Workspace/capabilities 被拒；disabled 修改后必须重新 probe；limit=0/超过全局池及同公司 root 相同/父子重叠均拒绝。
- Fake clock 验证 enabled/draining 的 30 秒周期、disabled/archived 不进入定时探测、3 秒超时、90 秒 stale；workspace/handshake/process pool/git_cli 各自失败映射明确 reason code，未声明 git_cli 时该检查为 NULL 且不误报，状态不变不重复发事件，disabled→enabled 必须 fresh healthy。
- health retention 聚合计数/p95 正确、重复执行幂等；当日窗口不得产生 daily 行，跨 UTC 日后才生成唯一不可变聚合；聚合或 source_count 校验失败不删原始记录，失败类记录未满 90 天不清理。
- 公司创建重放不产生第二个默认 Backend；consumer 未完成、probe 失败或默认不唯一时激活被拒且无半状态，修复配置并成功 probe 后可唯一激活；公司解散只在 Backend 全部 disabled 且 lease 清零后上报唯一 watermark。
- create 不会绕过 probe 直接 enabled；默认自动 probe 成功才可调度，失败保持 disabled/unknown 或 unavailable 并向 UI 返回明确原因。

**DoD**：九个 Backend Registry/Health RPC 均有 handler、权限与成功/失败契约测试；active/dissolving 公司默认 Backend 唯一，P4 激活门禁已接真实 adapter，配置/状态/健康事实可审计，Backend dissolution consumer 可幂等恢复。

### P6-T1c：BackendScheduler、持久化 lease 与崩溃对账

**文件**：
- `sidecar/acos/backends/scheduler.py`
- `sidecar/acos/backends/process_supervisor.py`
- `sidecar/acos/backends/reconciler.py`
- `sidecar/tests/backends/test_scheduler.py`
- `sidecar/tests/backends/test_backend_recovery.py`

**依赖**：P1-T7、P6-T1b。本任务先定义 ports 并用 fake run/turn repository 完成调度器测试；后续 P7-T1 与 P9-T1b 分别提供 session turn、task run adapter，不构成 P6 的反向开工依赖。

**接口**：
- `BackendSelector.resolve(company_id, explicit_backend_id, requirements) -> BackendSelection`
- `BackendQueueRepository.enqueue(backend_id, run_id=None, session_turn_id=None) -> BackendQueueEntry`
- `BackendLeaseRepository.acquire_next() -> BackendLease | WaitReason`
- `backend.checkAvailability(company_id, backend_id) -> AvailabilityStatus`
- `LocalProcessSupervisor.start(lease_id, launch_spec) -> (worker_pid, process_start_token)`；token 由 OS process start time + launch nonce 派生
- `bind_process(lease_id, worker_pid, process_start_token, expected_version)`
- `heartbeat(lease_id, expected_version)`、`release(lease_id, expected_version, reason)`
- `BackendLeaseReconciler.reconcile_expired(now)`

**实现要点**：
- selector 优先使用任务显式 Backend，否则公司默认；先校验 company、workspace_types、capabilities、security_level 与 lifecycle=enabled，并返回当前健康/容量快照。task.create/PV-13 初次放行要求 fresh healthy；已放行 run 或会话在 acquire 前健康转差时仍可持久化排队并标 unhealthy，但不得启动 Runtime。Workflow 与 Session 不得绕过 selector/queue 直接启动 Runtime。
- enqueue 对 run/turn 二选一且活动唯一，Workflow/Session 共用 backend_queue_entries。Rust 从只读应用默认配置加载 `global_process_limit`（未配取 clamp(logical_cpu_count,2,16)，显式 1..64），经认证 bootstrap 注入 Sidecar；WebView/RPC/环境变量不可改写。`acquire_next` 按设计方案 §6.11 的 Backend 内 FIFO + 跨 Backend 队首全局最早算法，在一个事务检查双层上限、写 lease 和 queue 投影；deadline/cancel_reason 同该节，不维护第二套内存计数。
- Runtime 子进程统一经 Sidecar `LocalProcessSupervisor` 启动，启动后立即把 worker_pid/process_start_token CAS 绑定 lease；start token 用 OS process start time + 单次 launch nonce 防 PID 重用误认。heartbeat 每 10 秒，30 秒过期。reconciler 联合查询 Supervisor、持久化 run/turn 和副作用：未绑定且未启动可释放；身份匹配进程仍存活则恢复监管或先确认终止；无法确认身份/终止时 Backend 置 unavailable 且 lease 继续占槽；进程已终止才按 committed/unknown 完成或创建/复用 HumanIntervention。unknown 绝不自动重跑，重复 bind/release/reconcile 返回同一结果。
- 无法自动确认进程身份、存活状态或安全终止时创建/复用 `backend_recovery` intervention，并写 `BackendRecoveryRequired`；实现 LocalOwner-only 的 `workflow.backendRecovery.resolve`。`retry_inspect` 只重跑无副作用探测；`terminate_process` 必须再次匹配 `(worker_pid,process_start_token)` 且确认退出；`mark_failed` 必须先确认进程不存在，再把关联 run/turn 置失败、保留证据并释放 lease。三个动作均用 intervention/lease version CAS、写 Backend 审计；安全关闭时写 `BackendRecoveryResolved`，均不得直接重跑原业务。
- lifecycle/health 变化与 acquire 竞态由同一 Backend version/事务校验关闭 TOCTOU；draining 后不发新 lease，已有 lease 可到安全边界；最后释放者幂等完成 disabled 转换并通知排队调度器/公司解散协调器。每次 lease 获取/释放/queue 变化（entry 状态转换）/recovery 完成时发送 `notify.backendStatus` 通知，携带 Backend id、held/limit、queue 长度、open recovery 计数等变化字段。
- 完成 `backend.checkAvailability(company_id,backend_id,request_ref?)`：无 request_ref 时两级 position/reason 为 null；有 request_ref 时校验其同公司且匹配活动 waiting entry，按 Backend 内前置数量+1计算 backend_position，并按真实调度算法模拟 global_schedulable_rank；不可调度时 rank=null 且返回 wait_reason。结果带 observed_at，只作瞬时诊断。
- 创建 Backend Recovery 时 `human_interventions.target_ref` 固定为 `backend_lease:<lease_id>`，并校验该 lease 与 intervention 同公司；`notify.backendStatus.open_recovery_count` 每次都在领域/CAS 事务提交后过滤 open backend_recovery interventions、解析 target_ref 并连接 backend_leases 后按 backend_id 查询投影，不维护自增/自减字段。悬空/跨公司引用使 Backend 保持 unavailable 并进入一致性告警。并发 resolve 只有 version CAS 胜者执行并发通知；丢通知或乱序由 `workflow.humanIntervention.list` 与 reconciler 重算事实，不会双减。

**测试**：
- 以并发事务争抢 `concurrency_limit=2`，断言单 Backend 任意时刻 held≤2；再用三个 Backend 各自 limit=2、global_process_limit=3 并发争抢，断言总 held≤3，释放后从各 Backend 可调度队首中按全局最早者继续。capacity/health/lifecycle 在校验与 acquire 间变化时 acquire 失败，不超发。
- 跨 Backend 公平性测试：3 个 Backend 各 limit=2、global=5，当 A 满载（held=2）、B 满载（held=2）、C 有 1 空槽时，全局第 5 个排队任务必须分配到 C（而非等待 A/B 释放）。
- Sidecar 冷启动时 `global_process_limit` 从 Rust bootstrap 消息注入，在注入完成前 `acquire_next` 返回 `BACKEND-UNAVAILABLE`（不能使用未初始化的默认值）。
- task run 与 session turn 混合 FIFO、重复 enqueue、三种 wait_reason、四种 cancel_reason、降并发低于当前 held、draining 排空、重复 bind/heartbeat/release、过期 lease 的 unbound/alive/dead/unknown 四分支与 PID 复用 start-token 不匹配全部覆盖；无法终止活进程时不释放槽并把 Backend 置 unavailable。
- Fake clock 覆盖 session 30 秒与 task node deadline：超时 entry 唯一取消、线程/attempt 回到正确状态，稍后释放槽位也不会启动已取消请求。
- 切换默认后 drain 旧 Backend：waiting session turn 保留原 queued_at 重入新默认且不重复发送，waiting task entry 被取消并明确要求 retry/replan；公司解散取消两类且不重排。
- 在 acquire 已提交但 Runtime 未启动、Runtime 已启动未 heartbeat、release 前后强杀 Sidecar，重启对账不重复执行副作用且槽位最终收敛。
- `backend_recovery` 覆盖 active/dissolving 公司、非 LocalOwner/跨公司拒绝、start-token 不匹配、活进程安全终止、进程不存在后 mark_failed、重复 resolve 幂等和未知副作用不直接重跑；dissolving 下释放最后 lease 后能继续 Backend/公司 watermark，释放前必须有可验证的退出/不存在证据。
- 两个不同 recovery 并发关闭与同一 recovery 双提交均验证通知里的 open_recovery_count 等于数据库 open 行数；故意丢弃通知后查询刷新与 reconciler 仍恢复同一计数。
- `backend.checkAvailability` 覆盖无 request_ref 时 position/reason 全 null、有 ref 时 backend_position 与 global_schedulable_rank 的精确样例、ref 不匹配/跨公司拒绝、健康 stale、两级满载及 dissolving/dissolved；并与并发 acquire 使用同一调度算法和容量事实。

**DoD**：Backend 选择、Backend/全局双层限流、跨 Backend 公平排队、lease 心跳/释放/过期和崩溃恢复均由持久化事实驱动；`backend.checkAvailability` 有真实 handler 与成功/失败契约测试；P7/P9 可只依赖上述 ports 接入，不自行实现第二套并发计数。

### P6-T2：Credential Broker（Rust 侧 Keychain 代理 + Python 侧客户端）
**文件**：
- `apps/desktop/src-tauri/src/credential_broker.rs`
- `sidecar/acos/providers/credential_broker_client.py`
- `sidecar/acos/providers/credential_capability.py`

**实现要点**（对照 §11.2、§12.3——**解决"Keychain 只在 Rust 侧"与"API Provider 要在 Python 侧发 HTTP 请求需要明文"的矛盾**）：
- Keychain 条目键为 `(company_id, provider_id, credential_slot)`；同一 Provider 被多家公司分别使用时凭据互相隔离，`credential_slot` 区分同一公司同 Provider 下的多组凭据。
- `provider.credential.set` / `provider.credential.delete` 是**Tauri-only 命令**：WebView 直接 `invoke` Rust Core 写入/删除 Keychain，**完全不经过 Sidecar、不经过 UDS JSON-RPC 通道**——这两个方法只出现在附录 B 表里说明契约，Sidecar 代码里不实现、不路由它们。
- UDS 创建在应用私有运行目录并固定 `0600`；Rust/Sidecar 每次启动用 nonce 建立双向认证会话和临时 session key，任一进程重启即失效。
- Task/Session 服务完成公司、assignment、ProviderPolicy 与预算校验后，把不可由 RPC DTO 构造的 `VerifiedCredentialContext` 交给 `CredentialCapabilityIssuer`，签发绑定 `capability_id/company/provider/slot/task_run_id|session_turn_id/request_hash/expiry/nonce` 的短期单次 capability。
- capability TTL 固定 30 秒且只可兑换一次；兑换前过期必须重新做全部校验后签发，不能续期。兑换后正在进行的 HTTP 流不因 token 到期自动终止，其取消由绑定 run/turn 的 ProviderAdapter.cancel 控制。
- owner=`internal_only` 的 `provider.credential.resolve` 是 Credential Broker 取值通道，只接受当前会话签名、字段完全一致、未过期且未消费的 capability；Rust 原子消费 nonce 后才从 Keychain 取值。Broker 元数据日志仅含 capability/company/provider/run/decision，不含 secret。
- Python 侧客户端：调用该取值通道拿到明文后，**只在本次 HTTP 请求的函数调用栈内持有**，用完立即丢弃引用；不写入任何变量之外的存储、不传入子进程环境；捕获异常时对该值做屏蔽处理，不让明文出现在异常堆栈日志里。
- CLI Provider 不走这条通道：CLI 自身的登录态由用户在其官方登录流程里完成，Sidecar 不代管。

**测试**：`apps/desktop/src-tauri/src/credential_broker.rs` 内 `#[test]`、`sidecar/tests/providers/test_credential_broker_client.py`
- 验证 `provider.credential.set/delete` 未在 Sidecar 的 RPC 分发表里注册（确保这两个方法确实是 Tauri-only，不会被误路由到 Sidecar）。
- 验证跨公司、篡改 provider/slot/run、过期、重放、错误系统用户、旧 IPC 会话和 Sidecar 重启后的 capability 均被拒绝。
- Fake clock 验证 30 秒前可兑换、到期即拒绝且旧 token 不可续期；重新签发必须重新走业务校验。已兑换并启动的流不因 capability 到期中断，但 cancel 后 secret 引用释放且不可再次使用。
- 验证同一 `provider_id` 在两个不同 `company_id` 下可分别设置互不覆盖的凭据。
- 验证该内部通道的请求/响应不会出现在标准日志输出里（用日志捕获断言）。
- 验证 Python 侧拿到明文后，即便调用过程中抛异常，异常日志里也不含明文内容。
- 验证明文不会被写入任何本地文件或环境变量。

**DoD**：Tauri-only set/delete 与 internal resolve owner 分离；只有 VerifiedCredentialContext 能签发单次 capability，Broker 负向契约和 secret 泄漏测试全绿。

### P6-T3：Claude Code CLI Provider Driver（v1 必选）
**文件**：`sidecar/acos/providers/cli/claude_code.py`

**实现要点**（对照 §11.2，若 Phase 0-T5 的选型结论是"采用 OpenHands SDK"，本任务在内部封装它，对外仍只暴露 `ProviderAdapter`）：
- `checkAvailability`：`detectInstalled`（查 PATH）+ `checkAuth`（探测登录态，若无法可靠探测则退化为"尝试一次最小调用判断是否报未登录错误"）。
- `createSession`：为该 Provider 生成/绑定原生 session id 的载体（真正的原生 resume 逻辑在 Phase 7 与会话线程打通，这里先把子进程调用与参数数组拼装做对：**必须用参数数组而非字符串拼接**，绝不能有 shell 注入风险）。
- 子进程环境：最小环境变量继承，API Key 不出现在命令行参数或日志里（CLI 场景通常不需要 Credential Broker，因为凭据由 CLI 自己的登录态管理）。
- `send()`：一次调用即为一次子进程调用（one-shot-per-turn，CLI 通常不是长驻进程），把 stdout 增量解析为 `RuntimeEvent` 流。

**测试**：`sidecar/tests/providers/test_claude_code.py`
- Mock 子进程调用（不依赖真实安装 Claude Code CLI 也能跑单测），验证参数数组构造正确、环境变量最小化、`send()` 产出符合 `RuntimeEvent` 结构。
- 集成测试（标记为 `@pytest.mark.requires_cli`，CI 里若环境没装该 CLI 则跳过）：真机上验证一次真实调用能跑通。

**DoD**：Claude Code CLI Driver 可用且真实集成测试通过；其余 CLI Driver 不属于 v1 DoD。

### P6-T4：OpenAI API Provider Driver（v1 必选）
**文件**：`sidecar/acos/providers/api/openai.py`

**实现要点**（对照 §11.2、§6.11）：
- `createSession`：API Provider 没有真实子进程会话，`Session` 是内存态对话上下文对象（消息列表）。
- `send()`：标准 HTTP 调用（同步一次性或流式 SSE），凭据经 P6-T2 的 Credential Broker 获取。
- `capabilities()` 返回 `streaming/tool_call/vision/max_context/billing_mode/enforces_output_cap`；价格只能由 P6-T1a 的版本化目录读取，Adapter 不维护第二份单价。
- `send()` 若调用方传入 `forced_max_output_tokens`（硬预算路径），必须把它作为该 Provider API 的硬性输出上限参数真正发出（如 OpenAI 的 `max_tokens`/`max_completion_tokens`），不是仅在本地记录。

**测试**：`sidecar/tests/providers/test_openai.py`
- Mock HTTP 调用，验证请求体构造正确、`RuntimeEvent` 解析正确（尤其是把 SSE chunk 正确翻译为增量事件）。
- 验证凭据不会出现在任何日志输出中（可用日志捕获断言）。
- 验证 capabilities 与价格目录职责分离，且 `enforces_output_cap=true` 时强制上限真实进入请求体。
- 真实集成测试标记为 `@pytest.mark.requires_openai_api`：从签名 `provider-models.json` 取具体 OpenAI 模型 ID，经 Credential Broker 分别验证普通、流式、一次受控工具调用、取消和用量回传；不得用 Mock 成绩代替 Phase 6 Go/No-Go 与发布候选验收。CI 无凭据时可跳过，但 `docs/发布记录.md` 必须有发布候选环境的 manifest version/hash、model ID 和通过结果。

**DoD**：OpenAI API Driver 的普通/流式/工具调用/取消/用量与 Credential Broker 链路可用，且签名 manifest 中的具体模型已通过真实 API 集成测试；其余 API Driver 不属于 v1 DoD。

### P6-T5：Provider 不可用降级链
**文件**：`sidecar/acos/providers/registry.py`

**实现要点**（对照 §11.2"不可用降级"）：
- `probe_all(company_id)`：启动时按公司对已配置 Provider 调 `checkAvailability(company_id, provider_id)`，结果按 `(company_id, provider_id)` 缓存展示给 UI，禁止把一个公司的凭据/可用性结果复用于另一公司。
- `resolve_provider(employee, requested_tier)`：按 `provider_override → 模板默认 → 公司 default_provider_policy` 顺序找可用 Provider；全部不可用时返回明确的"转人工"信号（不是抛异常吞掉，而是返回可被 Phase 9 识别的结构化结果）。
- 选出替代 Provider/模型后必须重新调用 P5-T2 生成新的 ResolvedRunConfig/config_hash，并让 P7 按新 provider/model 创建或选择安全上下文线程；预算、能力和 Backend requirements 重验，禁止在旧 config/thread 上原地换模型。
- 硬预算候选必须同时满足 metered、enforces_output_cap、有当前有效 pricing version 且未被公司级 freeze；未知/过期价格 fail-closed。
- 实现 CompanyDissolutionStarted 的 Provider consumer，冻结该公司的新 Provider 调用并幂等上报 watermark。

**测试**：`sidecar/tests/providers/test_registry.py`
- 模拟职员的 override Provider 不可用，断言正确降级到模板默认；模板默认也不可用则降级到公司策略；全部不可用返回"需转人工"结果而不是抛未捕获异常。
- 按硬预算条件过滤：请求"硬预算"时，`billing_mode=unknown/estimated` 或 `enforces_output_cap=false` 的 Provider 均不会被选中；只有同时满足 `billing_mode=metered` 与 `enforces_output_cap=true` 的 Provider 才会被选中。
- 两个公司配置同一 Provider 但凭据状态不同，`provider.list/probeAll/checkAvailability` 返回各自独立的可用性，缓存不串公司。
- 对 `CompanyDissolutionStarted` 重放两次，当前公司新的 Provider 选择/调用均被拒绝、其他公司不受影响，Provider watermark 只上报一次；在冻结写入与 watermark 上报之间强杀后重启可幂等补完，失败会被公司解散协调器列为未完成 consumer。

**DoD**：`provider.list` / `provider.probeAll` / `provider.checkAvailability`（附录 B.6）可用，Provider dissolution consumer 有独立的重放、崩溃恢复与跨公司隔离测试。

### P6-T6：Agent Runtime 接口骨架
**文件**：`sidecar/acos/runtime/agent_runtime.py`

**实现要点**（对照 §11.1，**本阶段先打通"不依赖职员/能力概念"的最小闭环**）：
- 实现 `createAgent(resolved_run_config)`、`createConversation(agent, workspace)`、`sendMessage`、`run`、`pause`、`resume`、`cancel`、`streamEvents`、`collectArtifacts`、`dispose`。
- 本阶段 `workspace` 参数先接受一个最简单的本地目录路径（真实 Workspace 分类体系在 Phase 9 落地），保证 Runtime 接口本身可独立测试。
- Runtime **不**查询 Organization Service，`createConversation` 是否复用会话的判断逻辑放在 Phase 7 的调用方，不下沉到这里。
- `dispose(run_id)` 必须真实验证资源释放：临时目录删除、子进程终止、DB 连接归还。

**测试**：`sidecar/tests/runtime/test_agent_runtime.py`
- 用 `FakeProviderAdapter` 走一遍 `createAgent → createConversation → sendMessage → run → dispose` 全流程，断言产出的 `RuntimeEvent` 序列合理、`dispose` 后资源确实被清理。

**DoD**：Agent Runtime 接口全部可用并有 P6-T3/T4 至少各一个真实 Provider 接入验证。

### 阶段验收（Phase 6）
Provider、Backend、Credential Broker 与 Runtime 骨架具备：可用公司默认 `local_process` Backend 取得 lease 后跑通最小对话，容量满/健康 stale/draining 时不启动执行，崩溃后 lease 可对账；凭据全链路不落盘不进日志。对应 §19 第 8、15、25 条的 Phase 6 部分。

---

## Phase 7：职员会话：安全上下文线程

**目标**：把 Runtime 会话绑定到职员身份，同时确保跨任务的原始对话上下文不会绕过 ACL 造成泄漏，并接入公司 Backend lease。依赖 Phase 4（Employee）与 Phase 6（Provider/Backend/Runtime）。

**会话隔离约束**（详见设计方案 §11.4）：会话按 `security_context_key = hash(company_id, department_id, task_id_or_null, capability_snapshot_checksum, provider_id, model_id, workspace_policy_hash, security_policy_hash, effective_grants_hash)` 拆成多条**上下文线程**；任何一个维度变化都产生新线程。跨线程的"记忆"只通过受 ACL 约束的知识检索获得，不存在绕过 ACL 的原始记忆通道。

设计方案 §1 提到的 agentflow 仅是理念参考；本阶段不得链接其代码、启动其进程、读取其数据目录或复用其协议。session/resume、transcript 与摘要全部由本计划列出的 Sidecar 模块独立实现和测试。

### P7-T1：会话线程存储（按安全上下文分片，公司隔离路径）
**文件**：
- `sidecar/acos/runtime/session_thread_store.py`
- `sidecar/acos/runtime/service.py`
- `sidecar/acos/runtime/transcript.py`
- `sidecar/acos/runtime/path_broker.py`（若 Phase 3-T4 已建路径 broker 核心函数，本任务扩展到会话路径场景）
- `sidecar/migrations/0011_session_threads_and_events.sql`

**实现要点**（对照 §11.4）：
- 文件布局严格照抄 §11.4；可信应用数据根由 Rust 通过认证 bootstrap 注入，canonical-path/symlink/公司边界只由 Sidecar `runtime/path_broker.py` 校验，业务代码不拼绝对路径，Rust 不实现第二套 broker。
- `session.json` 写入用**原子写**（写临时文件再 rename，不直接覆盖原文件），目录权限收紧（`0700`）。
- SQLite `session_threads` 是线程元数据事实，`conversation_events` 是消息/可观察工具事件事实；唯一约束 `(employee_id, security_context_key)` 与 `(thread_id,sequence)`。`session.json/transcript.jsonl/context-summary.md` 是带 event watermark/checksum 的可重建投影，提供 `rebuild_projection_from_db(thread_id)`，禁止用旧文件覆盖数据库。
- 提供唯一 `compute_security_context_key(...)`。三个策略 hash 严格按设计方案 §11.4：分别使用 `acos:workspace-policy:v1\n`、`acos:security-policy:v1\n`、`acos:effective-grants:v1\n` 域前缀 + RFC 8785 canonical JSON 后取 SHA-256；workspace/security 输入字段完整固定，grant 按 grant_id+expires_at 排序，空集合固定为 `SHA256("acos:effective-grants:v1\n[]")`，不得用 NULL/空串/运行库默认 hash。
- 消息先在单个 SQLite 事务写 `conversation_events/domain_events/outbox_deliveries`，投影器再按 event id 幂等追加 transcript；单条超阈值内容落受引用保护的 artifact。
- `transcript.jsonl` 实现 §11.4 的固定行 schema、canonical checksum 与 Provider 格式归一化。`context-summary.md` 按 20 条/8,000 token 任一先到生成，固定 front matter、NFC/LF/空白规范化、工具 request hash、超长内容 artifact_ref；不调用模型。恢复预算为目标 max_context 扣 system_prompt 和 20% response reserve。

**测试**：`sidecar/tests/runtime/test_session_thread_store.py`
- 原子写测试：模拟写入过程中进程被杀，验证旧 `session.json` 内容未被破坏。
- 删除/篡改投影文件后可从 SQLite 重建相同 event 序列和 checksum；旧投影 watermark 不能反向覆盖新 DB 状态。
- `context-summary.md` 生成函数两次调用相同输入产出完全一致的内容（确定性，可用 mock 断言没有调用任何 Provider）。
- golden fixtures 验证 transcript 行 schema/checksum、空 grants hash、策略字段排序和 context-summary 字节级稳定；不支持的 schema_version fail-closed 并新建线程。
- 路径 broker 测试：验证不同公司的会话线程路径互不可达（构造跨公司路径穿越尝试，断言被拒绝）。
- `compute_security_context_key` 测试：仅改变 `model_id`（Provider 不变）产出不同 key；仅改变 `workspace_policy_hash`/`security_policy_hash`/`effective_grants_hash` 分别产出不同 key；九个维度全相同则 key 相同（确定性）。

**DoD**：SQLite 事实与文件投影边界、重建、路径隔离和事件原子写均有测试；不存在第二事实源。

### P7-T2：职员 ↔ 会话线程绑定与惰性创建（按安全上下文查找）
**文件**：`sidecar/acos/runtime/session_thread_store.py`（扩展）、`sidecar/acos/organization/service.py`（接线 `primary_session_thread_id`）

**实现要点**（对照 §11.1、§11.4）：
- `get_or_create_current_thread(employee_id, task_id_or_null)`：服务端根据当前 Employee/Capability/Provider/Workspace/SecurityPolicy/有效授权重新计算 `security_context_key`，查到则复用，查不到则创建带稳定 `thread_id` 的线程并写索引。外部请求不接受客户端自造 key。
- `task_id_or_null = null` 的通用线程回写 `employee.primary_session_thread_id`；任务绑定的线程通过 `(employee_id, security_context_key)` 或 `(employee_id, task_id)` 查询，不经过 `primary_session_thread_id`。
- `send_to_thread(employee_id, thread_id?, message)`：不传 `thread_id` 时走当前通用线程；传入时加载线程、校验 employee 归属并重算当前 key。key 不一致报 `RT-SESSION-STALE`，`dormant/archived` 报 `RT-SESSION-READONLY`。任务页面必须传选中任务线程的 `thread_id`。
- `session.list/get/transcript.get/cancel` 均使用稳定 `thread_id`；transcript 对 dormant/archived 只读开放，但读取前仍调用 P4-T3 的 `authorize`。
- 单个线程同时只允许一个 active turn：用 `session_threads.active_turn_id/status/version` 的数据库 CAS 占有并辅以进程内锁；CAS 获取模式：`UPDATE session_threads SET active_turn_id = ?, status = 'running', version = version + 1 WHERE thread_id = ? AND active_turn_id IS NULL AND version = ?`（命中才返回 affected_rows=1，否则返回 `RT-SESSION-BUSY`）；CAS 释放模式：`UPDATE session_threads SET active_turn_id = NULL, status = ?, version = version + 1 WHERE thread_id = ? AND active_turn_id = ? AND version = ?`。进程内锁只作为优化（防止同一进程内重复 acquire），数据库 CAS 是唯一权威。Sidecar 重启后，所有内存锁释放，数据库中的 `active_turn_id` 通过对账器安全释放：核对关联的 process token + heartbeat 时间，若进程已不存在则 CAS 释放 turn 并恢复线程状态（与 P6-T1c 的 lease 对账类似）；无法确认进程状态时创建 `employee_drain` intervention 转人工，不猜测性释放。
- active turn 在首次 Provider 调用前经 P6-T1c 从公司默认 Backend 取得绑定 `session_turn_id` 的 lease，Runtime 子进程启动后立即绑定 Supervisor process token；容量满时线程置 `waiting_backend` 并按 FIFO 等待，cancel/完成/失败在安全边界确认进程终止并释放。Backend id 不作为第十个安全上下文维度：v1 所有 Backend 都是同机 `local_process+policy_only`，Workspace/SecurityPolicy 已进入九维 key；切换默认 Backend 后可在兼容 Backend 继续该线程，但每个 turn 固化实际 backend/lease 并走原生 resume→transcript 兜底。

**测试**：`sidecar/tests/runtime/test_session_binding.py`、`sidecar/tests/runtime/test_session_rpc.py`
- 首次调用某安全上下文创建新线程；第二次调用相同上下文复用同一线程（不新建）。
- 不同 `task_id`（因而不同 `security_context_key`）产生不同线程，互不干扰。
- 并发对同一线程发两条消息，第二条应立即收到 `RT-SESSION-BUSY`。
- 同一职员打开通用线程与两个任务线程，分别按 `thread_id` 发送、取消和读取 transcript，消息与通知不得串线；传入其他职员的 thread_id 被拒绝。
- 安全上下文已变化的 thread_id 返回 `RT-SESSION-STALE`；dormant/archived 返回 `RT-SESSION-READONLY`，但经鉴权后仍可分页读取 transcript。
- 能力升级（`capability_snapshot_checksum` 变化）后，同一职员同一部门同一任务的调用会得到一条**新**线程，不是复用旧线程。
- 切换模型（`model_id` 变化，`provider_id` 不变）、切换 Workspace 策略、切换 SecurityPolicy，分别得到新线程；旧线程转 `dormant`，其 transcript 不出现在新线程发给 Provider 的请求里。
- 创建一条临时跨部门授权（第 8.4 节）后得到新线程；撤销该授权后再次得到新线程；授权自然过期（`expires_at` 已过）后同样得到新线程——三种情况各自验证：授权期间在旧线程 transcript 里写入的哨兵文本，不会出现在授权失效后新线程发往 Provider 的请求内容里。
- Backend capacity 满时不调用 Provider，释放前一 lease 后排队 turn 才启动；健康 stale/draining 时保持 waiting/返回结构化原因；cancel 与 Sidecar 重启后 turn CAS 和 lease 均收敛且不重复发送消息。

**DoD**：`session.list/get/sendMessage/cancel/transcript.get`（附录 B.4）可用，稳定 thread_id 寻址、按安全上下文分片、同时一个 active turn、九维度任一变化即新线程及 Backend lease 接入均有测试验证。

### P7-T3：原生恢复优先 + 规范化日志降级
**文件**：`sidecar/acos/runtime/resume.py`

**实现要点**（对照 §11.4 恢复策略——**恢复目标不是"最近 50 条"，是"最近检查点 + 有界 tail"**）：
- 优先调 `ProviderAdapter.resume(checkpoint)` 用原生 session id；失败或该 Provider 不支持原生会话时，加载最近一个滚动检查点 + 之后到当前的有界 tail（按 token 预算裁剪，不是固定条数），走 `createSession` 并把重建的上下文作为初始输入，`resume_mode` 更新为 `transcript`。
- 失败降级要记录 `RT-RESUME-FAILED` 到日志/事件，但**不能让整个请求失败**——降级成功后应正常返回给调用方。

**测试**：`sidecar/tests/runtime/test_session_resume.py`
- Mock 原生 resume 成功场景，验证走原生路径。
- Mock 原生 resume 抛异常/该 Provider 不支持，验证自动降级到"检查点+有界 tail"重建，且 `resume_mode` 字段被正确更新。
- 构造一个包含超大单条消息（如大工具输出）的 transcript，验证"按 token 预算裁剪"确实生效，不会因为"凑够 50 条"而让上下文超出模型窗口。

**DoD**：`session.resume`（附录 B.4，内部）两条路径均有测试；对应设计方案 §19 第 13 条。

### P7-T4：调岗 Handoff（状态机 + 崩溃对账，范围仅限通用线程）
**文件**：`sidecar/acos/runtime/handoff.py`，实现并注册 P4-T5 `EmployeeDrainRuntimePort` 的 transfer Handoff 部分。

**实现要点**（对照 §11.4，**安全关键路径：不假设"一个 SQLite 事务能连带回滚文件系统操作"（SQLite 无法撤销已发生的文件写入），改用显式状态机 + 崩溃对账**）：
- **前置条件**：本函数只在 P4-T5 的排空阶段完成、`session_transfer_state` 已置 `transferring`、`employee.department_id` 已更新之后才被调用；调用时该职员名下不存在任何 `active` 的 `task_assignments`（P9-T1a），因此"运行中任务的原始上下文与运行时 ACL 分别处于新旧部门"这种竞态在进入本函数前已被排空阶段消除。
- `handle_transfer(employee_id, new_department_id)`（只处理该职员的**通用会话线程**，任务绑定的线程此刻均已终态/关闭，天然按 `task_id` 隔离，不受调岗影响，不需要特殊处理）：
  1. 按新部门在 staging 路径写入一个新的通用线程，写完后原子 rename 到最终位置。
  2. 把旧通用线程的 `session.json` 置 `archived`（不删除，留一条指向旧线程 `security_context_key` 的审计引用；不把旧 transcript 带入新线程的活跃上下文）。
  3. 短事务内更新 `employee.primary_session_thread_id` 指向新线程、`employee.session_transfer_state` 置回 `none`、写 `EmployeeTransferred`（**调岗最终完成事件，全流程只有这一步写它**）、写 `org_change_audit`，提交。
- **崩溃对账器**（`reconciler_scan_transferring()`）：Sidecar 启动时扫描 `session_transfer_state=transferring` 的职员——判定条件如下：
  1. **可安全判定已完成**：staging 路径下的 `session.json` 存在且完整（checksum 校验通过），其 `security_context_key` 与目标线程一致，旧通用线程 `session.json` 的 `status` 已为 `archived` → 补完第 3 步的数据库更新（`primary_session_thread_id` 指向新线程、`session_transfer_state` 置回 `none`）与 `EmployeeTransferred` 事件（幂等，保证恰好一次）。
  2. **无法安全判定**：staging 文件不存在、不完整、checksum 不匹配，或旧线程未归档 → 删除 staging 残留目录，保持 `needs_repair`，写 `EmployeeTransferNeedsRepair`，不自动猜测性继续，等待人工在人工干预中心确认。

**测试**：`sidecar/tests/runtime/test_handoff.py`（**本任务的核心测试目的是防止"旧部门私有知识绕过 ACL 泄漏到新部门"**）
- 调岗前在旧通用线程的 transcript 里写入一条包含"旧部门私有信息"标记字符串的消息；调岗后，新通用线程首次 `sendMessage` 传给 Provider 的上下文里**不应包含**这条旧消息——直接断言传给 Provider 的内容不含该标记字符串。
- 旧线程归档后 `status=archived`，不再接受新的 `sendMessage`。
- 模拟在"写完新线程但未归档旧线程"时崩溃，重启后对账器能正确补完或识别为 `needs_repair`。
- 模拟"新线程 staging 写入中途崩溃、staging 目录不完整"，对账器应判定为 `needs_repair` 而不是错误地当作"已完成"，并验证写入了 `EmployeeTransferNeedsRepair`。
- 任务绑定的会话线程（`task_id` 非空）在调岗前后内容不变，不受 Handoff 触碰。
- 正常路径与对账器补完路径分别验证：全流程恰好产生一次 `EmployeeTransferred`，不重复、不遗漏。

**DoD**：以上全部测试全绿；这是 §19 第 14 条的核心验收点，**不允许打折扣**。

### P7-T5：会话线程状态机与公司解散/职员归档的处理
**文件**：`sidecar/acos/runtime/session_thread_store.py`（补充状态转换）、`sidecar/acos/runtime/employee_drain_port.py`

**实现要点**（对照 §11.4）：
- 状态机：`idle→running→idle`；`idle→waiting_backend→running`（取消回 idle）；`running→waiting_approval→running`；`idle|waiting_backend|running→dormant`（任务结束/长期未使用）；`idle|waiting_backend|running|dormant→archived`（公司解散/职员归档/调岗使旧通用线程失效）；`running→failed→recovering→running`（崩溃恢复，幂等）。
- 实现 P4-T5 的 Runtime port：suspend operation 只接受服务端 drain token，让已登记 active turn 收敛到安全 checkpoint/当前调用终点、释放对应 Backend lease 后把全部线程转 dormant；公共 sendMessage 不接受该 token。消费 `EmployeeResumed` 时，仅在 employee active、无 open drain、九维 key 未变时把当前 dormant 线程 CAS 回 idle，否则惰性建新线程；`get_or_create_current_thread` 以同一规则幂等补齐尚未消费的 resume。archive operation 把全部线程 archived；每个 operation 只有在该职员无 held turn lease 后才按 drain_id 返回幂等 ACK。
- 消费 `CompanyDissolutionStarted`：停止/取消 waiting_backend 与 active turn，在可确认安全的 checkpoint 释放对应 Backend lease；副作用 unknown 创建 intervention。该公司全部 held turn lease 收敛且所有职员的**全部**会话线程（不只是通用线程）置 `archived` 后，才持久化 Session watermark 并通知 P2-T1 协调器；最终 `CompanyDissolved` 只作完成确认，不能等到该事件才归档，否则会与“等待 Session/Backend watermark 后才能发 CompanyDissolved”形成循环依赖。
- 消费 `EmployeeArchived`：同事务提交后的 outbox consumer 幂等归档该职员全部通用/任务线程；归档失败进入 HumanIntervention，不允许已归档职员继续发送新 turn。

**测试**：`sidecar/tests/runtime/test_session_lifecycle.py`
- 非法状态转换（如 `archived → running`）应被拒绝。
- 收到 `CompanyDissolutionStarted` 后，该公司 waiting_backend/active turn 与 Backend lease 安全收敛、全部线程变为 `archived` 后才上报唯一 watermark；重复投递不重复 release/归档，且验证 P2-T1 只有取得 Session 与 Backend 两个 watermark 后才允许完成解散。
- `EmployeeArchived` 重放不重复写事件，归档前已 running 的线程先 checkpoint 后只读，后续 sendMessage 被拒绝。
- suspend 时 active turn 安全停下且所有线程 dormant，employee 非 active 时即使伪造 idle thread_id 也不能发送；resume 的同 key 复用与 key 变化新建、archive ACK 重放分别有测试。
- drain token 绑定 drain/employee/run/active_turn 且只走内部端口；字段篡改、其他 run 使用、公共 RPC 携带和 drain 终态后重放均被拒绝，重启后只能从持久化 open drain 为原 run 重建。

**DoD**：对应 §19 第 14 条后半句（公司解散/职员归档后会话线程只读归档）。

### 阶段验收（Phase 7）
对应 §19 第 13、14 条全部。这是继 Phase 4 之后第二个"安全红线密集"的阶段，Handoff 相关测试（尤其"跨安全上下文不泄漏原始记忆"）是全项目除权限引擎外最重要的测试集合。

---

## Phase 8：知识库与 RAG

**目标**：落地双层存储、知识提炼流水线、混合检索。依赖 Phase 1（Outbox）、Phase 3（能力 knowledge_scope）、Phase 4（权限引擎）、**Phase 6（知识提炼需要调用 ProviderAdapter）**。

### P8-T1：第一层：原始事件存储
**文件**：
- `sidecar/acos/knowledge/raw_store.py`
- `sidecar/migrations/0012_knowledge_sources.sql`

**实现要点**（对照 §9.1、§9.3）：
- 禁止建立第二套 raw_event/message 表：会话原始事实来自 P7 的 `conversation_events`，任务事实来自 `domain_events`；`raw_store.py` 只提供按 company/event watermark 读取和保留策略接口。
- `knowledge_sources` 不是第二套事件正文，而是派生链的来源索引：字段严格采用设计方案 §9.2，`UNIQUE(company_id,source_type,source_id)`；事件来源保存 source_event_id，file/manual 保存受 path broker 校验的 original_ref。一个 source 可对应 0..N 个 document。
- Knowledge consumer 通过 `outbox_deliveries` 消费上述事实并记录 ingestion watermark；文件 transcript 是投影，不作为摄取事实源。
- 保留矩阵（对照 §9.1）：本阶段实现"正常软删除"路径（标记 `deleted_at`），"用户请求硬删除"的级联清理逻辑在 P8-T4 之后统一实现（需要先有检索/索引层才能级联）。

**测试**：`sidecar/tests/knowledge/test_raw_store.py`
- 写入 conversation event 后同事务出现 delivery；删除/篡改 transcript 投影不影响 raw_store，重放 consumer 不重复创建 ingestion job。

**DoD**：原始层写入路径可用，且知识提炼失败不影响它（对照 §19 第 2 条）。

### P8-T2：知识提炼流水线（进程池隔离，依赖 Provider）
**文件**：
- `sidecar/acos/knowledge/extractor.py`
- `sidecar/acos/knowledge/chunker.py`
- `sidecar/acos/knowledge/policy_service.py`
- `sidecar/migrations/0013_knowledge_documents.sql`

**实现要点**（对照 §9.2、§9.3、§9.5、§4.6——**提炼调用真实 Provider，因此依赖 Phase 6；CPU 密集的分块工作跑在独立进程池，不占用主事件循环**）：
- Knowledge Worker 消费 delivery → 幂等创建/读取 knowledge_source → 清洗脱敏 → 调提炼模型产出 5 类知识 → 按 source_record_id 写 0..N 个 knowledge_documents 与 chunks；documents 字段、同公司 FK、document_id=RPC knowledge_id 均严格采用设计方案 §9.2。
- `knowledge_ingestion_jobs` 的完整状态枚举为 `pending|running|retryable|succeeded|failed|cancelled`（与 §9.2 一致）；每次状态 CAS 成功后发 `notify.knowledgeStatus`，通知的 `status` 直接取持久化枚举值。
- 按 `knowledge_sources.source_type` 分支处理：`conversation_event` 来源需按 thread 聚合（同一线程内多条消息合并为一个 extraction unit）后再提取；`manual` 来源跳过 extraction 步骤，直接创建 knowledge_document 入库（状态直接为 `succeeded`）；`file` 来源的文件内容读取受 Path Broker 路径校验约束（只能读取 Workspace allowed_paths 内的文件）；`domain_event` 和 `artifact` 来源走通用 extraction 流程。
- `settings.knowledgePolicy.get/update` 管理 P2-T1 建立的版本化策略：update 必须携带 get 返回的 expected_policy_version，以旧 active version CAS 创建 version+1、supersede 旧版并切 pointer；extraction provider/model/mode(local|cloud)/fallback(local|pause)/allow_cloud/consent。云端模式必须有当前 policy version 的显式同意；撤回后新云端 job 立即停止。local 不可用时绝不静默切 cloud。
- ingestion job 固化 policy version；提炼 Provider 与职员对话 Provider 解耦，Knowledge Worker 使用锁定的 provider/model/policy version 构建一次性 config，调统一 `ProviderAdapter.createSession(config)` + `send(session, extraction_prompt, stream)`，不定义 `ProviderAdapter.chat`；API Provider 经 Credential Broker，CLI Provider 用官方登录态；Embedding 只走 EmbeddingCapable，能力声明与错误码分别测试。
- KnowledgeDocument.source_category 在创建时从 knowledge_source 不可变物化，trigger 校验同公司、同 category 且禁止单独修改，供 FTS/LanceDB 预过滤；权威来源仍是 knowledge_sources。
- chunks/citations/ingestion_jobs 字段和约束逐项采用设计方案 §9.2：chunk 以 document+generation+index 幂等；Knowledge Worker 在写 chunk 的同一 SQLite 事务生成唯一 citation，locator 只包含 source 适用的事件序号/页/行/字节区间且至少一键，仅存 locator/quote_hash 不复制原文；job 锁定 policy id/version，并以 source+policy+attempt 唯一、version CAS 收敛。
- 分块（`chunker.py`）是 CPU 密集工作，用 `ProcessPoolExecutor` 隔离，不在主 asyncio 事件循环里跑同步计算（对照 §4.6）。
- 提炼失败：`knowledge_ingestion_jobs` 表标记该任务为可重试状态，**不影响**已落盘的原始事件。
- 每次 job 状态 CAS 成功后发 `notify.knowledgeStatus`，通知的 `status` 直接取持久化枚举 `pending|running|retryable|succeeded|failed|cancelled`；断线 gap 后 UI 通过 job/document 查询刷新事实，不根据最后一条通知反写数据库。

**测试**：`sidecar/tests/knowledge/test_extractor.py`
- 构造一条含明显密钥格式字符串的原始消息，验证清洗后该字符串不出现在提炼结果里。
- Mock 提炼模型调用失败，验证 `knowledge_ingestion_jobs` 正确标记可重试，且原始事件表内容不受影响。
- 验证每个 chunk 恰有一条同公司、同 document/source 的 citation；locator 为空、同 chunk 重复引用或 quote_hash 与定位片段不符均拒绝。
- 对六个 ingestion job 状态逐一验证通知值与数据库值相同；重放通知不改写 job，模拟 stream gap 后查询可恢复最终状态。
- 未同意 cloud、同意版本过期、撤回同意、local provider 不可用的 fallback=pause、策略更新期间运行中 job 锁版均有测试。
- 两个携带相同 `expected_policy_version` 的并发策略更新只有一个成功，失败方返回 `SYS-OPTIMISTIC-LOCK-CONFLICT`，且不产生孤立策略版本或重复治理审计。
- 验证不保存"隐藏推理过程"——提炼结果 schema 里没有原始 chain-of-thought 字段。
- 性能隔离测试：分块一个大文档时，同时发起的其他前台 RPC 请求延迟不受明显影响（用简单的并发计时验证，作为 `observational` 指标）。

**DoD**：对应 §19 第 2 条（提炼失败不丢原始信息）与第 8 条（密钥不进知识库）。

### P8-T3：向量存储与本地 Embedding（含预过滤能力验证）
**文件**：
- `sidecar/acos/knowledge/vector_store.py`（`VectorStore` 抽象 + LanceDB 实现）
- `sidecar/acos/knowledge/embedding.py`（定义 `EmbeddingCapable.embed(texts)->Vector[]` Protocol 与 `LocalOnnxEmbedding` 实现，推理跑在独立进程池）
- `sidecar/migrations/0013b_index_generations.sql`

**实现要点**（对照 §9.5、§14、§17——**冻结 LanceDB 版本前必须验证它真的支持 pre-filter，而不是先召回再过滤**）：
- `VectorStore` 抽象接口独立于 LanceDB 具体实现，便于将来替换。
- **本任务的第一步是验证**：所选 LanceDB 版本的查询 API 能否接受过滤条件并在计算相似度之前应用（pre-filter），而不是"先取回 top-K 再在应用层丢弃不满足条件的结果"（后者等同于"先跨范围召回再让模型忽略"，是设计方案明确禁止的模式）。若验证不通过，需要在本任务内换版本或换向量库，不能带着错误假设往下走。
- 本地 Embedding 固定用 `BAAI/bge-m3` ONNX、1024 维；`embedding-models.json` 固定 revision、权重/tokenizer SHA-256 与 dimension，加载时逐项校验。权重不进可执行文件，推理跑独立进程池。
- `index_generations` 按设计方案 §9.5 建 `generation_id UUID PK/company/model/version/dimension/generation/status`，company+generation 唯一且每公司最多一条 active；embedding_policies.active_generation_id 初始可空，非空时为同公司 active generation FK。chunks 与 LanceDB 都存 generation_id，并按 `(chunk_id,generation_id)` 幂等；整数 generation 只展示排序。检索在同一读事务固定 pointer。切换以 policy version+旧 pointer 做 CAS，在同一写事务完成旧代 retiring（若有）、新代 building→active、pointer/version 更新与 `EmbeddingGenerationSwitched` Outbox；任一步失败整体回滚。旧代未清理时，回滚用同一 CAS 机制反向切换；已清理则必须重建。

**测试**：`sidecar/tests/knowledge/test_vector_store.py`、`test_embedding.py`
- **预过滤验证测试**：写入若干带不同 `company_id` 的向量，构造一个过滤条件查询，断言返回结果的候选集合本身就受过滤条件约束（不是查询 API 内部先取了更大范围再丢弃——若 LanceDB 的 API 本身不暴露"查询计划"信息，至少要验证性能特征符合 pre-filter 预期，或改用能验证的方式）。
- `reindex` 流程：新建索引版本期间旧索引仍可查询（模拟并发查询），切换完成后新查询走新索引、旧索引可被清理。
- 在切换事务的每个写步骤注入失败，断言 pointer 与状态整体保持旧值；并发两个切换仅一个 CAS 成功。验证切换前已开始的读事务继续旧代、提交后的新读走新代，以及旧代保留时成功回滚、旧代清理后回滚被明确拒绝。

**DoD**：对应 §19 第 16 条（换 embedding 模型可回滚）；LanceDB 预过滤能力已验证并记录在 `docs/打包验证记录.md` 或独立的技术选型记录里。

### P8-T4：混合检索流水线（结构化谓词下推查询条件）
**文件**：`sidecar/acos/knowledge/retriever.py`

**实现要点**（对照 §9.4，**检索前 ACL 是本任务的安全关键点：谓词是结构化分支，不是扁平交集**）：
```text
1. `query_with_audit(operation=search)` 验证 subject context，调 `compute_scope()`，与 Capability 的
   visibility_scope 逐分支求交，并下推 source_categories 过滤
2. SQLite FTS5 关键词检索（AuthorizedScope 各分支条件下推到 SQL WHERE 里，按 visibility 分支
   构造 OR 条件：`visibility='company' AND company_id=当前公司` / `department_id IN...` /
   `task_id IN...` / `employee_id IN...`，不是查完再过滤）
3. LanceDB 向量检索（同样把分支条件作为 pre-filter 条件，需 P8-T3 已验证的预过滤能力支撑）
4. Reciprocal Rank Fusion 融合
5. governance_confirmed 优先 + 时间衰减 + status 过滤（跳过 superseded/rejected/deleted）
6. Token 预算裁剪
7. 生成带引用的最终 Context Pack，调用 P1-T5 的 `write_knowledge_access` 精确记录最终返回的
   knowledge ids、scope_hash、matched_rules 后返回
```
**约束**：步骤 2、3 的范围过滤必须在数据库/索引查询条件里，不允许"先查全部再在应用层过滤"。

**测试**：`sidecar/tests/knowledge/test_retriever.py`（**安全测试为主，真实集成测试而非纯 mock**）
- 用真实 SQLite FTS5 与真实 LanceDB（不是 mock 查询语句）构造跨公司的"哨兵"知识数据，验证检索结果在数据库/索引层就不包含其他公司的数据；同理验证跨部门越权、`employee_private`/`task_private` 越权（联调 Phase 4-T3 的核心断言场景）。
- 负向 fuzz 测试：随机构造大量越权查询组合，验证零泄漏。
- `rejected`/`deleted` 状态的知识不出现在结果中。
- Context Pack 每条结果都带 `citation` 引用字段。
- allow 场景的 `knowledge_access_logs.result_knowledge_ids` 与最终 Context Pack 完全一致；deny 场景记录空结果与拒绝规则；向量候选但未进入最终结果的 chunk 不记为已返回。

**DoD**：`query_with_audit` 的 search 路径和 `kg.search` 可用；ACL/来源类别都在查询前收窄，真实数据库集成测试全绿。

### P8-T4a：知识浏览、引用与治理命令

**文件**：
- `sidecar/acos/knowledge/service.py`
- `sidecar/tests/knowledge/test_service.py`

**实现要点**（对照附录 B.5）：
- 把 P8-T4 的 `query_with_audit` 扩展为 search/list/get/citation/context_pack 五种 operation。任务/会话内部 subject 由活动 assignment/session 注入；UI RPC 使用 `view_as_employee_id`，服务端 actor 固定为 LocalOwner，并在日志同时记录 operator/subject。客户端不能传 actor。
- 实现 `kg.source.delete`：先用 `(company_id,source_type,source_id)` 锁定唯一 source；soft 模式同事务标记 source/documents，把该 source 的 citations 幂等更新为 `source_deleted`，并移除索引；hard 模式只级联该 source 的原始正文/文件、documents/chunks/vectors 与 knowledge_citations 内部关联。reports/review_findings/fix_items/artifacts、领域事件与审计不删除，只保留不含正文的 id/hash/不可用状态；两种模式均写治理审计并由 reconciler 收敛。
- `kg.knowledge.reject/confirm` 均为 LocalOwner 治理命令；confirm 设置 `governance_confirmed`，两者写 knowledge governance audit，不伪装成 AI employee 领导操作。
- 实现 `kg.ingest.retry`：只允许对 `retryable`/`failed` job 创建新 attempt，保留旧 attempt 与错误，使用 job id + attempt 作为幂等边界，并写 `knowledge_governance_audit`。

**测试**：
- 列表分页、单条详情和引用均覆盖成功与越权拒绝，且访问日志与最终返回 ids 一致。
- soft/hard 删除后的 SQLite、LanceDB、citation 状态符合保留矩阵；重复删除幂等，备份仍可能含历史数据的披露不被绕过。
- 伪造 actor、缺 view-as、跨公司 view-as、已归档 subject 和直接调用 compute_scope 绕过 query wrapper 均拒绝；confirm 审计 operator 为 LocalOwner。
- ingest retry 对运行中/不可重试 job 拒绝；重复请求不创建重复 attempt。

**DoD**：`kg.document.list/get`、`kg.citation.get`、`kg.source.delete`、`kg.knowledge.reject/confirm`、`kg.ingest.retry` 均有后端 handler、权限检查和成功/失败契约测试。

### P8-T5：SQLite / LanceDB 双写一致性对账
**文件**：`sidecar/acos/knowledge/reconciler.py`

**实现要点**（对照 §9.5——**知识元数据（SQLite）与向量（LanceDB）是两个独立存储，写入不是原子的，需要后台对账兜底**）：
- 后台对账 Worker 定期比对 SQLite `knowledge_chunks` 的期望状态与 LanceDB 实际内容：SQLite 有记录但 LanceDB 缺向量 → 重新嵌入补齐；LanceDB 有向量但 SQLite 无对应记录（孤儿）→ 删除。
- 覆盖场景：知识删除、拒绝、`reindex` 中途崩溃。
- 实现 CompanyDissolutionStarted 的 Knowledge consumer：停止新 ingestion/reindex，把 documents/index generation 置只读并上报 watermark，重放幂等。

**测试**：`sidecar/tests/knowledge/test_reconciler.py`
- 模拟"SQLite 写成功、LanceDB 写失败"场景，验证对账 Worker 能检测并补齐向量。
- 模拟"reindex 中途崩溃留下孤儿向量"场景，验证对账 Worker 能清理。

**DoD**：双写不一致场景都有对账测试覆盖，不依赖"人工发现后手动修复"。

### 阶段验收（Phase 8）
对应 §19 第 1、2、3、4、5、6、7、8、16 条。这是继权限引擎、Handoff 之后第三个安全测试密集阶段，且是全项目唯一要求"真实数据库集成测试而非纯 mock"的检索安全测试。

---

## Phase 9：任务工作流引擎

**目标**：落地任务创建、Manager Plan 校验、按 Workspace 与 Backend lease 并行执行、并行审查、合并修复、成本分层降级、Checkpoint 恢复——**全项目最复杂的阶段**，依赖 Phase 5（Capability Engine）、Phase 6（Runtime/Provider/Backend）、Phase 7（会话线程）、**Phase 10 的审批基础设施必须先于本阶段的 P9-T5 就位**。建议投入最多人力，任务之间尽量按子模块分给不同人并行。

### P9-T1：Task / Subtask（task_node）数据模型
**文件**：
- `sidecar/acos/task/models.py`
- `sidecar/migrations/0014_tasks.sql`

**实现要点**（对照 §10.2、§10.1.3、§15）：
- `tasks` 保存 `active_generation_id` 与可选 `backend_id`，不覆盖旧 plan hash；状态机与 manager_scope/department CHECK 对照设计方案 §10.2。显式 Backend 必须同公司，未传时执行阶段解析公司默认。
- `tasks` 的成本预算字段为 `budget_currency/budget_limit_micros/token_limit?`；金额使用 int64 micros 并校验 ISO-4217、非负与溢出，禁止使用 float 或无币种 `budget_limit`。
- `task_node` 字段包含 `generation_id/backend_id?`，旧 generation 节点永久保留但不再调度。`manual_task` 是节点类型，`waiting_approval` 是状态，两者不得混用；Backend 排队顺序/原因只在 P6-T1c 的 queue entry，节点仅投影 ready 状态。
- `depends_on` 存为 JSON 数组（不建独立的 `task_dependencies` 表，避免依赖关系被两处数据结构重复表达）。
- 证据链字段（对照 §10.1.3）：`reports`/`review_findings`/`fix_items`/`artifacts` 各表统一带 `source_node_id, run_id, employee_id, capability_snapshot_checksum, artifact_hash, trace_id`，本任务建表时一并加上这些列，不要等后续任务补。
- 四类证据对象字段与状态逐项按设计方案 §10.1.3：artifact `available→unavailable|deleted`，report `draft→final`，finding `open→accepted|rejected` 且 `accepted→resolved`，fix item `pending→running→fixed|failed|wont_fix`。`review_findings` 另带 `review_node_id/reviewer_employee_id/lens/finding_fingerprint/severity(critical|major|minor)`；每个 lens 是独立 review_task node，不能让多个 Reviewer 争用同一 `(node,generation,reviewer)` assignment 或覆盖同一 finding 行。有未收敛 critical/major 项时不得创建 final report 或把任务置 completed。
- `tool_calls` 按设计方案 §10.1.3 建可恢复状态、request_hash、approval_id、authorization_audit_id、side_effect_state/result_ref/version；`workspace_changes` 建 append-only change_type/path hash/before-after hash/artifact/tool_call 关联。Runtime 在执行前写 tool call 并 CAS 状态，Workspace 在 manifest/diff 确认后写 change；conversation_events 只承载可观察顺序，acl_audit_log 仍是鉴权事实，三者不得互相替代。
- `task_node.status` 包含 `cancelled`；未启动节点可在 `task.cancel` 时进入该终态，已 completed/failed/dead_letter 的节点保留原终态。

**测试**：`sidecar/tests/task/test_models.py`
- 非法状态转换测试（如 `completed → executing`）。
- `depends_on` 引用不存在的 `node_id` 应在创建时校验失败。
- 证据链字段完整性：创建 `review_findings` 记录时缺 `capability_snapshot_checksum` 应报错。
- 四类证据状态的每条合法转换与跨级/逆向转换均覆盖；只有 accepted finding 可建 fix item，`wont_fix` 缺 Manager resolution 被拒，未收敛 critical/major 项阻断 final report/completed。
- 任务取消时 evidence 级联：running 的 fix_item 终止为 `wont_fix`，pending 的 fix_item 终止为 `cancelled`，draft 的 report 保留 `draft`（不自动变为 final），open/accepted 的 finding 保持不变；验证非法转换（如 cancelled 节点的 finding 从 `open` 转 `resolved`、fix_item 从 `wont_fix` 转 `fixed`）被拒绝。
- `manager_scope=dept` 但 `department_id` 为空、或 `manager_scope=company` 但 `department_id` 非空，均应被 CHECK 约束拒绝。
- task/node 的 backend_id 跨公司被拒；ready 节点关联的活动 backend queue entry 必须同 company/run，终态节点不得仍有 waiting entry。

**DoD**：`task.create` / `task.get` / `task.list`（附录 B.3）可用；模型允许 `cancelling→cancelled`，协调器与 `task.cancel` 在 P9-T10 完成。

### P9-T1a：task_assignments（任务参与关系表）
**文件**：
- `sidecar/acos/task/models.py`（新增 `TaskAssignment`）
- `sidecar/migrations/0014b_task_assignments.sql`

**实现要点**（对照 §10.2.1——**本任务是 P4-T3 `visible_task_ids` 的数据来源，必须在 Phase 9 尽早完成，供权限引擎的集成测试尽快从 mock 换成真实数据**）：
- 字段：`assignment_id, company_id, task_id, node_id, employee_id, assignment_role(worker|reviewer|fixer), generation_id(FK), run_id?, attempt, department_id_at_assignment, granted_by, reason, status, active_from, active_until, version`；数字 `generation` 只用于展示，跨表引用统一使用 UUID `generation_id`。Manager 使用 tasks.manager_employee_id/manager_scope 与管理范围授权，不创建 node_id 为空的伪 assignment。
- `(node_id, generation_id, assignment_role)` 至多一条 active；关闭按 assignment/node/generation CAS 精确执行。最后一条活动 assignment 关闭后才收回参与者权限。
- 提供 `TaskAssignmentRepository.list_active_task_ids(employee_id) -> [task_id]`，供 P4-T3 的 `compute_scope` 调用替换掉之前的空实现。
- 提供 `TaskRepository.list_by_managed_department_ids(ids)` 与 `list_company_scope_tasks_for_root_leader`；禁止使用普通职员的 visible_department_ids 放行任务。

**测试**：`sidecar/tests/task/test_task_assignments.py`
- 分配创建 `active` 记录；节点到终态后自动置 `closed`；换人后旧记录 `closed`、新记录 `active`。
- `list_active_task_ids` 只返回 `active` 记录对应的 task_id，不包含 `closed`。
- `list_by_managed_department_ids` 与 `list_company_scope_tasks_for_root_leader` 分别返回正确结果。
- 与 P4-T3 联调：把 P4-T3 里 mock 的 repository 换成本任务的真实实现重跑一遍 P4-T3 的核心断言，确认结果一致。
- 同一职员多节点、部分完成、retry、replan、Reviewer/Fixer 重派和 transfer drain 均只影响目标 assignment。
- Manager 在尚未生成节点时即可规划并通过管理范围看到任务，但 task_assignments 中不存在空 node_id 或 manager role。

**DoD**：`task_assignments` 数据模型与三个查询接口就位，且已替换 P4-T3 的空实现并通过联调测试。

### P9-T1b：工作流恢复事实表与 Repository

**文件**：`sidecar/acos/task/run_store.py`、`sidecar/migrations/0014c_workflow_runtime.sql`、`sidecar/tests/task/test_run_store.py`

**实现要点**：建立 `plan_generations/task_runs/checkpoints/usage_reservations/usage_records/approvals/dead_letters`，字段、外键、状态、CAS、唯一键和 company 索引严格对照设计方案 §10.2.2/§10.6/§12.2/§15；复用 P1-T7 的 `human_interventions` 和 P4-T5 的 `employee_drain_items`，禁止在本迁移重复建表。task run 固化 assignment、generation、attempt、capability checksum、pricing version、backend_id/backend_lease_id 与 side_effect_state，并只允许 `created→waiting_backend→running↔waiting_approval→succeeded|failed|cancelled`；usage reservation 只允许 `held→settled|released|violated`。创建 run 时通过 P6-T1c port 校验 lease 的 run_id/company 一致，不能把 session turn lease 绑定到 task run。接入跨领域 intervention repository 与真实 TaskAssignment adapter，重跑 P4 drain contract tests。

**测试**：覆盖跨 company/task 外键、attempt 单调递增、唯一 active generation、重复 intervention/resolve、reservation/run 绑定、task run 每条合法/非法迁移、reservation 的三个互斥终态与重复结算 CAS、unknown side effect 禁止自动 retry；强杀并重新打开数据库后所有恢复事实仍可查询。

**DoD**：P9-T3—T11 的恢复决策全部来自持久化事实，不依赖进程内对象或临时 JSON。

### P9-T2：任务创建两入口
**文件**：`sidecar/acos/task/service.py`（`create_task`）

**实现要点**（对照 §10.1 步骤 1）：
- 入口 a（直达部门）：`manager_scope=dept`，Manager 为该部门负责人，作用域限定本部门及下级。
- 入口 b（经公司负责人）：`manager_scope=company`，Manager 为公司负责人，可能拆分下发给多个部门负责人（子 DAG 节点归属不同部门）。
- 两条入口最终都产出同一 `tasks` 记录，只是 `manager_employee_id`/`manager_scope` 不同。
- 创建时校验公司状态必须为 `active`；`initializing` 状态的公司不能创建任务。
- 未传 budget 时原子复制 company 的 `default_budget_policy`；显式 budget 必须是 `{currency,limit_micros,token_limit?}`，币种必须能在所选硬预算 Provider 的价格目录解析，负数、溢出和无币种输入拒绝。
- 可选 backend_id 必须属于本公司且 `enabled+fresh healthy`；不传时由 P6-T1c 解析公司默认。当前没有可调度 Backend 时 `task.create` fail-closed 返回可操作的 Backend 配置提示；成功创建后在 task/node/run 逐级固化实际选择，运行前仍重验并 acquire lease。
- 调用 P2-T2 的组织状态校验；目标部门和 manager 所属部门必须 active，frozen/archived 拒绝。
- 创建时发 `TaskCreated` 事件。

**测试**：`sidecar/tests/task/test_create_task.py`
- 两种入口分别创建任务，验证 `manager_employee_id` 正确指向部门/公司负责人。
- `manager_scope=dept` 时若目标部门无负责人应报错。
- `company.status=initializing` 时创建任务应报错，并作为普通必过测试执行。
- 默认预算复制后不随公司设置变化；显式预算的币种、int64 边界和 token_limit 均有正负向测试。
- 显式跨公司/archived/draining/stale Backend 被拒；无健康默认 Backend 时创建失败且不留下半成品 task，配置恢复后重试可由 RPC 幂等键得到唯一任务。

**DoD**：两入口均可用且行为符合 §10.1 描述。

### P9-T3：Manager Plan（DAG 生成）
**文件**：`sidecar/acos/task/planner.py`

**实现要点**（对照 §10.1 步骤 2，**本任务调用 Agent 完成实际的计划生成，是"AI 生成 DAG"而非人写 DSL**）：
- 通过 Manager 职员（用 Phase 5 的 Capability Engine 装配 Manager 的运行配置，Phase 6 的 Runtime 执行一次对话）产出子任务 DAG（结构对照 P9-T1 的 `task_node`）、职员分配、Workspace 策略分配（见 P9-T5）、验收方式。
- 规划规则：优先让无依赖节点落到不同职员；同一职员多节点须标记隐式串行。
- Manager 模型输出不接受任意 backend_id；Planner 在解析后调用 P6-T1c，根据 task 显式 Backend（若有）否则公司默认为 agent/review/fix/merge 节点服务端填充 backend_id，并把 Backend requirements/选择纳入 plan_hash；manual/condition 保持 NULL，避免提示注入选择跨公司执行资源。
- 每次规划新增 `plan_generations` 并计算 plan_hash；初始为 draft，旧代在 replan 后标 superseded，只有通过校验/审批的新代才能 CAS 成为 tasks.active_generation_id。
- **本任务只产出 Plan，不落 Checkpoint、不进入执行**——校验（P9-T4）通过后才落首个 Checkpoint；"生成→校验→执行"三步必须严格分离，不允许未校验的 Plan 提前进入执行状态。

**测试**：`sidecar/tests/task/test_planner.py`
- Mock Manager 的模型输出为一个固定 DAG 结构，验证 Planner 能正确解析并写入 `task_node` 记录。
- 验证"同一职员多节点标记隐式串行"规则。
- 模型输出伪造 backend_id 被 schema 拒绝；相同 task/default/requirements 服务端填充相同 backend_id，默认 Backend 改变后新 generation 得到新 plan_hash，旧 generation 不漂移。
- `plan_hash` 对相同 DAG 结构的两次计算结果一致（确定性）。

**DoD**：Plan 生成、`plan_hash` 均可用并测试覆盖；Plan 此时状态应为"待校验"，不是"可执行"。

### P9-T4：PlanValidator（Plan 校验，执行前必经关卡）
**文件**：`sidecar/acos/task/plan_validator.py`

**实现要点**（对照 §10.1.1——**Manager 的输出是不可信的模型生成内容，必须校验后才能执行，这是任务进入调度前的强制关卡**）：
```text
PV-01 JSON Schema 结构校验（字段完整、类型正确）
PV-02 环检测（DAG 必须无环，复用图算法）
PV-03 规模上限（最大节点数、最大深度，公司策略可配置默认值）
PV-04 部门边界校验：每个节点的 assignee 必须落在 Manager 的 manager_scope 允许范围内
      （调用 Phase 4 的 permission_engine 判断）
PV-05 职员状态校验：assignee 必须是 active 状态
PV-06 Reviewer 独立性校验：Review 节点不能把原 Worker 指定为 Reviewer
PV-07 Workspace 合法性校验：分配的 Workspace 策略与该节点的任务性质匹配（P9-T5）
PV-08 预算可行性粗估：按节点数与各自档位的同币种粗略成本估算是否明显超出 budget_limit_micros
PV-09 Tool Binding 校验：节点引用的工具必须确实存在于该 assignee 能力快照的 skill_set 里
PV-10 输出 schema 校验：每个节点声明了 outputs_schema
PV-11 硬预算 Provider 校验：要求硬预算的节点只能使用
      billing_mode=metered AND enforces_output_cap=true、有有效价格版本且未冻结的 Provider
PV-12 组织状态校验：任务、Manager、assignee 所属部门必须 active；frozen/archived 部门不得
      创建、接收、重派或 replan 节点；管理范围内无关冻结部门不连带阻断其他部门
PV-13 Backend 可调度性校验：agent/review/fix/merge 节点的显式 backend_id 或公司默认 Backend 必须同公司、enabled、
      fresh healthy，并支持节点 Workspace/capabilities/security_level；执行前仍须再次校验并排队取得 lease；
      manual/condition 必须 backend_id=NULL 且不得创建 Backend queue/lease
```
PV-03 默认 `max_nodes=50/max_depth=8`，公司可配范围分别为 1..200/1..16，等于上限允许；计数含全部节点类型，深度按最长依赖路径节点数。PV-10 只接受设计方案 §10.2 的 manual task JSON Schema 受限子集，不支持的 `$ref/组合/递归` 直接拒绝。
任一步失败抛结构化错误。高风险计划创建 `approval_type=plan_approval`，绑定 `generation_id/plan_hash/risk_summary`；批准前保持 planning，拒绝/过期转人工。`manual_task` 不得用于计划审批。

**测试**：`sidecar/tests/task/test_plan_validator.py`（`PV-01..PV-13` 按规则 ID 参数化，缺一不可）
- 构造成环的 DAG，断言 `WF-PLAN-CYCLE`。
- 构造节点 assignee 越出 manager_scope 边界的场景，断言拒绝。
- 构造 Reviewer=原 Worker 的场景，断言拒绝。
- 构造引用了 assignee 能力快照里不存在的工具的场景，断言拒绝。
- 构造硬预算节点却分配了不满足 `billing_mode=metered AND enforces_output_cap=true` 的 Provider 的场景，断言拒绝。
- frozen/archived 部门、未知/过期价格与公司级 Provider freeze 均拒绝；旧 generation 的 plan approval 在 replan 后 stale。
- 跨公司、无默认、disabled/draining、健康 stale/degraded/unavailable、Workspace/capability 不兼容的 Backend 均按 PV-13 拒绝；验证通过后若健康/状态在 acquire 前变化，P6-T1c 仍 fail-closed。
- manual/condition 携带 backend_id 或产生 queue/lease 时拒绝；agent/review/fix/merge 缺少可解析 Backend 时拒绝。
- 全部通过的正常 Plan，验证放行且落首个 Checkpoint。
- PV-03 覆盖默认值、等于/超过边界和非法公司配置；PV-10 对每个支持控件与禁止关键字各有正负向用例。

**DoD**：`PV-01..PV-13` 与 plan approval 均有独立测试；只有唯一 active generation 能进入 P9-T5。

### P9-T5：Worker Execute（按 Workspace 策略并行执行）
**文件**：
- `sidecar/acos/task/scheduler.py`
- `sidecar/acos/task/workspace_strategy.py`（Workspace 类型选择）
- `sidecar/acos/runtime/workspace.py`（`LocalWorkspace`/`TaskWorkspace`/`GitWorktreeWorkspace`/`ReadOnlyWorkspace`/`RestrictedWorkspace`）

**实现要点**（对照 §10.1 步骤 3、§10.1.2、§11.3、§4.6——**不强制所有节点都用 Git Worktree，按任务性质选择 Workspace 类型**）：
- `workspace_strategy.py`：代码类任务 → `GitWorktreeWorkspace`；通用文件/产出类 → `TaskWorkspace`（隔离目录 + artifact manifest）；只读研究类 → `ReadOnlyWorkspace`。Manager Plan（P9-T3）分配的策略经 PlanValidator（P9-T4）校验后，本任务据此实例化对应 Workspace。
- 需要受控写白名单的任务可显式选择 `RestrictedWorkspace`：Backend 能力仍为 `agent_runtime+filesystem_io`，每次操作同时强制 `ResolvedRunConfig.workspace.allowed_paths` 与 `security_policy.effective_allowed_commands`；`LocalWorkspace` 只允许 LocalOwner 明确选择，自动 Plan 不得默认使用。
- Scheduler 按 DAG 依赖关系推进：无依赖且未执行的节点进入 `ready` 队列；调度时检查目标职员/线程是否忙（Phase 7 的锁），忙则该子任务留在 `ready` 排队或（若规划允许）改派其他职员。
- 分派前重验 company/department/employee active，创建精确 assignment 与 task_run；task run 固化 P6-T1c 返回的 backend_id/lease_id，Runtime 启动后绑定 Supervisor process token；会话 turn 使用数据库 CAS，进程内锁仅作优化。
- employee 有 open drain 时不得创建新 assignment/run/Provider 调用；只有 drain 已登记的既有 run 可凭服务端 drain token 收敛到安全 checkpoint/当前调用终点，随后释放 active_turn_id 并 ACK，禁止把 suspended 当作普通 active 继续调度。
- 每个节点执行前经 Phase 3-T4 的 Tool Binding 四步校验链（此时四步校验的 Workspace 校验子步骤要接上真实实现，ACL 校验接 Phase 4，Runtime Policy 校验接 **Phase 10 的真实审批流程——这是为什么 Phase 10 必须提前于本任务**）。
- 并发上限遵循 Phase 0/1 已定的全局子进程池；每个节点在启动 Runtime 前还必须用 P6-T1c selector 幂等 enqueue，由 `acquire_next` 按全局 `(queued_at,queue_id)` FIFO 原子取得 lease。满载/不健康时节点保持 ready，原因和顺序来自 queue entry；任何路径完成/取消/失败都在安全边界更新队列/lease，禁止维护第二套内存并发计数。
- 每个 `task_node` 使用 P9-T1 已分配的 `idempotency_key`，执行完毕落 Checkpoint（Worker 完成边界）。

**测试**：`sidecar/tests/task/test_scheduler.py`（**并行性是本任务的核心验证点**）
- 构造一个有 3 个互相无依赖节点的 DAG，分配给 3 个不同职员，验证调度器确实并发拉起了 3 个执行。
- 构造一个节点的目标会话线程正忙的场景，验证该节点进入等待而不是强行并发发消息给同一线程。
- 每个 Worker 确实运行在其分配到的 Workspace 类型下（Git 类任务在独立 Worktree、非 Git 类任务在隔离目录、只读类任务无写入副作用）。
- 高风险工具调用触发真实审批流程（联调 Phase 10-T1），验证节点进入 `waiting_approval` 且不阻塞其他并行节点。
- `concurrency_limit=2` 下 3 个可运行节点只启动 2 个，释放后第三个按 FIFO 启动；跨公司 Backend、draining/stale Backend 和 Plan 校验后发生状态变化均不能取得 lease。

**DoD**：对应 §19 第 10、12、25 条（并行确实发生，Worker 只获得职责范围内知识和权限，Workspace 策略按任务性质选择而非硬编码 Git，所有执行均受持久化 Backend lease 约束）。

### P9-T6：Parallel Multi-Lens Review
**文件**：`sidecar/acos/task/strategies/parallel_review.py`

**实现要点**（对照 §10.1 步骤 4、§10.3）：
- `CollaborationStrategy` 接口 + 首版唯一实现 `ParallelReviewStrategy`：N 个 Reviewer 同一轮并发审查同一批产物，每人固定一个维度（correctness/security/test coverage/规范一致性）。
- 策略为每个 lens 创建独立 `review_task` node 与 reviewer assignment，Merge 节点依赖当前 review 批次的全部 review nodes；同一节点只有一个 active reviewer assignment，与 P9-T1a 唯一约束一致。
- 结果直接取并集，不做加权仲裁。
- **约束**：Reviewer 不能是该产物的原始 Worker（PlanValidator 在 P9-T4 已做静态校验，本任务在实际分派时也要有运行时兜底校验，防止 Plan 校验通过后运行时状态变化导致的边界情况）。

**测试**：`sidecar/tests/task/test_parallel_review.py`
- 验证 N 个 Reviewer 确实并发执行。
- 验证 N 个 lens 对应 N 个 node/assignment，任一 lens 失败可单独重试且不会覆盖其他 finding；Merge 必须等全部 lens 终态。
- 验证 Reviewer 分配排除了原始 Worker。
- 验证结果聚合是并集而非加权平均/投票。

**DoD**：对应 §10.3 的可插拔接口设计（本阶段只需 `ParallelReviewStrategy` 一个实现，接口要允许后续接入 `DebateStrategy` 而不改动调用方代码）。

### P9-T7：Merge & Fix（按 Workspace 类型分派合并策略，含 Git 安全规则）
**文件**：`sidecar/acos/task/merge.py`

**实现要点**（对照 §10.1 步骤 5、§10.4——**Git 类任务的合并必须遵守一组安全规则，绝不能触碰用户已有工作区**）：
- **Git 类任务**：
  - 创建 Worktree 前先记录不可变的基线 commit 引用，用 `git worktree add` 从该 commit/分支派生，**绝不对用户主工作目录执行 `git reset --hard`/`git checkout -- .`**；若目标仓库存在未提交改动导致无法安全创建 Worktree，视为设置失败转人工，不强行绕过。
  - 分支命名约定：`acos/task/<task_id>/<node_id>`。
  - 机械合并（无重叠改动）由 `MergeStrategy` 的 `GitMergeStrategy` 实现直接调用 Git 命令，不经过任何 Agent/LLM 调用；Workflow Engine 只调用策略接口，不在编排器里旁路 Workspace 类型分派。
  - 冲突分类：`Resource Conflict`（同文件重叠）→ 交 Manager 生成合并计划；`Decision Conflict`（Reviewer 结论互斥）→ 交 Manager 裁决；`Version Conflict`（基线漂移）→ 重新 rebase 或重做该子任务。
  - 机械合并只写本任务创建的 integration 分支，绝不更新用户目标分支、用户工作树或远端。最终固定生成 `GitDeliveryArtifact{repository_fingerprint,baseline_commit,integration_commit,diff_sha256,patch_path,bundle_path}`，patch 与 bundle 均为必需产物并纳入 artifact manifest；LocalOwner 在应用外自行检查和应用。任务 completed 只表示 integration 分支/交付物完成，不表示用户仓库已合并。
  - 清理只删除本任务创建的 Worktree 与临时分支，不触碰用户原有工作区；清理失败要记录，不静默忽略。
- **通用文件/产出类任务**：无 Git 语义，合并 = 比对各节点 artifact manifest，无重叠直接合并产出目录，有重叠交 Manager 裁决。
- **只读研究类任务**：无产出文件，不需要合并步骤。
- Fix item 按依赖关系分组，无依赖的并行分给多个 Worker，有依赖的按 DAG 顺序处理；最多 N 轮（默认 2，可配置），超出转 `dead_letter`。
- 高风险的外部副作用步骤记录可选 `compensation_hint` 字段，供转人工时展示——**不实现自动补偿引擎**。

**测试**：`sidecar/tests/task/test_merge.py`
- 无重叠文件改动场景：验证合并全程没有调用任何 Agent/Provider（mock 断言零次模型调用）。
- 构造真实文件重叠冲突场景，验证正确识别为 `Resource Conflict` 并生成合并计划交给 Manager。
- **安全规则测试**：构造用户主工作目录有未提交改动的场景，验证系统拒绝创建 Worktree（转人工），且用户的未提交改动分毫未变（直接读取工作目录内容比对）。
- 验证机械合并只更新任务 integration 分支，用户目标分支、工作树和远端 ref 全部不变；交付 artifact 的 baseline/integration/diff hash 可复算，patch 可在基线副本干净应用。
- 验证清理阶段只删除任务创建的 Worktree/分支，用户原有分支/文件不受影响。
- Fix 轮次超过配置上限后，验证任务/节点状态变为 `dead_letter` 并触发 `TaskEscalatedToHuman`。
- 通用文件类任务的合并测试：验证走 artifact manifest 比对，不调用任何 Git 命令。

**DoD**：对应 §10.4 全部规则；"不触碰用户已有工作区"与"机械合并零 Agent 调用"两条必须有测试断言支撑，不能只靠代码 review 保证。

### P9-T8：Checkpoint 与幂等恢复
**文件**：`sidecar/acos/task/checkpoint.py`（表由 P9-T1b 创建）

**实现要点**（对照 §10.5）：
- Checkpoint 结构与设计方案 §10.5 完全一致：`checkpoint_id, company_id, task_id, task_cursor, plan_hash, context_hash, generation_id, run_id?, event_offset, executor_state, checksum, created_at`；company_id/task_id/generation_id 建同租户 FK，checksum 覆盖除自身外的全部不可变内容。
- 落点：PlanValidator 通过后 / 每个 Worker 完成 / Review 完成 / 每轮 Fix 完成。
- 只恢复 tasks.active_generation_id 对应 checkpoint；校验 generation/plan hash/run side_effect_state。committed 跳过，unknown 进入 intervention，禁止猜测重跑。
- 实现 `workflow.checkpoint.list(task_id,page)`，按 `(created_at DESC,checkpoint_id DESC)` 返回设计方案 B.0 的 `Page<CheckpointSummary>`，概要含 checkpoint/company/task/cursor/generation/run/hash/event_offset/checksum/created_at，但不暴露可被客户端篡改的 executor_state；读取时校验 task company scope。

**测试**：`sidecar/tests/task/test_checkpoint_recovery.py`（**恢复测试是发布前必测项，见 Phase 13**）
- 模拟任务执行到"3 个 Worker 完成、Review 进行中"时进程被杀，重启后从最近 Checkpoint 恢复，验证已完成的 3 个 Worker 节点不会被重新执行。
- `checksum` 被篡改时，恢复应报错而不是"带病"继续跑。
- 恢复后预算/成本统计数值与"假设从未崩溃"的场景一致。
- 恢复时联合核对 checkpoint/run/backend lease：completed run 的 held lease 被幂等释放；active run 可安全续跑才 heartbeat；unknown side effect 转 intervention 且不因 lease 过期自动创建新 attempt。
- `workflow.checkpoint.list` 只返回目标任务的 checkpoint，跨公司 task_id 被拒绝。

**DoD**：对应 §19 第 9、10、21 条；此测试文件是 Phase 13 恢复测试套件的核心组成部分。

### P9-T9：成本分层与稳定性降级链（预算预留—结算模式）
**文件**：`sidecar/acos/task/cost_policy.py`、`sidecar/acos/governance/budget.py`（表由 P9-T1b 创建）

**实现要点**（对照 §10.6——**预算不能等 `collectUsage` 真实用量出来才检查，必须在分派前原子预留**）：
- 角色→档位默认映射：Worker 默认 `free`，负责人默认 `premium`，中等执行按需 `standard`。
- 稳定性曲线（1–10 五段行为，严格照抄 §10.6 表格）：
  - 1–3：0 次重试，直接判失败上报 Manager。
  - 4–6（默认 5）：同档重试 1 次，再失败升级 Manager 决策。
  - 7–9：同档 1 次 + 升 1 档重试 1 次，仍失败转人工。
  - 10：同上 + 升至最高可用档 + 执行后强制自检一轮，失败立即人工兜底。
- 统一降级链：同档重试 → 升配一档 → 改派本部门其他职员 → 升级本部门负责人 → 转人工。**链条严格约束在发起子任务的部门内部**，最高只到本部门负责人。
- 调 P6-T1a `resolve_price`，用 int64 micros 整数算法向上取整最坏成本，原子写 usage reservation 并固化 pricing_version/currency/run；未知、过期、币种冲突或溢出 fail-closed。调用完成写设计方案 §12.1 的 append-only usage record（含 token/tool 计数与 actual_amount_micros）并 CAS 结算，历史账单只用固化版本复算，禁止浮点累计误差。
- **结算**：调用结束后按 `collectUsage` 真实用量结算，多预留的释放回余额。若出现 `settled > reserved`（Provider 计价或输出上限执行异常，不是正常路径），立即冻结该 Provider 在当前公司后续的硬预算调用（`PROV-BOUNDED-COST-VIOLATION`）、写高优先级告警与审计，不得静默记为"正常超额"。
- `require_approval` 触顶时不创建超额 reservation；同事务对 `(task_id,currency)` 建立由 pending approval 表示的 budget revision lock，绑定 task/run/currency/current_limit_micros/requested_limit_micros/requested_delta_micros/usage watermark/hash。同任务同币种的新 reservation 在 pending 期间返回 `WF-BUDGET-APPROVAL-PENDING`。批准时重读同币种 settled+held 并按 watermark/budget version CAS 修改 limit、释放 lock；调用方随后重新执行正常 reservation，不能复用批准时计算。拒绝/过期/stale 释放 lock，重启从 pending approval 恢复锁定。
- Worker 自动升配天花板：`cost_policy.worker_upgrade_ceiling` 限制普通职员的自动升配上限。

**测试**：`sidecar/tests/task/test_cost_policy.py`（**每一档、每一条约束都要有独立测试**）
- 对 `stability_level=1,5,7,10` 各构造一次失败场景，逐一断言其重试/升配/自检行为与表格完全一致。
- **预留—结算测试**：分派前预留成功后立即消耗掉预算，验证第二次分派因预留失败而不会真的发起模型调用（不是"调用了才发现超支"）。
- 结算测试：调用结束后按真实用量释放多预留部分；构造最大输入/输出、工具调用费、整数取整边界和价格版本切换场景，证明正常路径下 `settled_micros <= reserved_micros` 且 `settled_total_micros <= budget_limit_micros` 恒成立，不存在“少预留后正常补扣”的路径。
- 异常路径测试：mock 一次 `collectUsage` 返回 `settled > reserved`，验证该 Provider 在当前公司被立即冻结、产生 `PROV-BOUNDED-COST-VIOLATION` 告警与审计记录，且不被静默放行。
- 验证降级链在"改派本部门其他职员"这一步，绝不会选中平级部门或上级部门的职员。
- 验证预算触顶时，即使 `stability_level=10` 仍立即停止升配转人工。
- 验证 Worker 升配不超过 `worker_upgrade_ceiling`。
- 价格切换后旧 run 可复算；未知/过期/币种冲突不发调用；budget approval 在用量变化、重复 resolve、重启和过期场景正确收敛。
- budget approval 前不产生 reservation；pending 期间同任务同币种并发分派全部被挡住，其他任务不受影响；批准后再预留仍可能因并发/价格变化失败并重新触顶，拒绝/过期/重启均不遗留永久 lock。

**DoD**：对应 §19 第 15、18 条。预留—结算模式必须有测试证明"预算检查发生在调用之前，不是之后才发现超支"。

### P9-T10：任务级并发调度整合
**文件**：`sidecar/acos/task/scheduler.py`、`sidecar/acos/task/retry_service.py`、`sidecar/acos/task/cancellation.py`、`sidecar/acos/task/service.py`（整合 P9-T4 至 P9-T9）

**实现要点**：串联运行态重验 → Backend enqueue/acquire → Runtime → 每次调用前预算 reservation。retry 只接受 failed/dead_letter 并创建新 attempt。cancel 进入 cancelling 后，pending/ready/waiting_approval 节点转 cancelled；API Driver 中止 HTTP/SSE，CLI Driver 对匹配 start token 的进程先 SIGTERM、3 秒后 SIGKILL。只有确认停止并落 checkpoint/副作用状态后才把活动节点转 cancelled、释放 lease；无法确认或 unknown 转 intervention 且保持 cancelling。Report 提交与 `TaskCompleted`/Knowledge consumer delivery 同事务，P8 Worker 经 Outbox 异步提炼，Workflow 禁止直调 extractor/chunker。CompanyDissolutionStarted 复用同一安全收敛路径。

**测试**：`sidecar/tests/task/test_end_to_end.py`、`sidecar/tests/task/test_task_cancel_rpc.py`（**端到端集成测试，本阶段验收的关键交付物**）
- 用 3–4 个 FakeProviderAdapter 跑完整小任务；Report 后验证同事务存在 `TaskCompleted` 与 Knowledge delivery，并由真实 Outbox Worker间接触发 Phase 8 提炼。断言 Workflow 对 extractor/chunker 零直接调用，状态、事件、Checkpoint、证据链完整。
- 用同样的场景但让其中一个 Worker 故意失败，验证走完整降级链最终成功或正确转人工。
- 对 failed 节点重试生成新 run_id/attempt 且旧 run 仍可追溯；对副作用状态不明的节点拒绝重试；相同幂等请求不创建两个新 run。
- 在 cancel 的 run 停止、reservation 结算、assignment 关闭和 Git workspace 清理各点强杀，重启后幂等续跑；最终 TaskCancelled 唯一，unknown 副作用不被误报已取消。
- cancel 同时覆盖尚在 Backend queue 与已持 lease 两种 run：waiting entry 不会在取消后启动，held lease 只在进程确认终止后释放，重启无孤儿 queue/lease。
- `CompanyDissolutionStarted` 的 Task consumer 对 planning/waiting/running/waiting_approval/cancelling 各状态走同一安全取消路径；事件重放不重复取消或释放，unknown 副作用保持 intervention。只有目标公司全部任务达到安全终态才上报 Task watermark；在停止 Provider、结算 reservation、释放 lease、关闭 assignment 各点强杀后均可重启续跑，其他公司任务不受影响。

**DoD**：对应 §19 第 10、25 条的完整闭环验证（含知识固化）；`task.retrySubtask` 有安全重试与幂等证据，`task.cancel` 与 Task dissolution consumer 都有 queue/lease/usage/assignment 可恢复收敛证据。

### P9-T11：人工任务、Dead Letter 与 Employee Drain 处理命令

**文件**：`sidecar/acos/task/human_intervention.py`、`sidecar/tests/task/test_human_intervention.py`

**实现要点**：

- `workflow.manualTask.complete(node_id, output, comment?)` 仅允许 `manual_task + waiting_approval`；按 `outputs_schema` 校验 output，写 task evidence、事件与 Checkpoint，再推进依赖节点。
- manual task schema 只接受设计方案 §10.2 的受限 JSON Schema，并返回 UI field descriptors；artifact-ref 必须属于当前公司/task 且通过 path broker/authorize，禁止任意路径。
- `workflow.deadletter.resolve(...)`：reassign 精确替换 assignment；replan 新增 generation 并重新执行 `PV-01..PV-13`；abort 转终态。所有动作使用 P9-T1b 的持久化事实和 CAS。
- `workflow.employeeDrain.resolve(drain_id, action, node_id?, target_employee_id?, comment?)`：只接受 P4-T5 持久化的 drain 级唯一 `employee_drain` intervention；intervention version 做 CAS，`wait` 延长该 drain 的期限，`reassign` 精确要求一个仍 waiting 的 node/item 与目标职员，重跑部门/状态/能力/Workspace/预算校验后原子关闭旧 assignment、创建新 assignment。每次动作重算 allowed_actions；仍有 waiting item 时保持 open，全部 item 收敛后按 operation 完成 suspend/archive 或 transfer Handoff、写 resolution_ref，再关闭 intervention，且带幂等键、审计与事件。
- `workflow.humanIntervention.list` 的查询实现放在 P11-T2；本任务定义统一 DTO 与 allowed_actions/required_params，使 UI 不自行推断状态机。

**测试**：

- manual task 输出不符合 schema 时返回 `WF-OUTPUT-INVALID` 且状态不变；成功完成后证据链、事件、Checkpoint 完整。
- dead letter 的三种 action 分别覆盖成功与非法状态；reassign 越部门、目标职员非 active 或能力不匹配时拒绝；replan 未通过任一 PV 规则不得执行。
- Employee Drain 的 transfer/suspend/archive × wait/reassign 覆盖成功、非法状态与并发提交；reassign 后旧 assignment 关闭且对应后继动作能继续，失败时两条 assignment 均不发生部分更新。
- 同一 drain 多个阻塞 item 只能产生一条 open intervention；处理一项后仍有 waiting item 时不提前 resolved，最后一项与领域后继动作完成后才关闭。公司解散把剩余 item 置 aborted_by_dissolution 并幂等关闭同一 intervention。
- 重复提交相同 idempotency_key 不产生重复 assignment、plan generation、事件或 Checkpoint。

**DoD**：`workflow.manualTask.complete`、`workflow.deadletter.resolve` 与 `workflow.employeeDrain.resolve` 后端命令可用，且能被 P11-T2 的统一读模型安全驱动。

### 阶段验收（Phase 9）
对应 §19 第 9、10、12、15、18、21、25 条。阶段验收逐条执行 `PV-01..PV-13`、generation/run/assignment/backend lease、预算锁版、并行/Checkpoint、人工干预与 Git 安全规则测试。

---

## Phase 10：治理：预算、审批、安全

**目标**：把预算控制、高风险命令审批显式化。**依赖顺序说明**：P10-T1 审批基础设施必须在 Phase 9 的 P9-T5（Worker Execute 接入真实 Tool Binding 四步校验链）之前就位，不能等 Phase 9 收尾才做——实际依赖是 `Phase 3-T4（Tool Binding 骨架） + Phase 7-T5（会话线程状态机） + P9-T1/T1b（task/approval schema 与 repository） → P10-T1 → P9-T5`。因此 P9-T1/T1a/T1b 在第 12–13 周先行，P10-T1 紧接完成，再开放执行器开发。

### P10-T1：统一审批流转（工具调用 / 计划 / 预算）
**文件**：
- `sidecar/acos/governance/approvals.py`

**实现要点**（对照 §12.2；`approvals` 表由 P9-T1b 的 `0014c_workflow_runtime.sql` 创建，P10 可提前按同一 migration contract 开发）：
- `approvals` 统一字段含 company/task/node/run/`generation_id`、approval_type、target_hash/target_snapshot、risk_reason、expiry、resolution 与 version；三类审批分别绑定 tool call、plan `generation_id/plan_hash`、budget currency/current/requested/delta micros/usage watermark。
- Tool Binding 高风险时创建 tool_call approval 并局部阻塞节点；P9-T4 创建 plan approval 并阻塞整代进入执行；P9-T9 创建 budget approval 并只阻塞新增额度的调用。
- 发 `ApprovalRequested` 事件（推送 UI 走 `notify.approvalRequested`）；通知的 `risk_reason` 直接取持久化字段，`target_summary` 仅由服务端从 `target_snapshot` 脱敏派生，不接受客户端传值或回写。
- `approval.resolve` 对 pending/version 做 CAS，按类型重算 target hash 并重验当前状态；tool 重验 ACL/Workspace/Capability，plan 确认仍是同代，budget 重读 usage watermark。拒绝、过期、stale 均不可复活。

**测试**：`sidecar/tests/governance/test_approvals.py`
- 高风险命令触发审批后，验证只有该节点被阻塞，同任务的其他并行节点状态不受影响。
- 拒绝审批后验证走的是失败策略而不是让任务卡死。
- **TOCTOU 测试**：创建审批后，在批准前修改底层参数（模拟能力快照被升级或参数被篡改），批准时验证系统检测到 `tool_call_hash` 不一致并拒绝直接执行，要求重新走审批。
- 过期审批（超过 `expires_at`）不能再被 `resolveApproval`。
- plan 在审批期间 replan、budget 在审批期间用量变化、重复 resolve、应用重启和跨公司 approval id 均有负向测试。

**DoD**：`approval.list/resolve` 支持三类不可变 target，TOCTOU、stale、CAS 和恢复测试全绿。

### P10-T2：预算查询接口
**文件**：`sidecar/acos/governance/budget.py`

**实现要点**：`gov.budget.get(task_id)`（附录 B.6）返回 `{currency, limit_micros, reserved_micros, settled_micros, remaining_micros, token_limit?}`；`reserved` 只求和 held reservation，`settled` 只求和 usage_records.actual_amount_micros，`remaining=max(0,limit-reserved-settled)`，released 与 settled reservation 的原预留上界不重复计入。直接读取 Phase 9-T9 同一聚合函数，不重复实现预算判断逻辑，也不在读路径转换成浮点金额。

**测试**：`sidecar/tests/governance/test_budget.py`
- 验证返回值与 `usage_reservations/usage_records` 按 company/task 聚合一致，跨公司 task id 被拒绝。
- 混合 held/settled/released/violated 数据验证公式、币种过滤、下限钳制和无重复计数；读模型与实际 reservation 放行判断使用同一聚合结果。

**DoD**：`gov.budget.get` 可用。

### P10-T3：安全基线检查清单代码化
**文件**：`sidecar/acos/governance/security_checks.py`（一个静态检查脚本，非运行时模块）

**实现要点**（对照 §12.3，把设计方案里的安全规则转成可自动化检查的项）：
- 检查子进程调用（`providers/cli/*.py`）是否均用参数数组而非字符串拼接。
- 检查日志输出模块是否对已知敏感字段（API Key/密码模式）做了脱敏；专门验证 Phase 6-T2 的 Credential Broker 内部通道确实不出现在标准日志里。
- 检查前端代码（`apps/desktop/src/`）是否存在直接访问文件系统/网络的代码。
- 检查 `packages/rpc-schema` 里任何写方法的请求 DTO 不包含 `actor`/`operator`/`approved_by` 字段（复用 Phase 1-T6 的静态检查，纳入 CI 常规扫描）。

**测试**：本任务本身产出的是一组**扫描脚本**，作为 CI 里的一个检查步骤（`scripts/security_scan.py`）。

**DoD**：CI 流水线中新增一个安全扫描步骤，任何违反上述规则的新代码在 CI 阶段就能被拦截。

### 阶段验收（Phase 10）
对应 §19 第 8、15 条与 §12 全文；P10-T1 必须在 Phase 9-T5 开工前完成。

---

## Phase 11：可观测性与读模型

**目标**：结构化日志、统一读模型视图（含人工干预与存储配额视图）。依赖 Phase 1（事件）与 Phase 9（任务数据已产生）。

### P11-T1：结构化日志与 trace_id 贯穿
**文件**：`sidecar/acos/observability/logging.py`（Python 侧 structlog 配置）、`apps/desktop/src-tauri/src/logging.rs`（Rust 侧 tracing 配置）

**实现要点**（对照 §14、§16）：
- 统一 JSONL 输出格式，每条日志带 `trace_id`（复用 Phase 1-T3 中间件生成的 trace_id，贯穿一次请求的所有日志行）。
- 日志文件轮转与大小上限（避免无限增长）。
- 显式验证 Phase 6-T2 Credential Broker 通道的日志排除生效。

**测试**：`sidecar/tests/observability/test_logging.py`
- 一次跨多个模块调用的请求，验证所有产生的日志行都带同一个 `trace_id`。

**DoD**：任意一次 RPC 调用出问题时，能用一个 `trace_id` 在日志里串联出完整调用链。

### P11-T2：统一读模型视图
**文件**：`sidecar/acos/observability/views.py`（SQLite 视图或查询封装）、`sidecar/acos/store/quota.py`（`StorageQuotaService`）

**实现要点**（对照 §16）：
- `Runtime Status`：各会话线程/任务当前状态及 Backend lifecycle/health/held/limit/排队原因汇总查询。
- `Task Timeline`：某任务 DAG 推进、各子任务状态与耗时。
- `Event History`：`domain_events` 按 `task_id`/`employee_id`/`company_id` 过滤视图。
- `Audit Record` 八类稳定映射：acl→acl log；knowledge_access→access logs；knowledge_governance→governance audit；org→org audit；approval→approvals/events；budget→reservations/usage/budget approvals/provider freezes；capability_publish→CapabilityPublished events；backend→backend_change_audit/Backend 状态事件。所有事实表先按 company_id 过滤，不解析任意 payload。
- `HumanIntervention` 子类型为 approval/manual_task/dead_letter/employee_drain/company_dissolution/backend_recovery；每项返回服务端 allowed_actions/required_params。
- `StorageQuota` 的 company quota 只统计可唯一归属公司的数据；全应用备份只计一次。自动清理仅允许无引用且可重建的 cache/投影/临时 workspace。RetentionCompactor 用最小权限连接，只对超过 90 天的 allow 明细与 `audit_record_refs` 做 NOT EXISTS 反连接；引用边由 evidence/citation/checkpoint/incident 创建事务写入，不扫描 payload 猜测。压缩在同一事务内完成：先写不可变的日聚合统计行，再写 `audit_compaction_manifests(source_table, company_id, time_range, source_count, source_merkle_root, aggregate_ids, compacted_at)`，校验 source_count 与 merkle_root 后才物理删除对应源明细；幂等键为 `(log_type, company_id, date)`，重复执行不重复聚合。失败事务不删源明细。
- 均实现为 SQLite 视图或参数化查询函数，**不引入独立 CQRS 基础设施**。

**测试**：`sidecar/tests/observability/test_views.py`、`sidecar/tests/store/test_quota.py`
- 每个视图对已有测试数据能返回正确聚合结果。
- `gov.audit.query` 对八类审计分别覆盖查询与跨公司拒绝；knowledge access 结果能追溯到实际返回的 knowledge ids，知识删除/拒绝/确认/重试能追溯到治理操作人及前后快照；Backend 默认/配置/状态变化可追溯。
- `gov.audit.query` 严格接收设计方案 B.0 的 AuditFilters + page，返回 `Page<AuditRecordSummary>`；覆盖稳定排序、下一页、篡改/跨 filter 游标拒绝，禁止返回未分页数组。
- `HumanIntervention` 视图能正确汇总六种子类型且不重复不遗漏。
- `workflow.humanIntervention.list` 按 company/subtype/status 正确过滤，跨公司不可见；返回动作与 P9-T11 的状态机一致。
- 磁盘配额告警阈值触发测试；"是否允许创建新任务"判断函数在模拟磁盘不足时正确返回 false。
- 多公司全局备份总量只计算一次；构造 evidence/citation/checkpoint/dead-letter/backup 引用图，清理后无悬空引用。
- RetentionCompactor 对 deny、治理/组织审计、未满 90 天或被引用 allow 明细一律不动；聚合写入、root 校验或 manifest 写入任一步失败时不删除源明细，重跑幂等。
- 构造每种 audit_record_refs 引用类型，验证只有删除引用边且满足 90 天条件后才可压缩；伪造 JSON 中出现 audit id 不影响引用判定。

**DoD**：全部读模型视图可用，供 Phase 12 UI 的观测面板与人工干预中心直接调用。

### 阶段验收（Phase 11）
支撑 §19 全部条目的"可验证性"，且人工干预与存储配额有统一、可被 UI 直接消费的视图。

---

## Phase 12：前端 UI

**目标**：落地附录 E 的信息架构与页面。**本阶段从第 2 周就应该开始**（不必等后端全部完成），随着各阶段 RPC 方法落地逐步接入真实数据，前期可用 mock 数据先行开发交互与布局。每个子任务都标注了其真实依赖的后端阶段与"从 mock 切换到真实数据"的判定条件，不再是笼统地只依赖 P1 契约冻结。

### P12-T1：Tauri Command 层与类型生成（rpc-schema 为单一事实来源）
**文件**：
- `apps/desktop/src-tauri/src/commands.rs`
- `packages/rpc-schema/`（JSON Schema）、`packages/rpc-types/`（生成产物）
- `packages/rpc-schema/coverage.yaml`（方法 → owner/handler/任务/测试/UI consumer）
- `scripts/check_rpc_coverage.py`

**实现要点**（对照附录 A 约定——**契约来自 `rpc-schema` 生成，不是手写同步，CI 检查生成产物与提交内容无漂移**）：
- owner=`sidecar_rpc` 的 Tauri command 是 Sidecar RPC 薄封装；owner=`tauri_only` 直接调用 Rust service；owner=`internal_only` 不注册 WebView command，其中只有 Credential Broker secret payload 排除通用日志。前端不直接拼 UDS JSON-RPC 请求。
- 建立一个生成脚本：从 `packages/rpc-schema` 的 JSON Schema 同时生成 Python 端 `sidecar/acos/rpc/dto.py` 里的 pydantic 模型与 `packages/rpc-types` 的 TS 接口。
- CI 新增一个检查步骤：对比生成产物与已提交的文件，若有差异（即有人手改了生成产物而没改 schema 源）则 CI 失败。
- `coverage.yaml` 必须逐方法记录 `owner, implementation_task, handler, auth_subject, idempotency, success_contract_test, failure_contract_test, ui_consumer?`。检查脚本验证：schema 中每个方法恰有一条覆盖记录；Sidecar 方法已注册 handler；Tauri-only 方法未注册到 Sidecar；所有非内部方法都有成功与失败契约测试；覆盖记录引用的任务和测试文件存在。

**测试**：`apps/desktop/src-tauri/src/commands.rs` 内 `#[test]` 验证 Sidecar 转发与 Tauri-only 直连两类命令；CI 脚本测试分别删除覆盖项、写错 owner、移除 handler/contract test，均必须失败；生成产物漂移同样失败。

**DoD**：附录 B 全部方法在覆盖矩阵中可追溯到 owner、实施任务、handler 与契约测试；`rpc-schema` 变更后 Python/TS 类型同步生成，CI 同时阻止 schema 漂移与接口覆盖缺口。

### P12-T2：主导航与布局
**文件**：`apps/desktop/src/pages/`, `apps/desktop/src/components/layout/`

**实现要点**（对照附录 E.1）：建立全部路由、错误边界、loading/empty/permission 状态与 typed mock adapter；后续任务只替换数据 adapter，不重写页面状态契约。

**测试**：前端组件测试（Vitest/Testing Library）覆盖路由可达性与基本渲染。

**DoD**：主导航全部可点击进入对应空页面。

### P12-T3：公司与组织（CRUD + 组织图）
**文件**：`apps/desktop/src/pages/organization/`, `apps/desktop/src/components/OrgGraph.tsx`

**依赖**：Phase 2（公司/部门 CRUD）、Phase 4（职员/调岗）、Phase 6（Backend bootstrap/health）。Mock 切换条件：`org.company.*`、`org.department.*`、`backend.list/checkAvailability/probe` 落地后接入真实数据。

**实现要点**：`org.company.create` 后进入 initializing 引导，先展示 `CompanyCreated` Backend bootstrap、默认映射与 fresh health 状态；未就绪时禁用激活并提供跳转 Backend 配置/主动 probe，不允许客户端猜测或绕过服务端 `BackendBootstrapGate`。就绪后选择已发布模板并调用 `org.company.activate` 原子创建首任负责人；组织页支持 setLeader、setManager、freeze/unfreeze/archive，调用 `org.graph.get` 渲染唯一领导/汇报事实。

**DoD**：能创建一个新公司；Backend bootstrap 失败时停留 initializing、展示可操作诊断且不产生半激活状态，恢复并 probe healthy 后走完引导到 `active`；能展示真实公司的组织结构并支持缩放/拖拽。

### P12-T4：能力中心（含职员模板）
**文件**：`apps/desktop/src/pages/capability/`, `apps/desktop/src/pages/templates/`

**依赖**：Phase 3（Skill/Prompt/Capability 全套 CRUD 与版本状态机）、Phase 4（EmployeeTemplate）。

**实现要点**：Skill/Prompt Asset/Capability 三个库的列表、详情、版本历史（`cap.*.version.list`/`createVersion`）、发布状态机可视化（`draft→review→published→deprecated→archived`）、只读度量展示；三类资产均提供显式 deprecate，archive 仅在 deprecated 后可用。已发布内容 UI 层面只读，修改引导为"发布新版本"，不提供绕过 review 态的"直接发布"按钮。职员模板列表/详情/CRUD，引用能力快照。

**DoD**：能创建一个 Skill/Prompt Asset/Capability 并分别走完整的发布、弃用、归档流程（含质量门禁失败时的错误提示，且 UI 无法跳过 `review` 或 `deprecated`）；能创建职员模板并引用一个已发布的能力版本。

### P12-T5：职员管理、调岗与能力升级
**文件**：`apps/desktop/src/pages/employees/`

**依赖**：Phase 4（Employee CRUD、P4-T2a 能力升级、调岗）、Phase 7（会话线程状态、Handoff）。

**实现要点**：职员列表/详情、setManager、activate/suspend/resume/archive、调岗状态和能力升级；suspend/archive/transfer 有 active work 时展示 Employee Drain 的 operation、阻塞节点和 wait/reassign 入口，open drain 时禁用 resume。领导无替补时展示服务端错误并引导先设置替补，前端不直接修改 employee_type。

**DoD**：调岗操作在 UI 上能观察到通用线程的状态转换；能力升级操作能观察到该职员之后的会话使用新的安全上下文（新线程）。

### P12-T6：任务中心（DAG 可视化）
**文件**：`apps/desktop/src/pages/tasks/`, `apps/desktop/src/components/TaskDAG.tsx`

**依赖**：Phase 9（任务全流程）。

**实现要点**：任务创建表单（两入口）；任务详情页用 React Flow 展示 DAG，节点带 `task_type` 与 Workspace 类型标记；Review 面板；修复轮次展示；证据链追溯（点击任意产物/finding 能跳转到 `source_node_id`/`run_id`）。通过 `notify.taskProgress` 实时更新。

**DoD**：能创建任务并实时观察其 DAG 推进，并行节点同时高亮为 `running`，不同 Workspace 类型的节点有视觉区分。

### P12-T7：会话页面（按安全上下文分线程）
**文件**：`apps/desktop/src/pages/sessions/`

**依赖**：Phase 7（会话线程）。

**实现要点**：用 `session.list` 展示"通用线程"与"各任务专属线程"；选中线程后所有 `get/sendMessage/cancel/transcript.get` 都携带稳定 `thread_id`，通用线程首次对话允许省略 thread_id 由服务端惰性创建。流式渲染 `notify.runtimeEvent`；`RT-SESSION-STALE` 时刷新列表并引导进入新线程，`RT-SESSION-READONLY` 时保留 transcript 回看但禁用输入；`waiting_approval` 提供跳转到人工干预中心的入口，`waiting_backend` 显示 Backend 健康/容量原因和取消入口，不伪装为 Provider 正在响应。

**DoD**：通用线程和至少两个任务线程可并列打开，发送、取消、通知与 transcript 均不串线；安全上下文变化后的 stale/read-only 行为符合设计。

### P12-T8：知识库、Provider/Backend 配置、授权管理、人工干预中心、审计页面
**文件**：`apps/desktop/src/pages/{knowledge,providers,backends,grants,humanIntervention,audit}/`

**依赖**：Phase 6（Provider/Backend/Credential）、Phase 8（知识）、Phase 4（授权）、Phase 11（RuntimeStatus/HumanIntervention/StorageQuota 读模型）。

**实现要点**：
- 知识库：必须先选择 view-as employee 并持续显示主体；search/list/get/citation 传 `view_as_employee_id`，治理命令明确显示 LocalOwner 身份。入库状态直接消费六态 `notify.knowledgeStatus`；`cancelled` 显示“已取消”、停止进度动画且不出现 retry，只有 `retryable|failed` 显示重试入口；stream gap 后以 job/document 查询恢复，不以通知反写状态。
- Provider 配置：模型/档位/凭据、版本化价格/来源、自定义 OpenAI-compatible 价格、硬预算能力与 freeze 状态；仅 LocalOwner 可发起解除，必须填写调查原因，UI 展示重新探测/验价结果并处理并发状态刷新。
- Backend 管理：按当前公司展示 `local_process` 列表/详情、默认标记、lifecycle/health reason/last probe、Backend held/limit、全局 held/limit、支持的 Workspace/capabilities 和排队项；提供创建、配置、默认切换、enable、drain、archive、主动 probe。跨公司切换立即清空旧缓存；按钮仅按服务端 allowed state 启用，CAS 冲突刷新后提示，不提供 Docker/Remote/K8s 选项，也不允许 WebView 改写受信任启动配置中的 `global_process_limit`。
- 授权管理：强类型 department/task 单目标授权，UI 不允许双目标/无目标，展示有效/过期/撤销状态。
- **人工干预中心**：六类均只渲染服务端 allowed_actions/required_params。manual_task 按 §10.2 受限 schema 渲染文本/数字/开关/枚举/日期/multiline/artifact-ref，unsupported schema 显示不可执行错误而不猜测；Employee Drain 与 Backend Recovery 其余动作严格按服务端状态。
- 审计：前端查询值严格使用 `acl|knowledge_access|knowledge_governance|org|approval|budget|capability_publish|backend`，显示名依次为 ACL、知识访问、知识治理、组织变更、审批、预算、能力发布、Backend 变更；禁止从中文显示名反向拼 type。

**DoD**：页面由真实数据驱动；view-as/LocalOwner 语义清晰，价格/授权可配置，Backend 管理和健康/容量状态与服务端一致，人工干预六类状态机一致。

### P12-T9：设置页、密钥管理与备份/更新
**文件**：`apps/desktop/src/pages/settings/`, `apps/desktop/src-tauri/src/keychain.rs`, `apps/desktop/src-tauri/src/backup.rs`, `apps/desktop/src-tauri/src/updater.rs`, `apps/desktop/src-tauri/src/update_journal.rs`, `sidecar/acos/settings/service.py`

**依赖**：Phase 1（迁移+备份框架）、Phase 6（Credential Broker）、Phase 11（StorageQuota）。

**实现要点**：`sidecar/acos/settings/service.py` 是 `settings.embeddingPolicy.*` 与 `settings.budgetDefault.*` 的唯一 handler；`knowledge/policy_service.py` 只实现 `settings.knowledgePolicy.*`，不得重复注册预算方法。Knowledge/Embedding Policy 修改严格按设计方案 §6.1 执行：update 必须携带 get 返回的 `expected_policy_version`，以旧 active version 做 CAS，新增 version、supersede 旧版并原子切 Company pointer；Embedding update 的业务字段为 `{model,execution_mode,allow_cloud,consent?}`，model 必须存在签名 manifest，cloud 模式必须同版 consent，撤回生成 local/allow_cloud=false 新版。`budgetDefault.update` 必须携带 `expected_company_version`，以 Company version 做 CAS，只替换 `default_budget_policy` 并返回新 `company_version`；同时校验 ISO-4217、int64 非负/溢出与三值策略，分别返回 `GOV-BUDGET-CURRENCY-INVALID/GOV-BUDGET-LIMIT-INVALID/GOV-BUDGET-POLICY-INVALID`，不得笼统映射成 ORG-VALIDATION。上述版本不匹配均返回 `SYS-OPTIMISTIC-LOCK-CONFLICT`。**失败语义**：embedding policy 和 budget default 更新是独立操作，各自在独立事务中完成；CAS 失败返回 `SYS-OPTIMISTIC-LOCK-CONFLICT`，客户端需重新 get 后重试。页面从 get 响应保留相应版本并原样带入 update，冲突后必须重新读取，不得静默覆盖。页面展示 extraction/embedding 配置与版本化云端同意/撤回；备份为全局策略，配额分 company/global。更新 journal 与 Updater 顺序严格按设计方案 §4.8。

**测试**：两公司 knowledge/embedding/预算策略隔离；预算币种非法、负数、int64 溢出、未知策略分别断言精确错误码；单 active、version+1、旧版 superseded 与 pointer 原子性；EmbeddingPolicy 两个相同 `expected_policy_version` 并发更新、BudgetDefault 两个相同 `expected_company_version` 并发更新均只有一个成功，失败方返回 `SYS-OPTIMISTIC-LOCK-CONFLICT`，数据库无孤立版本、丢失更新或重复审计；前端冲突后重新读取并显示最新事实。未同意/同意版本不匹配/撤回后 cloud 提取和 cloud embedding 均禁用；未知或 hash 失配 embedding model 被拒；全局备份只计一次。更新覆盖包/manifest 篡改、错误签名者、跨 channel、降级版本、密钥轮换，以及迁移/健康检查各阶段失败回滚；恢复 `pre_update_backup_id` 后 journal 仍保留 rolling_back/rolled_back 事实，rollback 中途重启可幂等续跑。

**DoD**：API Key 不出现在日志或本地明文文件；备份策略可配置且备份/恢复可操作；更新迁移前后任一阶段失败均有确定回退状态，旧二进制从不直接连接新 schema。

### 阶段验收（Phase 12）
对应附录 E 全部页面与交互规范；支撑 §19 中所有需要"用户可观察/可操作"的验收条目的界面呈现；人工干预相关页面统一命名与数据源。

---

## Phase 13：质量门禁与发布加固

**目标**：收口。跑全部质量门禁与专项测试，完成签名公证与首个可发布版本。

### P13-T1：权限逃逸测试套件
**文件**：`sidecar/tests/security/test_permission_escape.py`

**实现要点**（对照 §17，**汇总前面各阶段散落的安全测试，补齐遗漏组合**）：
- 跨公司越权（穷举：普通职员/部门负责人/公司负责人 × 尝试访问其他公司任意资源）。
- 平级/上级部门私有知识越权。
- **同部门 `employee_private` 越权**（复用 Phase 4-T3 的核心断言场景，在此处做汇总回归，确保端到端也验证到）。
- `task_private` 泄漏：同部门但没有当前 generation/node/run 活动 assignment 的普通职员必须被拒绝；retry、replan、Reviewer/Fixer 重派与 transfer drain 只改变精确 assignment，不得扩大或误收回其他节点权限。
- 部门负责人只通过 `managed_department_ids` 获得任务管理权限，普通 `visible_department_ids` 不能放行 `task_private`；LocalOwner 的 view-as 由服务端生成受约束 subject，客户端不能伪造 employee principal。
- 能力 `knowledge_scope` 越权（能力配置想看更多但 ACL 不允许）。
- 调岗后旧知识可见性（复用 Phase 7-T4 的测试场景）。
- search/list/get/citation/Context Pack 均验证结构化 ACL 谓词在检索前下推，且 `knowledge_access_logs` 记录 scope hash、最终结果 ids、operator/subject；具体资源授权同时核实 `acl_audit_log.decision`，不能只验证业务返回值。
- Backend 管理/选择穷举跨公司 list/get/update/setDefault/acquire，任何伪造 backend_id、lease_id、run_id/session_turn_id 组合均在查询/调度前拒绝并留下审计。

**DoD**：这是一个独立可运行的测试文件，CI 里作为发布前必跑项，任一用例失败即阻断发布。

### P13-T2：恢复测试（Recovery Test）
**文件**：`sidecar/tests/recovery/test_crash_recovery.py`

**实现要点**（对照 §17，把 Phase 9-T8 的单测场景提升为真实集成测试，并覆盖所有持久化恢复点）：
- 起一个真实的 Sidecar 子进程，分别在节点执行中、预算预占后、工具/计划/预算审批等待中、replan 新 generation 后、Dead Letter 处理前和 Report→Knowledge Consolidation 前注入强杀。Supervisor 重启后验证 `outbox_deliveries` 续跑，并从 generation/run/reservation/intervention/Checkpoint 恢复；不得跨代执行、重复 Provider 调用、重复 Git 提交、重复扣预算或重复知识固化。
- 在线程已取得 `active_turn_id` 后强杀，验证数据库 CAS 与 turn event/Checkpoint 能确定续跑或释放，不会因进程内锁消失产生双 active turn。
- 分别在 Backend lease acquire 已提交但 Runtime 未启动、运行中 heartbeat 前后、终态 release 前后强杀；重启后 held/limit 收敛且不重复调用 Provider。无法确认进程或副作用 unknown 必须进入 backend_recovery，start-token 不匹配时拒绝释放；在 active 与 dissolving 状态分别走安全 terminate/mark_failed，确认退出证据后才释放。draining 与公司解散必须等 lease 清零再完成 disabled/watermark。
- 在 Employee Drain、调岗文件系统操作、公司解散各消费者执行中途强杀，验证重启后对账器能幂等补完或生成 `needs_repair`/`employee_drain` 人工干预，不留下悬空状态或提前物理删除证据。

**DoD**：对应 §19 第 9、21、25 条的端到端验证（而非模块内 mock 验证）；Handoff 与 Backend lease 崩溃对账均有独立的端到端证据。

### P13-T3：性能基线测量（release_gate 与 observational 分开判定）
**文件**：`sidecar/tests/perf/test_benchmarks.py` + 记录到 `docs/性能基线记录.md`

**实现要点**（对照 §4.5——**不是所有指标都笼统地"记录数据就算通过"，`release_gate` 类指标未达标必须阻断发布**）：
- 实测以下指标，与 §4.5 目标值对比：
  - `sidecar_restart_ready_time`（release_gate，< 3s）——只算进程重启到能接受 RPC。
  - `task_recovery_ready_time`（observational，首版先记录基线）——单任务从 Checkpoint 恢复到继续调度，与任务规模相关，不是常数。
  - `thread_lookup_and_dispatch_time`（release_gate，< 500ms）——从请求进入到完成线程查找/安全上下文校验并调用 ProviderAdapter，不含外部进程启动和网络。
  - Checkpoint 写入（release_gate，< 100ms）。
  - `provider_fallback_selection_time`（release_gate，< 200ms）——当前 Provider 已知不可用后，基于缓存矩阵选择替代者，不含外部探测。
  - `provider_native_resume_e2e_time`、`provider_probe_e2e_time`（observational）——按 Provider、冷/热启动和网络环境分别记录 p50/p95；同时验证每个 Adapter 的有界 timeout 与失败降级功能，不把外部延迟作为发布阻断阈值。
  - `backend_slot_acquire_time`（release_gate，< 50ms）——只测缓存健康状态下的选择与 SQLite 原子 acquire，不含排队/主动 probe；`local_backend_probe_time`（release_gate，< 500ms）只测本机 workspace/worker/process pool，不含 Provider 网络。
  - `permission_compute_scope_time`（release_gate，< 10ms）、`permission_authorize_and_audit_time`（observational，< 30ms）与 `knowledge_access_audit_write_time`（observational，< 30ms）分开测量。
- 测试基线明确记录：机型（Apple Silicon M 系列）、内存（16GB）、数据规模（约 1 万条知识/100 个职员）、p95 而不是单次采样。observational 指标在 v1 发布前记录基线值，不设 release_gate；v2 规划时根据基线数据决定是否升级为 release_gate。
- 每项 release_gate 跑 3 个独立轮次、每轮至少 30 个有效样本；阈值为严格上界，任一轮 p95 `>=` 阈值即失败。临界超标不能在 Go/No-Go 现场改成 observational 或人工豁免；只能优化重测，或先正式同步修改设计/计划/验收。环境无效轮次须有机器日志并整轮重跑，不能删慢样本。
- 任一 `release_gate` 指标未达标，本任务 DoD 不通过，不能进入 P13-T5。

**测试**：见上。
**DoD**：`docs/性能基线记录.md` 产出，全部指标有明确计时边界与实测数据；本地可控的 release_gate 全部达标，外部 Provider 指标按环境记录且 timeout/降级功能测试通过。

### P13-T4：备份恢复演练（不是迁移 down 回滚）
**文件**：`scripts/backup_restore_drill.sh`

**实现要点**（对照 §5.4、§17——**生产迁移策略是 Forward-only + 自动备份，演练的是"备份→迁移→模拟失败→恢复"，不是对已发布迁移执行 `down`**）：
- 用一份带真实历史数据的数据库副本（不是空库），执行：备份快照（复用 P1-T4b 的 `backup.py`）→ 应用一批迁移 → 模拟迁移失败 → 从快照恢复 → 校验数据完整性、跨存储 watermark 一致性与业务可用性。
- 验证 `down` 脚本只在开发阶段迁移使用，演练脚本本身不对任何已标记"已发布"的迁移执行 `down`。

**DoD**：演练脚本产出通过记录；`docs/性能基线记录.md` 或独立文档记录一次真实数据规模下的演练结果。

### P13-T4b：自动更新事务回退演练

**文件**：`scripts/update_rollback_drill.sh`、`docs/更新回退演练记录.md`

**实现要点**：用可安装的 N-1 与 N 两个签名测试包、带真实历史数据的副本执行完整更新事务。先验证签名 manifest、SHA-256、发布 channel、bundle id、Team ID、版本单调性与受控公钥轮换；再分别在 `backed_up`、迁移进行中、迁移成功后的 Runtime/Provider/Backend Registry 初始化、Backend lease reconciler、RPC 握手、schema/data canary、观察窗口阶段注入失败，验证失败状态持久化、恢复 `pre_update_backup_id`、启动 N-1、业务读写可用的顺序不可颠倒。

**测试**：

- 迁移成功后注入失败，确认 N-1 启动前数据库已恢复到 N-1 schema/data；禁止通过 mock schema 兼容绕过。
- 在 rollback 中途终止应用，重启后按 `update_transaction_id` 幂等续跑，不重复创建备份或反复迁移。
- 备份恢复也失败时进入 `needs_repair`、保持写入关闭并出现在人工干预中心，不循环启动。
- 对包/manifest 任一字节篡改、错误签名者、跨 channel 清单、降级版本、未知或过期轮换密钥逐项拒绝，且拒绝发生在停写、备份和迁移之前。

**DoD**：演练记录覆盖全部故障注入点，证明“迁移成功后失败”也能安全回到旧版本。

### P13-T5：签名公证与最终打包
**文件**：`apps/desktop/src-tauri/tauri.conf.json`（正式证书配置）、`docs/发布记录.md`

**实现要点**（承接 Phase 0-T4 的验证结果，换成正式开发者证书与公证账号）：完整走一遍签名、公证、验证 bundle id/Team ID/entitlements 与更新 manifest 发布者一致性，并在多台干净 macOS arm64 机器上安装测试，确认 P13-T3 的 `release_gate` 指标在正式签名包上依然达标（不只是开发环境）。在发布候选环境重跑 P6-T3 的真实 Claude Code CLI 调用和 P6-T4 的真实 OpenAI API 五类契约，发布记录固化 Provider manifest version/hash、具体 model ID 与结果。至少一台具备受信任 Git 的机器真实完成 GitWorktreeWorkspace 创建、只写任务 integration 分支的机械合并、patch/bundle 交付物复算和安全清理，并断言用户目标分支/工作树/远端不变；另用无 Git 环境确认默认 Backend 不声明 git_cli/GitWorktreeWorkspace、文件/只读任务可运行且 Git 任务被 PV-13 明确拒绝。

**DoD**：对应 §19 第 11、25 条的发布环境部分——正式签名公证的 `.app` 在无 Python 环境的干净 macOS arm64 上独立运行，本地 embedding/SQLite/FTS5/LanceDB 均能真实加载并完成一次读写；Claude Code CLI 与签名 manifest 中的具体 OpenAI 模型均有发布候选环境的真实通过证据；受信任 Git 存在时 Git Workspace 真实可用，缺失时能力声明与错误提示正确；未安装的 Claude Code CLI 被明确标记而非导致崩溃。

### 阶段验收（Phase 13，即项目最终验收）
逐条对照设计方案 §19 全部 25 条验收标准（见下节映射表），全部通过方可视为首版完成。

---

## 2. 测试策略总纲

测试金字塔（对照 §17）：

```text
单元测试            -- 每个 Phase 内的模块级测试（占比最大，各任务已列出）
契约测试            -- ProviderAdapter 各实现对抽象接口的一致性；RPC 请求/响应符合 packages/rpc-schema
权限逃逸测试         -- Phase 13-T1（发布前必跑，任一失败阻断发布）
恢复测试            -- Phase 9-T8（模块级）+ Phase 13-T2（端到端，含 Handoff/Backend lease 崩溃对账）
Backend 契约测试     -- Phase 6-T1b/T1c（生命周期、健康、并发 lease、FIFO、公司隔离）
能力发版质量门禁测试  -- Phase 3-T5/T6（每次能力/技能发布前跑）
端到端集成测试       -- Phase 9-T10（任务全流程，含知识固化闭环）
双写一致性对账测试    -- Phase 8-T5
性能基线测量         -- Phase 13-T3（release_gate 指标未达标阻断发布）
备份恢复演练         -- Phase 13-T4
更新供应链与事务演练  -- Phase 13-T4b
```

**强制项**（不可因进度压力削减）：权限逃逸与访问审计测试（P4-T3/P8-T4/P13-T1）、Handoff 隔离测试（P7-T4）、Backend 生命周期/健康/lease/FIFO/崩溃对账（P6-T1b/T1c/P13-T2）、generation/run/assignment/Checkpoint 幂等恢复测试（P9-T8/P13-T2）、成本上界与降级链测试（P9-T9）、MergeStrategy/Git 安全测试（P9-T7）、PlanValidator `PV-01..PV-13`（P9-T4）、工具/计划/预算审批 TOCTOU（P10-T1）、更新供应链与事务回退（P12-T9/P13-T4b）、RPC 覆盖门禁（P12-T1）。每条设计规则都要有直接测试，不允许用少量示例替代规则覆盖。

---

## 3. 阶段 → 验收标准映射表

对照设计方案 §19 的 25 条验收标准，标注由哪个阶段/任务负责满足，便于第三方自查进度：

| §19 条目 | 内容简述 | 负责阶段 |
|---|---|---|
| 1 | 对话原始记录，写入后确认 | Phase 8 (P8-T1) |
| 2 | 提炼失败不丢原始信息 | Phase 8 (P8-T2) |
| 3 | 部门知识边界（含同部门 employee_private/task_private 不越权） | Phase 4 (P4-T3), 8 (P8-T4) |
| 4 | 部门负责人/公司负责人读取范围 | Phase 4 (P4-T3), 8 (P8-T4/P8-T4a) |
| 5 | 检索结果带来源引用 | Phase 8 (P8-T4) |
| 6 | 错误知识标记 rejected + 保留矩阵级联清理 | Phase 8 (P8-T1/P8-T4a/P8-T5) |
| 7 | 检索前 ACL + 具体资源/知识结果访问审计 + knowledge_scope 收窄 | Phase 1 (P1-T5), 4 (P4-T3), 5 (P5-T2), 8 (P8-T4/P8-T4a) |
| 8 | 密钥不进知识库/日志 + 单次短期 Credential capability | Phase 6 (P6-T2), 8 (P8-T2), 10 (P10-T3), 13 (P13-T1) |
| 9 | 崩溃自动恢复 + Outbox 续跑 + 更新事务安全回退 | Phase 1 (P1-T2/T4b), 9 (P9-T8), 12 (P12-T9), 13 (P13-T2/T4b) |
| 10 | 任务全流程闭环可追溯（含 PV-01..PV-13、人工干预、知识固化） | Phase 9 (P9-T1/T4/T10/T11) |
| 11 | 签名公证独立运行，native 依赖真实可用 | Phase 0 (P0-T4), 13 (P13-T5) |
| 12 | 并行确实发生，Workspace 策略按任务性质选择 | Phase 9 (P9-T5) |
| 13 | 会话线程按九维安全上下文复用 + thread_id 寻址 + 降级恢复 | Phase 7 (P7-T1/T2/T3), 12 (P12-T7) |
| 14 | 调岗 Handoff/排空干预 + 能力升级线程轮换 + 解散/删除归档 | Phase 4 (P4-T2a/T5), 7 (P7-T2/T4/T5), 9 (P9-T11) |
| 15 | 版本化价格预留—结算 + 硬预算异常冻结/安全复验解冻 + 工具/计划/预算审批 TOCTOU + 局部阻塞 | Phase 6 (P6-T1a), 9 (P9-T9), 10 (P10-T1), 12 (P12-T8) |
| 16 | Embedding 换模型可回滚 + 双写一致性对账 | Phase 8 (P8-T3/T5) |
| 17 | 角色默认档位 + 逐层覆盖 | Phase 9 (P9-T9) |
| 18 | stability_level 降级链 + 部门边界 + 预算约束 | Phase 9 (P9-T9) |
| 19 | 能力资产版本化不可变 + publish 门禁 + 职员能力升级事务 | Phase 3 (P3-T5/T6), 4 (P4-T2a), 7 (P7-T2) |
| 20 | 能力度量只读，无自动改写路径 | Phase 3 (P3-T7) |
| 21 | 跨聚合写按 company/actor/method/key 幂等并校验 request hash + 事件投递分离 + RPC 覆盖完整 | Phase 1 (P1-T2/T3/T5), 9 (P9-T8), 12 (P12-T1) |
| 22 | 组织变更同事务 + 事件 + 防成环 + 显式激活与六消费者可恢复解散 | Phase 2 (P2-T1/T2), 4 (P4-T2/T5), 6 (P6-T1b/T1c/T5), 7 (P7-T5), 8 (P8-T5), 9 (P9-T10), 12 (P12-T8), 13 (P13-T2) |
| 23 | company/global StorageQuota + 证据安全清理 | Phase 11 (P11-T2), 12 (P12-T9), 13 (P13-T2) |
| 24 | KnowledgePolicy 云端同意 + visibility/source category 正交收窄 + 统一审计查询 | Phase 3 (P3-T2), 5 (P5-T2), 8 (P8-T2/T4/T4a), 12 (P12-T8/T9) |
| 25 | 公司激活 bootstrap 门禁 + local_process Backend 默认/健康 + Backend/全局双层限流 + 有界 FIFO + backend_recovery + 管理界面/Git Workspace 发布门禁 | Phase 4 (P4-T2), 6 (P6-T1b/T1c), 7 (P7-T2), 9 (P9-T1/T4/T5/T8/T10), 11 (P11-T2), 12 (P12-T3/T7/T8), 13 (P13-T1/T2/T3/T5) |

---

## 4. 风险登记与缓解

| 风险 | 影响阶段 | 缓解措施 |
|---|---|---|
| PyInstaller 对 native 依赖（ONNX/LanceDB）打包不完整，或打包后无法真实推理/读写 | Phase 0 | 第一周即验证真实推理与向量读写（P0-T4），不只验证能启动 |
| OpenHands SDK 与自研 ProviderAdapter 契约不兼容，集成成本超预期 | Phase 0 | Runtime 选型 Spike（P0-T5）在写 Provider Driver 代码前先决策，避免推到 Phase 6 才发现 |
| CLI Provider 行为随其自身版本升级漂移 | Phase 6 | Provider 契约测试标记 `requires_cli`，CI 定期跑真机集成测试并记录基线 |
| Backend lease 在 Sidecar 崩溃后遗留，错误释放或重发可能造成超并发/重复副作用 | Phase 6, 7, 9, 13 | lease/heartbeat/expiry 全部持久化；reconciler 先核对 run/turn/side_effect_state，无法确认转 `backend_recovery`，仅在 token/退出证据满足时安全终止或释放；P6-T1c/P13-T2 在 acquire/heartbeat/release 各点强杀 |
| 多个 local_process Backend 被误解为 OS 强隔离或远端算力 | Phase 6, 12 | v1 schema 只允许 local_process+policy_only，UI 明示本机逻辑资源池；禁止任意 executable/env/path，Docker/Remote/K8s 继续列为非目标 |
| LanceDB 实际不支持真正的 pre-filter，检索前 ACL 退化为"先召回再过滤" | Phase 8 | P8-T3 在选型阶段就验证预过滤能力，不通过则换版本/换库；`VectorStore` 抽象接口隔离，预留替换空间 |
| 本地 Embedding 中文/代码混合场景检索质量不足 | Phase 8 | 用真实业务文本尽早做检索质量基线测试，允许后续接入 Reranker |
| 任务工作流引擎（Phase 9）涉及 PlanValidator/WorkspaceStrategy 等多个子系统，复杂度高导致进度延误 | Phase 9 | 提前完成其依赖（P5/P6/P7），投入最多人力，子任务尽量分给不同人并行 |
| 权限/Handoff 测试因赶工被削减 | Phase 4, 7, 13 | 第 2 节"强制项"明确列出不可削减的测试集合，纳入 CI 门禁 |
| 会话按安全上下文分片后，用户感觉职员"记忆碎片化"、连续性变差 | Phase 7, 12 | 跨上下文的连续性设计为通过知识检索获得（第 9 节），这是产品层面的权衡取舍，非缺陷；Phase 12 的会话页面需清晰展示"通用线程 vs 任务线程"的划分，管理好用户预期 |
| 预算预留—结算模式增加了每次模型调用的额外一次数据库写入，可能影响吞吐 | Phase 9 | 性能基线测量（P13-T3）中纳入预留/结算操作的耗时观测，超预期再优化为批量结算 |
| 前后端契约（`rpc-schema`）生成流程本身出问题，导致生成产物与手改代码不一致 | Phase 12 | P12-T1 的 CI 漂移检查作为硬门禁 |
| 5 人团队在 25 周（或 6 人在 24 周）功能基线内完成 Runtime/RAG/Backend/工作流/UI/签名，集成返工或人员不可用挤压质量阶段 | 全阶段 | 功能排期只使用 85% 总人周；第 26–29 周只用于集成/修复；Phase 0/6/9/13 Go/No-Go 未通过时关闭弹性范围，不削减隔离、审计、Backend 恢复、备份与安全测试 |
| 自动更新迁移成功后新版本仍启动失败，旧二进制无法读取新 schema | Phase 12, 13 | 更新事务绑定 `pre_update_backup_id`；观察窗口失败先恢复数据再启动旧版本；P13-T4b 对各阶段做故障注入演练 |

---

## 5. 交付物清单（按阶段汇总）

- Phase 0：可运行的 monorepo 骨架、Tauri↔Sidecar 通信回环、真实推理/向量读写验证的签名公证记录、Runtime 选型决策记录。
- Phase 1：错误码、事件与投递分离、迁移与一致备份、ACL/知识访问/组织审计、本地身份主体基础设施。
- Phase 2：Company（含 initializing 引导）/Department + 闭包表，含防成环与根部门自动创建测试。
- Phase 3：Skill/Prompt Asset/Capability 全套版本管理、快照、Tool Binding 骨架、质量门禁、发布状态机集成。
- Phase 4：Employee/汇报链模型、职员能力升级事务、结构化 Permission Engine（含具体资源鉴权）、临时授权、Employee Drain 与调岗。
- Phase 5：Capability Engine 装配器，knowledge_scope 按分支收窄测试。
- Phase 6：ProviderAdapter 抽象 + Credential Broker + Claude Code CLI/OpenAI API 两个 v1 Driver、公司级 local_process Backend Registry/健康/持久化 lease 调度、Agent Runtime 骨架。
- Phase 7：按九维安全上下文分片且以 thread_id 寻址的会话线程、原生恢复/规范化日志降级、能力升级轮换、Handoff 与崩溃对账。
- Phase 8：双层存储（含保留矩阵）、知识提炼（进程池隔离）、向量存储（含预过滤验证）、混合检索（结构化谓词下推）、双写一致性对账。
- Phase 9：完整任务工作流引擎（PV-01..PV-13、generation/run/assignment/backend lease、Workspace/MergeStrategy、并行执行审查、成本上界、Checkpoint、安全重试与人工干预命令），端到端测试含知识固化。
- Phase 10：工具/计划/预算三类不可变 target 审批流转、预算查询、安全扫描脚本。
- Phase 11：结构化日志、统一读模型视图（含 HumanIntervention/StorageQuota）。
- Phase 12：完整前端 UI、rpc-schema 类型生成与 RPC 覆盖矩阵、人工干预中心、Rust 更新事务状态机。
- Phase 13：权限逃逸/访问审计测试、崩溃与 Handoff 恢复、可控/外部性能分级基线、备份与更新回退演练、正式签名公证发布包。

**最终交付**：一份签名公证过的 macOS arm64 `.app`，配套本计划全部阶段验收记录、§19 全部 25 条验收标准的通过证据（测试报告/截图/日志），以及《打包验证记录》《Runtime 选型记录》《性能基线记录》《更新回退演练记录》《发布记录》五份交付证据文档。

### 5.1 Forward-only 迁移与数据所有权清单

迁移按下表严格顺序发布；`up` 必须幂等，已随版本发布的迁移禁止执行生产 `down`。每次升级先由 P1-T4b 创建一致备份，失败时整体恢复该备份。Owner 对 schema、repository、保留策略和恢复测试共同负责；同一表不得被另一个迁移重复创建。

| 迁移 | 权威表/对象 | Owner / 实施任务 | 恢复与保留验证 |
|---|---|---|---|
| `0001_domain_events.sql` | domain_events, outbox_deliveries | Platform / P1-T2 | 投递可重放，领域事实不可改 |
| `0001b_rpc_idempotency.sql` | rpc_idempotency_records | Platform / P1-T3 | company/actor/method/key + request hash；按策略过期 |
| `0002_audit_tables.sql` | acl_audit_log, knowledge_access_logs, knowledge_governance_audit, org_change_audit, audit_record_refs, audit_compaction_manifests | Security / P1-T5/P11-T2 | 引用边显式维护；deny/治理/组织禁止清理，allow 仅受控压缩 |
| `0002b_local_owner.sql` | local_owner | Security / P1-T6 | 本机唯一主体，不从客户端导入 |
| `0002c_snapshot_epochs_backups.sql` | snapshot_epochs, backup_manifests | Platform / P1-T4b | 跨存储 watermark、hash、加密恢复 |
| `0002d_human_interventions.sql` | human_interventions | Platform / P1-T7 | company 隔离、open 唯一、CAS resolve；领域动作由 subtype owner 校验 |
| `0003_companies_and_policies.sql` | companies（含 default_provider_policy/default_budget_policy）, security_policies, knowledge_policies, embedding_policies | Organization / P2-T1 | 状态机与默认策略原子创建；不建 provider_policies/budget_default_policies |
| `0004_departments.sql` | departments, department_closure | Organization / P2-T2 | 移动防成环、闭包重建 |
| `0005_skills_prompts.sql` | skills, skill_versions, prompt_assets, prompt_asset_versions | Capability / P3-T1 | published 版本不可变 |
| `0006_capabilities.sql` | capabilities, capability_versions, skill_bindings | Capability / P3-T2 | 引用完整性与发布状态机；tool_bindings 作为 SkillVersion 的版本化 JSON，不另建第二事实表 |
| `0006b_capability_snapshots.sql` | capability_snapshots | Capability / P3-T3 | checksum 与运行快照不漂移 |
| `0007_capability_metrics.sql` | capability_metrics | Capability / P3-T7 | 只读聚合，可重建 |
| `0008_employee_templates.sql` | employee_templates | Organization / P4-T1 | 模板版本与归档 |
| `0009_employees.sql` | employees, employee_reporting_closure | Organization / P4-T2 | manager 防成环、调岗/能力升级 CAS |
| `0009b_employee_drains.sql` | employee_drain_items | Organization / P4-T5 | transfer/suspend/archive drain CAS、崩溃后可恢复 |
| `0010_access_grants.sql` | access_grants | Security / P4-T4 | 强类型单目标、撤销审计 |
| `0010b_provider_registry_pricing.sql` | providers, provider_models, provider_model_prices, provider_budget_freezes | Provider / P6-T1a | 历史价格追加、冻结可审计 |
| `0010c_backends.sql` | backends, company_backend_defaults, backend_health_checks, backend_health_daily, backend_queue_entries, backend_leases, backend_change_audit | Backend / P6-T1b/T1c | 默认单行 CAS、queue/lease XOR 与活动唯一、健康受控压缩、排空/崩溃可恢复 |
| `0011_session_threads_and_events.sql` | session_threads, conversation_events | Runtime / P7-T1 | active_turn CAS；文件投影可从 DB 重建 |
| `0012_knowledge_sources.sql` | knowledge_sources | Knowledge / P8-T1 | `(company,source_type,source_id)` 唯一；1:N 派生与保留矩阵 |
| `0013_knowledge_documents.sql` | knowledge_documents, knowledge_chunks, knowledge_citations, knowledge_ingestion_jobs | Knowledge / P8-T2/T4a | document→source 同公司 FK；chunk→generation；硬删除边界可测 |
| `0013b_index_generations.sql` | index_generations、embedding_policies.active_generation_id 扩展 | Knowledge / P8-T3/T5 | UUID generation FK、原子切换、双写对账与回滚 |
| `0014_tasks.sql` | tasks, task_node, tool_calls, workspace_changes, artifacts, reports, review_findings, fix_items | Workflow / P9-T1 | generation 外键与证据链完整 |
| `0014b_task_assignments.sql` | task_assignments | Workflow / P9-T1a | node/generation/role 精确关闭与审计保留 |
| `0014c_workflow_runtime.sql` | plan_generations, task_runs, checkpoints, usage_reservations, usage_records, approvals, dead_letters | Workflow / P9-T1b | 重启后恢复；复用既有 intervention/drain 事实，副作用 unknown 转人工 |

发布门禁 `scripts/check_migration_inventory.py` 同时比对本表、`sidecar/migrations/`、设计方案 §15 与 ORM metadata：漏表、重复 owner、编号碰撞、已发布脚本 hash 改变或缺少恢复测试均阻断发布。Rust 更新 journal 由 P12-T9/P13-T4b 的独立状态机测试覆盖，不伪装成 Sidecar migration。

---

## 6. RPC 实施覆盖矩阵

机器可校验的唯一来源为 `packages/rpc-schema/coverage.yaml`。该文件对附录 B 的 **140 个请求方法**逐项记录 `owner`、`handler`、`task_id`、`auth_subject`、`idempotency`、`success_contract_test`、`failure_contract_test` 与 `ui_consumer`；下表是便于实施排期的分组视图。`scripts/check_rpc_coverage.py` 必须同时比对设计方案附录 B、Sidecar registry、Tauri command registry 与该文件：方法缺失、重复 owner、owner 与 registry 不符、缺少成功/失败契约测试均阻断合并和发布。

Owner 只有三个稳定枚举：`sidecar_rpc`、`tauri_only`、`internal_only`。下表使用 “Sidecar RPC / Tauri-only / internal-only” 显示名；`tauri_only` 不得注册到 Sidecar，`internal_only` 不得注册 WebView command。

| 方法 | Owner | 实施任务 / handler | 契约测试与 UI consumer |
|---|---|---|---|
| `org.company.create`、`org.company.list`、`org.company.get`、`org.company.update`、`org.company.activate`、`org.company.dissolve` | Sidecar RPC | P2-T1、P4-T2 / `organization/service.py` | `test_company_rpc.py` / 公司与组织页 |
| `org.department.create`、`org.department.list`、`org.department.get`、`org.department.update`、`org.department.setLeader`、`org.department.move`、`org.department.freeze`、`org.department.unfreeze`、`org.department.archive` | Sidecar RPC | P2-T2、P4-T2 / `organization/service.py` | `test_department_rpc.py` / 公司与组织页 |
| `org.employee.create`、`org.employee.list`、`org.employee.get`、`org.employee.update`、`org.employee.setManager`、`org.employee.activate`、`org.employee.resume`、`org.graph.get` | Sidecar RPC | P4-T2 / `organization/service.py` | `test_employee_rpc.py` / 职员、组织图页 |
| `org.employee.suspend`、`org.employee.archive` | Sidecar RPC | P4-T2/P4-T5/P7-T5/P9-T1b / `organization/service.py`、`organization/employee_drain_service.py` | `test_employee_drain_rpc.py` / 职员、人工干预中心 |
| `org.employee.transfer` | Sidecar RPC | P4-T5、P7-T4 / `organization/employee_drain_service.py` | `test_transfer_rpc.py` / 职员页 |
| `org.employee.upgradeCapability` | Sidecar RPC | P4-T2a、P7-T2 / `organization/service.py` | `test_employee_capability_upgrade.py` / 职员页 |
| `org.template.create`、`org.template.saveDraft`、`org.template.list`、`org.template.get`、`org.template.update`、`org.template.archive` | Sidecar RPC | P4-T1 / `organization/template_service.py` | `test_template_rpc.py` / 职员模板页 |
| `org.permission.resolve` | Sidecar RPC | P4-T3 / `organization/permission_engine.py` | `test_permission_rpc.py` / 权限诊断页 |
| `org.grant.create`、`org.grant.list`、`org.grant.get`、`org.grant.revoke` | Sidecar RPC | P4-T4 / `organization/grant_service.py` | `test_grant_rpc.py` / 授权管理页 |
| `cap.skill.create`、`cap.skill.saveDraft`、`cap.skill.list`、`cap.skill.get`、`cap.skill.version.list`、`cap.skill.createVersion`、`cap.skill.submitReview`、`cap.skill.publish`、`cap.skill.deprecate`、`cap.skill.archive` | Sidecar RPC | P3-T1、P3-T5、P3-T6 / `capability/skill_service.py` | `test_skill_rpc.py` / 能力中心 |
| `cap.prompt.create`、`cap.prompt.saveDraft`、`cap.prompt.list`、`cap.prompt.get`、`cap.prompt.version.list`、`cap.prompt.createVersion`、`cap.prompt.submitReview`、`cap.prompt.publish`、`cap.prompt.deprecate`、`cap.prompt.archive` | Sidecar RPC | P3-T1、P3-T5、P3-T6 / `capability/prompt_service.py` | `test_prompt_rpc.py` / 能力中心 |
| `cap.capability.create`、`cap.capability.saveDraft`、`cap.capability.list`、`cap.capability.get`、`cap.capability.version.list`、`cap.capability.createVersion`、`cap.capability.submitReview`、`cap.capability.publish`、`cap.capability.deprecate`、`cap.capability.archive` | Sidecar RPC | P3-T2、P3-T5、P3-T6 / `capability/service.py` | `test_capability_rpc.py` / 能力中心 |
| `cap.snapshot.build`、`cap.metrics.get` | Sidecar RPC | P3-T3、P3-T7 / `capability/snapshot.py`、`metrics.py` | `test_snapshot_rpc.py`、`test_metrics_rpc.py` / 能力中心 |
| `cap.engine.resolve` | internal-only | P5-T2 / `capability/engine.py` | `test_engine_contract.py` / 无直接 UI |
| `task.create`、`task.get`、`task.list` | Sidecar RPC | P9-T1、P9-T2 / `task/service.py` | `test_task_rpc.py` / 任务中心 |
| `task.cancel` | Sidecar RPC | P9-T10 / `task/service.py` | `test_task_cancel_rpc.py` / 任务中心 |
| `task.retrySubtask` | Sidecar RPC | P9-T10 / `task/retry_service.py` | `test_retry_rpc.py` / 任务中心 |
| `workflow.checkpoint.list` | Sidecar RPC | P9-T8 / `task/checkpoint.py` | `test_checkpoint_rpc.py` / 任务中心 |
| `workflow.humanIntervention.list` | Sidecar RPC | P11-T2 / `observability/views.py` | `test_human_intervention_rpc.py` / 人工干预中心 |
| `workflow.deadletter.resolve`、`workflow.manualTask.complete`、`workflow.employeeDrain.resolve` | Sidecar RPC | P9-T11 / `task/human_intervention.py` | `test_human_intervention.py` / 人工干预中心 |
| `workflow.companyDissolution.resolve` | Sidecar RPC | P2-T1 / `organization/dissolution.py` | `test_company.py` / 人工干预中心 |
| `workflow.backendRecovery.resolve` | Sidecar RPC | P6-T1c / `backends/reconciler.py` | `test_backend_recovery.py` / 人工干预中心 |
| `session.list`、`session.get`、`session.sendMessage`、`session.cancel`、`session.transcript.get` | Sidecar RPC | P7-T1、P7-T2 / `runtime/service.py` | `test_session_rpc.py` / 会话页 |
| `session.resume` | internal-only | P7-T3 / `runtime/resume.py` | `test_session_resume.py` / 无直接 UI |
| `approval.list`、`approval.resolve` | Sidecar RPC | P10-T1 / `governance/approvals.py` | `test_approval_rpc.py` / 人工干预中心 |
| `kg.search` | Sidecar RPC | P8-T4 / `knowledge/retriever.py` | `test_search_rpc.py` / 知识库 |
| `kg.document.list`、`kg.document.get`、`kg.citation.get`、`kg.source.delete`、`kg.knowledge.reject`、`kg.knowledge.confirm`、`kg.ingest.retry` | Sidecar RPC | P8-T4a / `knowledge/service.py` | `test_knowledge_service_rpc.py` / 知识库 |
| `kg.reindex` | Sidecar RPC | P8-T3、P8-T5 / `knowledge/vector_store.py` | `test_reindex_rpc.py` / 知识库 |
| `provider.list`、`provider.model.list`、`provider.pricingPolicy.update`、`provider.budgetFreeze.clear`、`provider.tierMapping.update`、`provider.probeAll`、`provider.checkAvailability` | Sidecar RPC | P6-T1/P6-T1a/P6-T5 / `providers/registry.py`、`providers/pricing.py` | `test_provider_rpc.py`、`test_pricing.py` / Provider 配置页 |
| `provider.credential.set`、`provider.credential.delete` | Tauri-only | P6-T2、P12-T9 / `keychain.rs` | Rust command contract / Provider 配置页 |
| `provider.credential.resolve` | internal-only | P6-T2 / `credential_broker.rs`、`providers/credential_broker_client.py` | Rust/Python Broker 负向契约 / 无 WebView consumer |
| `backend.list`、`backend.get`、`backend.create`、`backend.update`、`backend.setDefault`、`backend.enable`、`backend.drain`、`backend.archive`、`backend.probe`、`backend.checkAvailability` | Sidecar RPC | P6-T1b/T1c / `backends/service.py`、`backends/health.py`、`backends/scheduler.py` | `test_backend_rpc.py`、`test_health.py`、`test_scheduler.py` / Backend 管理页 |
| `gov.budget.get` | Sidecar RPC | P10-T2 / `governance/budget.py` | `test_budget_rpc.py` / 任务、审计页 |
| `gov.audit.query` | Sidecar RPC | P11-T2 / `observability/views.py` | `test_audit_query_rpc.py` / 审计页 |
| `settings.embeddingPolicy.get`、`settings.embeddingPolicy.update`、`settings.budgetDefault.get`、`settings.budgetDefault.update` | Sidecar RPC | P12-T9 / `settings/service.py` | `test_company_settings_rpc.py` / 设置页 |
| `settings.knowledgePolicy.get`、`settings.knowledgePolicy.update` | Sidecar RPC | P8-T2 / `knowledge/policy_service.py` | `test_knowledge_policy.py` / 设置页 |
| `settings.backupPolicy.get`、`settings.backupPolicy.update` | Tauri-only | P12-T9 / `backup.rs` | Rust backup policy command contract / 设置页 |
| `settings.backup.create`、`settings.backup.list`、`settings.backup.restore`、`settings.backup.delete` | Tauri-only | P1-T4b、P12-T9 / `backup.rs` 调内部 snapshot service | Rust command + 跨存储恢复测试 / 设置页 |
| `settings.update.status`、`settings.update.check`、`settings.update.apply` | Tauri-only | P12-T9 / `updater.rs` | Rust 更新事务测试 / 设置页 |
| `sys.health`、`sys.migration.status` | Sidecar RPC | P0-T2、P1-T4 / `rpc/server.py`、`store/migrator.py` | `test_system_rpc.py` / 总览、设置页 |
| `sys.storageQuota.get` | Sidecar RPC | P11-T2 / `store/quota.py` | `test_storage_quota_rpc.py` / 设置、审计页 |

服务端通知也必须登记 producer 与消费测试，但不作为请求方法注册：`notify.runtimeEvent/sessionStatus` 由 P6/P7 产生并由会话页消费；`notify.taskProgress` 由 P9 产生并由任务页消费；`notify.approvalRequested` 由 P10 产生并由人工干预中心消费；`notify.knowledgeStatus` 由 P8 产生并由知识库消费，其 `status` 严格复用 `knowledge_ingestion_jobs` 的 `pending|running|retryable|succeeded|failed|cancelled`，不建第二套 UI 状态机；`notify.backendStatus` 由 P6-T1b/T1c 在 lifecycle/health/queue/lease/recovery 变化时产生，携带 Backend/全局 held/limit、waiting/open recovery 计数，由 Dashboard、Backend 管理页和人工干预中心消费。所有通知统一通过 P1-T3 的 NDJSON `stream_id + sequence` 契约测试。

**完成条件**：附录 B 的 140 个请求方法在 `coverage.yaml` 中各恰好出现一次；所有非内部方法至少有一条成功和一条权限/校验失败契约测试；所有写方法声明幂等策略；UI 使用的方法均指向已存在的 handler。矩阵校验与全量契约测试通过后，RPC 接口才允许冻结。

---

# review 问题汇总

> 以下问题由实施方案与设计方案交叉审阅产生，按类别分为：设计方案内部问题、两文档不一致、实施计划模糊/缺失。每条标注涉及的设计章节和实施任务编号，供定向修正。
>
> **变更说明**：本次审阅（第 2 轮）基于全文逐行通读两份文档后重新生成。第 1 轮中部分审阅项存在文档定位错误（如误判表字段"缺失"实际已定义在附录 D ER 图中），本轮已修正。同时新增了第 1 轮未覆盖的问题。

---

## A. 设计方案内部问题

### A-1 §6.10 `employee_type` 作为"字段"与"派生列"的双重身份表述不清

**涉及章节**：§6.10（Employee）

§6.10 将 `employee_type: company_leader | department_leader | employee` 列在 Employee 的字段清单中，紧接着又说"新建普通职员时由服务端固定初始化为 `employee`，RPC 和模板均不得传入该字段"。这两个表述在语义上是正确的（该列存在但由服务端派生写入），但对开发者而言容易产生歧义——它既像一个"可写字段"又像一个"只读派生属性"。§6.11 ER 图中同样将该字段列为普通列，未标注派生属性。

**建议**：在 §6.10 的字段列表中对该字段加注释标注 `(derived, read-only)`，或在字段说明首句明确"此字段由服务端根据领导关系自动维护，RPC 和模板不可设置"。

---

### A-2 §5.5 审计类型表述：正文列出 5 类但编号/标题不显式

**涉及章节**：§5.5（审计）

§5.5 正文明确说"五类业务 append-only 审计共同覆盖具体鉴权、知识查询、知识治理、组织变更和 Backend 变更"，并逐一定义了：`acl_audit_log`、`knowledge_access_logs`、`knowledge_governance_audit`、`org_change_audit`、`backend_change_audit`。但段落标题未使用"审计一～五"之类的显式编号，开发者需要逐段计数才能确认总数。

**建议**：使用编号列表（如 `① acl_audit_log` … `⑤ backend_change_audit`）以减少计数错误。

---

### A-3 §11.4 线程状态机与 §10 任务运行状态机的边界不够显式

**涉及章节**：§10（任务与工作流）、§11.4（会话线程）

§10 定义 `task_run` 的状态机为 `created→waiting_backend→running↔waiting_approval→succeeded|failed|cancelled`；§11.4 定义线程状态机为 `idle→running→idle`，加上 `waiting_backend`、`waiting_approval`、`dormant`、`archived`。两者在 `waiting_backend` 和 `waiting_approval` 上有交集，但 §11.4 未显式说明"线程的 `waiting_backend`/`waiting_approval` 状态分别对应 task_run 的同名状态"。在实现 P7-T5 时，开发者需要自行推断这两个状态机的映射关系。

**建议**：§11.4 补充一段说明，指出线程 `waiting_backend`/`waiting_approval` 与 task_run 同名状态的因果关系。

---

### A-4 §6.8 `skill_bindings` / §10.1.3 `tool_calls` / `workspace_changes` 表字段定义不完整

**涉及章节**：§6.8、§10.1.3、§15（迁移清单）

设计方案在正文中多次引用以下表，但未在任何节给出完整的字段列表：

1. **`skill_bindings`**——§6.8 提到"Capability 进入 review 后 bindings 不可修改"；§6.5 提到它按 ordinal 投影 `skill_set`；附录 D ER 图标注了 `binding_id, capability_id, capability_version, ordinal, skill_id, skill_version, skill_version_checksum, created_at`，但正文中无独立的表定义节。
2. **`tool_calls`**——§10.1.3 提到"Runtime 在执行前写 tool call 并 CAS 状态"，但未给出完整字段列表。实施计划 P9-T1 提到 `tool_calls` 有 `request_hash, approval_id, authorization_audit_id, side_effect_state, result_ref, version`，但这些字段在设计方案中散落于不同段落，无统一定义。
3. **`workspace_changes`**——§10.1.3 提到"append-only change_type/path hash/before-after hash/artifact/tool_call 关联"，但字段列表同样不完整。

**影响**：P9-T1 实施时需从多处拼凑字段定义，易遗漏或错解。

**建议**：§6.8/§10.1.3 分别补充 `skill_bindings`、`tool_calls`、`workspace_changes` 的完整字段表，或在附录 D ER 图中补充这些表的详细字段块（目前附录 D 仅对部分表列出了字段）。

---

### A-5 §10.1.3 Evidence 状态机：`cancelled` 任务时 evidence 级联行为未定义

**涉及章节**：§10.1.3（证据链）

§10.1.3 定义了四类 evidence 的状态转换，但未说明 `task.cancel` 导致节点进入 `cancelled` 终态时，各 evidence 对象如何级联：
- `report` 从 `draft` 能否直接到终态（如 `archived`）？还是保留在 `draft`？
- `finding` 未收敛时（仍有 `open` 或 `accepted` 项），任务被取消后这些 finding 的最终状态是什么？
- `fix_item` 处于 `running` 时任务被取消，是否需要终止并标记为 `wont_fix`？

**影响**：P9-T10 实现 `task.cancel` 时需自行设计级联规则，不同开发者可能做出不一致的决策。

**建议**：§10.1.3 补充"任务取消时 evidence 级联规则"小节，明确定义每类 evidence 在 `cancelled` 场景下的终态。

---

## B. 两文档不一致

### B-1 `knowledge_ingestion_jobs` 的 6 个状态值在两文档中一致但 P8-T2 描述顺序不同

**涉及章节**：§9.2（设计方案）、P8-T2 / RPC 矩阵（实施计划）

§9.2 列出 `pending|running|retryable|succeeded|failed|cancelled`；RPC 矩阵也列出同样的 6 个值；但 P8-T2 正文未显式列出这 6 个状态。

**影响**：低风险，但为一致性建议在 P8-T2 补充显式状态列表。

---

### B-2 设计方案 §5.5 的 RetentionCompactor 描述与实施计划 P11-T2 的覆盖范围不完全对齐

**涉及章节**：§5.5（设计方案）、P11-T2（实施计划）

§5.5 描述 RetentionCompactor 的工作范围为"仅处理超过 90 天、`decision=allow` 且没有引用的 `acl_audit_log/knowledge_access_logs` 明细"，并要求"在同一事务先写不可变日聚合与 `audit_compaction_manifests`"。实施计划 P11-T2 提到"RetentionCompactor with 90-day threshold and `NOT EXISTS` reference check"，但**未提及 `audit_compaction_manifests` 表**的建表和写入逻辑。迁移清单 §5.1 确认 `audit_compaction_manifests` 属于 `0002_audit_tables.sql`（由 P1-T5 负责建表），但 P11-T2 的实现要点和测试中均未提及该表的使用。

**影响**：P11-T2 实现时可能遗漏 compaction manifest 写入，导致 compaction 不可审计。

**建议**：P11-T2 补充"RetentionCompactor 同事务写入 `audit_compaction_manifests`，幂等键为 `(log_type, company_id, date)`"。

---

### B-3 设计方案 §6.8 快照 lock 结构与实施计划 P3-T3 的字段描述部分不一致

**涉及章节**：§6.8（设计方案）、P3-T3（实施计划）

§6.8 的快照 lock 描述为 `capability.lock = {capability_id, capability_version, dependency_tree[{skill_id,version,checksum},{prompt_asset_id,version,checksum}], snapshot_checksum, published_at}`。但 P3-T3 的 `build_snapshot` 产出描述为 `capability.lock = {capability_id, capability_version, dependency_tree[{skill_id,version,checksum},{prompt_asset_id,version,checksum}], snapshot_checksum, published_at}`——内容一致但 P3-T3 额外提到"完整 snapshot 与 lock 持久化到 `capability_snapshots`"，其中包含 `snapshot_json, dependency_tree` 两个字段，lock 结构与存储字段的关系不够清晰（`snapshot_json` 是否就是 lock 本身？还是 lock 的超集？）。

**影响**：开发者不确定 `capability_snapshots.snapshot_json` 存储的完整内容是什么。

**建议**：P3-T3 明确 `snapshot_json` 的 schema（建议 = lock 本身，或包含 lock + 扩展字段），并说明与 `dependency_tree` 列的关系（冗余存储 vs 派生）。

---

### B-4 `settings.backup.restore` 的 `backup_id` 参数在附录 B 中未明确定义

**涉及章节**：附录 B.6（设计方案）

附录 B.6 的 `settings.backup.restore` 方法 params 列为 `backup_id | all`，但未定义 `backup_id` 的类型和来源（UUID? 引用 `backup_manifests.backup_id`?）。P1-T4b 实现了 `backup_manifests` 表并提供 `list_snapshots()` 接口，但 `restore` 的参数校验规则（如：只接受 `status=available` 的 backup）在附录 B 中未提及。

**影响**：前端开发和契约测试时不确定 restore 的入参约束。

**建议**：附录 B.6 补充 `settings.backup.restore` 的参数校验规则："只接受 `status=available` 且 `deleted_at IS NULL` 的 backup_id；`all` 表示恢复最近一份可用备份"。

---

## C. 实施计划模糊/缺失

### C-1 P1-T1 错误码常量未引用附录 C 的完整枚举

**涉及章节**：P1-T1、附录 C

P1-T1 说"模块前缀常量 `ORG_*`、`CAP_*`、`WF_*` 等"，但未引用设计方案附录 C 中的完整错误码表。开发者需要自行从附录 C 整理常量列表。附录 C 中每个领域小节末尾都列出了该领域的错误码（如 `ORG-VALIDATION`、`ORG-NOT-FOUND`、`ORG-STATE-INVALID` 等），但 P1-T1 未指定实现范围（是先实现所有错误码，还是按 Phase 逐步补充？）。

**建议**：P1-T1 补充"常量列表以附录 C 为准，首版实现 §5.1 示例中的核心错误码子集（约 30 个），后续 Phase 按需补充"。

---

### C-2 P3-T3 Capability Snapshot 的 `build_snapshot` 逻辑缺乏详细说明

**涉及章节**：P3-T3、§6.8

P3-T3 描述"build_snapshot produces dependency_tree with checksums, persists to capability_snapshots"，但未说明 `build_snapshot` 的输入和 `dependency_tree` 的结构。§6.8 定义了 lock 的结构（见 B-3），P3-T3 补充了 lock 内容的具体字段，但以下细节仍缺失：
- `dependency_tree` 中每个条目是否包含 `ordinal`（与 `skill_bindings.ordinal` 对应）？
- lock 的 `snapshot_checksum` 覆盖范围是什么？（是 dependency_tree 所有 checksum 的哈希？还是包含 `published_at`？）
- 当 Skill 或 Prompt Asset 的 checksum 在 lock 生成后变化时，`CAP-SNAPSHOT-CHECKSUM-MISMATCH` 的具体检测逻辑是"逐条比对 dependency_tree 条目与当前实际 checksum"？

**影响**：P3-T3 的 DoD 不足以让开发者写出确定性代码。

**建议**：P3-T3 补充 `build_snapshot` 的伪代码或决策表，明确 checksum 计算范围与 mismatch 检测逻辑。

---

### C-3 P4-T5 Employee Drain 超时值未指定

**涉及章节**：P4-T5

P4-T5 描述"background drain waits for assignment terminal state"和"HumanIntervention on timeout"，但未指定超时时长。§11.4 的调岗时序图 C.3 提到"超时→人工 reassign 或继续等待"，但同样未给出具体数值。

**影响**：开发者需要自行决定超时值，可能导致不同实现之间行为不一致。

**建议**：在 P4-T5 或 §6.10 中指定 drain 超时值（例如 10 分钟），并标注该值可通过 `knowledge_policies` 或公司配置调整。

---

### C-4 P7-T4 Handoff Crash Reconciler 恢复步骤不完整

**涉及章节**：P7-T4、§11.4、附录 C.3

P7-T4 提到"crash reconciler: `reconciler_scan_transferring()` detects incomplete staging → `needs_repair`"，但未说明 `needs_repair` 状态下恢复器的具体修复步骤。§11.4 和附录 C.3 提到"若在 FS 操作阶段崩溃:重启后对账器扫描 transferring 状态职员,能安全判定已完成则补提交(写 EmployeeTransferred),否则置 needs_repair+写 EmployeeTransferNeedsRepair 转人工确认"——这里给出了两个分支（已完成→补提交、未完成→needs_repair），但"能安全判定已完成"的判定条件未定义。

**影响**：开发者无法确定对账器的判定逻辑边界。

**建议**：P7-T4 补充判定条件："（1）staging 路径下的 session.json 与目标线程的 `security_context_key` 一致且文件完整 → 完成 rename + 更新 pointer + 补写 EmployeeTransferred；（2）staging 文件不存在或不完整 → 删除 staging 残留 + 保持 `needs_repair` + 写 EmployeeTransferNeedsRepair 转人工"。

---

### C-5 P13-T3 性能指标中 `observational` 类别缺乏明确的基线目标

**涉及章节**：P13-T3、§4.5

§4.5 列出了 `task_recovery_ready_time`、`provider_native_resume_e2e_time`、`provider_probe_e2e_time` 标注为 `observational`。P13-T3 说"首版先记录基线"，但未说明"积累基线"的判定标准。

**影响**：v1 发布时这些指标的达标标准不明确。

**建议**：P13-T3 补充"observational 指标在 v1 发布前记录基线值，不设 release_gate；v2 规划时根据基线数据决定是否升级为 release_gate"。

---

### C-6 P9-T1 Evidence 状态转换未覆盖 cancelled 场景

**涉及章节**：P9-T1、§10.1.3

P9-T1 列出了 evidence 的合法状态转换，但未说明 `task.cancel` 导致节点进入 `cancelled` 终态时，各 evidence 对象的级联行为（见 A-5）。P9-T1 的测试项也未覆盖"任务取消后 evidence 状态"场景。

**建议**：P9-T1 补充测试用例："任务取消时，running 的 fix_item 被终止为 `wont_fix`，draft 的 report 保留 `draft` 状态（不自动变为 final）；同时验证非法转换（如 cancelled 节点的 finding 从 `open` 转 `resolved`）被拒绝"。

---

### C-7 P12-T9 Settings 更新失败行为未指定

**涉及章节**：P12-T9

P12-T9 描述 `settings.service.py` 是 embedding/budget defaults 的唯一 handler，但未说明以下失败场景的处理：
- Policy version CAS 失败时返回什么错误？（推测为 `SYS-OPTIMISTIC-LOCK-CONFLICT`，但未显式说明）
- 嵌入策略和预算默认值分别更新、部分成功部分失败时的行为？（两者的 CAS target 不同：embedding 用 `expected_policy_version`，budget 用 `expected_company_version`，它们是独立的还是在同一事务中？）

**建议**：P12-T9 补充失败语义："embedding policy 和 budget default 更新是独立操作，各自在独立事务中完成；CAS 失败返回 `SYS-OPTIMISTIC-LOCK-CONFLICT`，客户端需重新 get 后重试"。

---

### C-8 P6-T1c BackendScheduler 跨 Backend 调度测试覆盖不足

**涉及章节**：P6-T1c、§6.11

§6.11 描述了 Backend 与全局双层限流的 FIFO 语义。P6-T1c 的测试覆盖了并发 lease 争抢和三种 wait_reason，但以下场景在测试中未显式覆盖：
- 多 Backend 并发满载时全局空槽分配的公平性（3 个 Backend 各 limit=2，global=5 的样例）
- `global_process_limit` 首次 bootstrap 注入时的时序（P6-T1c 从 Rust 加载配置，需确保 Sidecar 启动时配置已就绪）

**建议**：P6-T1c 补充测试用例："3 个 Backend 各 limit=2、global=5，当 A 满载、B 满载、C 有 1 空槽时，全局第 5 个任务必须分配到 C"；并补充"Sidecar 冷启动时 `global_process_limit` 从 Rust bootstrap 消息注入，在注入完成前 `acquire_next` 返回 `BACKEND-UNAVAILABLE`"。

---

### C-9 RPC 矩阵中 `notify.backendStatus` 的触发时机与 P6-T1b/P6-T1c 的任务边界不清晰

**涉及章节**：RPC 矩阵、P6-T1b、P6-T1c

RPC 矩阵说 "`notify.backendStatus` 由 P6-T1b/T1c 在 lifecycle/health/queue/lease/recovery 变化时产生"，但 P6-T1b（Backend registry）和 P6-T1c（BackendScheduler）的任务描述中均未明确"产生 `notify.backendStatus` 通知"这一职责。

**影响**：开发者可能在 P6-T1b/T1c 中遗漏通知发送逻辑。

**建议**：P6-T1b 补充"每次 lifecycle 状态变更和 probe 结果变化时发送 `notify.backendStatus`"；P6-T1c 补充"每次 lease 获取/释放/queue 变化/recovery 完成时发送 `notify.backendStatus`"。

---

### C-10 P8-T2 知识提取 pipeline 未覆盖"对话事件来源"的特殊处理

**涉及章节**：P8-T2、§9.2

§9.2 定义 `knowledge_sources.source_type` 包括 `conversation_event|domain_event|artifact|file|manual`。P8-T2 描述了通用的 extraction 流程，但未说明：
- `conversation_event` 来源是否需要特殊的对话上下文拼接（如将同一线程内的多条消息合并为一个 extraction unit）？
- `manual` 来源是否跳过 extraction 直接创建 document？
- `file` 来源的文件内容读取是否受 Workspace 路径限制（Path Broker 校验）？

**建议**：P8-T2 补充"按 `source_type` 分支处理：conversation_event 需按 thread 聚合后提取；manual 来源跳过 extraction 直接入库；file 来源受 Path Broker 校验"。

---

### C-11 P1-T4b `backup.restore_snapshot` 的 `backup_id` 参数校验规则未在实施计划中说明

**涉及章节**：P1-T4b、附录 B.6

P1-T4b 实现了 `create_snapshot`、`restore_snapshot`、`list_snapshots`、`delete_snapshot` 四个接口，但 `restore_snapshot` 的参数校验规则（如：只接受 `status=available` 的 backup）在实施计划中未说明。附录 B.6 的 `settings.backup.restore` 同样未定义 `backup_id` 的校验规则（见 B-4）。

**影响**：P12-T9 实现前端 restore 入口时，以及 P13-T4 演练脚本时，不确定 restore 的入参约束。

**建议**：P1-T4b 补充 `restore_snapshot(backup_id)` 的校验规则："backup_id 必须指向 `status=available` 且 `deleted_at IS NULL` 的 manifest 行；不存在或已删除返回 `SYS-BACKUP-NOT-FOUND`"。

---

### C-12 P9-T1b `active_turn_id` 的 CAS 语义在实施计划中未详细说明

**涉及章节**：P9-T1b、§11.4

§11.4 ER 图中 `session_threads.active_turn_id` 标注为"nullable, DB CAS owner"，暗示该字段是 turn 级别的互斥锁。P7-T1/P7-T2 创建了该表，P9-T1b 引用了它，但以下 CAS 语义在实施计划中未显式说明：
- 获取 `active_turn_id` 的 CAS 模式：`UPDATE session_threads SET active_turn_id = ? WHERE active_turn_id IS NULL AND thread_id = ?`？
- 释放时的 CAS：`UPDATE session_threads SET active_turn_id = NULL WHERE active_turn_id = ? AND thread_id = ?`？
- Sidecar 重启后，如何判定 `active_turn_id` 对应的进程已死亡并安全释放？

**影响**：P7-T2 和 P9-T5 实现 turn 锁时可能使用内存锁而非数据库 CAS，导致 Sidecar 重启后出现双 active turn。

**建议**：§11.4 或 P7-T2 补充 `active_turn_id` 的 CAS 获取/释放伪代码，以及重启后的恢复规则（与 P6-T1c 的 lease 对账类似：核对 process token + heartbeat 时间，无法确认则转 intervention）。

---

## D. 总结

| 类别 | 数量 | 严重程度 |
|---|---|---|
| 设计方案内部问题（A） | 5 | 中（A-4 影响 3 张表建表，A-5 影响 cancel 级联） |
| 两文档不一致（B） | 4 | 中（B-2、B-3 可能导致功能缺失或数据不一致） |
| 实施计划模糊/缺失（C） | 12 | 高（C-1、C-2、C-4、C-6、C-9 阻塞开发） |

**建议优先处理**：C-1（错误码枚举）、C-2（snapshot 结构）、C-4（handoff 恢复）、C-9（通知职责分配），这四项若不在开发前澄清，将直接阻塞对应 Phase 的编码工作。
