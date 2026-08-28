"""Agent 内部工具调用协议模块

本模块只负责 LLM 文本指令协议的解析、构建与格式说明生成：

1. **解析（parser）**：``command`` 文本 → ``ParsedCommand``（工具名 + 参数）。
2. **构建（builder）**：结构化参数 → ``command=|<|...|>|`` 文本（``parse`` 的逆操作）。
3. **提示词（prompt）**：工具描述 → 指令格式说明文本（供 LLM 提示词拼接）。

不在这里实现 Agent 运行时、工具路由、LLM 客户端或工作流引擎集成。
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
