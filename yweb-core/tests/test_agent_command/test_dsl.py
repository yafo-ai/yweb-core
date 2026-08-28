"""DSL 端到端测试

覆盖函数式 DSL 解析能力：

- 命令提取的**括号平衡扫描**（支持嵌套函数调用、引号内 ``)|>`` 不误判）；
- 函数式内部对象 ``role(...)`` / ``agent(...)`` → ``CallValue``；
- 参数分隔符兼容换行与逗号；
- ``@artifact(...)`` → ``ArtifactRef``，含数组场景。

断言基于 DSL 规格（而非解析器实现细节），并对每个核心行为包含失败/边界反例。
"""

from yweb.agent.command import (
    ArtifactRef,
    CallValue,
    parse_command_output,
)


class TestDSLCommandExtraction:
    """命令提取：括号平衡扫描与嵌套函数调用"""

    def test_nested_call_extracted_as_single_command(self):
        """嵌套 role(...) 数组应作为单条命令提取，next_roles 为 CallValue 列表"""
        text = '<|assignment(next_roles=[role(name="A", message="m1"), role(name="B")])|>'
        cmds = parse_command_output(text)
        assert len(cmds) == 1
        cmd = cmds[0]
        assert cmd.toolname == "assignment"
        roles = cmd.args["next_roles"]
        assert roles == [
            CallValue(name="role", args={"name": "A", "message": "m1"}),
            CallValue(name="role", args={"name": "B"}),
        ]

    def test_close_paren_pipe_inside_quotes_not_truncated(self):
        """引号内出现 )|> 不应被误判为命令结束（引号感知扫描）"""
        text = '<|assignment(next_roles=[role(name="A", message="hi)|>fake")])|>'
        cmds = parse_command_output(text)
        assert len(cmds) == 1
        role = cmds[0].args["next_roles"][0]
        assert role.args["message"] == "hi)|>fake"

    def test_two_commands_in_sequence(self):
        """文本中多条命令应按出现顺序全部提取"""
        text = (
            '<|notify(message="hello")|>'
            '<|assignment(next_roles=[role(name="A")])|>'
        )
        cmds = parse_command_output(text)
        assert [c.toolname for c in cmds] == ["notify", "assignment"]

    def test_missing_closing_pipe_yields_nothing(self):
        """缺少结尾 |> 时不应提取出命令（关键反例）"""
        assert parse_command_output('<|assignment(next_roles=[role(name="A")])') == []

    def test_unmatched_paren_yields_nothing(self):
        """左括号无匹配右括号时不应提取出命令（关键反例）"""
        assert parse_command_output('<|assignment(next_roles=[role(name="A")]') == []


class TestDSLParamSeparators:
    """参数分隔符：换行与逗号兼容"""

    def test_newline_separated_params(self):
        """换行分隔的参数应被正确拆分（推荐写法）"""
        text = (
            '<|assignment(next_roles=[role(\n'
            '    name="商品参数客服"\n'
            '    message="提供加墨步骤"\n'
            ')])|>'
        )
        role = parse_command_output(text)[0].args["next_roles"][0]
        assert role == CallValue(
            name="role",
            args={"name": "商品参数客服", "message": "提供加墨步骤"},
        )

    def test_comma_separated_params_compatible(self):
        """逗号分隔的参数应等价于换行写法（向后兼容）"""
        text = '<|assignment(next_roles=[role(name="商品参数客服", message="提供加墨步骤")])|>'
        role = parse_command_output(text)[0].args["next_roles"][0]
        assert role == CallValue(
            name="role",
            args={"name": "商品参数客服", "message": "提供加墨步骤"},
        )

    def test_mixed_newline_and_comma(self):
        """换行与逗号混用也应正确拆分为两个参数"""
        text = '<|assignment(next_roles=[agent(name="A",\n task="T")])|>'
        agent = parse_command_output(text)[0].args["next_roles"][0]
        assert agent == CallValue(name="agent", args={"name": "A", "task": "T"})


class TestDSLArtifactReference:
    """@artifact 外部资源引用"""

    def test_artifact_positional(self):
        """位置参数 @artifact(\"path\") 应解析为 ArtifactRef"""
        cmd = parse_command_output('<|custom(script=@artifact("sql/query.sql"))|>')[0]
        assert cmd.args["script"] == ArtifactRef(path="sql/query.sql")

    def test_artifact_keyword(self):
        """关键字参数 @artifact(path=\"...\") 应解析为 ArtifactRef"""
        cmd = parse_command_output('<|custom(script=@artifact(path="a/b.py"))|>')[0]
        assert cmd.args["script"] == ArtifactRef(path="a/b.py")

    def test_artifact_inside_array(self):
        """数组内的 @artifact 引用应逐元素解析为 ArtifactRef 列表"""
        cmd = parse_command_output(
            '<|custom(files=[@artifact("a.sql"), @artifact("b.sql")])|>'
        )[0]
        assert cmd.args["files"] == [
            ArtifactRef(path="a.sql"),
            ArtifactRef(path="b.sql"),
        ]

    def test_unknown_at_prefix_stays_string(self):
        """未知 @xxx 前缀不识别为引用，保留原始字符串（关键反例）"""
        cmd = parse_command_output('<|custom(x=@unknown("v"))|>')[0]
        assert cmd.args["x"] == '@unknown("v")'


class TestDSLArrayMixed:
    """数组：函数调用 / 引用 / 字面量混排"""

    def test_array_of_calls(self):
        """纯函数调用数组应解析为 CallValue 列表"""
        cmd = parse_command_output(
            '<|assignment(next_roles=[agent(name="A", task="t1"), agent(name="B", task="t2")])|>'
        )[0]
        assert cmd.args["next_roles"] == [
            CallValue(name="agent", args={"name": "A", "task": "t1"}),
            CallValue(name="agent", args={"name": "B", "task": "t2"}),
        ]

    def test_pure_literal_array_unchanged(self):
        """纯字面量数组不应被改写（保持 y-agent 行为，关键反例）"""
        cmd = parse_command_output("<|custom(tags=[1, 2, 3])|>")[0]
        assert cmd.args["tags"] == [1, 2, 3]

    def test_dict_array_parsed_as_dicts(self):
        """JSON 对象数组解析为 dict 列表（合法字面量，关键反例）"""
        cmd = parse_command_output(
            '<|assignment(next_roles=[{"role": "A", "message": "m"}])|>'
        )[0]
        assert cmd.args["next_roles"] == [{"role": "A", "message": "m"}]
