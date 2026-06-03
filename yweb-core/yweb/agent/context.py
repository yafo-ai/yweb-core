"""Agent 指令执行上下文协议

定义指令系统与具体工作流引擎之间的抽象边界。指令系统本身不依赖任何
特定的 WorkingSpace / Graph / LLM 实现，消费者通过实现 ``CommandContext``
协议把指令执行桥接到自己的业务对象上。
"""

from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class CommandContext(Protocol):
    """指令执行上下文协议

    消费者必须实现此接口，以桥接到自己的 WorkingSpace / Graph。

    线程安全要求:
        ``CommandDispatcher`` 使用 ThreadPoolExecutor 并发执行 Handler。
        所有写入方法（``add_message``、``write_variable``、``set_terminate``）
        必须在内部加锁，保证线程安全。

    Example:
        ::

            import threading

            class AgentCommandContext:
                def __init__(self, working_space):
                    self._working_space = working_space
                    self._lock = threading.Lock()

                @property
                def current_role(self) -> str:
                    return self._working_space.current_role

                def add_message(self, from_role, to_role, message):
                    with self._lock:
                        self._working_space.add_talk(from_role, to_role, message)

                # ... 其他方法
    """

    @property
    def current_role(self) -> str:
        """当前角色名称。

        作为各 Handler 的 ``from_role`` 来源。
        """
        ...

    def add_message(self, from_role: str, to_role: str, message: str) -> None:
        """添加消息到对话历史。

        必须是线程安全的。

        Args:
            from_role: 发送方角色。
            to_role: 接收方角色。
            message: 消息内容。
        """
        ...

    def write_variable(self, key: str, value: Any) -> None:
        """写入变量。

        必须是线程安全的。消费者应在此方法内部实现 space/role 分流逻辑
        （如需要），``WriteVarHandler`` 只会调用此方法。

        Args:
            key: 变量名。
            value: 变量值。
        """
        ...

    def call_function(self, name: str, args: Dict[str, Any]) -> Any:
        """调用函数。

        函数调用本身通常不需要锁（由函数内部处理），但如果有副作用需要加锁。

        Args:
            name: 函数名。
            args: 函数参数。

        Returns:
            函数返回值。
        """
        ...

    def has_function(self, name: str) -> bool:
        """检查函数是否存在。

        Args:
            name: 函数名。

        Returns:
            是否存在。
        """
        ...

    def get_function_option(self, name: str) -> Optional[Dict[str, Any]]:
        """获取函数选项。

        用于 ``CustomFunctionHandler``，返回函数执行时需要的配置选项。

        Args:
            name: 函数名。

        Returns:
            函数选项字典，如果函数没有选项则返回 None。
        """
        ...

    def set_terminate(self) -> None:
        """设置终止标记。

        必须是线程安全的。
        """
        ...
