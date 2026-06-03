"""Agent 指令系统数据模型

定义指令系统在解析、分发、执行过程中传递的数据容器。

与 yweb-core 其他模块一致，使用 ``@dataclass`` 承载内部数据对象
（而非 Pydantic BaseModel）。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ParsedCommand:
    """解析后的指令

    从 LLM 文本输出中提取出的单条结构化指令。

    Attributes:
        toolname: 指令名称（如 assignment、write_var、notify 等），
            解析层正则保证至少一个字符，永不为空字符串。
        args: 指令参数键值对。
    """

    toolname: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CallValue:
    """函数式内部对象

    DSL 中嵌套的函数调用值，如 ``role(name="客服", message="...")`` 或
    ``agent(name="...", task="...")``。统一“万物皆函数”模型：函数名作为类型标识保留，
    参数解析为 ``args`` 字典（值可继续递归为 ``CallValue`` / ``ArtifactRef`` / 字面量）。

    Attributes:
        name: 函数名（即对象类型，如 role、agent、ref、attachment）。
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


@dataclass
class CommandResult:
    """指令执行结果

    Attributes:
        toolname: 指令名称。
        success: 是否执行成功。
        target_roles: assignment 产生的下游目标角色。
        return_value: 函数调用的返回值（ReAct 场景需要）。
        error: 错误信息。
        is_terminal: terminate 指令标记。
        start_time: 指令开始执行时间（dispatcher 统一记录）。
        end_time: 指令执行结束时间（dispatcher 统一记录）。
        duration: 执行耗时（秒，dispatcher 统一计算）。
    """

    toolname: str
    success: bool
    target_roles: List[str] = field(default_factory=list)
    return_value: Any = None
    error: Optional[str] = None
    is_terminal: bool = False
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: Optional[float] = None
