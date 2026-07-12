# YWeb Agent 工具统一执行层设计

本文档描述 YWeb 的统一工具执行方案：把本地 Python 函数、Web API、CLI、外部 HTTP、本地能力以及远程 Agent 接入同一个执行接口，并支持 Provider 实时返回进度、增量输出和最终结果。

---

## 0. 命名约定：FCL

本设计中的 LLM 指令语言称为 **FCL（Function-Calling Language）**。

FCL 是面向 LLM 输出的函数式领域语言，用于把自由文本中的工具调用解析成结构化数据：

```text
command=|<|user_query(user_id=1)|>|
```

核心特征：

- 函数式语法：`tool_name(key=value, ...)`
- 锚点定界：`command=|<| ... |>|`
- 参数可用逗号或换行分隔
- `@artifact("path")` 只产生引用，不内联大段内容

FCL **只用于 LLM 输出到 Agent Host 的协议层**。Host 内部、Gateway 与 Provider 之间、工具结果回传均使用结构化 Python 对象或 JSON，不再次传输和解析 FCL。

实现位置为 `yweb.agent.command`，负责 parser / builder / prompt / types，不负责执行、权限、路由和 Provider 通信。

### 0.1 工具命名限制

当前 parser 使用正则表达式 `\w+` 解析工具名：

- `\w` 表示一个“单词字符”。在 Python 默认 Unicode 模式下，它不只包含英文字母、数字和下划线，也可能匹配中文等 Unicode 字符。
- `+` 表示前面的规则至少出现一次，可以连续出现多次。
- 因此 `\w+` 的意思是“连续一个或多个单词字符”，并不是“W 加”，也不负责区分工具在哪里执行。

为了让工具名规则明确、跨语言实现一致，第一版正式约束为：

```regex
[A-Za-z_][A-Za-z0-9_]*
```

含义是：工具名必须以英文字母或下划线开头，后续只能包含英文字母、数字或下划线。例如：

- `user_query`
- `git_status`
- `file_read`

以下名称第一版不允许：

- `123_query`：不能以数字开头
- `user.query`：包含点号
- `git-status`：包含连字符
- `client/file_read`：包含斜杠

工具名只表达业务能力，不编码执行位置。因此不使用 `client_file_read`、`server_file_read` 区分客户端和服务端，也不通过点号命名空间区分。执行位置由 `ToolDefinition.provider` 决定，与 FCL parser 无关。

---

## 1. 背景

YWeb 已有 `yweb.agent.command` 协议层，可以完成：

- FCL 文本解析为 `ParsedCommand`
- 结构化参数构建为 FCL 文本
- 生成供 LLM 使用的工具格式说明

目前缺少从 `ParsedCommand` 到实际工具执行的统一实现，导致各业务场景重复编写工具分发逻辑，也没有统一处理异步调用、权限、超时、取消、本地/远程执行和结果回传。

本设计新增 `yweb.agent.runtime`，将这些复杂性收敛到一个小而稳定的执行接口后面。

---

## 2. 设计决策

1. **协议层保持纯粹**：`yweb.agent.command` 只处理 FCL codec。
2. **执行层从第一版就是异步的**：HTTP、客户端本地执行和远程 Agent 调用天然属于异步 I/O。
3. **执行位置对 LLM 透明**：由工具注册配置决定在服务端、指定客户端或远程 Provider 执行，不让 LLM 选择 `target`。
4. **Gateway 是轻量运行模块，不是微服务中心**：默认与 Agent Host 同进程，只提供注册、路由、校验和执行治理；不要求独立部署、服务网格或集中式基础设施。
5. **机器间只传 JSON**：FCL 只在 Host 解析一次，Provider 不实现第二套 parser。
6. **实时双向通信是正式能力**：支持进度、增量输出、心跳、取消和最终结果。
7. **最低安全基线从阶段 1 开始**：显式注册、参数校验、超时和结果大小限制不能推迟。
8. **Registry 是可注入实例**：不使用不可替换的进程全局单例，避免多应用和测试污染。
9. **工具来源可以是服务端静态注册或客户端动态上报**：服务端能力、客户端能力、远程 API 和外部 Agent 使用相同定义进入 Gateway；能力归属不改变统一调用接口。
10. **发现不等于授权**：LLM 可以通过精确查询或 RAG 检索工具文档并自主选择工具，实际执行仍须经过 Dispatcher、Host 策略和本地沙箱校验。

### 2.1 三类角色与单向调用原则

```text
Agent Host
  持有模型、用户会话和工作流编排权
        │
        ▼
Capability Gateway
  能力注册、发现、路由、校验、权限、超时、取消和审计
        │
        ▼
Capability Provider
  Python / CLI / 本地能力 / Web API / 外部 Agent
```

- `Agent Host` 解析 FCL、选择能力并拥有主动调用权。
- `Capability Gateway` 是可嵌入 Host 的轻量模块，不承担业务实现，也不要求成为独立微服务。
- `Capability Provider` 只接收结构化调用并返回结果、事件或等待状态，不反向调用或控制 Host。

唯一主动调用方向是：

```text
Agent Host → Capability Gateway → Capability Provider
```

Provider 需要用户输入或确认时，只返回 `waiting_input` / `requires_approval` 等声明式状态；由 Host 根据本地策略决定下一步，不建立 `Provider → Host` 的反向 RPC。

### 2.2 客户端能力代理，而不是 MCP 式多 Server 互操作

本设计不要求每个本地设备、内网系统或需要用户身份的公网系统分别实现一套 Agent 协议。客户端运行一个轻量 `Client Capability Proxy`，把用户当前环境中的能力汇总为统一工具：

```text
Client Capability Proxy
├── 本机文件 / CLI / 浏览器
├── 局域网打印机 / NAS / IoT / 其他设备接口
├── 只能从用户内网访问的系统
└── 需要客户端证书、USB Key、浏览器登录态或用户现场授权的公网服务
```

这些下游仍然使用最适合它们的普通接口，例如 HTTP、设备 SDK、系统 API 或 CLI。Proxy 负责协议转换、凭据使用、本地授权和实际调用，只把经过整理的能力定义上报给服务端。

```text
服务端 Agent Host
  └── 结构化 ToolInvocation
             ↓
客户端 Client Capability Proxy
  ├── 选择本地 Adapter
  ├── 请求用户授权
  └── 调用真实设备或服务
```

因此“互操作”被收敛为客户端内部的 Adapter 问题：服务端只面对一个稳定的客户端能力接口，不直接连接用户内网设备，也不要求银行、打印机或第三方软件成为 MCP Server。能够直接由服务端访问的公网接口仍使用 `remote` Adapter；必须使用客户端网络、证书或用户身份的接口注册为 `client` 工具。

---

## 3. 目标与非目标

### 3.1 目标

| 目标 | 说明 |
|------|------|
| 统一执行 | 不同工具都满足同一个异步执行接口 |
| 深接口 | Dispatcher 不感知 Python、CLI、HTTP、本地能力或远程 Agent 通信细节 |
| 运行上下文明确 | 用户、会话、工作区、截止时间等不混入业务参数 |
| 实时回传 | 本地或远程 Provider 持续返回进度、日志和增量结果 |
| 可治理 | 从第一版具备校验、超时、错误封装和显式工具白名单 |
| 可测试 | Registry、Gateway 和 Adapter 均可注入替身测试 |

### 3.2 非目标

- 不实现 LLM 客户端。
- 不实现 DAG、自动补偿等工作流引擎。
- 不建设微服务中心、服务网格或通用 API Gateway。
- 不以 MCP/A2A 作为内部模型；确有外部兼容需求时才通过边缘 Adapter 桥接。
- 不提供通用 `shell_exec`，CLI 必须注册为具名工具。
- 第一版不实现跨服务实例的分布式调度；单进程跑通后再引入 Redis。
- 第一版不承诺断网期间无限续传，只保证明确的失败状态和相同 `invocation_id` 的传输去重。

---

## 4. 总体架构

```text
LLM 输出
   │ FCL
   ▼
yweb.agent.command
   │ ParsedCommand
   ▼
yweb.agent.runtime
   ├── ToolRegistry
   ├── ToolCatalog（精确查询 / RAG 语义发现）
   ├── Dispatcher
   ├── ToolPolicy / 参数校验
   └── Adapter
        ├── FunctionAdapter
        ├── CliAdapter
        ├── HttpAdapter
        ├── WebApiAdapter
        ├── ClientToolAdapter
        └── RemoteAgentAdapter
                 ├── 普通 HTTP API
                 ├── 流式/长任务 API
                 └── 可选 MCP/A2A 兼容 Adapter
```

关键 seam：

- 协议层到执行层：`ParsedCommand`
- Dispatcher 到 Adapter：`await adapter.invoke(invocation, context)`
- Gateway 到 Provider：结构化 `ToolInvocation`，传输由 Adapter 隐藏
- 执行层到上层调用者：`ToolResult` 和可选的实时事件流

---

## 5. 核心数据模型

### 5.1 ToolDefinition

工具注册时必须提供 schema，不再允许“无 schema、手写提示词后直接执行”。手写描述可以保留，但执行参数必须可校验。

```python
@dataclass
class ToolDefinition:
    name: str
    summary: str
    input_schema: dict
    provider: ProviderBinding
    policy: ToolPolicy
```

执行归属显式记录在 `ProviderBinding` 中：

```python
@dataclass(frozen=True)
class ProviderBinding:
    execution_target: Literal["server", "client", "remote"]
    adapter: ToolAdapter
    provider_id: str | None = None
```

```text
server  在 Agent Host 所在服务端执行，例如 Python 函数、服务端 CLI
client  下发结构化调用，由指定客户端执行器调用本地文件、CLI、浏览器
remote  通过 HTTP、流式或长任务 Adapter 调用第三方系统或外部 Agent
```

FCL 中仍然只出现稳定的业务名称，例如 `file_read(...)`。服务端 Gateway 查到 `ToolDefinition` 后，根据 `provider.execution_target` 选择执行位置；LLM 不输出执行位置，也不能自行改变执行位置。

`ToolPolicy` 至少包含：

```python
@dataclass
class ToolPolicy:
    timeout_seconds: float
    max_result_bytes: int
    read_only: bool = False
    destructive: bool = False
    requires_approval: bool = False
    permission_code: str | None = None
```

### 5.2 ToolInvocation 与 ToolContext

业务参数和运行上下文必须分开：

```python
@dataclass
class ToolInvocation:
    invocation_id: str
    tool_name: str
    arguments: dict
    deadline: datetime

@dataclass
class ToolContext:
    user_id: str | None
    session_id: str | None
    client_id: str | None
    workspace_id: str | None
    artifact_base_dir: Path | None
    emit: Callable[[ToolEvent], Awaitable[None]]
```

`invocation_id` 在一次调用生命周期内全局唯一，用于关联结果、进度、取消和断线后的晚到消息。

### 5.3 ToolResult 与 ToolEvent

执行层使用独立结果类型，不直接复用面向 HTTP 响应的 `Resp`：

```python
@dataclass
class ToolResult:
    status: str
    content: object | None
    is_error: bool = False
    error_code: str | None = None
    message: str | None = None
    metadata: dict = field(default_factory=dict)
```

这里不是放弃 YWeb 的“统一响应格式”设计，而是区分领域结果与传输层响应对象：

- `ToolResult` 是工具执行的领域结果，可用于 Python 内部调用、WebSocket、MCP、CLI 等不同 seam。
- `Resp` 当前返回 FastAPI `JSONResponse`，并携带 200、400、401、404、500 等 HTTP 状态码，属于 HTTP seam 的响应构造器。
- 如果 Adapter 直接返回 `Resp`，非 HTTP 调用方就必须理解或反向解析 `JSONResponse`，HTTP 语义也会泄漏到客户端工具、MCP 和内部函数执行中。

两者应统一核心字段和错误语义，而不是强制使用同一个对象。`ToolResult` 尽量沿用 YWeb 已有响应哲学：

```text
status
message
data/content
error_code
```

当工具结果通过 Web API 返回时，在 HTTP seam 做标准转换：

```python
def tool_result_to_resp(result: ToolResult):
    if not result.is_error:
        return Resp.OK(data=result.content, message=result.message or "执行成功")
    return error_code_to_resp(result.error_code, result.message)
```

通过 WebSocket 返回时，则直接序列化成带 `type` 和 `invocation_id` 的 JSON；通过 MCP 返回时，再映射成 MCP 的 structured content / `isError`。因此最终原则是：

> 统一响应字段和错误语义，但不统一传输层响应对象；`ToolResult` 是领域结果，`Resp` 是它在 HTTP seam 上的呈现形式。

实时事件至少支持：

- `progress`：进度、当前步骤
- `output_chunk`：stdout、stderr、增量文本
- `heartbeat`：任务仍在运行但暂时没有输出

最终结果必须自包含，不能要求调用方重放所有 `output_chunk` 才能理解结果。

---

## 6. ToolRegistry 与 Dispatcher

### 6.1 ToolRegistry

Registry 是普通可注入实例，由具体 YWeb app/runtime 持有：

```python
registry.register(ToolDefinition(
    name="user_query",
    summary="查询用户信息",
    input_schema={...},
    provider=ProviderBinding(
        execution_target="server",
        adapter=FunctionAdapter(user_query_handler),
    ),
    policy=ToolPolicy(timeout_seconds=10, max_result_bytes=256_000),
))
```

注册时使用 `[A-Za-z_][A-Za-z0-9_]*` 完整校验工具名，并拒绝重名。即使底层 FCL parser 的 `\w+` 能暂时读出 Unicode 名称，Registry 也不能接受不符合正式规则的工具。工具提示词由 `ToolDefinition` 批量生成，提示词和实际校验使用同一份 schema。

### 6.2 工具目录与发现

工具来源分为两类：

- 服务端通过 `ToolRegistry` 显式注册的能力
- 客户端会话动态上报的本地能力
- 通过 HTTP、流式或长任务 Adapter 注册的远程能力

每项能力提供名称、功能文档、`input_schema`、版本、执行位置和安全要求。远程能力离线或被撤销后，对应定义立即从在线可执行目录失效。

`ToolCatalog` 在静态工具和动态工具之上提供两种发现方式：

```python
class ToolCatalog(Protocol):
    def get(self, name: str, context: ToolContext) -> ToolDefinition | None: ...

    async def search(
        self,
        query: str,
        context: ToolContext,
        limit: int = 10,
    ) -> list[ToolDefinition]: ...
```

- 精确发现：已知工具名时直接查询
- 语义发现：将工具文档建立向量索引，通过 RAG 召回与用户请求相关的候选工具

LLM 可以读取召回工具的名称、说明、schema、示例和风险信息，并自主选择工具；工具较多时，只把召回后的候选工具放入本次提示词，避免注入完整目录。

发现结果只表示“当前可供模型选择”，不构成执行授权。Dispatcher 执行时必须重新确认能力仍在线、参数符合 schema、上下文匹配且权限和审批策略允许；本地 Provider 还要执行本地策略和沙箱校验。

```text
可发现工具 = 服务端注册能力 ∪ 当前在线客户端能力 ∪ 已注册远程能力

当前可执行工具 = 可发现工具
               ∩ 在线能力
               ∩ 上下文适配条件
               ∩ 当前授权策略
```

### 6.3 Dispatcher

Dispatcher 的外部接口保持小而稳定：

```python
async def dispatch(
    parsed: ParsedCommand,
    context: ToolContext,
) -> ToolResult:
    ...
```

内部固定流程：

1. 查找 `ToolDefinition`
2. 校验参数并拒绝未知字段
3. 检查权限和审批策略
4. 创建 `ToolInvocation` 和 deadline
5. 在超时控制下调用 Adapter
6. 限制并规范化结果
7. 记录审计信息并返回 `ToolResult`

Dispatcher 不根据工具类型或执行位置写分支；差异全部隐藏在 Adapter 实现中。

### 6.4 同一轮多个工具调用的并发语义

如果 LLM 在同一轮输出多个普通工具调用，而 FCL 中没有显式依赖信息，运行时无法从调用顺序可靠判断它们是串行还是并行。因此第一版采用明确规则：

> 同一轮输出的多个普通工具调用默认互相独立，并行分发；代码不得根据文本先后顺序擅自推断依赖。

例如同一轮输出：

```text
command=|<|query_user(user_id=1)|>|
command=|<|file_read(path="README.md")|>|
command=|<|search_docs(query="权限设计")|>|
```

解析后生成三个独立 `ToolInvocation`。Dispatcher 可以同时把它们分别路由到服务端、客户端和远程 Provider，再按原调用标识汇总结果。

需要串行依赖时只能使用以下两种方式：

1. **多轮调用**：LLM 第一轮只调用前置工具；收到结果后，下一轮再输出依赖该结果的工具调用。
2. **显式依赖协议**：未来增加独立的批量计划结构，由 LLM 明确输出 `call_id` 和 `depends_on`。在该结构正式定义前，不支持同一批普通 FCL 调用的隐式串行。

示意：

```json
{
  "calls": [
    {"call_id": "read", "tool": "file_read", "arguments": {}},
    {"call_id": "analyze", "tool": "analyze_document", "arguments": {}, "depends_on": ["read"]}
  ]
}
```

此结构属于未来的显式编排扩展，不属于普通 `ToolInvocation`，也不能由 Dispatcher 猜测生成。

### 6.3 Adapter 接口

```python
class ToolAdapter(Protocol):
    async def invoke(
        self,
        invocation: ToolInvocation,
        context: ToolContext,
    ) -> ToolResult: ...
```

| Adapter | 作用 |
|---------|------|
| `FunctionAdapter` | 调用同步或异步 Python 函数；同步函数放入受控线程池 |
| `CliAdapter` | 调用预定义 argv 模板，禁用 `shell=True`，限制环境变量、目录和进程树 |
| `HttpAdapter` | 调用外部 HTTP，控制认证、域名、超时和响应大小 |
| `WebApiAdapter` | 将显式允许的 FastAPI 路由暴露为工具 |
| `ClientToolAdapter` | 通过轻量客户端会话通道下发结构化调用，等待客户端执行结果 |
| `RemoteAgentAdapter` | 将外部 Agent 的普通 API 或长任务 API 适配为统一工具调用 |

MCP/A2A 若将来需要兼容，只作为 `RemoteAgentAdapter` 或外部 Provider 的可选传输实现，不进入核心接口。

---

## 7. Web API 工具接入

不直接复用 `APIResourceController.scan()` 作为工具扫描器。当前 `scan()` 主要把路由的 path、method 和 name 写入权限资源表，不能提供完整的参数 schema、请求体、响应模型和依赖信息。

正确方式是抽取独立的“FastAPI 路由元数据读取”实现，基于 `app.routes` 或 OpenAPI schema 生成 `ToolDefinition`。RBAC 路由扫描和 Agent 工具扫描可以共享底层元数据读取代码，但保持各自用途。

Web API 默认不自动成为工具，必须显式声明，例如：

```python
@post(..., agent_tool=True, agent_tool_name="user_create")
async def create_user(...):
    ...
```

内部 Web API 是否通过 ASGI transport、HTTP 请求或直接调用业务函数，由 `WebApiAdapter` 决定；不能因为“同服务”就绕过原有认证语义。

---

## 8. 服务端 Agent Loop 与客户端工具执行

### 8.1 总体结构

Agent Host、LLM Loop、FCL parser 和 Capability Gateway 通常位于服务端。客户端只运行轻量 `Client Capability Proxy`，不运行第二套 Agent Loop，也不建设微服务中心：

```text
服务端 Agent Host
├── LLM Loop / FCL parser
├── CapabilityGateway
│   ├── ToolRegistry / ToolCatalog
│   ├── Dispatcher / ToolPolicy
│   ├── ServerAdapter
│   ├── ClientToolAdapter ───────┐
│   └── HttpAdapter / RemoteAgentAdapter
└───────────────────────────────│────────
                                │ 结构化 ToolInvocation
客户端 Client Capability Proxy  │
├── ClientToolRegistry <────────┘
├── ApprovalPolicy
├── SandboxRunner
└── Adapter
    ├── 本机文件 / CLI / 浏览器
    ├── 内网设备 / 内网系统
    └── 客户端证书 / USB Key / 用户登录态保护的公网服务
```

客户端工具可以在建立会话时向服务端上报定义：

```json
{
  "tools": [
    {
      "name": "file_read",
      "summary": "读取当前工作区中的文件",
      "description": "读取指定文本文件并返回内容",
      "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
      "version": "1.0.0",
      "policy": {"read_only": true, "requires_approval": false},
      "sandbox_profiles": ["workspace_readonly"]
    }
  ]
}
```

服务端将客户端能力绑定到 `user_id / client_id / workspace_id / connection_id`。客户端断线后，对应工具立即变为不可执行。第一版只需要进程内连接表和 WebSocket/SSE 通道；只有多服务实例确有需要时才增加 Redis。

### 8.2 谁解析、谁路由、谁真正调用

同一个 Agent Loop 中存在三个不同责任，不能都笼统称为“调用工具”：

1. **服务端 Agent Loop 发起工具意图**：LLM 输出 FCL。
2. **服务端 Gateway 解析和路由**：FCL 只在服务端解析一次，生成结构化 `ToolInvocation`，并根据 `execution_target` 选择执行方。
3. **执行方真正调用工具**：服务端工具由服务端 Adapter 调用；客户端工具由 Client Capability Proxy 校验后，通过本地 Adapter 调用本机、内网设备或需要客户端身份的公网服务。

因此客户端不解析 FCL。服务端也不直接获得客户端文件系统或进程调用能力；它只能向已连接客户端发送结构化调用请求。

```text
LLM 输出 FCL
      │
      ▼ 只解析一次
服务端 Agent Host / Gateway
      │
      ├── execution_target=server
      │       └── 服务端 Adapter 真正调用工具
      │
      ├── execution_target=client
      │       └── 发送结构化 ToolInvocation
      │               ▼
      │          客户端 Proxy 再校验、审批并选择 Adapter
      │               └── 客户端真正调用本地工具
      │
      └── execution_target=remote
              └── 服务端 Adapter 调用第三方 API/Agent
```

这里服务端拥有 Agent Loop 的编排权，客户端拥有其代理能力的最终执行权。客户端可以因工具未注册、设备不可达、证书不可用、权限不足、用户拒绝或沙箱限制而拒绝执行。

### 8.3 FCL 不作为机器间格式

FCL 在服务端 Agent Host 中解析一次，服务端内部使用结构化对象，客户端只接收 JSON。这样可以：

- 避免 Python 与前端 parser 行为漂移
- 防止任何远程 Provider 重复解释未经验证的 LLM 文本
- 明确传递调用 ID、deadline、工作区和沙箱配置
- 让浏览器、桌面端和其他客户端使用相同结构化协议

客户端收到的消息必须至少包含：

```json
{
  "type": "tool.invoke",
  "invocation_id": "01J...",
  "tool": "file_read",
  "arguments": {"path": "README.md"},
  "deadline": "2026-07-12T04:30:00Z",
  "workspace_id": "project-123"
}
```

客户端按 `invocation_id` 返回 `accepted / progress / output_chunk / result / error`。它只理解这套结构化执行协议，不需要实现 FCL parser。

### 8.4 Provider 任务事件

本地或远程 Provider 的典型调用流程：

```text
Host/Gateway                    Provider
  │── tool.invoke ─────────────>│
  │<─ tool.accepted ────────────│
  │<─ tool.progress ────────────│
  │<─ tool.output_chunk ────────│  可重复多次
  │── tool.cancel ─────────────>│  可随时取消
  │<─ tool.result / tool.error ─│
```

调用消息示例：

```json
{
  "type": "tool.invoke",
  "invocation_id": "01J...",
  "tool": "file_read",
  "arguments": {"path": "src/main.py"},
  "deadline": "2026-07-12T04:30:00Z",
  "workspace_id": "project-123",
  "sandbox_profile": "workspace_readonly"
}
```

增量输出示例：

```json
{
  "type": "tool.output_chunk",
  "invocation_id": "01J...",
  "sequence": 12,
  "stream": "stdout",
  "content": "正在编译 module_a...\n"
}
```

### 8.4 实时输出与背压

Provider 不能无上限发送每一行日志：

- 合并约 50～200ms 内的小块输出
- 每个 chunk 带递增 `sequence`
- 限制单 chunk 和累计输出大小
- Host 可以确认最后消费的序号
- Host 消费变慢时，Provider 暂停、合并或丢弃低价值日志，并显式报告截断
- 最终结果独立于增量日志

第一版可以只做有界队列和截断，不必立即实现断线续传。需要续传时，再增加 `last_acked_sequence` 和有限大小的 Provider 环形缓冲区。

---

## 9. 任务状态、超时、取消与断线

### 9.1 状态机

```text
created → dispatched → accepted → running
                                ├→ completed
                                ├→ failed
                                ├→ timed_out
                                └→ cancelled
```

`completed`、`failed`、`timed_out`、`cancelled` 是终态。进入终态后，晚到结果只能记录，不能再次改变状态。

### 9.2 三类超时

| 超时 | 含义 | 示例 |
|------|------|------|
| `accept_timeout` | Provider 收到调用后多久必须确认接收 | 5 秒 |
| `execution_timeout` | 工具允许执行的总时长 | 按工具配置 |
| `idle_timeout` | 运行中多久没有进度、输出或任务心跳才认为卡死 | 30 秒 |

`idle_timeout` 不代表非实时等待。Provider 执行期间可以持续返回 `progress` 和 `output_chunk`；暂时没有输出的长任务发送任务心跳。

连接心跳和任务心跳必须分开：

- 连接心跳证明 WebSocket/Client Agent 在线
- 任务心跳证明某个具体任务仍在运行

### 9.3 取消语义

Host 或用户可发送：

```json
{
  "type": "tool.cancel",
  "invocation_id": "01J...",
  "reason": "user_requested"
}
```

取消是尽力而为：Provider 应停止任务并释放资源，但必须处理“取消和完成同时发生”的竞态。Host 状态机是最终裁决者。

### 9.4 断线语义

第一版规则：

- 未 `accepted` 即断线：调用失败，可由上层决定是否重试
- 已运行时断线：标记 `client_disconnected`，尝试取消本地任务
- Provider 重连不自动重跑旧调用
- 框架对所有工具一律不自动重试，不区分“幂等工具”和“非幂等工具”
- 相同 `invocation_id` 的重复投递只属于传输去重，客户端返回已保存结果或当前状态，不再次执行
- 如果结果不确定，Agent 应先调用查询工具确认现实状态，再决定是否生成一次新的调用

---

## 10. Host 策略与本地沙箱

本地 Provider 的沙箱是必要的，但不能替代 Host 的权限控制。

### 10.1 Host 职责

- 工具必须显式注册
- 校验用户权限和工具策略
- 校验参数、结果大小和数据发送范围
- 决定是否需要用户审批
- 记录调用与结果摘要
- 不信任 Provider 自行声明“已安全执行”

### 10.2 本地 Provider 职责

- 验证调用来自当前受信 Host/Gateway
- 只执行本机已注册工具
- 实施本地用户审批
- 限制文件、进程、网络和环境变量
- 执行超时、取消和资源回收
- 对结果和日志做大小限制

### 10.3 第一版沙箱最低要求

- 路径规范化后必须位于允许的工作区根目录
- 防止 `..`、符号链接或 junction 逃逸
- CLI 使用预定义 argv，禁用 `shell=True`
- 环境变量使用白名单，不默认继承全部宿主环境
- 固定工作目录，调用使用独立临时目录
- 网络默认关闭，按工具声明域名白名单
- 可终止整个子进程树
- 限制运行时长、stdout/stderr 和最终结果大小
- 读、写、执行和网络权限分别声明，不使用单一“完全信任”开关

后续可按平台增强为 Windows 受限 Token / Job Object、Linux namespace / seccomp / cgroups、macOS sandbox profile 等 OS 级隔离。

---

## 11. 错误模型与审计

必须区分：

- **协议错误**：未知工具、消息格式错误、调用 ID 不存在
- **校验错误**：参数不符合 schema
- **策略错误**：权限不足、审批拒绝、沙箱策略不允许
- **执行错误**：工具本身失败
- **基础设施错误**：Provider 离线、连接断开、超时

错误返回稳定的 `error_code`，例如：

- `TOOL_NOT_FOUND`
- `INVALID_ARGUMENTS`
- `PERMISSION_DENIED`
- `APPROVAL_REJECTED`
- `CLIENT_OFFLINE`
- `CLIENT_DISCONNECTED`
- `TIMEOUT`
- `RESULT_TOO_LARGE`
- `EXECUTION_FAILED`

审计记录不得无上限保存完整 stdout、密钥或敏感文件内容，只记录必要参数摘要、策略结果、耗时、终态和截断后的错误摘要。

---

## 12. 分阶段落地计划

### 阶段 1：Host 最小执行闭环

- 新增 `yweb.agent.runtime`
- 实现可注入 `ToolRegistry`
- 实现 `ToolDefinition` / `ToolPolicy` / `ToolInvocation` / `ToolContext` / `ToolResult`
- 实现异步 `Dispatcher`
- 实现 `FunctionAdapter`
- 同时实现 schema 校验、超时、结果大小限制和稳定错误码
- 从同一 schema 生成工具提示词

产出：Python 工具可安全注册并执行，核心接口和测试 seam 得到验证。

### 阶段 2：轻量 Gateway 与本地能力闭环

- 在 Agent Host 内嵌入 `CapabilityGateway`
- 实现本地能力注册、更新和撤销
- 实现本地与远程能力的统一 `ToolCatalog` 精确查询
- 支持 `invoke / accepted / progress / output_chunk / result / error / cancel`
- 实现调用状态机、三类超时和有界输出队列
- 实现最小工作区沙箱

产出：一个 Host 可以统一调用本地能力和远程 API，并实时接收结果或取消。

### 阶段 3：治理与发现

- 能力目录和 Provider 路由策略
- 工具文档向量索引与 RAG 语义发现
- 根据上下文过滤候选工具并生成本次 LLM 工具提示词
- 用户、会话、工作区上下文
- RBAC 权限、审批和审计
- 并发限制与限流
- 明确框架不自动重试；失败或结果不确定时由 Agent 查询状态后重新决策

产出：支持多用户、多工作区的受控执行，不要求集中式微服务中心。

### 阶段 4：外部 Adapter

- `HttpAdapter`
- `CliAdapter`
- 显式标记的 `WebApiAdapter`
- `RemoteAgentAdapter`（普通 API、流式 API、长任务 API）
- 抽取 FastAPI 路由元数据读取模块，供 RBAC 和工具扫描分别复用

产出：异构远程能力统一接入。

### 阶段 5：分布式与高级能力（按实际需要）

- Redis 会话路由和任务状态
- 多服务实例下的消息转发
- 有限断线续传
- 长任务持久化与查询
- OS 级强化沙箱

这些能力只有在单实例闭环已经证明有实际需求后再实现。

---

## 13. 与现有模块的关系

| 现有模块 | 复用方式 |
|---------|---------|
| `yweb.agent.command` | 只负责 FCL 与 `ParsedCommand`，不加入执行和通信概念 |
| `yweb.rbac` | 提供 Host 权限判断；不直接把所有路由暴露成工具 |
| `APIResourceController.scan` | 不直接作为工具扫描器；未来与工具扫描共享路由元数据读取实现 |
| `yweb.response.Resp` | 与 `ToolResult` 共享核心字段和错误语义；仅在 HTTP seam 将 `ToolResult` 转成 `JSONResponse` |
| `yweb.log` | 记录脱敏后的调用审计和状态变化 |
| `yweb.ratelimit` | 对用户、工具和 Provider 调用进行限流 |
| `yweb.orm.async_db_call` | 仅供涉及同步 ORM 的具体 handler 使用，不作为统一异步 Adapter 方案 |

`httpx` 若用于正式 `HttpAdapter` / `WebApiAdapter`，应移入正式依赖或独立的可选依赖组，不能只保留在 dev dependencies。

---

## 14. 待实现验证的问题

以下问题保留到相应阶段用原型和测试决定：

1. `ToolSchema` 使用 Pydantic Model、JSON Schema，还是两者互转。
2. Host 审批是按单次、会话、工作区还是永久授权；高风险工具是否禁止永久授权。
3. `@artifact` 的解析基目录、允许协议及目录逃逸防护。
4. 增量输出采用简单有界队列，还是第一版就增加 ack。
5. Provider 重连后是否允许查询仍在运行的任务。
6. 远程 Agent 长任务如何映射为 `ToolResult` / `ToolEvent` / `ExecutionHandle`。
7. 工具 schema 版本变化后的兼容和提示词缓存失效策略。
8. 如果未来需要单轮显式依赖，批量计划结构放在独立编排层；普通同轮工具调用固定默认并行，Dispatcher 不推断依赖。
9. 工具向量索引采用何种 embedding、更新策略和租户隔离方式。
10. 外部能力文档如何进行提示注入防护、大小限制和可信度标记。

---

## 15. 设计原则小结

1. FCL 只服务于 LLM 输出解析，机器间使用结构化 JSON。
2. Dispatcher 只依赖一个异步 Adapter 接口，执行位置和通信细节隐藏在实现内。
3. 业务参数与用户、会话、工作区等运行上下文分离。
4. Gateway 默认与 Agent Host 同进程，是轻量运行模块，不做微服务中心。
5. FCL 只在服务端解析；服务端工具由服务端调用，客户端工具由客户端 Runtime 在收到结构化请求并校验后真正调用。
6. 参数校验、白名单、超时和结果限制是基础能力，不推迟到最后。
7. Host 授权与本地 Provider 沙箱构成双层安全，双方都不能单独替代另一方。
8. 先完成单服务端、单客户端闭环，再按真实需求增加 Redis、续传和 OS 级隔离。
9. 本地能力、远程 API 和外部 Agent 使用同一 ToolDefinition 注册，执行位置只影响 Adapter。
10. LLM 可以通过精确查询或 RAG 阅读并发现工具，但发现、授权和沙箱执行是三个独立环节。
11. 同一轮多个普通工具调用默认并行；串行只能通过多轮调用或 LLM 显式输出依赖结构表达。
