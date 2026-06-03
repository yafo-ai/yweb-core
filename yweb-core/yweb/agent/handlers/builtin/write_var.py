"""write_var 指令处理器

存储 LLM 输出的结果数据。
"""

from ...context import CommandContext
from ...types import CommandResult, ParsedCommand


class WriteVarHandler:
    """处理 ``write_var`` 指令。

    遍历 ``command.args`` 的每个键值对，调用
    ``context.write_variable(key, value)``。

    space/role 分流逻辑由消费者在 ``write_variable`` 内部实现，本 Handler 不关心。
    """

    @property
    def toolname(self) -> str:
        return "write_var"

    def handle(self, command: ParsedCommand, context: CommandContext) -> CommandResult:
        for key, value in command.args.items():
            context.write_variable(key, value)
        return CommandResult(toolname=command.toolname, success=True)
