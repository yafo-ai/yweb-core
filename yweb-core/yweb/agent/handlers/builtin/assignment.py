"""assignment 指令处理器

LLM 选择下游节点并传递任务。
"""

from typing import Any, Optional

from ...context import CommandContext
from ...types import CallValue, CommandResult, ParsedCommand


def _extract_role_message(item: Any) -> tuple[Optional[str], str]:
    """从单个 next_roles 条目中提取 ``(role, message)``，超集兼容两种形态。

    - 旧 dict 形态：``{"role": "...", "message": "..."}``；
    - 新 DSL 函数调用形态（``CallValue``）：``role(name=..., message=...)`` 或
      ``agent(name=..., task=...)``——角色名取 ``name``（回退 ``role``），
      消息取 ``message``（回退 ``task``）。

    无法识别角色名时返回 ``(None, message)``，由调用方按缺失处理。
    """
    if isinstance(item, CallValue):
        args = item.args
        role = args.get("name", args.get("role"))
        message = args.get("message", args.get("task", ""))
    elif isinstance(item, dict):
        role = item.get("role")
        message = item.get("message", "")
    else:
        return None, ""
    return role, message if message is not None else ""


class AssignmentHandler:
    """处理 ``assignment`` 指令。

    遍历 ``args["next_roles"]``，对每个 role 调用
    ``context.add_message(current_role, role, message)``，并返回去重后的
    ``target_roles``。

    next_roles 条目超集兼容两种形态（见 ``_extract_role_message``）：
        - 旧 dict：``{"role": "...", "message": "..."}``；
        - 新 DSL：``role(name=..., message=...)`` / ``agent(name=..., task=...)``。

    行为对齐 y-agent：
        - 每个 next_roles 条目都发送一次消息（不去重）；
        - ``target_roles`` 用集合去重；
        - 某条目 ``role`` 为 None → 返回 success=False（y-agent 抛 ValueError）。
    """

    @property
    def toolname(self) -> str:
        return "assignment"

    def handle(self, command: ParsedCommand, context: CommandContext) -> CommandResult:
        next_roles = command.args.get("next_roles")
        if next_roles is None:
            return CommandResult(
                toolname=command.toolname,
                success=False,
                error="assignment missing next_roles",
            )

        seen = set()
        target_roles = []
        for to_role in next_roles:
            role, message = _extract_role_message(to_role)
            if role is None:
                return CommandResult(
                    toolname=command.toolname,
                    success=False,
                    error="assignment role is None",
                )
            if role not in seen:
                seen.add(role)
                target_roles.append(role)
            context.add_message(context.current_role, role, message)

        return CommandResult(
            toolname=command.toolname,
            success=True,
            target_roles=target_roles,
        )
