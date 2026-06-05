---
name: yweb-agent-command
description: YWeb Agent 指令系统使用规范。在编写或修改 LLM 文本指令的解析（parser）、构建（builder）、格式说明生成（prompt）、指令 DSL（函数式 item()/record()/@artifact()）等代码时使用。
---

# YWeb Agent 指令系统使用规范

本 Skill 是为 `yweb.agent`（Agent 指令系统）编写代码的**权威指南**。

> **核心定位**：本模块提供三项能力——
>
> 1. **解析（parser）**：`command` 文本 → `ParsedCommand`（工具名 + 参数）。
> 2. **构建（builder）**：结构化参数 → `command=|<|...|>|` 文本（`parse` 的逆操作）。
> 3. **格式说明（prompt）**：工具描述 → 指令格式说明文本（供 LLM 提示词拼接）。

---

## 1. 模块结构

```
yweb/agent/
├── __init__.py          # 统一导出（公共 API 入口）
├── types.py             # 数据模型：ParsedCommand / CallValue / ArtifactRef
├── builder.py           # build_command（结构化 → command 文本）
├── prompt.py            # CommandPromptBuilder（格式说明文本生成）
└── parser/
    ├── __init__.py
    └── parser.py        # parse_command_output / parse_param_string / split_param_expressions
```

测试位于 `tests/test_agent/`：`test_parser.py` / `test_dsl.py` / `test_builder.py` / `test_prompt.py`。

---

## 2. 核心架构原则

1. **范围限定为三项能力**：解析、构建、格式说明生成。
2. **零外部运行时依赖**：仅用标准库 `ast` / `re`，不依赖 `json-repair` 等。
3. **零框架耦合**：不 import 工作流引擎、LLM 客户端等外部运行时。
4. **数据容器用 `@dataclass`**（不用 Pydantic）：与 yweb-core 内部数据对象约定一致。
5. 解析失败要**优雅降级**（保留原始字符串 / 去引号），不抛异常、不修复畸形 JSON。

---

## 3. 指令 DSL 规范

### 3.1 指令包络

LLM 输出中的指令以 `command=|<| toolname(args) |>|` 形式出现，解析器从文本中提取
`<| toolname(args) |>` 片段。一段文本可包含多条指令，按出现顺序提取。

```
command=|<|invoke(items=[item(name="A", text="处理请求")])|>|
```

### 3.2 函数式语法

- **函数用小括号**：`toolname(参数名=值, ...)`、嵌套对象 `item(...)`、`record(...)`
- **数组用方括号**：`items=[...]`、`tags=[...]`、`queries=[...]`
- **嵌套对象统一为函数调用** → 解析为 `CallValue`：

```text
<|invoke(
    items=[
        item(
            name="A"
            text="提供操作步骤"
        )
        record(
            id="B"
            value="排查异常"
        )
    ]
)|>
```

- **外部资源用 `@artifact(...)`** → 解析为 `ArtifactRef`（长文本不要内联）：

```text
<|run_script(script=@artifact("scripts/query.sql"))|>
```

### 3.3 参数分隔符（换行 / 逗号都兼容）

标准写法建议用**换行**；解析器同时兼容**逗号**。**同行空格不作为参数分隔符**。引号内、`()`/`[]`/`{}` 内的分隔符不切分。

```text
item(
name="A"
text="任务"
priority=1
)                                               # 推荐：换行分隔

item(name="A", text="任务", priority=1)         # 兼容：逗号分隔

item(name="A" text="任务")                      # ❌ 不支持：同行空格分隔
```

### 3.4 字面量

值为合法 Python 字面量时按 `ast.literal_eval` 解析（字符串/数字/布尔/列表/字典）：

```text
<|set_tags(tags=[1, 2, 3])|>                                    # 纯字面量数组 → list
<|invoke(items=[{"name":"A","text":"任务"}])|>                   # JSON 字典数组 → list[dict]
```

> **关键约定**：值是 `name(...)` 形态才解析为 `CallValue`；带引号的 `"item(x)"` 仍是字符串；
> 未知 `@xxx(...)`（非 `@artifact`）保留为原始字符串。**不做畸形 JSON 修复**。

---

## 4. 公共 API 速查

全部从 `yweb.agent`（或顶层 `yweb`）导出：

| 符号 | 类型 | 说明 |
|------|------|------|
| `parse_command_output(text)` | 函数 | 文本 → `List[ParsedCommand]`（括号平衡扫描，支持嵌套） |
| `parse_param_string(s)` | 函数 | 参数串 → `Dict[str, Any]`（值含 `CallValue`/`ArtifactRef`/字面量） |
| `split_param_expressions(s)` | 函数 | 状态机分割参数表达式（兼容换行/逗号，**不认同行空格**） |
| `build_command(toolname, **params)` | 函数 | 结构化参数 → `command=|<|...|>|` 文本（`parse` 的逆操作） |
| `CommandPromptBuilder` | 类 | 指令格式说明文本生成 |
| `ParsedCommand` | dataclass | 解析后的指令（`toolname` / `args`） |
| `CallValue` | dataclass | 函数式嵌套对象（`name` / `args`） |
| `ArtifactRef` | dataclass | 工件引用（`path`，仅标记不读文件） |

### 4.1 数据模型

```python
@dataclass
class ParsedCommand:
    toolname: str                       # 工具名，永不为空
    args: Dict[str, Any]

@dataclass
class CallValue:                        # item(name=..., text=...) 等嵌套对象
    name: str                           # 函数名（item / record / ref / ...）
    args: Dict[str, Any]

@dataclass
class ArtifactRef:                      # @artifact("path")，仅产生引用标记，不读文件
    path: str
```

---

## 5. 快速开始

```python
from yweb.agent import (
    build_command,
    CallValue,
    parse_command_output,
    CommandPromptBuilder,
)

# 1) 文本 → 结构化
commands = parse_command_output(llm_output_text)   # List[ParsedCommand]
for cmd in commands:
    process(cmd.toolname, cmd.args)

# 2) 结构化 → command 文本（嵌套对象用 CallValue）
dsl = build_command("invoke", items=[
    CallValue("item", {"name": "A", "text": "..."}),
])

# 3) 生成格式说明，供提示词拼接
text = CommandPromptBuilder.function_prompt(
    func_name="rag_search",
    description="知识库检索工具",
    command_example='rag_search(querys=["问题"])',
)
```

---

## 6. 格式说明生成（CommandPromptBuilder）

根据工具名、描述、指令示例，拼出可供 LLM 提示词使用的格式说明文本。

```python
from yweb.agent import CommandPromptBuilder

CommandPromptBuilder.function_prompt(
    func_name="search",
    description="检索工具",
    command_example='search(q="...")',
)
# →  "search 工具介绍： 检索工具。\nsearch 工具指令：command=|<|search(q=\"...\")|>|\n\n"
```

---

## 7. 解析器内部结构（修改 parser.py 时必读）

- `parse_command_output`：**括号平衡扫描**——`_COMMAND_START` 定位 `<|name(`，用
  `_find_matching_paren`（引号/转义感知）找匹配 `)`，再要求其后为 `|>`。**禁止退回非贪婪正则**。
- `parse_param_string` → `split_param_expressions` 拆参数 → 每个值过 `_parse_value`。
- `_parse_value` 优先级：`@artifact(...)` → `name(...)` 函数调用（`CallValue`，递归）→
  含调用/引用的数组（逐元素解析）→ 否则 `_parse_literal`（纯 `ast.literal_eval`，失败降级）。

---

## 8. 测试规范

测试编写遵循 `.cursor/skills/yweb-testing/SKILL.md`，并注意本模块要点：

- 解析/DSL/Builder/Prompt 用例分别放 `test_parser.py` / `test_dsl.py` / `test_builder.py` / `test_prompt.py`。
- 每个核心行为至少一个**失败/边界反例**（空参数、缺字段、不配对括号 → `[]`）。
- 测试失败时遵循 `test-quality-and-failure-workflow.mdc`：先诊断 → 给 ≥2 方案 → 用户确认后再改。

---

## 9. 常见反模式（避免）

```python
# ❌ 在库内实现指令路由或消费逻辑
class CommandRouter: ...

# ❌ 引入对工作流引擎 / LLM 运行时的依赖
from some_engine import Runtime

# ❌ 用 Pydantic BaseModel 承载内部数据对象
class ParsedCommand(BaseModel): ...

# ❌ 命令提取退回非贪婪正则
re.findall(r"\<\|(\w+)\((.*?)\)\|>", text)    # 无法支持嵌套，误判引号内 )|>

# ❌ 引入外部依赖修复畸形 JSON
from json_repair import repair_json
```

```python
# ✅ 库只做：解析（parse_*）+ 构建（build_command）+ 格式说明（CommandPromptBuilder）
# ✅ 数据容器用 @dataclass
# ✅ 命令提取用括号平衡扫描（引号/转义感知）
# ✅ 解析失败优雅降级（保留原始字符串），不抛异常
```

---

## 10. 快速检查清单

修改指令系统代码前，对照此清单：

- [ ] 改动落在解析 / 构建 / 格式说明三项能力之内
- [ ] 未引入外部运行时依赖（仅 `ast` / `re`）
- [ ] 未 import 工作流引擎、LLM 客户端等外部运行时
- [ ] 新数据容器用 `@dataclass`
- [ ] 新符号已在 `agent/__init__.py` 与 `yweb/__init__.py` 同步导出
- [ ] 命令提取仍用括号平衡扫描，未退回非贪婪正则
- [ ] 解析失败优雅降级，不抛异常、不修复畸形 JSON
- [ ] 新增/改动有对应单元测试 + 关键反例
- [ ] `ruff check` 与 `mypy`（`yweb/agent`）零错误
