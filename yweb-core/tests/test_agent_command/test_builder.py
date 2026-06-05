"""build_command 单元测试 —— parse 的逆操作与往返一致性。"""

import pytest

from yweb.agent.command import (
    ArtifactRef,
    CallValue,
    build_command,
    parse_command_output,
)


class TestBuildCommand:
    """结构化参数 → command 文本"""

    def test_literal_params_round_trip(self):
        """测试字面量参数构建后可被解析还原"""
        text = build_command("notify", receiver="human", message="你好")
        cmds = parse_command_output(text)
        assert len(cmds) == 1
        assert cmds[0].toolname == "notify"
        assert cmds[0].args == {"receiver": "human", "message": "你好"}

    def test_call_value_round_trip(self):
        """测试 CallValue 列表构建后可被解析还原"""
        text = build_command(
            "assignment",
            next_roles=[
                CallValue("role", {"name": "A", "message": "m1"}),
                CallValue("role", {"name": "B"}),
            ],
        )
        cmds = parse_command_output(text)
        assert len(cmds) == 1
        assert cmds[0].args["next_roles"] == [
            CallValue(name="role", args={"name": "A", "message": "m1"}),
            CallValue(name="role", args={"name": "B"}),
        ]

    def test_artifact_round_trip(self):
        """测试 ArtifactRef 构建后可被解析还原"""
        text = build_command("run_sql", script=ArtifactRef("sql/query.sql"))
        cmds = parse_command_output(text)
        assert cmds[0].args["script"] == ArtifactRef(path="sql/query.sql")

    def test_empty_list_and_bool(self):
        """测试空列表与布尔值构建后可被解析还原"""
        text = build_command("write_var", tags=[], enabled=True)
        cmds = parse_command_output(text)
        assert cmds[0].args == {"tags": [], "enabled": True}

    def test_dict_serializes_as_json_literal(self):
        """dict 按字面量 JSON 输出；嵌套对象应优先用 CallValue。"""
        text = build_command("x", meta={"k": "v"})
        assert '{"k": "v"}' in text
        cmds = parse_command_output(text)
        assert cmds[0].args["meta"] == {"k": "v"}

    def test_unsupported_type_raises(self):
        """测试不支持的参数类型会抛出 TypeError"""
        with pytest.raises(TypeError, match="不支持的 DSL 值类型"):
            build_command("x", data=object())


class TestBuildCommandEnvelope:
    """输出包络格式"""

    def test_wraps_with_command_envelope(self):
        """测试构建结果包含 command 包络"""
        text = build_command("search", q="hi")
        assert text.startswith("command=|<|")
        assert text.endswith("|>|")
