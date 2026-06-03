"""Agent 指令系统模块

LLM 与工作流引擎之间的通信协议：从 LLM 的文本输出中解析结构化指令，
按类型分发到对应 Handler 执行，并生成指令格式的提示词说明。

本模块不绑定任何特定的工作流引擎、图引擎或 LLM 实现，只提供：
解析（parser）、分发（dispatcher）、内置 Handler（handlers）、提示词生成（prompt）。

快速开始（推荐）:
================

1. 创建分发器并注册内置 Handler:

    from yweb.agent import (
        CommandDispatcher, WILDCARD_HANDLER_NAME,
        AssignmentHandler, WriteVarHandler, NotifyHandler,
        SendMessageHandler, TerminateHandler, CustomFunctionHandler,
    )

    dispatcher = CommandDispatcher()
    dispatcher.register("assignment", AssignmentHandler())
    dispatcher.register("write_var", WriteVarHandler())
    dispatcher.register("notify", NotifyHandler())
    dispatcher.register("send_message", SendMessageHandler())
    dispatcher.register("terminate", TerminateHandler())
    dispatcher.register(WILDCARD_HANDLER_NAME, CustomFunctionHandler())

2. 实现 CommandContext（桥接到自己的工作空间），解析并分发:

    from yweb.agent import parse_command_output

    commands = parse_command_output(llm_output_text)
    results = dispatcher.dispatch(commands, my_context)

高级用法:
========

- 自定义 Handler：实现 ``BaseCommandHandler`` 协议（鸭子类型，无需继承）后注册。
- 提示词生成：``CommandPromptBuilder`` 生成 assignment / write_var / function / react
  各类指令的格式说明文本。
- 可选依赖：解析畸形 JSON 的修复依赖 ``json-repair``（``pip install yweb[agentcmd]``），
  缺失时自动降级为不修复，模块仍可正常导入与使用。
"""

from .context import CommandContext
from .dispatcher import WILDCARD_HANDLER_NAME, CommandDispatcher
from .handlers import (
    AssignmentHandler,
    BaseCommandHandler,
    CustomFunctionHandler,
    NotifyHandler,
    SendMessageHandler,
    TerminateHandler,
    WriteVarHandler,
)
from .parser import (
    parse_command_output,
    parse_param_string,
    split_param_expressions,
)
from .prompt import CommandPromptBuilder
from .types import ArtifactRef, CallValue, CommandResult, ParsedCommand

__all__ = [
    # ===== 核心类与常量（推荐） =====
    "CommandDispatcher",
    "WILDCARD_HANDLER_NAME",
    # ===== 上下文与协议 =====
    "CommandContext",
    "BaseCommandHandler",
    # ===== 数据模型 =====
    "ParsedCommand",
    "CommandResult",
    "CallValue",
    "ArtifactRef",
    # ===== 解析函数 =====
    "parse_command_output",
    "parse_param_string",
    "split_param_expressions",
    # ===== 提示词生成 =====
    "CommandPromptBuilder",
    # ===== 内置 Handler =====
    "AssignmentHandler",
    "WriteVarHandler",
    "NotifyHandler",
    "SendMessageHandler",
    "TerminateHandler",
    "CustomFunctionHandler",
]
