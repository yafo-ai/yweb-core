"""指令分发器

按 ``toolname`` 把解析出的指令路由到对应 Handler 执行，支持并发执行与
执行时序记录。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TYPE_CHECKING

from .context import CommandContext
from .types import CommandResult, ParsedCommand

if TYPE_CHECKING:
    from .handlers.base import BaseCommandHandler

WILDCARD_HANDLER_NAME = "__custom_function__"
"""通配 Handler 的注册标记。注册时以此名注册的 Handler 会作为兜底，
处理所有未精确匹配的 toolname（用于自定义函数调用）。"""

_DEFAULT_MAX_WORKERS = 8


class CommandDispatcher:
    """指令分发器，按 toolname 路由到对应 Handler。

    路由规则（按优先级）：
        1. ``_handlers`` 中精确匹配 toolname → 用对应 handler；
        2. 未匹配 → 若注册了通配 handler（CustomFunctionHandler）→ 用通配 handler；
        3. 两者都没有 → 返回 ``CommandResult(success=False, error="no handler found")``。

    注意:
        解析层正则 ``(\\w+)`` 保证 toolname 至少一个字符，``ParsedCommand.toolname``
        永不为空字符串，因此 dispatcher 无需处理空 toolname。"LLM 无指令输出"
        体现为 ``parse_command_output`` 返回空列表 → ``dispatch`` 返回空结果列表。
    """

    def __init__(self) -> None:
        self._handlers: dict[str, BaseCommandHandler] = {}
        self._wildcard_handler: BaseCommandHandler | None = None

    def register(self, toolname: str, handler: BaseCommandHandler) -> None:
        """注册 handler。

        ``toolname`` 为 ``WILDCARD_HANDLER_NAME`` 时注册为通配 handler
        （存入 ``_wildcard_handler`` 而非 ``_handlers``）。

        Args:
            toolname: 指令名称，或 ``WILDCARD_HANDLER_NAME``。
            handler: 处理器实例。
        """
        if toolname == WILDCARD_HANDLER_NAME:
            self._wildcard_handler = handler
        else:
            self._handlers[toolname] = handler

    def register_many(self, mappings: dict[str, BaseCommandHandler]) -> None:
        """批量注册 handler。"""
        for toolname, handler in mappings.items():
            self.register(toolname, handler)

    def unregister(self, toolname: str) -> None:
        """注销 handler。

        ``toolname`` 为 ``WILDCARD_HANDLER_NAME`` 时清除通配 handler；
        否则从精确匹配表中移除（不存在则忽略）。
        """
        if toolname == WILDCARD_HANDLER_NAME:
            self._wildcard_handler = None
        else:
            self._handlers.pop(toolname, None)

    def has(self, toolname: str) -> bool:
        """查询 toolname 是否已注册（精确匹配或通配标记）。"""
        if toolname == WILDCARD_HANDLER_NAME:
            return self._wildcard_handler is not None
        return toolname in self._handlers

    def _resolve_handler(self, toolname: str) -> BaseCommandHandler | None:
        """解析 handler：精确匹配 → 通配 → None。"""
        if toolname in self._handlers:
            return self._handlers[toolname]
        if self._wildcard_handler is not None:
            return self._wildcard_handler
        return None

    def dispatch_one(self, command: ParsedCommand, context: CommandContext) -> CommandResult:
        """执行单条指令，恒返回 ``CommandResult`` 并自动记录时序。

        Args:
            command: 待执行指令（含真实 toolname/args）。
            context: 执行上下文。

        Returns:
            执行结果。无匹配 handler 或 handler 抛异常时返回 ``success=False``。
        """
        start_time = datetime.now()
        handler = self._resolve_handler(command.toolname)

        if handler is None:
            end_time = datetime.now()
            return CommandResult(
                toolname=command.toolname,
                success=False,
                error="no handler found",
                start_time=start_time,
                end_time=end_time,
                duration=(end_time - start_time).total_seconds(),
            )

        try:
            result = handler.handle(command, context)
        except Exception as e:  # handler 异常统一兜底
            end_time = datetime.now()
            return CommandResult(
                toolname=command.toolname,
                success=False,
                error=str(e),
                start_time=start_time,
                end_time=end_time,
                duration=(end_time - start_time).total_seconds(),
            )

        end_time = datetime.now()
        result.start_time = start_time
        result.end_time = end_time
        result.duration = (end_time - start_time).total_seconds()
        return result

    def dispatch(
        self,
        commands: list[ParsedCommand],
        context: CommandContext,
        concurrent: bool = True,
    ) -> list[CommandResult]:
        """执行指令列表，返回结果列表（顺序与输入一致）。

        Args:
            commands: 指令列表。
            context: 执行上下文（必须线程安全）。
            concurrent: 是否并发执行（默认 True，``ThreadPoolExecutor(max_workers=8)``）。

        Returns:
            与 ``commands`` 等长、顺序一致的结果列表；``commands`` 为空时返回空列表。
        """
        if not commands:
            return []

        if not concurrent or len(commands) == 1:
            return [self.dispatch_one(command, context) for command in commands]

        with ThreadPoolExecutor(max_workers=_DEFAULT_MAX_WORKERS) as executor:
            # executor.map 保证返回顺序与输入顺序一致，结果收集线程安全
            results = list(executor.map(lambda c: self.dispatch_one(c, context), commands))
        return results
