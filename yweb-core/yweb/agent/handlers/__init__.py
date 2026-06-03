"""指令处理器层

定义 Handler 基类协议与内置 Handler。
"""

from .base import BaseCommandHandler
from .builtin import (
    AssignmentHandler,
    CustomFunctionHandler,
    NotifyHandler,
    SendMessageHandler,
    TerminateHandler,
    WriteVarHandler,
)

__all__ = [
    "BaseCommandHandler",
    "AssignmentHandler",
    "WriteVarHandler",
    "NotifyHandler",
    "SendMessageHandler",
    "TerminateHandler",
    "CustomFunctionHandler",
]
