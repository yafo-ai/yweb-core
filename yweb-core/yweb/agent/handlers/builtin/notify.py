"""notify 指令处理器

向用户/角色发送通知消息。
"""

from ...context import CommandContext
from ...types import CommandResult, ParsedCommand


class NotifyHandler:
    """处理 ``notify`` 指令。

    调用 ``context.add_message(current_role, receiver, message)``，
    ``receiver`` 默认为 ``"human"``。

    行为对齐 y-agent：``message`` 为 None 或空白字符串 → 返回 success=False。
    """

    @property
    def toolname(self) -> str:
        return "notify"

    def handle(self, command: ParsedCommand, context: CommandContext) -> CommandResult:
        receiver = command.args.get("receiver", "human")
        message = command.args.get("message", None)
        if message is None or (isinstance(message, str) and message.strip() == ""):
            return CommandResult(
                toolname=command.toolname,
                success=False,
                error="notify message is None",
            )
        context.add_message(context.current_role, receiver, message)
        return CommandResult(toolname=command.toolname, success=True)
