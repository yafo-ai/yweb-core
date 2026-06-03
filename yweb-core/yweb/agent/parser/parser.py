"""指令文本解析

从 LLM 文本输出中提取 ``|<|func_name(args)|>|`` 格式的结构化指令。

在 y-agent 解析算法基础上扩展为**超集** DSL（仅 yweb-core）：

1. ``parse_command_output`` 返回 ``List[ParsedCommand]``（而非 ``List[dict]``）。
2. ``json_repair`` 改为可选依赖：未安装时跳过畸形 JSON 修复，其余逻辑不变。
   （安装 ``json-repair`` 后旧字面量行为与 y-agent 完全一致。）
3. 内部对象支持函数调用式 ``role(name=..., message=...)`` → ``CallValue``；
   非函数式的值（字符串/数字/列表/字典字面量）仍走原字面量路径。
"""

import ast
import re
from typing import Any, Dict, List, Optional

from ..types import ArtifactRef, CallValue, ParsedCommand

try:
    from json_repair import repair_json
except ImportError:  # 降级：缺少 json-repair 时不修复畸形 JSON
    repair_json = None


def split_param_expressions(s: str) -> List[str]:
    """使用状态机分割参数表达式，处理嵌套结构和转义字符。

    顶层分隔符同时兼容逗号 ``,`` 与换行 ``\\n``（DSL 标准写法用换行，亦兼容逗号）。
    引号内、``()`` / ``[]`` / ``{}`` 内的分隔符不切分。空 token 自动跳过
    （连续分隔符、行首行尾空白不会产生空项）。

    Args:
        s: 要分割的字符串。

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
            if not stack:  # 不在嵌套结构中
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


def _try_parse_call(value_str: str) -> Optional[CallValue]:
    """尝试把整个值解析为函数式内部对象 ``name(...)`` → ``CallValue``。

    仅当值是“未加引号的标识符 + 括号”且括号闭合后无多余字符时才匹配，
    否则返回 None（交由字面量解析处理）。函数参数递归调用 ``parse_param_string``。
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
    return CallValue(name=name, args=parse_param_string(inner))


def _parse_literal(value_str: str) -> Any:
    """解析字面量值（引号字符串 / JSON 列表字典 / 数字 / 布尔）。

    保留 y-agent 原始算法：``ast.literal_eval`` + 可选 ``json_repair`` 修复畸形 JSON，
    失败时降级为去引号或原始字符串。
    """
    # 处理引号包裹的字符串
    if (value_str.startswith('"') and value_str.endswith('"')) or (
        value_str.startswith("'") and value_str.endswith("'")
    ):
        try:
            if value_str.index("[{") < 3 or value_str.index("{") < 3:
                if repair_json is not None:
                    repair_value_str = repair_json(value_str, ensure_ascii=False)  # 修复操作
                    if repair_value_str and repair_value_str != '""':
                        value_str = str(repair_value_str)
            # 使用 literal_eval 安全解析
            return ast.literal_eval(value_str)
        except (SyntaxError, ValueError):
            # 解析失败时移除外层引号
            return value_str[1:-1]

    # 尝试解析其他类型
    try:
        if value_str.startswith("[") or value_str.startswith("{"):
            if value_str.startswith("[{") and not value_str.endswith("]"):
                value_str += "]"
            if repair_json is not None:
                repair_value_str = repair_json(value_str, ensure_ascii=False)  # 修复操作
                if repair_value_str and repair_value_str != '""':
                    value_str = str(repair_value_str)
        return ast.literal_eval(value_str)
    except (SyntaxError, ValueError):
        # 无法解析时保留原始字符串
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


def _try_parse_array_with_calls(value_str: str) -> Optional[list]:
    """当数组 ``[...]`` 含函数调用/``@`` 引用元素时，按元素递归解析为列表。

    纯字面量数组（不含调用/引用）返回 None，交由 ``_parse_literal`` 整体解析
    （保留 y-agent 原始行为，回归不变）。
    """
    if not (value_str.startswith("[") and value_str.endswith("]")):
        return None
    inner = value_str[1:-1]
    parts = split_param_expressions(inner)
    if not any(_looks_like_call_or_ref(p) for p in parts):
        return None
    return [_parse_value(p) for p in parts]


def _parse_value(value_str: str) -> Any:
    """解析单个参数值。

    优先级：``@artifact(...)`` 引用 → 函数式内部对象 ``name(...)`` →
    含调用/引用的数组（按元素解析）→ 其余走字面量解析。
    """
    v = value_str.strip()
    if not v:
        return v

    if v.startswith("@"):
        ref = _parse_reference(v)
        if ref is not None:
            return ref

    call = _try_parse_call(v)
    if call is not None:
        return call

    array = _try_parse_array_with_calls(v)
    if array is not None:
        return array

    return _parse_literal(v)


def parse_param_string(param_str: str) -> Dict[str, Any]:
    """解析参数字符串为键值对字典。

    Args:
        param_str: 格式如 ``'key1=value1, key2=value2, ...'`` 的字符串
            （分隔符兼容逗号与换行）。

    Returns:
        包含解析后键值对的字典。值可能是字面量、``CallValue`` 等。
    """
    param_str = param_str.strip()
    if not param_str:
        return {}

    expressions = split_param_expressions(param_str)
    params: Dict[str, Any] = {}
    pattern = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.*)$", re.DOTALL)

    for expr in expressions:
        expr = expr.strip()
        if not expr:
            continue

        match = pattern.match(expr)
        if not match:
            continue

        key = match.group(1)
        value_str = match.group(2).strip()
        params[key] = _parse_value(value_str)

    return params


_COMMAND_START = re.compile(r"\<\|\s*(\w+)\s*\(")
_COMMAND_TAIL = re.compile(r"\s*\|>")


def parse_command_output(output: str) -> List[ParsedCommand]:
    """从 LLM 文本输出中提取所有结构化指令。

    识别 ``|<| func_name(args) |>|`` 格式。采用**括号平衡扫描**（替代非贪婪正则）：
    定位 ``func_name(`` 后，用引号/转义感知的方式找到与之匹配的 ``)``，再要求其后为
    ``|>``。因此支持嵌套函数调用，如 ``|<|assignment(next_roles=[role(name="x")])|>|``。

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
            commands.append(
                ParsedCommand(toolname=func_name, args=parse_param_string(params_str))
            )
            pos = tail.end()
        else:
            # 闭合括号后不是 |>，不是合法指令，跳过此起点继续搜索
            pos = m.end()

    return commands
