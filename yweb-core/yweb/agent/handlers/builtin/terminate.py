"""terminate 指令处理器

终止工作流并输出最终结果。
"""

from ...context import CommandContext
from ...types import CommandResult, ParsedCommand


class TerminateHandler:
    """处理 ``terminate`` 指令。

    调用 ``context.set_terminate()`` 并把最终消息发给 ``"human"``。

    行为对齐 y-agent：
        - ``message`` 是 dict 时转为 str；
        - ``message`` 缺失（None）→ 返回 success=False，且不终止；
        - 成功时 ``is_terminal=True``。
    """

    @property
    def toolname(self) -> str:
        return "terminate"

    def handle(self, command: ParsedCommand, context: CommandContext) -> CommandResult:
        message = command.args.get("message", None)
        if message is None:
            return CommandResult(
                toolname=command.toolname,
                success=False,
                error="terminate message is None",
            )
        if isinstance(message, dict):
            message = str(message)
        context.set_terminate()
        context.add_message(context.current_role, "human", message)
        return CommandResult(
            toolname=command.toolname,
            success=True,
            is_terminal=True,
        )
