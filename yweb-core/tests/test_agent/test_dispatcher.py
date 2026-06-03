"""分发层测试

覆盖 CommandDispatcher 的注册 / 分发 / 并发 / 异常 / 通配路由 / 时序记录。
"""

import time
from typing import List

from yweb.agent import CommandDispatcher, CommandResult, ParsedCommand
from yweb.agent.dispatcher import WILDCARD_HANDLER_NAME


class RecordHandler:
    """记录调用的简单 handler，可指定返回的 target_roles。"""

    def __init__(self, name: str, target_roles: List[str] = None) -> None:
        self._name = name
        self._target_roles = target_roles or []
        self.calls: List[ParsedCommand] = []

    @property
    def toolname(self) -> str:
        return self._name

    def handle(self, command: ParsedCommand, context) -> CommandResult:
        self.calls.append(command)
        return CommandResult(
            toolname=command.toolname,
            success=True,
            target_roles=list(self._target_roles),
        )


class RaiseHandler:
    """总是抛异常的 handler。"""

    @property
    def toolname(self) -> str:
        return "boom"

    def handle(self, command: ParsedCommand, context) -> CommandResult:
        raise RuntimeError("handler failed")


class WildcardHandler:
    """模拟 CustomFunctionHandler 的通配 handler。"""

    @property
    def toolname(self) -> str:
        return WILDCARD_HANDLER_NAME

    def handle(self, command: ParsedCommand, context) -> CommandResult:
        return CommandResult(
            toolname=command.toolname,
            success=True,
            return_value=f"called:{command.toolname}",
        )


class SlowAssignmentHandler:
    """模拟耗时的 assignment handler，用于并发测试。"""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def toolname(self) -> str:
        return self._name

    def handle(self, command: ParsedCommand, context) -> CommandResult:
        time.sleep(0.02)
        return CommandResult(
            toolname=command.toolname,
            success=True,
            target_roles=[command.args["role"]],
        )


class TestRegistration:
    """注册相关测试"""

    def test_d01_register_and_dispatch_one(self, context):
        """测试注册后单条分发能正确调用 handler"""
        d = CommandDispatcher()
        h = RecordHandler("a")
        d.register("a", h)
        result = d.dispatch_one(ParsedCommand(toolname="a"), context)
        assert result.success is True
        assert len(h.calls) == 1

    def test_d02_register_many(self, context):
        """测试批量注册多个 handler"""
        d = CommandDispatcher()
        d.register_many({"a": RecordHandler("a"), "b": RecordHandler("b")})
        assert d.has("a")
        assert d.has("b")

    def test_d03_unregister(self, context):
        """测试注销后分发返回 success=False"""
        d = CommandDispatcher()
        d.register("a", RecordHandler("a"))
        d.unregister("a")
        result = d.dispatch_one(ParsedCommand(toolname="a"), context)
        assert result.success is False
        assert result.error == "no handler found"

    def test_d04_has(self):
        """测试 has 查询已注册/未注册"""
        d = CommandDispatcher()
        d.register("a", RecordHandler("a"))
        assert d.has("a") is True
        assert d.has("nope") is False

    def test_d12_override_register(self, context):
        """测试同名重复注册时后者覆盖前者"""
        d = CommandDispatcher()
        first = RecordHandler("a")
        second = RecordHandler("a")
        d.register("a", first)
        d.register("a", second)
        d.dispatch_one(ParsedCommand(toolname="a"), context)
        assert len(second.calls) == 1
        assert len(first.calls) == 0

    def test_d13_wildcard_stored_separately(self, context):
        """测试通配 handler 独立存储且精确匹配优先"""
        d = CommandDispatcher()
        exact = RecordHandler("x")
        d.register("x", exact)
        d.register(WILDCARD_HANDLER_NAME, WildcardHandler())
        # 精确匹配优先
        r_exact = d.dispatch_one(ParsedCommand(toolname="x"), context)
        assert r_exact.success is True
        assert len(exact.calls) == 1
        # 未匹配走通配
        r_wild = d.dispatch_one(ParsedCommand(toolname="y"), context)
        assert r_wild.return_value == "called:y"


class TestDispatch:
    """分发相关测试"""

    def test_d05_dispatch_serial(self, context):
        """测试串行分发多条指令并保序"""
        d = CommandDispatcher()
        d.register("a", RecordHandler("a"))
        d.register("b", RecordHandler("b"))
        cmds = [ParsedCommand(toolname="a"), ParsedCommand(toolname="b")]
        results = d.dispatch(cmds, context, concurrent=False)
        assert [r.toolname for r in results] == ["a", "b"]
        assert all(r.success for r in results)

    def test_d06_dispatch_concurrent(self, context):
        """测试并发分发多条指令且结果保序"""
        d = CommandDispatcher()
        d.register("a", RecordHandler("a"))
        d.register("b", RecordHandler("b"))
        d.register("c", RecordHandler("c"))
        cmds = [
            ParsedCommand(toolname="a"),
            ParsedCommand(toolname="b"),
            ParsedCommand(toolname="c"),
        ]
        results = d.dispatch(cmds, context, concurrent=True)
        assert len(results) == 3
        assert [r.toolname for r in results] == ["a", "b", "c"]

    def test_d07_unregistered_no_wildcard(self, context):
        """测试未注册且无通配 handler 时返回 success=False"""
        d = CommandDispatcher()
        result = d.dispatch_one(ParsedCommand(toolname="unknown"), context)
        assert result.success is False
        assert result.error == "no handler found"

    def test_d08_handler_raises(self, context):
        """测试 handler 抛异常时被 dispatcher 捕获为 success=False"""
        d = CommandDispatcher()
        d.register("boom", RaiseHandler())
        result = d.dispatch_one(ParsedCommand(toolname="boom"), context)
        assert result.success is False
        assert "handler failed" in result.error

    def test_d09_empty_command_list(self, context):
        """测试空指令列表返回空结果列表"""
        d = CommandDispatcher()
        assert d.dispatch([], context) == []

    def test_d10_wildcard_route(self, context):
        """测试未精确匹配的 toolname 路由到通配 handler"""
        d = CommandDispatcher()
        d.register(WILDCARD_HANDLER_NAME, WildcardHandler())
        result = d.dispatch_one(
            ParsedCommand(toolname="rag_search", args={"q": "x"}), context
        )
        assert result.success is True
        assert result.return_value == "called:rag_search"

    def test_d11_concurrent_target_roles_threadsafe(self, context):
        """测试并发分发时 target_roles 收集线程安全、无丢失"""
        d = CommandDispatcher()
        d.register("assignment", SlowAssignmentHandler("assignment"))
        cmds = [
            ParsedCommand(toolname="assignment", args={"role": f"role_{i}"})
            for i in range(16)
        ]
        results = d.dispatch(cmds, context, concurrent=True)
        collected = []
        for r in results:
            collected.extend(r.target_roles)
        assert sorted(collected) == sorted([f"role_{i}" for i in range(16)])


class TestTiming:
    """时序记录测试"""

    def test_timing_recorded(self, context):
        """测试成功执行时记录 start_time/end_time/duration"""
        d = CommandDispatcher()
        d.register("a", RecordHandler("a"))
        result = d.dispatch_one(ParsedCommand(toolname="a"), context)
        assert result.start_time is not None
        assert result.end_time is not None
        assert result.duration is not None
        assert result.duration >= 0

    def test_timing_recorded_on_no_handler(self, context):
        """测试无匹配 handler 时同样记录时序"""
        d = CommandDispatcher()
        result = d.dispatch_one(ParsedCommand(toolname="missing"), context)
        assert result.start_time is not None
        assert result.duration is not None
