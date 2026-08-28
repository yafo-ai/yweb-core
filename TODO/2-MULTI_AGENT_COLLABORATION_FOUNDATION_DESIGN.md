# YWeb Core 多 Agent 协作底层框架设计

本文档描述将多 Agent 协作、流程编排、消息通信、共享工作空间和远程 Agent 执行抽象为 YWeb Core 底层能力的方案。

设计以原 `y-agent` 的领域模型为主要基础，保留其有向有环图、动态下游选择、多路并行、多上游依赖、流程嵌套、分身、聊天室以及三类共享变量语义；同时用 YWeb 的 ORM、状态机、事件、权限、日志、存储、WebSocket 和工具执行层，将其升级为异步、持久化、可恢复、可审计、可远程执行的框架模块。

本文档描述底层框架，不包含可视化流程编辑器、具体 LLM 客户端、RAG、训练语料生产及具体业务 Agent。

***

## 1. 背景与目标

### 1.1 y-agent 已有能力

原 `y-agent` 已经形成一套比较完整的 Agent 协作语义：

- 有向有环流程图
- 多下游并行执行
- 多上游依赖汇合
- LLM 动态选择下游角色
- 边最大执行次数
- 跳过分支后的“虚拟执行”
- 嵌套流程和循环节点
- 同一节点拆分为多个分身并发执行
- 全局工作空间变量和角色变量
- 覆盖、追加、不重复追加三种变量写入方式
- Agent 聊天室
- `assignment`、`send_message`、`notify`、`terminate` 等 FCL 指令
- LLM、工具和固定流程混合编排

这些能力比通用状态图库更贴近 YWeb 的目标业务，应作为新框架的领域基础，而不是被简单替换。

### 1.2 当前实现需要升级的部分

原实现主要面向单进程内存执行：

- 流程定义和本次运行状态存放在同一个 Node 对象
- `run_times`、`virtual_run_times` 等状态只存在内存
- 节点完成后递归触发下游节点
- 并行主要依赖 `ThreadPoolExecutor`
- Workspace 是加锁的共享可变对象
- 聊天室是内存消息列表
- 服务退出后不能从执行点恢复
- 无法自然扩展到远程客户端、多进程和多服务实例

新设计保留领域语义，但重新实现运行内核。

### 1.3 目标

| 目标    | 说明                                       |
| ----- | ---------------------------------------- |
| 混合编排  | Agent、工具、固定函数、人工节点和子流程使用同一套调度模型          |
| 支持有环图 | 支持审查、返工、迭代等循环，不限制为 DAG                   |
| 动态路由  | Agent 可以选择一个或多个合法下游角色                    |
| 动态建图  | 模型可以用受控工作流元语创建新流程，并在运行中扩展尚未执行的部分       |
| 串行与并行 | 支持依赖、并发、汇合、跳过和分身                         |
| 可靠通信  | Agent 消息可持久化、关联任务、幂等投递和审计                |
| 共享状态  | 保留 y-agent 三类 reducer，并增加 schema、版本和冲突控制 |
| 大产物支持 | 文件和大结果通过 Artifact 管理，不塞入消息或共享变量          |
| 可恢复   | 服务重启后能够识别并继续处理未完成运行                      |
| 远程执行  | 将普通 API 或外部 Agent 作为远程 Provider，在流程图中作为正式节点执行 |
| 框架中立  | 不绑定 LangGraph、OpenAI Agents SDK 或特定模型厂商  |

### 1.4 非目标

- 第一版不实现可视化流程编辑器。
- 第一版不实现 Temporal 级别的通用分布式工作流引擎。
- 第一版不提供任意 Python 条件表达式作为边条件。
- 第一版不支持两个 Agent 自动合并同一个代码文件。
- 第一版不实现跨断网无限续传。
- 不把所有复杂任务都强制拆成多 Agent；单 Agent 足够时仍使用单 Agent。

***

## 2. 核心设计原则

1. **定义与运行分离**：流程图是不可变定义，每次执行产生独立运行状态。
2. **Scheduler 是确定性模块**：LLM 只能提出结构化路由意图，不能直接修改运行状态。
3. **节点不等于 Agent**：节点可以是 Agent、工具、函数、人工步骤或子流程。
4. **消息不等于任务**：Message 用于沟通；Task/NodeRun 表示正式工作；Artifact 表示正式产出。
5. **Workspace 不暴露内部字典**：只能通过 schema 化操作和 reducer 更新。
6. **有环但有界**：通过边遍历次数、节点执行次数、Run deadline 和终止条件限制循环。
7. **持久化先于投递**：状态与 Outbox 在同一事务提交后才发送消息。
8. **消息至少一次投递并按 ID 去重**：消息通道允许重复，但重复消息不得再次触发同一个工具执行；这只是传输去重，不表示业务动作具备幂等性。
9. **机器间只传结构化 JSON**：FCL 只用于 LLM 输出到服务端协议层。
10. **统一能力接口**：本地工具、远程 API 和外部 Agent 都通过 `ToolInvocation` / `ToolResult` 接入，不为外部 Agent 建立第二套内部模型。
11. **Host 拥有编排权**：Provider 不反向调用 Host；需要输入或确认时只返回声明式等待状态。
12. **轻量优先**：Capability Gateway 默认与 Host 同进程，不建设微服务中心；只有真实的多实例需求出现后才增加分布式设施。
13. **小图组合优先**：模型只规划粗粒度顶层流程；复杂步骤优先封装成子流程节点，子流程内部使用小图或简单循环，不鼓励生成一张包含大量 Agent 的巨型图。

***

## 3. 模块结构

建议在 YWeb Core 中形成以下模块：

```text
yweb.agent
├── command                    # 现有 FCL 协议层
├── runtime                    # 工具统一执行层
├── flow                       # 流程定义与运行调度
│   ├── definition.py
│   ├── run.py
│   ├── scheduler.py
│   ├── state_machine.py
│   ├── events.py
│   └── repository.py
├── collaboration              # Agent 角色、消息与动态路由
│   ├── agents.py
│   ├── messages.py
│   ├── routing.py
│   └── repository.py
├── workspace                  # 结构化共享状态与 Artifact
│   ├── schema.py
│   ├── operations.py
│   ├── reducers.py
│   ├── store.py
│   └── artifacts.py
├── transport                  # 实时事件与可靠投递
│   ├── outbox.py
│   ├── event_bus.py
│   └── websocket.py
└── adapters
    ├── llm_node.py
    ├── tool_node.py
    ├── function_node.py
    ├── client_agent.py
    ├── a2a.py
    └── subflow.py
```

对上层调用方主要暴露三个深接口：

```python
run = await flow_engine.start(flow_definition, inputs, context)
await flow_engine.signal(run.run_id, signal)
state = await flow_engine.get_state(run.run_id)
```

Workspace、消息、事件和调度细节隐藏在实现内部；高级调用方可以按需使用更细接口。

***

## 4. 四类核心概念

必须明确区分以下四类对象：

### 4.1 FlowDefinition

描述“可以怎样运行”，是可版本化、不可变的流程定义。

### 4.2 FlowRun / NodeRun

描述“这一次实际运行到了哪里”，包含状态、次数、错误、时间和执行实例。

### 4.3 AgentMessage

描述 Agent、用户和系统之间的沟通，不直接代表工作已经完成。

### 4.4 Workspace / Artifact

Workspace 保存小型结构化协作状态；Artifact 保存文件、大文本和正式任务产出。

这四类对象不能继续混在一个内存 `WorkingSpace` 或 Node 对象中。

***

## 5. 流程定义模型

### 5.1 FlowDefinition

```python
@dataclass(frozen=True)
class FlowDefinition:
    flow_id: str
    version: int
    name: str
    nodes: tuple[NodeDefinition, ...]
    edges: tuple[EdgeDefinition, ...]
    workspace_schema: WorkspaceSchema
    run_policy: RunPolicy
```

同一个 `flow_id` 的已发布版本不可原地修改；修改后生成新版本。已开始的 FlowRun 始终绑定创建时的版本。

### 5.2 NodeDefinition

```python
@dataclass(frozen=True)
class NodeDefinition:
    node_id: str
    role: str
    node_type: NodeType
    description: str
    config: dict
    join_policy: JoinPolicy = JoinPolicy.ALL_ACTIVE
    max_runs: int = 1
    timeout_seconds: float | None = None
```

第一版 `NodeType`：

```text
start
llm
tool
function
human
subflow
```

以后可以增加 `client_agent` 等便捷类型，但底层仍通过 NodeAdapter 执行。

### 5.3 EdgeDefinition

```python
@dataclass(frozen=True)
class EdgeDefinition:
    edge_id: str
    source_node_id: str
    target_node_id: str
    max_traversals: int = 1
    label: str | None = None
```

`max_traversals` 对应 y-agent 的 `max_run_times`。有环流程必须通过它或节点 `max_runs` 限制无限循环。

第一版不允许在 Edge 上配置任意 Python 表达式。动态选择通过合法下游列表和 `RoutingDecision` 完成。

### 5.4 JoinPolicy

```text
ALL_ACTIVE   所有本轮被激活的上游进入终态后执行
ALL_SUCCESS  所有上游都成功后执行；失败则下游失败或跳过
ANY_SUCCESS  任意一个上游成功即可执行
```

第一版优先实现 `ALL_ACTIVE` 和 `ALL_SUCCESS`。

`ALL_ACTIVE` 是对 y-agent“真实执行 + 虚拟执行”语义的正式化：未被选中的分支明确记为 `skipped`，汇合节点不再永久等待。

### 5.5 RunPolicy

```python
@dataclass(frozen=True)
class RunPolicy:
    timeout_seconds: float | None
    max_total_node_runs: int
    max_parallel_nodes: int
    fail_fast: bool = False
```

即使各边都有次数限制，也需要全局 `max_total_node_runs` 作为最后保险。

### 5.6 模型可用的工作流元语

当前 y-agent 的动态能力主要是在已定义流程中选择下游、分身和循环。新框架还需要允许模型根据当前任务创建流程，但模型不能直接修改数据库或 Scheduler 状态。

模型先产生 `WorkflowDraft`，框架验证后再发布为不可变 `FlowDefinition`：

```text
用户目标
  ↓
Planner Agent
  ↓ WorkflowDraft
确定性验证器
  ↓
FlowDefinition revision
  ↓
FlowRun
```

第一版元语保持最小：

```text
create_workflow     创建草稿
add_node            增加节点
connect_nodes       建立依赖
use_subflow         将已有流程作为一个节点
set_join_policy     设置汇合方式
set_run_limits      设置次数、并发和超时上限
validate_workflow   验证草稿
publish_workflow    发布不可变版本
start_workflow      启动运行
```

这些元语最终应汇总成一次原子 `WorkflowDraft` 或 `WorkflowPatch` 提交，不能逐条写入后留下半张无效流程图。

运行中发现新任务时，模型可以提交：

```python
@dataclass(frozen=True)
class WorkflowPatch:
    run_id: str
    base_revision: int
    operations: tuple[WorkflowOperation, ...]
    reason: str
```

已发布的 `FlowDefinition` 始终不可变。`WorkflowPatch` 不修改它，而是在当前 FlowRun 上追加一个 `RunPlanRevision`；这个 revision 只描述本次运行从当前时刻开始新增或调整的未来计划。

运行中修改遵守：

- 已经 `assigned/running/completed` 的 NodeRun 和已遍历的 Edge 不可删除或改写。
- 可以增加新节点、新边和新的子流程节点。
- 只能替换或跳过尚未开始的节点。
- 每次 Patch 基于当前 `RunPlanRevision` 原子校验和应用，成功后产生新的 run-local revision。
- 新增循环必须具有 `max_runs/max_traversals`，并受 RunPolicy 总上限约束。
- 每个 NodeRun 记录创建时的流程 revision，保证历史可解释和可恢复。

### 5.7 分层流程与子流程节点

复杂工作流默认采用分层组合，而不是展开成一张巨型图：

```text
顶层流程（只表达粗粒度目标）
├── 需求理解：简单 Agent 循环
├── 调研：Research 子流程
├── 实现：Implementation 子流程
├── 验证：Review/Test 子流程
└── 汇总：简单 Agent 循环
```

`subflow` 节点对父流程只暴露小而稳定的输入输出 Interface：

```python
SubflowBinding(
    flow_id="research_flow",
    version="latest_compatible",
    input_mapping={...},
    output_mapping={...},
)
```

`latest_compatible` 只用于规划时选择；子流程节点进入 ready/assigned 前必须解析并固定为确切版本，恢复运行时不能重新漂移到更新版本。

父流程不需要知道子流程内部有多少 Agent、循环和工具。这样可以：

- 限制单张图的节点、边和 Prompt 复杂度。
- 独立测试、复用和替换子流程。
- 让 Planner 优先组合已有可靠流程，只在没有合适模块时创建新草稿。
- 将失败、超时和产物收敛到子流程的输入输出 Interface，而不是泄漏全部内部状态。

建议默认复杂度限制：顶层图只保留少量粗粒度节点；超过节点/边阈值时，验证器要求拆为子流程。嵌套深度也应有小的全局上限，避免用层级隐藏无限复杂度。

***

## 6. 运行状态模型

### 6.1 FlowRun

```python
@dataclass
class FlowRun:
    run_id: str
    flow_id: str
    flow_version: int
    status: FlowRunStatus
    workspace_id: str
    created_by: str | None
    started_at: datetime | None
    ended_at: datetime | None
    deadline: datetime | None
    version: int
```

状态：

```text
created
running
waiting_input
completed
failed
cancelled
timed_out
```

### 6.2 NodeRun

一个 NodeDefinition 可以在循环中产生多个 NodeRun：

```python
@dataclass
class NodeRun:
    node_run_id: str
    run_id: str
    node_id: str
    iteration: int
    status: NodeRunStatus
    triggered_by: list[str]
    assigned_agent_instance_id: str | None
    started_at: datetime | None
    ended_at: datetime | None
    error_code: str | None
    error_message: str | None
    version: int
```

状态：

```text
pending
waiting
ready
assigned
running
waiting_input
completed
failed
skipped
cancelled
timed_out
```

终态：

```text
completed / failed / skipped / cancelled / timed_out
```

原 y-agent 的状态对应：

| 原实现                      | 新模型                  |
| ------------------------ | -------------------- |
| `run_times += 1`         | 新增一次 NodeRun         |
| `virtual_run_times += 1` | NodeRun 进入 `skipped` |
| `is_terminate=True`      | FlowRun 进入终态并取消剩余节点  |
| 节点对象上的下游计数               | 持久化 EdgeTraversal    |

### 6.3 EdgeTraversal

```python
@dataclass
class EdgeTraversal:
    traversal_id: str
    run_id: str
    edge_id: str
    source_node_run_id: str
    target_iteration: int
    status: str
```

它用于审计每次边触发、限制有环图执行次数，并支持服务重启后的正确恢复。

***

## 7. Scheduler

### 7.1 职责

Scheduler 是确定性模块，负责：

- 验证流程定义
- 创建 FlowRun、NodeRun 和 EdgeTraversal
- 判断节点依赖是否满足
- 处理动态下游选择
- 把未选择分支标记为 `skipped`
- 控制最大并发
- 分配执行实例
- 执行超时和取消策略
- 传播失败
- 判断流程是否自动结束
- 产生持久化事件

Scheduler 不负责：

- 生成 LLM Prompt
- 调用模型
- 执行具体工具
- 保存大文件内容
- 决定业务路由策略

### 7.2 核心接口

```python
class FlowEngine:
    async def start(
        self,
        definition: FlowDefinition,
        inputs: dict,
        context: RunContext,
    ) -> FlowRunHandle: ...

    async def signal(
        self,
        run_id: str,
        signal: FlowSignal,
    ) -> None: ...

    async def get_state(self, run_id: str) -> FlowRunState: ...
```

NodeAdapter 完成执行后不能直接调用下游节点，只向 FlowEngine 提交结果：

```python
await flow_engine.signal(
    run_id,
    NodeCompleted(node_run_id=node_run_id, result=result),
)
```

### 7.3 调度循环

```text
读取持久化事件
      ↓
在事务中加载当前 Run 状态
      ↓
校验信号和状态版本
      ↓
执行状态迁移
      ↓
计算新 ready 节点
      ↓
保存 NodeRun / EdgeTraversal / OutboxEvent
      ↓
提交事务
      ↓
异步投递执行与实时事件
```

### 7.4 自动结束

FlowRun 在满足以下条件时自动完成：

- 不存在 `pending / waiting / ready / assigned / running / waiting_input` NodeRun
- 不存在仍可合法遍历、但尚未处理的边
- 没有未完成的 fan-out 子任务
- 未收到新的动态子任务请求

LLM 也可以通过 `terminate` 提议提前结束，但最终由 Scheduler 校验和执行。

***

## 8. 串行、并行、动态分支与有环执行

### 8.1 串行

```text
A → B → C
```

A 完成后 B 进入 ready，B 完成后 C 进入 ready。

### 8.2 多路并行

```text
       ┌→ B ─┐
A ─────┤     ├→ D
       └→ C ─┘
```

A 完成后 B、C 同时进入 ready。D 根据 JoinPolicy 等待汇合。

### 8.3 动态选择下游

LLM 节点只能从流程定义中已经存在的合法下游中选择：

```python
RoutingDecision(
    source_node_run_id="...",
    targets=[
        RouteTarget(node_id="review", instruction="检查风险"),
        RouteTarget(node_id="summarize", instruction="整理内容"),
    ],
)
```

未选择的同轮分支产生 `NodeSkipped` 或 `BranchSkipped` 记录，使汇合节点明确知道其不再参与本轮等待。

### 8.4 有环执行

```text
计划 → 执行 → 审查
       ↑       │
       └─返工──┘
```

每次回到“执行”节点都创建新的 NodeRun，并增加相应 EdgeTraversal。不能复用和修改旧 NodeRun。

### 8.5 失败传播

默认规则：

- `ALL_SUCCESS` 下任一必要上游失败，下游标记为 skipped 或 failed，由配置决定。
- `ALL_ACTIVE` 下所有激活上游进入任意终态后继续，下游可读取上游状态决定如何处理。
- `fail_fast=True` 时任一失败终止整个 FlowRun。
- 框架不自动重试失败节点；是否再次执行由 Agent 查询现实状态后产生新的决策，或由流程显式进入新的 NodeRun。

***

## 9. 分身：Fan-out / Fan-in

y-agent 的“分身”保留为框架正式能力，但底层命名为 fan-out/fan-in。

### 9.1 Fan-out

```python
FanOutRequest(
    parent_node_run_id="...",
    sections=[
        Section(name="market", input={...}),
        Section(name="technical", input={...}),
        Section(name="risk", input={...}),
    ],
    max_parallel=3,
    join_policy="require_all",
)
```

每个 Section 产生独立子 NodeRun，因此具有独立：

- 状态
- 超时
- 错误
- Token 统计
- Workspace View
- 日志和 Artifact

### 9.2 Fan-in

```text
require_all      全部成功才汇总
collect_partial  收集成功结果并附带失败信息
fail_fast        任一失败立即取消其他分身
```

第一版保留 y-agent 默认最多三个并发分身的合理限制，但允许上层显式配置更低值。

### 9.3 与 ReAct 的关系

原 y-agent 将分身和 ReAct 设为互斥。新框架不在底层硬编码互斥，但默认策略仍应禁止“每个分身无限 ReAct”，避免并发和 Token 成本失控。是否允许由 NodeDefinition 的执行策略决定。

***

## 10. Agent 定义与执行实例

### 10.1 AgentDefinition

```python
@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    description: str
    capabilities: tuple[str, ...]
    input_schema: dict | None
    output_schema: dict | None
    default_execution_target: str
    max_concurrency: int = 1
```

AgentDefinition 描述能力，不表示某个实例当前在线。

### 10.2 AgentInstance

```python
@dataclass
class AgentInstance:
    instance_id: str
    agent_id: str
    execution_target: str
    session_id: str | None
    client_id: str | None
    status: str
    current_load: int
    last_heartbeat: datetime
```

执行位置：

```text
server    Agent Host 所在服务端进程
client    通过 Client Capability Proxy 在用户客户端执行
remote    通过普通 API、流式 API 或长任务 API 调用远程能力；实现可以是微服务或外部 Agent
```

执行位置由注册配置和策略决定，不作为 LLM 参数。

### 10.3 Agent 作为节点与 Agent 作为工具

- 长任务、需要通信和独立生命周期的 Agent 使用 Agent Node。
- 短小、同步等待结果的专业 Agent 可以通过 AgentAdapter 包装成工具。
- 两种方式最终都产生可追踪 NodeRun/ToolInvocation，不允许黑盒递归失控。
- 外部 Agent 即使通过统一能力接口调用，也仍可作为流程图中的正式 Agent Node；接口统一不等于抹掉节点语义。
- Scheduler 仍负责决定节点是否进入 `ready/skipped`、何时执行、串行或并行、如何汇合、超时和取消。
- NodeAdapter 只负责“怎样执行这个节点”，不负责“这个节点是否应该执行”。

***

## 11. Agent 通信协议

### 11.1 AgentMessage

```python
@dataclass
class AgentMessage:
    message_id: str
    run_id: str
    node_run_id: str | None
    sender: AgentAddress
    recipients: list[AgentAddress]
    kind: MessageKind
    parts: list[MessagePart]
    correlation_id: str | None
    causation_id: str | None
    sequence: int | None
    created_at: datetime
```

第一版 MessageKind：

```text
inform
request
reply
clarification
input_required
notify
```

控制命令不作为普通消息：

```text
assignment → RoutingDecision
terminate  → TerminateRunRequest
spawn      → FanOutRequest / SpawnTaskRequest
cancel     → CancelSignal
```

### 11.2 MessagePart

```text
TextPart
DataPart
ArtifactRefPart
```

消息中不内联大型文件和超长工具输出，只保存 ArtifactRef。

### 11.3 投递语义

- 至少一次投递
- `message_id` 全局唯一
- 消费方必须幂等
- 同一发送方到同一 NodeRun 可使用递增 sequence
- 不承诺多个发送方之间的全局顺序
- Message 必须先持久化，再通过 Outbox 投递
- 消息是否展示给 LLM 由 ContextPolicy 决定，不默认把全聊天室塞入 Prompt

### 11.4 聊天室兼容

上层仍可以提供和 y-agent 相同的聊天室视图：

```python
messages = await message_store.list(
    run_id=run_id,
    sender=role_a,
    recipient=role_b,
    limit=20,
)
```

聊天室是 AgentMessage 的查询视图，不再是单独的内存列表。

### 11.5 可靠 Outbox

```text
同一数据库事务：
  更新 FlowRun/NodeRun
  保存 AgentMessage
  保存 OutboxEvent
提交
  ↓
Publisher 投递 WebSocket / EventBus
  ↓
消费者按 message_id 幂等处理
```

这样可以避免“数据库提交成功但消息没有发出去”或“消息发出但状态没有保存”的不一致。

***

## 12. FCL 与协作控制协议

FCL 保持 LLM 友好的文本协议，仅用于 LLM 输出到服务端：

```text
command=|<|assignment(...)|>|
command=|<|send_message(...)|>|
command=|<|terminate(...)|>|
```

解析后立即转换为结构化命令：

| FCL 指令         | 结构化命令                 | 处理模块                |
| -------------- | --------------------- | ------------------- |
| `assignment`   | `RoutingDecision`     | Scheduler           |
| `send_message` | `AgentMessage`        | MessageStore        |
| `notify`       | `AgentMessage`        | MessageStore / 用户通道 |
| `terminate`    | `TerminateRunRequest` | Scheduler           |
| `write_var`    | `WorkspaceOperation`  | WorkspaceStore      |
| 普通工具名          | `ToolInvocation`      | Tool Dispatcher     |
| `plan_workflow` | `WorkflowDraft`       | Workflow Validator  |
| `extend_workflow` | `WorkflowPatch`      | FlowEngine          |

Host、Gateway 和本地/远程 Provider 之间不传原始 FCL，只传 JSON。

### 12.1 普通工具批次与流程依赖必须分开

- LLM 在同一轮输出多个普通工具调用时，如果没有显式依赖字段，工具执行层默认并行，不能按文本顺序推断串行关系。
- 需要前一个工具结果才能调用后一个工具时，LLM 应分多轮输出；或者使用未来单独定义的 `call_id / depends_on` 显式批量计划。
- FlowDefinition 中已经存在的节点边、JoinPolicy 和 Scheduler 依赖属于流程层的正式编排信息，不受“同轮工具默认并行”规则影响。
- Tool Dispatcher 只执行当前已经就绪的调用，不负责猜测工具之间的依赖；流程节点的串并行仍由 FlowEngine 决定。

***

## 13. 共享工作空间

### 13.1 Workspace 的定位

Workspace 保存一次 FlowRun 内的小型结构化协作状态，不保存无限增长日志和大文件。

命名空间：

```text
input.xxx   运行输入，只读
space.xxx   整个 FlowRun 共享
role.xxx    角色私有/角色输出
node.xxx    当前 NodeRun 临时数据
```

### 13.2 WorkspaceSchema

```python
@dataclass(frozen=True)
class WorkspaceField:
    name: str
    value_schema: dict
    reducer: str
    default: object | None
    visibility: str = "shared"
    max_bytes: int = 64_000
```

### 13.3 保留 y-agent 三类 reducer

```text
overwrite      覆盖型
append         追加型
append_unique  不重复追加型
```

后续可以增加：

```text
merge_object
max
min
sum
```

但 reducer 必须由框架注册，不允许流程定义注入任意代码。

### 13.4 WorkspaceOperation

```python
SetValue(field="final_answer", value=...)
AppendValues(field="evidence", values=[...])
AppendUniqueValues(field="entities", values=[...], key="id")
```

统一接口：

```python
snapshot = await workspace_store.read(workspace_id, view)

result = await workspace_store.apply(
    workspace_id=workspace_id,
    node_run_id=node_run_id,
    expected_version=snapshot.version,
    operations=operations,
)
```

### 13.5 并发与冲突

- `append`、`append_unique` 等可交换 reducer 可以在事务中合并。
- `overwrite` 默认使用乐观锁；两个节点基于同一旧版本覆盖时，第二个收到冲突。
- 冲突不得静默采用“最后获得线程锁者胜出”。
- 冲突处理由节点策略决定：重新读取后重试、交给汇总节点或失败。

### 13.6 Workspace View

NodeAdapter 只获得与该节点相关的只读 snapshot 和允许写入字段：

```python
WorkspaceView(
    readable_fields=[...],
    writable_fields=[...],
    snapshot_version=12,
)
```

这样可以限制 Agent 看到和修改的共享状态，并减少 Prompt 上下文。

***

## 14. Artifact 与文件工作空间

### 14.1 Artifact

```python
@dataclass
class Artifact:
    artifact_id: str
    run_id: str
    producer_node_run_id: str
    kind: str
    uri: str
    content_hash: str
    size: int
    version: int
    metadata: dict
```

Artifact 一旦发布即不可原地修改；修改后生成新版本或新 Artifact。

### 14.2 Workspace 与 Artifact 的区别

| 内容            | 存放位置                          |
| ------------- | ----------------------------- |
| 状态、计数、小型结构化结果 | Workspace                     |
| 聊天和澄清         | AgentMessage                  |
| 文件、大文本、图片、报告  | Artifact                      |
| 任务状态          | NodeRun / FlowRun             |
| 实时日志          | ToolEvent / RunEvent，按策略持久化摘要 |

### 14.3 每任务隔离目录

不让并行 Agent 直接共享一个可写目录：

```text
base snapshot
    ├── node-run-A workspace
    ├── node-run-B workspace
    └── node-run-C workspace
```

每个 NodeRun：

1. 获取输入 Artifact 或基础 snapshot。
2. 在独立目录中执行。
3. 只从声明的输出目录收集文件。
4. 发布 Artifact 或 ChangeSet。
5. 由后续确定性节点显式合并。

代码仓库可以使用 Git worktree/branch；普通文件可以使用临时目录或 copy-on-write。

### 14.4 与 yweb.storage 的关系

ArtifactStore 只定义接口，具体 Adapter 复用 YWeb Storage：

```text
LocalArtifactStore
S3ArtifactStore
OSSArtifactStore
```

***

## 15. NodeAdapter 执行 seam

```python
class NodeAdapter(Protocol):
    async def execute(
        self,
        node: NodeDefinition,
        node_run: NodeRun,
        context: NodeExecutionContext,
    ) -> NodeExecutionResult: ...
```

`NodeExecutionResult` 可以包含：

```python
@dataclass
class NodeExecutionResult:
    output: object | None
    workspace_operations: list[WorkspaceOperation]
    artifacts: list[ArtifactDraft]
    messages: list[AgentMessageDraft]
    routing_decision: RoutingDecision | None
    fan_out: FanOutRequest | None
```

FlowEngine 在一个事务中校验并应用结果；Adapter 不直接修改数据库中的 FlowRun 状态。

第一版 Adapter：

### 15.1 LLMNodeAdapter

- 构建 Prompt
- 调用模型
- 解析 FCL
- 返回结构化协作命令
- 不直接触发下游

### 15.2 ToolNodeAdapter

- 构造 ToolInvocation
- 调用现有 `yweb.agent.runtime.Dispatcher`
- 将 ToolResult 映射为 NodeExecutionResult

### 15.3 RemoteAgentNodeAdapter

- 将远程 Agent 视为一种 Capability Provider，构造统一 `ToolInvocation`
- 通过 `RemoteAgentAdapter` 调用普通 HTTP、流式或长任务 API
- 将远程进度、等待输入和最终结果映射为 NodeRun 事件与 `NodeExecutionResult`
- 不允许远程 Agent 直接修改 FlowRun、选择任意下游或反向调用 Host
- 节点的串行、并行、动态指派、汇合、跳过、超时和取消继续完全由 Scheduler/FlowEngine 管理

### 15.4 FunctionNodeAdapter

- 运行框架注册的确定性 Python 函数
- 支持同步函数受控线程池和异步函数

### 15.5 HumanNodeAdapter

- 将节点置为 `waiting_input`
- 通过消息或 WebSocket 通知用户
- 收到带 correlation\_id 的 Signal 后继续

### 15.6 SubflowAdapter

- 启动子 FlowRun
- 父节点等待子流程终态
- 子流程结果通过 Artifact/Workspace 显式映射回父流程
- 子流程内部状态不自动泄漏给父流程，只通过声明的输入输出 Interface 交互
- 同一个可靠子流程可以被模型规划出的不同顶层流程复用

***

## 16. 服务端 Host、轻量客户端执行器与实时通信

Agent Host、FlowEngine 和 CapabilityGateway 位于服务端。客户端只运行轻量 `Client Capability Proxy`，负责汇总本机、内网及客户端身份保护的能力，并完成注册、审批、沙箱和执行；它不运行第二套流程编排器，也不建设微服务中心。

### 16.1 调用所有权

- 服务端能力由 Host 的 Gateway 直接调用。
- 客户端能力由 Gateway 生成结构化 `ToolInvocation` 并发送给指定客户端；客户端 Runtime 完成本地校验后真正调用工具。
- 远程 API 或外部 Agent 由 `RemoteAgentAdapter` 调用。
- 客户端不解析 FCL，也不能改变工具名和参数；但拥有批准或拒绝本地执行的最终权力。
- WebSocket/SSE 只承载事件、进度和任务状态，不改变主动调用方向。

### 16.2 实时消息

```text
服务端 Host/Gateway             客户端 Runtime
  │── tool.invoke ─────────────>│
  │<─ tool.accepted ────────────│
  │<─ tool.progress ────────────│
  │<─ tool.output_chunk ────────│
  │── tool.cancel ─────────────>│
  │<─ tool.result/error ────────│
```

所有消息携带：

```text
run_id
node_run_id
invocation_id
message_id
deadline
```

### 16.3 超时

```text
accept_timeout     Provider 确认接收的时间
execution_timeout  整个节点执行时间
idle_timeout       多久没有进度、输出或任务心跳
```

实时输出不会因为 idle timeout 被阻塞；只有完全没有进展消息才视为可能卡死。

### 16.4 本地 Provider 沙箱

- 具名能力白名单
- 工作区路径限制
- 禁止路径和符号链接逃逸
- CLI 禁用 `shell=True`
- 环境变量白名单
- 网络默认拒绝、按工具放行
- 可终止完整进程树
- 限制时间、输出和结果大小
- Host 权限与本地审批双层控制

***

## 17. 外部 Agent 作为 Capability Provider

YWeb 不要求外部 Agent 实现一套新的 Agent 通信协议。只要外部系统能通过普通 API 声明能力、接收结构化调用并返回结果或任务状态，就可以注册为远程 Provider：

```text
Flow 中的 Agent Node
        │ Scheduler 决定是否运行及串并行关系
        ▼
RemoteAgentNodeAdapter
        │ ToolInvocation / ToolEvent / ToolResult
        ▼
RemoteAgentAdapter
        ├── 普通 HTTP API
        ├── SSE / WebSocket 流式 API
        ├── 创建任务 + 查询状态 API
        └── 可选 A2A 兼容 Adapter
```

统一调用接口不会取消 Agent Node 的编排能力：

- `NodeDefinition` 仍声明依赖、JoinPolicy、并发和执行策略。
- 动态 `assignment` 仍可以选择或跳过这个节点。
- 多个远程 Agent Node 可以并行运行，也可以按边串行运行。
- Fan-out/Fan-in、循环、超时、取消和失败传播仍由 Scheduler 处理。
- 远程 Agent 只完成节点工作，不拥有 YWeb 流程图的控制权。

短小、同步等待结果的外部 Agent 可以直接作为 Tool Node；长任务或需要独立状态的外部 Agent 使用 Remote Agent Node。两者共享 Capability Gateway，不共享生命周期模型。

外部输入一律视为不可信：校验能力描述、参数、结果和 Artifact，限制网络、权限、超时和结果大小，并防止外部描述造成 Prompt Injection。

A2A/MCP 仅在确有第三方兼容需求时作为边缘 Adapter，不进入内部 Scheduler、Workspace 或数据库模型。

***

## 18. 事件与实时观察

框架事件：

```text
FlowStarted
FlowCompleted
FlowFailed
NodeReady
NodeAssigned
NodeStarted
NodeProgress
NodeOutputChunk
NodeCompleted
NodeFailed
NodeSkipped
MessageCreated
ArtifactPublished
WorkspaceUpdated
RunWaitingInput
RunCancelled
```

事件用途：

- WebSocket 实时界面
- 审计日志
- 流程可视化
- 调试和回放
- 指标统计

不是所有实时 chunk 都永久保存。默认持久化状态事件和摘要；stdout 等高频事件使用有界缓存或按策略抽样。

***

## 19. 持久化模型

第一版建议使用 YWeb ORM 表：

```text
agent_definitions
agent_instances
flow_definitions
flow_runs
node_runs
edge_traversals
agent_messages
workspace_instances
workspace_values
workspace_operations
artifacts
run_events
outbox_events
```

### 19.1 并发更新

FlowRun、NodeRun 和覆盖型 WorkspaceValue 使用乐观锁 `version`：

```sql
UPDATE node_runs
SET status = :new_status,
    version = version + 1
WHERE id = :node_run_id
  AND status = :expected_status
  AND version = :expected_version;
```

更新行数为零表示状态已经被其他 Worker 修改，当前处理者必须重新读取，不能覆盖。

### 19.2 抢占 ready 节点

可使用数据库行锁或条件更新把 ready 节点原子转为 assigned。第一版不要求引入消息队列。

多服务实例后，可以增加 Redis/EventBus，但数据库仍然是运行状态的事实来源。

### 19.3 恢复

服务启动时扫描：

- 超过租约但仍 assigned/running 的 NodeRun
- 尚未投递的 OutboxEvent
- 已到 deadline 的 FlowRun/NodeRun
- waiting\_input 的长期任务

恢复时不自动重新执行工具或 Agent 节点。状态不确定的运行标记为 `recovery_required`，由 Agent 查询外部现实状态、人工确认或显式流程分支决定下一步。

***

## 20. 不自动重试与 Agent 现实状态确认

框架不区分“幂等工具”和“非幂等工具”，也不提供工具自动重试策略。原因是框架无法仅根据工具声明判断现实世界中的动作是否已经发生。

例如下单请求返回前网络断开时，Agent 不应让框架盲目重复下单，而应像人一样先调用订单查询能力：

```text
下单结果不确定
      ↓
查询订单/流水/设备现实状态
      ↓
Agent 根据查询结果判断
      ├── 已成功：继续后续任务
      └── 未成功：产生一次新的 ToolInvocation
```

框架只负责：

- 每次执行携带稳定的 `node_run_id` 和 `invocation_id`
- 相同 `invocation_id` 的重复消息不再次触发执行，这是传输去重，不是业务幂等
- 记录调用、进度、结果和“结果不确定”状态，供 Agent 后续查询和判断
- 取消不承诺回滚已经发生的现实副作用
- 不自动生成补偿动作，不自动创建新的重试调用

如果业务本身提供查询、撤销或补偿接口，它们作为普通工具暴露，由 Agent 或显式流程节点决定何时调用。

***

## 21. 权限、安全与上下文隔离

### 21.1 服务端权限

- 谁可以启动某个 FlowDefinition
- Agent 可以调用哪些工具
- Node 可以读取和写入哪些 Workspace 字段
- Agent 可以向哪些角色发送消息
- 哪些 Artifact 可以被下游读取
- 是否允许远程客户端或外部 Agent 执行

### 21.2 Prompt 上下文

不把全部运行日志、Workspace 和聊天室自动注入每个 Agent。

```python
ContextPolicy(
    workspace_fields=[...],
    message_query=...,
    upstream_outputs=[...],
    artifacts=[...],
    max_tokens=...,
)
```

### 21.3 审计

记录：

- 状态变化
- 路由决策
- 工具/Agent 调用摘要
- Workspace 修改操作
- Artifact 元数据
- 审批和权限结果
- 错误与耗时

不默认记录密钥、完整敏感文件和无限量模型输出。

***

## 22. 与 YWeb 现有模块的关系

| 现有模块                 | 复用方式                                    |
| -------------------- | --------------------------------------- |
| `yweb.agent.command` | 解析 y-agent 继承下来的 FCL 指令                 |
| `yweb.agent.runtime` | 执行 Tool Node 和 Agent-as-tool            |
| `yweb.orm`           | 持久化运行、消息、Workspace、事件和 Outbox           |
| `yweb.storage`       | ArtifactStore 的具体存储 Adapter             |
| `yweb.rbac`          | Flow、Agent、Tool、Workspace 和 Artifact 权限 |
| `yweb.log`           | 脱敏审计与运行指标                               |
| `yweb.ratelimit`     | 按用户、流程、Agent 和工具限流                      |
| `yweb.state_machine` | FlowRun、NodeRun 状态迁移实现参考                |
| `yweb.domain_events` | 运行事件和 Outbox 实现参考                       |
| WebSocket            | 客户端 Agent、用户等待输入和实时观察                   |

协作层不重复实现工具调用；工具执行统一走 runtime。runtime 也不负责流程依赖；依赖调度统一走 flow。

***

## 23. 测试策略

### 23.1 图与调度测试

- 纯串行
- 一个节点多下游并行
- 多上游 `ALL_ACTIVE` 汇合
- 动态选择部分分支，其他分支 skipped
- 有环返工直到次数上限
- `terminate` 提前结束
- 上游失败传播
- 并发限制

### 23.2 Workspace 测试

- overwrite 乐观锁冲突
- append 并发合并
- append\_unique 稳定去重
- 非法字段和 schema 校验
- 读写权限
- 大值限制

### 23.3 消息测试

- 至少一次消息投递、按 message_id 去重，且重复消息不重复触发工具
- Outbox 重试
- correlation/causation 关联
- 同一发送方 sequence
- 消息持久化后重连查询

### 23.4 恢复测试

- Node 运行中服务退出
- 状态提交后 Outbox 尚未发送
- 重复 NodeCompleted
- 取消与完成竞态
- 超时与晚到结果
- 多 Worker 同时抢同一 ready 节点

### 23.5 y-agent 行为兼容测试

使用原 y-agent 典型流程作为验收用例：

- 动态 assignment
- 多角色聊天室
- 覆盖/追加/去重追加变量
- 分身并行
- 多上游跳过汇合
- 循环和最大执行次数
- 工具节点与 LLM 节点混编
- 模型生成 WorkflowDraft 后的验证、发布和启动
- 运行中 WorkflowPatch 只能改变尚未执行的未来结构
- 顶层流程组合多个子流程，父流程只看到声明的输入输出
- 超过复杂度阈值的巨型图被拒绝并要求拆分

***

## 24. 分阶段落地计划

### 阶段 1：运行内核原型

- FlowDefinition / NodeDefinition / EdgeDefinition
- FlowRun / NodeRun / EdgeTraversal
- 内存 Repository 和确定性 Scheduler
- 串行、并行、动态分支、skipped、多上游汇合
- FunctionNodeAdapter
- 完整图调度单元测试

产出：证明新内核可以等价表达 y-agent 的关键图语义。

### 阶段 2：Workspace 与 FCL 协作

- WorkspaceSchema
- overwrite / append / append\_unique reducer
- WorkspaceOperation 和版本冲突
- LLMNodeAdapter
- `assignment / send_message / notify / terminate / write_var` 映射
- AgentMessage 内存实现
- WorkflowDraft / WorkflowPatch 元语与确定性验证器
- 简单 Planner Agent：优先检索并组合已有子流程

产出：跑通多 Agent 动态协作，并能由模型创建受控的小型顶层流程。

### 阶段 3：YWeb ORM 持久化与恢复

- ORM Repository
- Outbox
- 乐观锁和 ready 节点抢占
- 服务启动恢复
- 状态事件和审计
- 故障注入测试

产出：服务重启后运行状态不丢失。

### 阶段 4：工具、Artifact 与子流程

- ToolNodeAdapter 接入统一 runtime
- ArtifactStore 接入 yweb.storage
- 独立任务文件工作区
- SubflowAdapter
- Fan-out / Fan-in 分身
- 父子流程显式输入输出映射、嵌套深度和复杂度限制

产出：覆盖原 y-agent 主要编排能力，并支持用多个简单子流程组合复杂任务。

### 阶段 5：服务端 Gateway、客户端能力代理与人工节点

- 服务端 Host 内嵌 CapabilityGateway
- Client Capability Proxy、客户端能力上报与会话路由
- 本机、内网设备以及需要客户端证书/登录态的公网服务 Adapter
- server/client/remote 三类执行目标
- 实时进度、输出、取消和超时
- 本地 Provider 沙箱
- HumanNode waiting\_input / resume

产出：支持本地客户端和人在环路中的流程。

### 阶段 6：多实例与外部互操作

- Redis/EventBus（确有多实例需求后）
- Remote Agent Node 能力路由
- 普通 API / 流式 API / 长任务 API Adapter
- 可选 A2A/MCP 兼容 Adapter
- 有限断线续传和长任务查询

产出：跨机器和外部 Agent 协作。

***

## 25. 迁移策略

不把 y-agent 整个仓库复制进 YWeb Core，采用“保留语义、重写内核”的方式。

### 优先迁移

- 图定义格式中的节点、边和最大次数
- 动态下游角色选择
- 虚拟执行对应的 skipped 语义
- 三类 Workspace reducer
- role/space 变量思想
- assignment/send\_message/notify/terminate
- 分身和循环用例
- 节点运行日志需要表达的信息

### 不直接迁移

- Node 对象上的可变运行计数
- 递归触发下游
- ThreadPoolExecutor 作为流程调度器
- 内存 WorkingSpace 作为事实来源
- 内存聊天室作为可靠消息通道
- 与旧业务数据库、RAG、训练语料和 UI 强耦合的实现
- 未经测试的图算法代码

### 兼容方式

可以先编写 `LegacyYAgentFlowLoader`，将旧流程 JSON 转换为新的 FlowDefinition，便于复用原案例和回归测试；它属于迁移 Adapter，不进入新核心模型。

***

## 26. 待验证问题

1. `ALL_ACTIVE` 在复杂强连通分量中的精确定义和轮次匹配方式。
2. 动态路由未选择分支应记录 NodeRun(skipped) 还是单独 BranchSkipped。
3. 循环中 NodeRun iteration 如何与多上游轮次对齐。
4. Workspace schema 使用 Pydantic Model 还是标准 JSON Schema。
5. append\_unique 的唯一键如何声明和处理嵌套对象。
6. FlowDefinition 版本与旧运行的兼容和清理策略。
7. 子流程共享父 Workspace 还是使用显式输入输出映射；默认建议显式映射。
8. AgentMessage 哪些进入 Prompt、哪些仅供 UI 和审计。
9. 分身输出的默认 FanInReducer。
10. 高副作用节点恢复时如何判断已执行但结果尚未提交。
11. 第一版使用数据库轮询还是进程内事件唤醒加数据库事实来源。
12. 远程 Agent 的长任务状态如何最小化映射为 NodeRun 事件，避免引入外部协议的数据模型。
13. 顶层流程默认允许多少节点和边，超过何种阈值必须拆成子流程。
14. WorkflowPatch 对尚未执行节点允许修改哪些字段，如何向 Planner 返回可理解的验证错误。
15. Planner 如何检索已有子流程的输入输出、适用范围和历史质量，而不把子流程内部图全部放进 Prompt。

这些问题应通过小型原型和行为测试决定，不在接口中预留大量假设性扩展点。

***

## 27. 最终架构结论

YWeb Core 的多 Agent 底层不应只是群聊，也不应只是一个通用 DAG：

```text
y-agent 领域语义
  有环编排 / 动态路由 / 分身 / 聊天室 / Workspace reducer
                         │
                         ▼
YWeb Core 可靠运行内核
  状态机 / ORM / Outbox / Artifact / 权限 / WebSocket / 工具执行
                         │
                         ▼
可选外部 Adapter
  本地能力 / 普通 API / 远程 Agent / 可选 A2A、MCP 兼容层
```

核心框架只需要稳定地回答五个问题：

1. 当前有哪些节点可以运行？
2. 某个节点由谁、在哪里执行？
3. Agent 之间如何可靠交换消息和正式产物？
4. 多个 Agent 如何安全共享和合并状态？
5. 服务失败、超时、取消或重启后如何得到一致结果？

外部 Agent 通过统一接口接入后，仍然是流程图中的正式节点：统一的是执行 seam，不是抹平 Scheduler 的节点语义。节点是否运行、串行或并行、如何汇合和失败传播，始终由 FlowEngine 决定。

因此最终原则是：

> 以 y-agent 的协作模型为领域核心，以 YWeb 的基础设施能力重写可靠运行内核；定义与运行分离、消息与任务分离、Workspace 与 Artifact 分离、LLM 意图与 Scheduler 状态迁移分离。
