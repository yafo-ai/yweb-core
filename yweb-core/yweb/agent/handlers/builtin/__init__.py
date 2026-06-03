"""内置指令处理器

assignment / write_var / notify / send_message / terminate / 自定义函数。
"""

from .assignment import AssignmentHandler
from .custom_function import CustomFunctionHandler
from .notify import NotifyHandler
from .send_message import SendMessageHandler
from .terminate import TerminateHandler
from .write_var import WriteVarHandler

__all__ = [
    "AssignmentHandler",
    "WriteVarHandler",
    "NotifyHandler",
    "SendMessageHandler",
    "TerminateHandler",
    "CustomFunctionHandler",
]
