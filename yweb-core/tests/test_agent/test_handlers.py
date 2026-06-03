"""内置 Handler 测试

覆盖 6 个内置 Handler 的正常/异常路径，行为对齐 y-agent。
"""

from yweb.agent import (
    AssignmentHandler,
    CustomFunctionHandler,
    NotifyHandler,
    ParsedCommand,
    SendMessageHandler,
    TerminateHandler,
    WriteVarHandler,
)


def cmd(toolname, **args):
    """构造 ParsedCommand 的测试辅助函数"""
    return ParsedCommand(toolname=toolname, args=dict(args))


class TestAssignmentHandler:
    """assignment 指令处理器测试"""

    def test_ah01_single_role(self, context):
        """测试指派单个角色：发送一条消息且返回该角色"""
        h = AssignmentHandler()
        r = h.handle(cmd("assignment", next_roles=[{"role": "客服", "message": "你好"}]), context)
        assert r.success is True
        assert r.target_roles == ["客服"]
        assert context.messages == [("test_role", "客服", "你好")]

    def test_ah02_multiple_roles(self, context):
        """测试指派多个角色：发送多条消息且返回多个角色"""
        h = AssignmentHandler()
        r = h.handle(
            cmd("assignment", next_roles=[
                {"role": "客服", "message": "a"},
                {"role": "质检", "message": "b"},
            ]),
            context,
        )
        assert len(context.messages) == 2
        assert sorted(r.target_roles) == ["客服", "质检"]

    def test_ah03_dedup_roles(self, context):
        """测试重复角色在 target_roles 中去重，但消息按条目发送"""
        h = AssignmentHandler()
        r = h.handle(
            cmd("assignment", next_roles=[
                {"role": "客服", "message": "a"},
                {"role": "客服", "message": "b"},
            ]),
            context,
        )
        assert r.target_roles == ["客服"]
        assert len(context.messages) == 2

    def test_ah04_role_none(self, context):
        """测试 role 为 None 时返回 success=False"""
        h = AssignmentHandler()
        r = h.handle(cmd("assignment", next_roles=[{"role": None, "message": "hi"}]), context)
        assert r.success is False

    def test_ah05_empty_message_allowed(self, context):
        """测试 message 为空字符串时允许指派"""
        h = AssignmentHandler()
        r = h.handle(cmd("assignment", next_roles=[{"role": "客服", "message": ""}]), context)
        assert r.success is True
        assert context.messages == [("test_role", "客服", "")]

    def test_ah06_missing_next_roles(self, context):
        """测试缺失 next_roles 时返回 success=False"""
        h = AssignmentHandler()
        r = h.handle(cmd("assignment"), context)
        assert r.success is False

    def test_ah07_non_dict_non_callvalue_entry(self, context):
        """测试 next_roles 含非预期类型（int/str）时 role 为 None → success=False"""
        h = AssignmentHandler()
        r = h.handle(cmd("assignment", next_roles=[1, 2, 3]), context)
        assert r.success is False

    def test_ah08_mixed_valid_and_invalid_entries(self, context):
        """测试 next_roles 混有合法条目与非法条目：首个合法成功，遇非法即失败"""
        h = AssignmentHandler()
        r = h.handle(
            cmd("assignment", next_roles=[{"role": "客服", "message": "ok"}, 42]),
            context,
        )
        # 第一个条目成功发送消息，第二个条目 role=None 触发失败
        assert r.success is False
        assert context.messages == [("test_role", "客服", "ok")]


class TestWriteVarHandler:
    """write_var 指令处理器测试"""

    def test_wv01_single(self, context):
        """测试写入单个变量"""
        h = WriteVarHandler()
        r = h.handle(cmd("write_var", key1="value1"), context)
        assert r.success is True
        assert context.variables["key1"] == "value1"

    def test_wv02_multiple(self, context):
        """测试写入多个变量"""
        h = WriteVarHandler()
        h.handle(cmd("write_var", a=1, b="text"), context)
        assert context.variables == {"a": 1, "b": "text"}

    def test_wv03_dict_value(self, context):
        """测试变量值为字典"""
        h = WriteVarHandler()
        h.handle(cmd("write_var", data={"k": "v"}), context)
        assert context.variables["data"] == {"k": "v"}

    def test_wv04_list_value(self, context):
        """测试变量值为列表"""
        h = WriteVarHandler()
        h.handle(cmd("write_var", items=[1, 2, 3]), context)
        assert context.variables["items"] == [1, 2, 3]

    def test_wv05_no_args(self, context):
        """测试空参数恒成功，不写入任何变量"""
        h = WriteVarHandler()
        r = h.handle(cmd("write_var"), context)
        assert r.success is True
        assert context.variables == {}


class TestNotifyHandler:
    """notify 指令处理器测试"""

    def test_nh01_normal(self, context):
        """测试正常通知"""
        h = NotifyHandler()
        r = h.handle(cmd("notify", receiver="human", message="你好"), context)
        assert r.success is True
        assert context.messages == [("test_role", "human", "你好")]

    def test_nh02_default_receiver(self, context):
        """测试 receiver 缺省为 human"""
        h = NotifyHandler()
        h.handle(cmd("notify", message="你好"), context)
        assert context.messages == [("test_role", "human", "你好")]

    def test_nh03_missing_message(self, context):
        """测试 message 缺失时返回 success=False 且不发送"""
        h = NotifyHandler()
        r = h.handle(cmd("notify", receiver="human"), context)
        assert r.success is False
        assert context.messages == []

    def test_nh04_whitespace_message(self, context):
        """测试 message 为纯空白字符串时返回 success=False 且不发送"""
        h = NotifyHandler()
        r = h.handle(cmd("notify", message="   "), context)
        assert r.success is False
        assert context.messages == []


class TestSendMessageHandler:
    """send_message 指令处理器测试"""

    def test_sm01_normal(self, context):
        """测试正常发送消息"""
        h = SendMessageHandler()
        r = h.handle(cmd("send_message", receiver="客服", message="你好"), context)
        assert r.success is True
        assert context.messages == [("test_role", "客服", "你好")]

    def test_sm02_receiver_none(self, context):
        """测试 receiver 为 None 时返回 success=False 且不发送"""
        h = SendMessageHandler()
        r = h.handle(cmd("send_message", receiver=None, message="你好"), context)
        assert r.success is False
        assert context.messages == []

    def test_sm03_receiver_empty(self, context):
        """测试 receiver 为空字符串时返回 success=False 且不发送"""
        h = SendMessageHandler()
        r = h.handle(cmd("send_message", receiver="", message="你好"), context)
        assert r.success is False
        assert context.messages == []

    def test_sm04_receiver_missing(self, context):
        """测试 receiver 缺失时返回 success=False 且不发送"""
        h = SendMessageHandler()
        r = h.handle(cmd("send_message", message="你好"), context)
        assert r.success is False
        assert context.messages == []

    def test_sm05_message_missing(self, context):
        """测试 message 缺失时返回 success=False 且不发送"""
        h = SendMessageHandler()
        r = h.handle(cmd("send_message", receiver="客服"), context)
        assert r.success is False
        assert context.messages == []

    def test_sm06_message_empty(self, context):
        """测试 message 为空字符串时返回 success=False 且不发送"""
        h = SendMessageHandler()
        r = h.handle(cmd("send_message", receiver="客服", message=""), context)
        assert r.success is False
        assert context.messages == []

    def test_sm07_receiver_whitespace(self, context):
        """测试 receiver 为纯空白字符串时返回 success=False 且不发送"""
        h = SendMessageHandler()
        r = h.handle(cmd("send_message", receiver="   ", message="你好"), context)
        assert r.success is False
        assert context.messages == []

    def test_sm08_message_whitespace(self, context):
        """测试 message 为纯空白字符串时返回 success=False 且不发送"""
        h = SendMessageHandler()
        r = h.handle(cmd("send_message", receiver="客服", message="   "), context)
        assert r.success is False
        assert context.messages == []


class TestTerminateHandler:
    """terminate 指令处理器测试"""

    def test_th01_normal(self, context):
        """测试正常终止：设置终止标记并把消息发给 human"""
        h = TerminateHandler()
        r = h.handle(cmd("terminate", message="任务完成"), context)
        assert r.success is True
        assert context.terminated is True
        assert context.messages == [("test_role", "human", "任务完成")]

    def test_th02_dict_message(self, context):
        """测试 message 为 dict 时转换为 str"""
        h = TerminateHandler()
        h.handle(cmd("terminate", message={"result": "ok"}), context)
        assert context.messages[0][2] == str({"result": "ok"})

    def test_th03_missing_message(self, context):
        """测试 message 缺失时返回 success=False 且不终止"""
        h = TerminateHandler()
        r = h.handle(cmd("terminate"), context)
        assert r.success is False
        assert context.terminated is False

    def test_th04_is_terminal_flag(self, context):
        """测试正常终止时 is_terminal 标记为 True"""
        h = TerminateHandler()
        r = h.handle(cmd("terminate", message="done"), context)
        assert r.is_terminal is True


class TestCustomFunctionHandler:
    """自定义函数（通配）指令处理器测试"""

    def test_cf01_normal_call(self, context):
        """测试正常调用已注册函数"""
        context.functions["rag"] = lambda **kw: f"result:{kw}"
        h = CustomFunctionHandler()
        r = h.handle(cmd("rag", q="x"), context)
        assert r.success is True
        assert r.return_value == "result:{'q': 'x'}"

    def test_cf02_function_raises(self, context):
        """测试函数抛异常时 success=False 且 return_value 含错误文本"""
        def boom(**kw):
            raise RuntimeError("calc error")

        context.functions["calc"] = boom
        h = CustomFunctionHandler()
        r = h.handle(cmd("calc", a=1), context)
        assert r.success is False
        assert "工具错误" in r.return_value
        assert "calc error" in r.return_value

    def test_cf03_function_not_found(self, context):
        """测试函数不存在时返回 success=False"""
        h = CustomFunctionHandler()
        r = h.handle(cmd("missing_fn"), context)
        assert r.success is False

    def test_cf04_returns_string(self, context):
        """测试函数返回字符串时原样返回"""
        context.functions["echo"] = lambda **kw: "hello"
        h = CustomFunctionHandler()
        r = h.handle(cmd("echo"), context)
        assert r.return_value == "hello"

    def test_cf05_returns_object(self, context):
        """测试函数返回对象（dict）时可序列化"""
        context.functions["obj"] = lambda **kw: {"k": "v"}
        h = CustomFunctionHandler()
        r = h.handle(cmd("obj"), context)
        assert r.return_value == {"k": "v"}
        assert str(r.return_value)
