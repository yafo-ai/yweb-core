"""自定义函数指令处理器（通配）

处理所有未精确匹配的 toolname，作为工具函数调用的兜底。
"""

from ...context import CommandContext
from ...dispatcher import WILDCARD_HANDLER_NAME
from ...types import CommandResult, ParsedCommand


class CustomFunctionHandler:
    """处理自定义函数调用（通配 Handler）。

    用 ``command.toolname`` 作为真实函数名，调用
    ``context.call_function(name, args)`` 并返回 ``return_value``。

    行为对齐 y-agent：函数调用失败时捕获异常，``return_value`` 设为
    ``"工具错误：..."``，``success=False``。
    """

    @property
    def toolname(self) -> str:
        return WILDCARD_HANDLER_NAME

    def handle(self, command: ParsedCommand, context: CommandContext) -> CommandResult:
        function_name = command.toolname
        try:
            return_value = context.call_function(function_name, command.args)
            return CommandResult(
                toolname=function_name,
                success=True,
                return_value=return_value,
            )
        except Exception as e:
            return CommandResult(
                toolname=function_name,
                success=False,
                return_value=f"工具错误：{e}",
                error=str(e),
            )
