"""Agent 指令协议数据模型

定义解析过程中产出的数据容器。

与 yweb-core 其他模块一致，使用 ``@dataclass`` 承载内部数据对象
（而非 Pydantic BaseModel）。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ParsedCommand:
    """解析后的指令

    从 LLM 文本输出中提取出的单条结构化指令。

    Attributes:
        toolname: 工具/指令名称（如 search、notify、invoke 等），
            解析层正则保证至少一个字符，永不为空字符串。
        args: 指令参数键值对。
        unparsed: 解析器未能纳入 ``args`` 的表达式原文，按出现顺序排列，
            含嵌套函数调用内部的表达式。两类情况会记入：

            1. 不符合 ``key=value`` 形式的表达式，如漏写 ``key=`` 的位置参数
               ``set_form([setValue(field="a", value=1)])``；
            2. 形似 ``[...]`` / ``{...}`` 容器但字面量解析失败的值，如
               ``patches=[{type="setValue"}]`` 这类花括号对象数组。

            空列表表示本条指令的全部输入都已进入 ``args``。非空即表示模型输出
            有一部分没被采纳，调用方据此判断是否要求模型重写、或记录失败率，
            不必再从 ``args`` 缺字段反推。
    """

    toolname: str
    args: Dict[str, Any] = field(default_factory=dict)
    unparsed: List[str] = field(default_factory=list)


@dataclass
class CallValue:
    """函数式内部对象

    DSL 中嵌套的函数调用值，如 ``item(name="A", text="...")`` 或
    ``record(id="1", value="...")``。函数名保留在 ``name`` 字段，
    参数解析为 ``args`` 字典（值可继续递归为 ``CallValue`` / ``ArtifactRef`` / 字面量）。

    Attributes:
        name: 函数名（如 item、record、ref）。
        args: 函数参数键值对。
    """

    name: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactRef:
    """工件引用

    DSL 中 ``@artifact("sql/query.sql")`` 形式的外部资源引用。解析器只产生引用标记，
    **不读取文件内容**；由消费者按 ``path`` 自行解析（yweb-core 不引入文件 IO/基目录依赖）。

    Attributes:
        path: 工件路径（相对或绝对，语义由消费者定义）。
    """

    path: str
