# Runtime 选型 Spike - OpenHands SDK 使用边界决策记录

> 最后更新：2026-07-19  
> 项目：iBreeze AI 公司桌面应用  
> 状态：已决策（ADR-001）  
> 决策人：技术团队

---

## 1. 选型背景

### 1.1 自研契约定义

iBreeze 的 Agent Runtime / ProviderAdapter / Workspace / Employee 会话是**自研契约**，定义了系统的核心边界：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Agent Runtime                               │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    ProviderAdapter                           │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │  │
│  │  │  CLI Provider│  │ API Provider│  │ Local Provider│         │  │
│  │  │  Driver      │  │ Driver      │  │ Driver       │         │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘          │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                     Workspace                                │  │
│  │  - 文件系统隔离                                                │  │
│  │  - 依赖管理                                                    │  │
│  │  - 沙箱执行                                                    │  │
│  └───────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                     Employee Session                         │  │
│  │  - 会话恢复                                                    │  │
│  │  - 事件流                                                      │  │
│  │  - 取消/超时                                                   │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 OpenHands SDK 定位

OpenHands SDK（`openhands-sdk`）是一个开源的 AI Agent 框架，提供：
- Agent 运行时环境
- 工具调用抽象
- 事件流处理
- Workspace 管理

**关键认知**：OpenHands SDK 至多作为某个代码类 CLI Provider Driver 的**内部实现细节**，不进入核心契约层。

### 1.3 选型目标

评估 OpenHands SDK 是否适合作为：
- CLI Provider Driver 的实现基础
- 会话管理的参考
- 工具调用的扩展点

---

## 2. 验证项目

### 2.1 能力清单

| # | 能力 | 描述 | 验证优先级 |
|---|------|------|-----------|
| 1 | CLI Provider 包装 | 将 OpenHands 包装为 CLI Provider Driver | P0 |
| 2 | 原生会话恢复 | Session 可序列化/反序列化，支持断点续跑 | P0 |
| 3 | 事件流式输出 | 实时流式返回 Agent 思考/工具调用/输出 | P0 |
| 4 | 取消 | 支持中断正在运行的 Agent 任务 | P1 |
| 5 | Workspace 挂载 | 指定工作目录，Agent 在受限环境操作 | P1 |
| 6 | 工具调用 | 定义/调用自定义工具，返回结构化结果 | P1 |

### 2.2 验证方法

对每项能力，进行以下验证：
1. **可行性检查**：SDK 是否提供该能力的 API
2. **适配成本**：需要多少包装代码才能融入自研契约
3. **约束冲突**：SDK 的假设是否与我们的契约冲突

---

## 3. 能力映射表

| 能力 | SDK 支持度 | 自研需求 | 映射关系 | 适配成本 |
|------|-----------|---------|---------|---------|
| **CLI Provider 包装** | 部分 | 完整 CLI 子进程管理 | SDK 提供 `Runtime` 类，但需包装为 CLI 接口 | 中等 |
| **原生会话恢复** | 内置 | 自定义序列化格式 | SDK 有 Session 持久化，但格式自定义 | 高 |
| **事件流式输出** | 内置 | 自定义事件类型 | SDK 有 EventStream，但类型定义不同 | 高 |
| **取消** | 部分 | 完整取消 + 资源清理 | SDK 有 `cancel()`，但清理逻辑不完整 | 中等 |
| **Workspace 挂载** | 内置 | 自定义挂载规则 | SDK 有 Workspace，但隔离级别不同 | 高 |
| **工具调用** | 内置 | 自定义工具注册 | SDK 有 Tool 定义，但接口不同 | 高 |

### 3.1 映射关系详解

#### CLI Provider 包装

```python
# 我们的契约
class CLIProviderDriver(ProviderDriver):
    async def run(self, task: str, workspace: Workspace) -> AsyncIterator[Event]:
        proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # 流式输出处理...
        yield Event(type="thinking", content="...")
```

```python
# OpenHands SDK 的 Runtime
from openhands import Runtime

runtime = Runtime(config)
await runtime.initialize()
action = MessageAction(content=task)
observation = await runtime.run_action(action)
# 问题：返回单个结果，不支持流式
# 问题：事件类型与我们的 Event 不兼容
```

**适配方案**：需要写一个 `OpenHandsCLIProviderDriver` 包装 SDK 的 `Runtime`，将 SDK 事件转换为我们的 Event 类型。成本：~200 行代码。

#### 原生会话恢复

```python
# 我们的契约
@dataclass
class Session:
    session_id: str
    messages: List[Message]
    state: Dict[str, Any]  # 可序列化
    created_at: datetime

    def serialize(self) -> bytes: ...
    @classmethod
    def deserialize(cls, data: bytes) -> 'Session': ...
```

```python
# OpenHands SDK 的 Session
from openhands import Session

session = Session(runtime)
# 问题：Session 内部状态不完全可序列化
# 问题：与我们的 Session 字段不兼容
# 问题：恢复后需要重新初始化 Runtime
```

**适配方案**：放弃 SDK 的 Session，完全自研。成本：~500 行代码。

#### 事件流式输出

```python
# 我们的契约
class Event:
    type: Literal["thinking", "tool_call", "tool_result", "output", "error"]
    content: str
    metadata: Dict[str, Any]
    timestamp: datetime

class ProviderDriver(ABC):
    @abstractmethod
    async def run(self, task: str, workspace: Workspace) -> AsyncIterator[Event]: ...
```

```python
# OpenHands SDK 的 EventStream
from openhands.events import EventStream, Event

stream = EventStream()
# 问题：事件类型是 Action/Observation，不是我们的 Event
# 问题：需要转换层
# 问题：流式输出的 backpressure 处理不同
```

**适配方案**：包装 SDK 的 EventStream，做事件类型转换。成本：~300 行代码。

---

## 4. 决策结论

**结论：不使用 OpenHands SDK，Phase 6 的 CLI Provider Driver 全部自研。**

### 4.1 决策矩阵

| 维度 | 使用 SDK | 自研 |
|------|---------|------|
| 开发速度（初期） | 快（有参考） | 慢（从零开始） |
| 维护成本（长期） | 高（适配层持续维护） | 低（代码完全可控） |
| 契约一致性 | 低（需转换层） | 高（原生实现） |
| 灵活性 | 受限于 SDK 设计 | 完全自由 |
| 依赖风险 | 中（SDK 更新可能破坏） | 无 |
| 学习成本 | 中（需理解 SDK 内部） | 低（代码即文档） |

### 4.2 关键数据点

| 指标 | 值 |
|------|-----|
| SDK 适配层代码量估算 | ~1000-1500 行 |
| 自研核心代码量估算 | ~800-1200 行 |
| SDK 版本稳定性 | 中（活跃开发中，API 变化频繁） |
| SDK 文档完整性 | 低（主要靠源码） |
| 我们的契约确定性 | 高（已设计完成） |

---

## 5. 决策理由

### 5.1 SDK 的对象模型与自研契约冲突过大

OpenHands SDK 的核心抽象是 `Runtime` → `Action` → `Observation`，而我们的契约是 `ProviderDriver` → `Event` → `Workspace`。

**具体冲突点**：

1. **Runtime vs ProviderDriver**
   - SDK 的 `Runtime` 是一个重量级对象，包含完整的沙箱环境
   - 我们的 `ProviderDriver` 是轻量级接口，只负责任务执行
   - 包装 SDK 需要在 `Runtime` 外面再套一层，增加复杂度

2. **Action/Observation vs Event**
   - SDK 的事件是 `Action`（Agent 做的）和 `Observation`（环境返回的）
   - 我们的事件是 `Event`（统一的流式输出）
   - 两种模型语义不同，转换困难

3. **Session 持久化**
   - SDK 的 Session 依赖 Runtime 状态
   - 我们的 Session 是纯数据，可独立恢复
   - 两种设计目标不同，无法兼容

### 5.2 适配成本高于自研

| 工作项 | 适配 SDK | 自研 |
|--------|---------|------|
| CLI Provider Driver | ~200 行包装 | ~150 行原生 |
| 会话恢复 | ~400 行适配 | ~300 行原生 |
| 事件流转换 | ~300 行适配 | ~200 行原生 |
| 取消逻辑 | ~150 行适配 | ~100 行原生 |
| Workspace 挂载 | ~300 行适配 | ~200 行原生 |
| 工具调用 | ~250 行适配 | ~200 行原生 |
| **总计** | **~1600 行适配 + 维护成本** | **~1150 行原生** |

**结论**：适配 SDK 的代码量比自研还多，且持续需要维护适配层。

### 5.3 我们的契约是确定的，SDK 的抽象不是为我们的场景设计的

我们的系统是**本地 AI 组织运行平台**，核心约束：
- 本地运行（无云端依赖）
- 桌面应用集成（Tauri）
- 多模型管理（ONNX, 本地 LLM）
- 员工会话管理（长期运行）

OpenHands SDK 的设计目标是：
- 云端 Agent 执行
- 代码生成/修改
- 通用工具调用
- 短期任务

**目标差异导致抽象不匹配**，强行使用只会增加复杂度。

---

## 6. 后续计划

### 6.1 Phase 6 自研范围

| 模块 | 实现方式 | 负责人 | 预计工期 |
|------|---------|-------|---------|
| CLI Provider Driver | 完全自研 | - | 2 周 |
| API Provider Driver | 完全自研 | - | 1 周 |
| Local Provider Driver | 完全自研 | - | 1 周 |
| Workspace 管理 | 完全自研 | - | 1 周 |
| 会话管理 | 完全自研 | - | 1 周 |
| 事件流 | 完全自研 | - | 1 周 |

### 6.2 参考 SDK 的设计

虽然不使用 SDK，但可以参考其设计思路：

1. **工具注册模式**：SDK 的工具注册表可以参考
2. **沙箱执行**：SDK 的沙箱隔离思路可以借鉴
3. **事件类型**：SDK 的 Action/Observation 分类可以参考

### 6.3 未来重新评估条件

如果以下条件满足，可以重新评估 SDK 使用：
1. SDK 提供稳定的 CLI Provider 接口
2. SDK 的 Session 持久化支持自定义格式
3. 我们的契约发生重大变化，与 SDK 对齐

---

## 7. ADR 状态

### 7.1 ADR-001: 不使用 OpenHands SDK

| 字段 | 值 |
|------|-----|
| ADR 编号 | ADR-001 |
| 标题 | 不使用 OpenHands SDK 作为 CLI Provider Driver 实现基础 |
| 状态 | **已决策** |
| 决策日期 | 2026-07-19 |
| 决策人 | 技术团队 |
| 影响范围 | Phase 6 CLI Provider Driver 实现 |

### 7.2 决策记录

**背景**：评估 OpenHands SDK 作为 CLI Provider Driver 实现基础的可行性。

**分析**：对 6 项核心能力进行验证，发现 SDK 的对象模型与自研契约冲突过大，适配成本高于自研。

**决策**：不使用 OpenHands SDK，Phase 6 的 CLI Provider Driver 全部自研。

**后果**：
- 正面：代码完全可控，无外部依赖，契约一致性高
- 负面：初期开发速度较慢，需要从零实现

### 7.3 变更流程

此决策已锁定。如需变更，必须：
1. 提交正式 ADR 变更请求
2. 技术团队评审
3. 评估变更影响
4. 批准后执行

---

## 附录 A：OpenHands SDK 调研记录

### A.1 SDK 版本信息

```bash
pip show openhands-sdk
# Name: openhands-sdk
# Version: 0.x.x
# Location: ...
```

### A.2 关键 API 调研

```python
# 1. Runtime 初始化
from openhands import Runtime, RuntimeConfig
config = RuntimeConfig(sandbox=SandboxConfig(...))
runtime = Runtime(config)

# 2. 执行 Action
from openhands.events.action import MessageAction
action = MessageAction(content="Hello, world!")
observation = await runtime.run_action(action)

# 3. 事件流
async for event in runtime.event_stream:
    print(event)

# 4. Workspace
from openhands import Workspace
workspace = Workspace(base_dir="/path/to/workspace")

# 5. 工具调用
from openhands.runtime.plugins import Plugin
class MyPlugin(Plugin):
    async def run(self, action):
        return Observation(content="result")
```

### A.3 调研结论

SDK 提供了完整的 Agent 运行时，但：
- API 设计面向云端场景
- Session 持久化格式自定义困难
- 事件类型与我们的不兼容
- 学习曲线陡峭

---

## 附录 B：自研契约详细设计参考

### B.1 ProviderDriver 接口

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator
from .event import Event
from .workspace import Workspace

class ProviderDriver(ABC):
    """Provider Driver 基类"""

    @abstractmethod
    async def run(
        self,
        task: str,
        workspace: Workspace,
        context: dict | None = None,
    ) -> AsyncIterator[Event]:
        """执行任务，流式返回事件"""
        ...

    @abstractmethod
    async def cancel(self, task_id: str) -> bool:
        """取消正在执行的任务"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        ...
```

### B.2 Event 类型

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Any

@dataclass
class Event:
    type: Literal["thinking", "tool_call", "tool_result", "output", "error"]
    content: str
    metadata: dict[str, Any] | None = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
```

### B.3 Session 接口

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Session:
    session_id: str
    messages: list[Message]
    state: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    def serialize(self) -> bytes:
        """序列化为字节流"""
        ...

    @classmethod
    def deserialize(cls, data: bytes) -> 'Session':
        """从字节流恢复"""
        ...

    def add_message(self, message: Message) -> None:
        """添加消息"""
        ...

    def get_context(self) -> dict[str, Any]:
        """获取会话上下文"""
        ...
```

---

## 附录 C：参考资源

- OpenHands SDK GitHub: https://github.com/All-Hands-AI/OpenHands
- OpenHands 文档: https://docs.all-hands.dev/
- 我们的自研契约设计: `docs/AI公司桌面应用设计方案.md`
- Phase 6 实施计划: `AI公司桌面应用-实施计划.md`
