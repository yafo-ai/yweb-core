"""Agent 指令系统模块

LLM 文本指令的解析、构建与格式说明生成：

1. **解析（parser）**：``command`` 文本 → ``ParsedCommand``（工具名 + 参数）。
2. **构建（builder）**：结构化参数 → ``command=|<|...|>|`` 文本（``parse`` 的逆操作）。
3. **提示词（prompt）**：工具描述 → 指令格式说明文本（供 LLM 提示词拼接）。

快速开始:
========

1. 解析 LLM 输出:

    from yweb.agent import parse_command_output

    commands = parse_command_output(llm_output_text)  # List[ParsedCommand]
    for cmd in commands:
        # cmd.toolname / cmd.args
        ...

2. 结构化 → command 文本:

    from yweb.agent import build_command, CallValue

    text = build_command("dispatch", items=[
        CallValue("item", {"name": "A", "message": "..."}),
    ])

3. 拼接工具指令格式说明:

    from yweb.agent import CommandPromptBuilder

    text = CommandPromptBuilder.function_prompt(
        func_name="rag_search",
        description="知识库检索工具",
        command_example='rag_search(querys=["问题"])',
    )

指令 DSL:
========

- 内部对象用函数调用式 ``item(name=... message=...)`` → ``CallValue``（参数用**换行或逗号**分隔，同行空格不切分）；
- 外部资源用 ``@artifact("path")`` → ``ArtifactRef``（只产生引用标记，不读文件）；
- 其余值按字面量解析（字符串/数字/列表/字典）；嵌套对象请用 ``CallValue``，不要用 ``dict`` 代替函数式写法。
"""

from .builder import build_command
from .parser import (
    parse_command_output,
    parse_param_string,
    split_param_expressions,
)
from .prompt import CommandPromptBuilder
from .types import ArtifactRef, CallValue, ParsedCommand

__all__ = [
    # ===== 数据模型 =====
    "ParsedCommand",
    "CallValue",
    "ArtifactRef",
    # ===== 解析函数（command 文本 → 结构化） =====
    "parse_command_output",
    "parse_param_string",
    "split_param_expressions",
    # ===== 构建函数（结构化 → command 文本，parse 的逆操作） =====
    "build_command",
    # ===== 提示词生成 =====
    "CommandPromptBuilder",
]
