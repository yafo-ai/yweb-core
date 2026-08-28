"""指令文本解析

从 LLM 文本输出中提取 ``|<|func_name(args)|>|`` 格式的结构化指令。

采用函数式 DSL：

1. ``parse_command_output`` 返回 ``List[ParsedCommand]``。
2. 内部对象用函数调用式 ``item(name=..., text=...)`` → ``CallValue``；
   外部资源用 ``@artifact(...)`` → ``ArtifactRef``；
   其余值（字符串/数字/列表/字典）按字面量解析。
"""

import ast
import re
from typing import Any, Dict, List, Optional

from ..types import ArtifactRef, CallValue, ParsedCommand


# 顶层分隔符之后是否紧跟新的 `key=`（或已到末尾）。
# 用 .match(s, pos) 定位，故不能带 ``^``——``^`` 只在串首生效，会导致永不切分。
_KV_AHEAD = re.compile(r"\s*(?:[a-zA-Z_]\w*\s*=|\Z)")

# 值的收尾字符：引号闭合或括号闭合，说明当前值已完整，其后的分隔符必是分隔符。
_VALUE_END_CHARS = ('"', "'", ")", "]", "}")


def split_param_expressions(s: str, *, kv_lookahead: bool = False) -> List[str]:
    """使用状态机分割参数表达式，处理嵌套结构和转义字符。

    顶层分隔符同时兼容逗号 ``,`` 与换行 ``\\n``（DSL 标准写法用换行，亦兼容逗号）。
    引号内、``()`` / ``[]`` / ``{}`` 内的分隔符不切分。空 token 自动跳过
    （连续分隔符、行首行尾空白不会产生空项）。

    Args:
        s: 要分割的字符串。
        kv_lookahead: 是否要求顶层分隔符后紧跟 ``key=`` 才切分。

            默认 ``False``：每个顶层 ``,`` / ``\\n`` 都切分，用于切分数组元素
            ——数组元素形如 ``setValue(...)``，后面跟的是 ``(`` 而非 ``=``。

            置 ``True`` 用于切分参数列表（``parse_param_string`` 如此调用）：
            此时分隔符满足以下任一条件才切分，否则视为值的一部分——

            1. 后面紧跟 ``标识符=``，或已到末尾；
            2. 前面的值以引号或右括号收尾，说明值本身已完整。

            这样未加引号的值里出现逗号（如 ``value=A, B``）会完整保留为
            ``"A, B"``，而不是切出无法匹配 ``key=value`` 的 ``B`` 再被丢弃；
            同时 ``field="a", 1`` 这类引号收尾后的多余位置参数仍会被切出来，
            交由 ``parse_param_string`` 回报，不会污染前一个值。

            残留边界：值与多余内容都未加引号且都是字面量时（如 ``a=1, 2``）无法
            区分，会并成一个值 ``(1, 2)``。这仍比原先切出后静默丢弃保留更多信息。

    Returns:
        分割后的参数表达式列表（已 strip，无空项）。
    """
    stack: List[str] = []
    current: List[str] = []
    result: List[str] = []
    escape = False
    i = 0
    n = len(s)

    while i < n:
        char = s[i]

        if escape:
            # 处理转义字符
            current.append(char)
            escape = False
            i += 1
            continue

        if char == "\\":
            # 设置转义标志
            escape = True
            current.append(char)
            i += 1
            continue

        # 处理引号（字符串边界）
        if char in ('"', "'"):
            if stack and stack[-1] == char:
                # 关闭相同类型的引号
                stack.pop()
            else:
                # 开启新引号
                stack.append(char)
            current.append(char)
            i += 1
            continue

        # 处理括号嵌套
        if char in ("(", "[", "{"):
            stack.append(char)
            current.append(char)
            i += 1
        elif char in (")", "]", "}"):
            if stack:
                if (
                    (char == ")" and stack[-1] == "(")
                    or (char == "]" and stack[-1] == "[")
                    or (char == "}" and stack[-1] == "{")
                ):
                    stack.pop()
            current.append(char)
            i += 1

        # 处理参数分隔符（逗号或换行）
        elif char in (",", "\n"):
            if not stack and (  # 不在嵌套结构中
                not kv_lookahead
                or _KV_AHEAD.match(s, i + 1)
                or "".join(current).rstrip().endswith(_VALUE_END_CHARS)
            ):
                token = "".join(current).strip()
                if token:
                    result.append(token)
                current = []
            else:
                current.append(char)
            i += 1
        else:
            current.append(char)
            i += 1

    # 添加最后一个表达式
    token = "".join(current).strip()
    if token:
        result.append(token)

    return result


def _find_matching_paren(s: str, open_idx: int) -> Optional[int]:
    """从 ``open_idx`` 处的 ``(`` 找到与之匹配的 ``)`` 下标。

    跟踪括号深度并跳过引号内（含转义）字符。找不到匹配时返回 None。

    Args:
        s: 源字符串。
        open_idx: 起始 ``(`` 的下标。

    Returns:
        匹配 ``)`` 的下标，或 None。
    """
    depth = 0
    in_quote: Optional[str] = None
    escape = False
    for i in range(open_idx, len(s)):
        c = s[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if in_quote is not None:
            if c == in_quote:
                in_quote = None
            continue
        if c in ('"', "'"):
            in_quote = c
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
    return None


def _try_parse_call(
    value_str: str, *, unparsed: Optional[List[str]] = None
) -> Optional[CallValue]:
    """尝试把整个值解析为函数式内部对象 ``name(...)`` → ``CallValue``。

    仅当值是“未加引号的标识符 + 括号”且括号闭合后无多余字符时才匹配，
    否则返回 None（交由字面量解析处理）。函数参数递归调用 ``parse_param_string``，
    ``unparsed`` 一并下传，使嵌套对象内部的未解析表达式也能回报。
    """
    m = re.match(r"^([a-zA-Z_]\w*)\s*\(", value_str)
    if not m:
        return None
    open_idx = m.end() - 1
    close_idx = _find_matching_paren(value_str, open_idx)
    if close_idx is None:
        return None
    # 括号必须覆盖整个值（闭合括号后只能是空白）
    if value_str[close_idx + 1:].strip() != "":
        return None
    name = m.group(1)
    inner = value_str[open_idx + 1: close_idx]
    return CallValue(name=name, args=parse_param_string(inner, unparsed=unparsed))


# 形似 [...] / {...} 容器的值：字面量解析失败即为结构性错误，而非无引号裸字符串。
_LOOKS_LIKE_CONTAINER = re.compile(r"^[\[{].*[\]}]$", re.DOTALL)


def _parse_literal(value_str: str, *, unparsed: Optional[List[str]] = None) -> Any:
    """解析字面量值（引号字符串 / 列表 / 字典 / 数字 / 布尔）。

    使用 ``ast.literal_eval`` 安全解析；失败时降级为去引号或保留原始字符串。
    不做畸形 JSON 修复（不引入外部依赖）。

    降级为原始字符串时，仅当值形似 ``[...]`` / ``{...}`` 容器才记入 ``unparsed``：
    这类值本应是结构化的，解析失败意味着写法不合协议（如 ``[{type="x"}]``）；
    而未加引号的裸字符串（如 ``value=年假``）是协议允许的容错写法，不记入。
    """
    # 处理引号包裹的字符串
    if (value_str.startswith('"') and value_str.endswith('"')) or (
        value_str.startswith("'") and value_str.endswith("'")
    ):
        try:
            return ast.literal_eval(value_str)
        except (SyntaxError, ValueError):
            # 解析失败时移除外层引号
            return value_str[1:-1]

    # 尝试解析其他类型（数字 / 布尔 / 列表 / 字典）
    try:
        return ast.literal_eval(value_str)
    except (SyntaxError, ValueError):
        # 无法解析时保留原始字符串
        if unparsed is not None and _LOOKS_LIKE_CONTAINER.match(value_str):
            unparsed.append(value_str)
        return value_str


def _parse_reference(value_str: str) -> Optional[ArtifactRef]:
    """尝试把整个值解析为 ``@artifact(...)`` 引用 → ``ArtifactRef``。

    支持位置参数 ``@artifact("path")`` 与关键字 ``@artifact(path="...")``。
    未识别的 ``@xxx`` 返回 None（交由字面量解析，保留为原始字符串）。
    """
    m = re.match(r"^@([a-zA-Z_]\w*)\s*\(", value_str)
    if not m:
        return None
    open_idx = m.end() - 1
    close_idx = _find_matching_paren(value_str, open_idx)
    if close_idx is None or value_str[close_idx + 1:].strip() != "":
        return None

    name = m.group(1)
    inner = value_str[open_idx + 1: close_idx].strip()
    if name != "artifact":
        return None

    args = parse_param_string(inner)
    if "path" in args:
        path = args["path"]
    else:
        path = _parse_value(inner)  # 位置参数：单个字符串字面量
    return ArtifactRef(path=path if isinstance(path, str) else str(path))


def _looks_like_call_or_ref(s: str) -> bool:
    """判断一个 token 是否为函数式调用 ``name(`` 或 ``@`` 引用（用于数组分流）。"""
    s = s.strip()
    if s.startswith("@"):
        return True
    return bool(re.match(r"^[a-zA-Z_]\w*\s*\(", s))


def _try_parse_array_with_calls(
    value_str: str, *, unparsed: Optional[List[str]] = None
) -> Optional[list]:
    """当数组 ``[...]`` 含函数调用/``@`` 引用元素时，按元素递归解析为列表。

    纯字面量数组（不含调用/引用）返回 None，交由 ``_parse_literal`` 整体解析
    （保留 y-agent 原始行为，回归不变）。
    """
    if not (value_str.startswith("[") and value_str.endswith("]")):
        return None
    inner = value_str[1:-1]
    # 数组元素形如 setValue(...)，后面跟 ``(`` 而非 ``=``，故不启用 kv_lookahead。
    parts = split_param_expressions(inner)
    if not any(_looks_like_call_or_ref(p) for p in parts):
        return None
    return [_parse_value(p, unparsed=unparsed) for p in parts]


def _parse_value(value_str: str, *, unparsed: Optional[List[str]] = None) -> Any:
    """解析单个参数值。

    优先级：``@artifact(...)`` 引用 → 函数式内部对象 ``name(...)`` →
    含调用/引用的数组（按元素解析）→ 其余走字面量解析。
    """
    v = value_str.strip()
    if not v:
        return v

    if v.startswith("@"):
        # @artifact("path") 的位置参数是协议内合法写法，不下传 unparsed 以免误报。
        ref = _parse_reference(v)
        if ref is not None:
            return ref

    call = _try_parse_call(v, unparsed=unparsed)
    if call is not None:
        return call

    array = _try_parse_array_with_calls(v, unparsed=unparsed)
    if array is not None:
        return array

    return _parse_literal(v, unparsed=unparsed)


def parse_param_string(
    param_str: str, *, unparsed: Optional[List[str]] = None
) -> Dict[str, Any]:
    """解析参数字符串为键值对字典。

    Args:
        param_str: 格式如 ``'key1=value1, key2=value2, ...'`` 的字符串
            （分隔符兼容逗号与换行）。
        unparsed: 可选的回收列表。传入时，未能纳入返回字典的表达式原文会按出现
            顺序追加进来（含嵌套对象内部），调用方据此判断输入是否被丢弃；
            不传则沿用原行为——丢弃且不留痕迹。

    Returns:
        包含解析后键值对的字典。值可能是字面量、``CallValue`` 等。
    """
    param_str = param_str.strip()
    if not param_str:
        return {}

    expressions = split_param_expressions(param_str, kv_lookahead=True)
    params: Dict[str, Any] = {}
    pattern = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.*)$", re.DOTALL)

    for expr in expressions:
        expr = expr.strip()
        if not expr:
            continue

        match = pattern.match(expr)
        if not match:
            if unparsed is not None:
                unparsed.append(expr)
            continue

        key = match.group(1)
        value_str = match.group(2).strip()
        params[key] = _parse_value(value_str, unparsed=unparsed)

    return params


_COMMAND_START = re.compile(r"\<\|\s*(\w+)\s*\(")
_COMMAND_TAIL = re.compile(r"\s*\|>")


def parse_command_output(output: str) -> List[ParsedCommand]:
    """从 LLM 文本输出中提取所有结构化指令。

    识别 ``|<| func_name(args) |>|`` 格式。采用**括号平衡扫描**（替代非贪婪正则）：
    定位 ``func_name(`` 后，用引号/转义感知的方式找到与之匹配的 ``)``，再要求其后为
    ``|>``。因此支持嵌套函数调用，如 ``|<|invoke(items=[item(name="x")])|>|``。

    参数中未能解析的表达式不会被静默丢弃，而是记入对应 ``ParsedCommand.unparsed``，
    供调用方判断模型输出是否被部分丢弃。

    Args:
        output: LLM 的原始文本输出。

    Returns:
        解析出的指令列表，顺序与文本中出现顺序一致。无指令时返回空列表。
    """
    commands: List[ParsedCommand] = []
    pos = 0
    length = len(output)

    while pos < length:
        m = _COMMAND_START.search(output, pos)
        if not m:
            break

        func_name = m.group(1)
        open_idx = m.end() - 1  # '(' 的下标
        close_idx = _find_matching_paren(output, open_idx)
        if close_idx is None:
            pos = m.end()
            continue

        tail = _COMMAND_TAIL.match(output, close_idx + 1)
        if tail:
            params_str = output[open_idx + 1: close_idx]
            unparsed: List[str] = []
            args = parse_param_string(params_str, unparsed=unparsed)
            commands.append(
                ParsedCommand(toolname=func_name, args=args, unparsed=unparsed)
            )
            pos = tail.end()
        else:
            # 闭合括号后不是 |>，不是合法指令，跳过此起点继续搜索
            pos = m.end()

    return commands
