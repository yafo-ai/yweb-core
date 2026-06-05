"""指令构建器 —— ``parse_command_output`` 的逆操作

把结构化参数序列化为 ``command=|<|toolname(...)|>|`` 文本（函数式 DSL，参数换行分隔）。

``toolname`` 与参数由调用方传入。值支持：

- ``str`` / ``int`` / ``float`` / ``bool`` → 字面量；
- ``CallValue`` → 嵌套函数调用 ``item(...)`` / ``record(...)``（可递归）；
- ``ArtifactRef`` → ``@artifact("path")``；
- ``list`` → ``[...]``（元素换行分隔，可含 ``CallValue``）；
- ``dict`` → JSON 字面量（仅用于真正的字典参数；嵌套对象请用 ``CallValue``）。
"""

from __future__ import annotations

import json
from typing import Any

from .types import ArtifactRef, CallValue


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, CallValue):
        return _format_call(value.name, value.args)
    if isinstance(value, ArtifactRef):
        return f"@artifact({json.dumps(value.path, ensure_ascii=False)})"
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[\n" + "\n".join(_format_value(v) for v in value) + "\n]"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"不支持的 DSL 值类型: {type(value)!r}")


def _format_call(name: str, params: dict[str, Any]) -> str:
    if not params:
        return f"{name}()"
    lines = [f"{name}("]
    lines.extend(f"{key}={_format_value(val)}" for key, val in params.items())
    lines.append(")")
    return "\n".join(lines)


def build_command(toolname: str, **params: Any) -> str:
    """结构化参数 → ``command=|<|toolname(...)|>|`` 文本（函数式 DSL）。

    ``parse_command_output`` 的逆操作。

    Example:
        >>> build_command("notify", receiver="human", message="你好")
        'command=|<|notify(\\nreceiver="human"\\nmessage="你好"\\n)|>|'

        >>> from yweb.agent import CallValue
        >>> build_command("invoke", items=[
        ...     CallValue("item", {"name": "A", "text": "..."}),
        ... ])
    """
    return f"command=|<|{_format_call(toolname, params)}|>|"
