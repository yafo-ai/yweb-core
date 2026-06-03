"""send_message 指令处理器

向指定角色发送消息。
"""

from ...context import CommandContext
from ...types import CommandResult, ParsedCommand


class SendMessageHandler:
    """处理 ``send_message`` 指令。

    调用 ``context.add_message(current_role, receiver, message)``。

    行为对齐 y-agent：``receiver`` 和 ``message`` 都必填，
    为 None 或空白字符串时返回 success=False，且不发送消息。
    """

    @property
    def toolname(self) -> str:
        return "send_message"

    def handle(self, command: ParsedCommand, context: CommandContext) -> CommandResult:
        receiver = command.args.get("receiver", None)
        message = command.args.get("message", None)
        if receiver is None or (isinstance(receiver, str) and receiver.strip() == ""):
            return CommandResult(
                toolname=command.toolname,
                success=False,
                error="send_message receiver is None",
            )
        if message is None or (isinstance(message, str) and message.strip() == ""):
            return CommandResult(
                toolname=command.toolname,
                success=False,
                error="send_message message is None",
            )
        context.add_message(context.current_role, receiver, message)
        return CommandResult(toolname=command.toolname, success=True)
