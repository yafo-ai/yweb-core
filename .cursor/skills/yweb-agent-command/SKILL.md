---
name: yweb-agent-command
description: YWeb Agent 指令系统使用规范。在编写或修改 LLM 文本指令的解析（parser）、分发（dispatcher）、内置/自定义 Handler、提示词生成（prompt）、指令 DSL（函数式语法 role()/agent()/@artifact()）等代码时使用。该系统是 LLM 与工作流引擎之间的通信协议，不绑定任何具体引擎。
---

# YWeb Agent 指令系统使用规范

本 Skill 是为 `yweb.agent`（Agent 指令系统）编写代码的**权威指南**。指令系统是
**LLM 与工作流引擎之间的通信协议**：从 LLM 文本输出中解析结构化指令，按类型分发到
Handler 执行，并生成指令格式的提示词说明。

> **核心定位**：本模块**不绑定**任何特定的工作流引擎、图引擎或 LLM 实现，只提供四件事：
> 解析（parser）、分发（dispatcher）、内置 Handler（handlers）、提示词生成（prompt）。
> 消费者通过实现 `CommandContext` 协议把指令执行桥接到自己的业务对象上。

---

## 1. 模块结构

```
yweb/agent/
├── __init__.py          # 统一导出（公共 API 入口）
├── types.py             # 数据模型：ParsedCommand / CommandResult / CallValue / ArtifactRef
├── context.py           # CommandContext 协议（消费者实现）
├── dispatcher.py        # CommandDispatcher（按 toolname 路由 + 并发执行）
├── prompt.py            # CommandPromptBuilder（指令格式提示词文本生成）
├── parser/
│   ├── __init__.py
│   └── parser.py        # parse_command_output / parse_param_string / split_param_expressions
└── handlers/
    ├── base.py          # BaseCommandHandler 协议
    └── builtin/         # 6 个内置 Handler
        ├── assignment.py        # AssignmentHandler
        ├── write_var.py         # WriteVarHandler
        ├── notify.py            # NotifyHandler
        ├── send_message.py      # SendMessageHandler
        ├── terminate.py         # TerminateHandler
        └── custom_function.py   # CustomFunctionHandler（通配兜底）
```

测试位于 `tests/test_agent/`：`test_parser.py` / `test_dsl.py` / `test_handlers.py` /
`test_dispatcher.py` / `test_prompt.py` / `test_parser_regression.py`（回归快照）。

---

## 2. 核心架构原则

1. **引擎无关**：指令系统不 import 任何 WorkingSpace / Graph / LLM；所有外部交互走 `CommandContext`。
2. **数据容器用 `@dataclass`**（不用 Pydantic）：与 yweb-core 内部数据对象约定一致。
3. **协议用 `@runtime_checkable` Protocol**：`CommandContext`、`BaseCommandHandler` 都是鸭子类型协议，自定义实现**无需继承**。
4. **超集兼容**：解析器是 y-agent 解析算法的**超集**——新 DSL 与旧 JSON 字面量形态都要能解析，且回归快照保持全绿。
5. **可选依赖降级**：`json-repair` 缺失时跳过畸形 JSON 修复，模块仍可导入与使用。

---

## 3. 指令 DSL 规范

### 3.1 指令包络

LLM 输出中的指令以 `command=|<| toolname(args) |>|` 形式出现，解析器从文本中提取
`<| toolname(args) |>` 片段。一段文本可包含多条指令，按出现顺序提取。

```
command=|<|assignment(next_roles=[role(name="客服", message="处理咨询")])|>|
```

### 3.2 一套函数式语法（推荐）

DSL 只保留一套规则，比 JSON 对象更利于小模型稳定生成：

- **函数用小括号**：`toolname(参数名=值, ...)`、内部对象 `role(...)`、`agent(...)`
- **数组用方括号**：`next_roles=[...]`、`tags=[...]`、`queries=[...]`
- **内部对象统一为函数调用** → 解析为 `CallValue`：

```text
<|assignment(
    next_roles=[
        role(name="商品参数客服" message="提供加墨步骤")
        agent(name="商品故障客服" task="排查加墨故障")
    ]
)|>
```

- **外部资源用 `@artifact(...)`** → 解析为 `ArtifactRef`（长 SQL / Python / Prompt 不要内联）：

```text
<|run_sql(script=@artifact("sql/query.sql"))|>
```

### 3.3 参数分隔符（换行 / 逗号都兼容）

标准写法建议用**换行**；解析器同时兼容**逗号**。引号内、`()`/`[]`/`{}` 内的分隔符不切分。

```text
role(name="客服" message="任务" priority=1)      # 推荐：换行分隔
role(name="客服", message="任务", priority=1)     # 兼容：逗号分隔
```

### 3.4 向后兼容（旧形态仍可解析）

旧 JSON 字面量形态保持原行为，不被改写：

```text
<|assignment(next_roles=[{"role":"客服","message":"任务"}])|>   # 旧形态 → list[dict]
<|write_var(tags=[1, 2, 3])|>                                     # 纯字面量数组 → list
```

> **关键约定**：值是 `name(...)` 形态才解析为 `CallValue`；带引号的 `"role(x)"` 仍是字符串；
> 未知 `@xxx(...)`（非 `@artifact`）保留为原始字符串。

---

## 4. 公共 API 速查

全部从 `yweb.agent` 导出：

| 符号 | 类型 | 说明 |
|------|------|------|
| `parse_command_output(text)` | 函数 | 文本 → `List[ParsedCommand]`（括号平衡扫描，支持嵌套） |
| `parse_param_string(s)` | 函数 | 参数串 → `Dict[str, Any]`（值含 `CallValue`/`ArtifactRef`/字面量） |
| `split_param_expressions(s)` | 函数 | 状态机分割参数表达式（兼容换行/逗号） |
| `CommandDispatcher` | 类 | 按 toolname 路由 + 并发执行 |
| `WILDCARD_HANDLER_NAME` | 常量 | 通配 Handler 注册标记 |
| `CommandContext` | Protocol | 消费者实现的执行上下文 |
| `BaseCommandHandler` | Protocol | Handler 协议 |
| `ParsedCommand` / `CommandResult` | dataclass | 指令 / 结果数据模型 |
| `CallValue` / `ArtifactRef` | dataclass | 函数式内部对象 / 工件引用 |
| `CommandPromptBuilder` | 类 | 指令格式提示词文本生成 |
| `AssignmentHandler` … `CustomFunctionHandler` | 类 | 6 个内置 Handler |

### 4.1 数据模型

```python
@dataclass
class ParsedCommand:
    toolname: str                       # 指令名，永不为空
    args: Dict[str, Any]

@dataclass
class CallValue:                        # role(name=..., message=...) 等内部对象
    name: str                           # 函数名即类型标识（role/agent/ref/...）
    args: Dict[str, Any]

@dataclass
class ArtifactRef:                      # @artifact("path")，仅产生引用标记，不读文件
    path: str

@dataclass
class CommandResult:
    toolname: str
    success: bool
    target_roles: List[str]             # assignment 产出的下游角色
    return_value: Any                   # 函数调用返回值（ReAct 场景）
    error: Optional[str]
    is_terminal: bool                   # terminate 标记
    start_time / end_time / duration    # dispatcher 统一记录
```

---

## 5. 快速开始

```python
from yweb.agent import (
    CommandDispatcher, WILDCARD_HANDLER_NAME,
    AssignmentHandler, WriteVarHandler, NotifyHandler,
    SendMessageHandler, TerminateHandler, CustomFunctionHandler,
    parse_command_output,
)

# 1) 注册内置 Handler
dispatcher = CommandDispatcher()
dispatcher.register_many({
    "assignment": AssignmentHandler(),
    "write_var": WriteVarHandler(),
    "notify": NotifyHandler(),
    "send_message": SendMessageHandler(),
    "terminate": TerminateHandler(),
    WILDCARD_HANDLER_NAME: CustomFunctionHandler(),   # 通配兜底：处理自定义函数
})

# 2) 解析并分发
commands = parse_command_output(llm_output_text)      # List[ParsedCommand]
results = dispatcher.dispatch(commands, my_context)    # List[CommandResult]
```

---

## 6. 内置指令与 Handler

| 指令 | Handler | 行为 | 失败条件（`success=False`） |
|------|---------|------|------------------------------|
| `assignment` | `AssignmentHandler` | 对 `next_roles` 每项 `add_message`，返回去重 `target_roles` | 缺 `next_roles`；某项角色名为 None |
| `write_var` | `WriteVarHandler` | 对每个 kv 调用 `write_variable` | 无（恒成功） |
| `notify` | `NotifyHandler` | `add_message(current, receiver, message)`，`receiver` 默认 `"human"` | `message` 为 None/空白 |
| `send_message` | `SendMessageHandler` | `add_message(current, receiver, message)` | `receiver` 或 `message` 为 None/空白 |
| `terminate` | `TerminateHandler` | `set_terminate()` + 发消息给 `"human"`，`is_terminal=True` | `message` 缺失（None） |
| `*`（通配） | `CustomFunctionHandler` | 用 `command.toolname` 作函数名调用 `call_function` | 函数抛异常（`return_value="工具错误：..."`） |

### 6.1 Handler 超集兼容写法

Handler 消费 `args` 时必须同时兼容新 DSL（`CallValue`）与旧 dict。参考 `AssignmentHandler`：

```python
from yweb.agent.types import CallValue

def _extract_role_message(item):
    if isinstance(item, CallValue):                 # role(name=..., message=...) / agent(name=..., task=...)
        args = item.args
        role = args.get("name", args.get("role"))
        message = args.get("message", args.get("task", ""))
    elif isinstance(item, dict):                    # 旧形态 {"role":..., "message":...}
        role = item.get("role")
        message = item.get("message", "")
    else:
        return None, ""
    return role, message if message is not None else ""
```

---

## 7. 实现 CommandContext（消费者侧）

`CommandContext` 是指令系统与业务的唯一边界。写方法被 dispatcher 并发调用，**必须线程安全**。

```python
import threading

class AgentCommandContext:
    """实现 yweb.agent.CommandContext 协议（鸭子类型，无需继承）。"""

    def __init__(self, working_space):
        self._ws = working_space
        self._lock = threading.Lock()

    @property
    def current_role(self) -> str:
        return self._ws.current_role

    def add_message(self, from_role, to_role, message):
        with self._lock:
            self._ws.add_talk(from_role, to_role, message)

    def write_variable(self, key, value):
        with self._lock:
            self._ws.set_var(key, value)            # space/role 分流逻辑在此实现

    def call_function(self, name, args):
        return self._ws.invoke_tool(name, **args)

    def has_function(self, name) -> bool:
        return self._ws.has_tool(name)

    def get_function_option(self, name):
        return self._ws.get_tool_option(name)

    def set_terminate(self):
        with self._lock:
            self._ws.terminate()
```

---

## 8. 自定义 Handler

实现 `BaseCommandHandler` 协议（`toolname` 属性 + `handle` 方法）后注册即可，无需继承：

```python
from yweb.agent import CommandDispatcher
from yweb.agent.types import CommandResult, ParsedCommand
from yweb.agent.context import CommandContext

class SummaryHandler:
    @property
    def toolname(self) -> str:
        return "summary"

    def handle(self, command: ParsedCommand, context: CommandContext) -> CommandResult:
        text = command.args.get("text", "")
        if not text:
            return CommandResult(toolname=command.toolname, success=False, error="empty text")
        # ... 业务逻辑 ...
        return CommandResult(toolname=command.toolname, success=True, return_value="...")

dispatcher.register("summary", SummaryHandler())
```

> `CustomFunctionHandler.handle` 必须接收完整 `ParsedCommand`（而非只接 args），因为它靠
> `command.toolname` 拿真实函数名——这是通配兜底机制能工作的关键。

---

## 9. 提示词生成（CommandPromptBuilder）

只生成**文本**，不感知节点/图/LLM。消费者传入角色/变量/函数信息，拿回文本自行拼接：

```python
from yweb.agent import CommandPromptBuilder

# 角色数 <= 1 时返回空串（无需选择）
text = CommandPromptBuilder.assignment_prompt(
    roles=[{"role": "客服", "description": "处理咨询"}, {"role": "质检", "description": "审核"}]
)
CommandPromptBuilder.write_var_prompt(variables_json="...")
CommandPromptBuilder.function_prompt(func_name="search", description="检索", command_example="search(q=\"...\")")
CommandPromptBuilder.react_prompt(step=1, max_times=5)    # step >= max_times 输出强制结束引导
```

---

## 10. 解析器内部结构（修改 parser.py 时必读）

- `parse_command_output`：**括号平衡扫描**——`_COMMAND_START` 定位 `<|name(`，用
  `_find_matching_paren`（引号/转义感知）找匹配 `)`，再要求其后为 `|>`。**禁止退回非贪婪正则**。
- `parse_param_string` → `split_param_expressions` 拆参数 → 每个值过 `_parse_value`。
- `_parse_value` 优先级：`@artifact(...)` → `name(...)` 函数调用（`CallValue`，递归）→
  含调用/引用的数组（逐元素解析）→ 否则 `_parse_literal`（`ast.literal_eval` + 可选 `json_repair`）。

> 修改任一环节后，必须跑回归快照 `test_parser_regression.py`。该快照锚定 yweb-core 自身行为：
> 多数与 y-agent 一致，但**引号不配对的畸形输入**有意分歧（详见快照文件 `_note`）。

---

## 11. 测试规范

测试编写遵循 `.cursor/skills/yweb-testing/SKILL.md`，并注意本模块要点：

- 解析/DSL/Handler 用例分别放 `test_parser.py` / `test_dsl.py` / `test_handlers.py`。
- Handler 测试用 `conftest.py` 的 `context` fixture（`MockContext`，记录所有调用）。
- 辅助类（如 `MockContext`）**不能**以 `Test` 开头。
- 每个核心行为至少一个**失败/边界反例**（空参数、缺字段、畸形输入、不配对括号 → `[]`）。
- 改解析逻辑后回归快照必须全绿。
- 测试失败时遵循 `test-quality-and-failure-workflow.mdc`：先诊断 → 给 ≥2 方案 → 用户确认后再改。

---

## 12. 可选依赖

```toml
# pyproject.toml
[project.optional-dependencies]
agentcmd = ["json-repair>=0.29.0"]
```

```bash
pip install "yweb[agentcmd]"     # 启用畸形 JSON 修复（与 y-agent 字面量行为完全一致）
```

未安装时 `parser.repair_json is None`，自动降级跳过修复。回归用例据此 `pytest.skip`。

---

## 13. 常见反模式（避免）

```python
# ❌ 在指令系统内 import 具体引擎 / LLM
from myproject.workflow import WorkingSpace   # 破坏引擎无关性

# ❌ 用 Pydantic BaseModel 承载内部数据对象
class ParsedCommand(BaseModel): ...           # 应用 @dataclass

# ❌ 命令提取退回非贪婪正则
re.findall(r"\<\|(\w+)\((.*?)\)\|>", text)    # 无法支持嵌套，误判引号内 )|>

# ❌ Handler 只吃 dict，忽略 CallValue
role = item["role"]                            # 新 DSL role(...) 会 KeyError

# ❌ CommandContext 写方法不加锁
def add_message(self, *a): self._ws.add(*a)   # dispatcher 并发下不安全

# ❌ json-repair 缺失时直接报错
from json_repair import repair_json            # 顶层硬 import，破坏可选降级
```

```python
# ✅ 通过 CommandContext 协议解耦
# ✅ 数据容器用 @dataclass，协议用 Protocol
# ✅ 命令提取用括号平衡扫描（引号/转义感知）
# ✅ Handler 同时兼容 CallValue 与旧 dict
# ✅ CommandContext 写方法加锁
# ✅ json-repair 用 try/except 降级为可选依赖
```

---

## 14. 快速检查清单

修改指令系统代码前，对照此清单：

- [ ] 未引入对具体引擎/LLM 的依赖（仅通过 `CommandContext` 交互）
- [ ] 新数据容器用 `@dataclass`，新协议用 `@runtime_checkable Protocol`
- [ ] 新值类型已在 `types.py` 定义并在 `agent/__init__.py` 与 `yweb/__init__.py` 导出
- [ ] 解析改动保持超集兼容（新 DSL + 旧 JSON 字面量都能解析）
- [ ] 命令提取仍用括号平衡扫描，未退回非贪婪正则
- [ ] Handler 同时兼容 `CallValue` 与旧 dict 形态
- [ ] `CommandContext` 写方法线程安全
- [ ] 回归快照 `test_parser_regression.py` 全绿
- [ ] 新增/改动有对应单元测试 + 关键反例
- [ ] `ruff check` 与 `mypy`（`yweb/agent`）零错误
