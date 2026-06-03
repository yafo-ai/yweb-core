"""指令处理器协议

定义所有 Handler 的统一接口。消费者可按需实现自定义 Handler，
无需继承基类（``Protocol`` 鸭子类型即可）。
"""

from typing import Protocol, runtime_checkable

from ..context import CommandContext
from ..types import CommandResult, ParsedCommand


@runtime_checkable
class BaseCommandHandler(Protocol):
    """指令处理器协议"""

    @property
    def toolname(self) -> str:
        """指令名称。

        内置 Handler 返回固定指令名（如 ``"assignment"``）；
        ``CustomFunctionHandler`` 返回 ``WILDCARD_HANDLER_NAME``（通配标记）。
        """
        ...

    def handle(self, command: ParsedCommand, context: CommandContext) -> CommandResult:
        """处理指令。

        Args:
            command: 解析后的指令，含 ``toolname``（真实指令/函数名）和 ``args``（参数）。
                ``CustomFunctionHandler`` 通过 ``command.toolname`` 拿到真实函数名——
                这是通配兜底机制能工作的关键，因此 handle 必须接收完整 ``ParsedCommand``，
                而不是只接收 args。
            context: 执行上下文。

        Returns:
            执行结果。
        """
        ...
