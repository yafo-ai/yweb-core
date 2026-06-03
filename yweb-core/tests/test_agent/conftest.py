"""test_agent 共享 fixtures

提供 MockContext —— 一个记录所有调用的 CommandContext 实现，供
dispatcher 与 handler 测试使用。
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest


class MockContext:
    """测试用的 CommandContext 实现，记录所有调用。

    实现 ``yweb.agent.CommandContext`` 协议（鸭子类型，无需继承）。
    """

    def __init__(self, role: str = "test_role") -> None:
        self._role = role
        self.messages: List[Tuple[str, str, str]] = []  # (from, to, message)
        self.variables: Dict[str, Any] = {}
        self.functions: Dict[str, Callable[..., Any]] = {}
        self.function_options: Dict[str, Dict[str, Any]] = {}
        self.terminated: bool = False
        self.function_calls: List[Tuple[str, Dict[str, Any]]] = []

    @property
    def current_role(self) -> str:
        return self._role

    def add_message(self, from_role: str, to_role: str, message: str) -> None:
        self.messages.append((from_role, to_role, message))

    def write_variable(self, key: str, value: Any) -> None:
        self.variables[key] = value

    def call_function(self, name: str, args: Dict[str, Any]) -> Any:
        self.function_calls.append((name, args))
        if name in self.functions:
            return self.functions[name](**args)
        raise KeyError(f"function not found: {name}")

    def has_function(self, name: str) -> bool:
        return name in self.functions

    def get_function_option(self, name: str) -> Optional[Dict[str, Any]]:
        return self.function_options.get(name)

    def set_terminate(self) -> None:
        self.terminated = True


@pytest.fixture
def context() -> MockContext:
    """提供一个全新的 MockContext。"""
    return MockContext()
