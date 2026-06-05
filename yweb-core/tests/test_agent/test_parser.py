"""指令解析层测试

覆盖 split_param_expressions / parse_param_string / parse_command_output。
"""

import pytest

from yweb.agent import ArtifactRef, CallValue, ParsedCommand
from yweb.agent.parser import (
    parse_command_output,
    parse_param_string,
    split_param_expressions,
)


class TestSplitParamExpressions:
    """split_param_expressions 状态机分割测试"""

    @pytest.mark.parametrize(
        "case_id, text, expected",
        [
            ("S-01", "a=1, b=2", ["a=1", "b=2"]),
            ("S-02", "", []),
            ("S-03", "a=1", ["a=1"]),
            ("S-04", "a=[1, 2, 3], b='hello'", ["a=[1, 2, 3]", "b='hello'"]),
            ("S-05", "a={'k1': 'v1', 'k2': 'v2'}", ["a={'k1': 'v1', 'k2': 'v2'}"]),
            ("S-06", "msg='你好，世界'", ["msg='你好，世界'"]),
            ("S-07", 'a="hello, world", b=1', ['a="hello, world"', "b=1"]),
            ("S-08", "a=[1, [2, 3]], b=(4, 5)", ["a=[1, [2, 3]]", "b=(4, 5)"]),
            ("S-09", r"a='hello\,world', b=2", [r"a='hello\,world'", "b=2"]),
            (
                "S-10",
                "a=[{'k': [1, 2]}, 3], b='test'",
                ["a=[{'k': [1, 2]}, 3]", "b='test'"],
            ),
            ("S-11", "a=1, b=2,", ["a=1", "b=2"]),
            ("S-12", "  a=1  ,  b=2  ", ["a=1", "b=2"]),
            ("S-13", 'name="x"\ntask="y"', ['name="x"', 'task="y"']),
            ("S-14", 'name="x"\n\ntask="y"\n', ['name="x"', 'task="y"']),
            ("S-15", 'name="x",\ntask="y"', ['name="x"', 'task="y"']),
            ("S-16", 'msg="第一行\n第二行", n=1', ['msg="第一行\n第二行"', "n=1"]),
            ("S-17", "items=[a(x=1)\nb(y=2)]", ["items=[a(x=1)\nb(y=2)]"]),
        ],
    )
    def test_split(self, case_id, text, expected):
        """测试参数表达式分割（嵌套/引号/转义/尾随逗号/换行分隔等场景）"""
        assert split_param_expressions(text) == expected


class TestParseParamString:
    """parse_param_string 参数解析测试"""

    @pytest.mark.parametrize(
        "case_id, text, expected",
        [
            ("P-01", "a=1, b='hello'", {"a": 1, "b": "hello"}),
            ("P-02", "", {}),
            ("P-03", "flag=True, other=False", {"flag": True, "other": False}),
            ("P-04", "items=[1, 2, 3]", {"items": [1, 2, 3]}),
            ("P-05", "data={'key': 'value'}", {"data": {"key": "value"}}),
            ("P-06", "price=45.67", {"price": 45.67}),
            ("P-07", "msg='value with \"quotes\"'", {"msg": 'value with "quotes"'}),
            (
                "P-08",
                "a=True, b=[1, 2], c='text', d={'k': 1}",
                {"a": True, "b": [1, 2], "c": "text", "d": {"k": 1}},
            ),
            (
                "P-09",
                "roles=[{'role': '客服', 'message': '你好'}]",
                {"roles": [{"role": "客服", "message": "你好"}]},
            ),
            ("P-10", "123bad='val', good_key='val'", {"good_key": "val"}),
            (
                "P-11",
                "message='惠普M233DW打印机连接方式'",
                {"message": "惠普M233DW打印机连接方式"},
            ),
        ],
    )
    def test_parse(self, case_id, text, expected):
        """测试 key=value 参数解析为字典（各类型/中文/非法键跳过等场景）"""
        assert parse_param_string(text) == expected


class TestCallValueParsing:
    """函数式内部对象 name(...) → CallValue 解析测试"""

    def test_cv01_single_call(self):
        """测试单个函数调用值解析为 CallValue"""
        result = parse_param_string('x=role(name="客服", message="你好")')
        assert result == {"x": CallValue("role", {"name": "客服", "message": "你好"})}

    def test_cv02_call_with_newline_args(self):
        """测试函数参数用换行分隔（DSL 标准写法）"""
        result = parse_param_string('agent=agent(\nname="商品参数客服"\ntask="提供加墨步骤"\n)')
        assert result == {
            "agent": CallValue("agent", {"name": "商品参数客服", "task": "提供加墨步骤"})
        }

    def test_cv07_space_separated_args_not_supported(self):
        """同行空格不作为参数分隔符，第二个参数会被吞进第一个值"""
        result = parse_param_string('x=role(name="A" message="B")')
        role = result["x"]
        assert isinstance(role, CallValue)
        assert role.args.get("name") == 'A" message="B'
        assert "message" not in role.args

    def test_cv03_mixed_arg_types(self):
        """测试函数参数含数字与布尔值"""
        result = parse_param_string('a=agent(name="a", priority=1, active=True)')
        assert result == {"a": CallValue("agent", {"name": "a", "priority": 1, "active": True})}

    def test_cv04_nested_call(self):
        """测试函数调用值内再嵌套函数调用"""
        result = parse_param_string('x=outer(inner=role(name="x"))')
        assert result == {"x": CallValue("outer", {"inner": CallValue("role", {"name": "x"})})}

    def test_cv05_quoted_call_is_string(self):
        """测试加引号的“伪函数调用”仍按字符串解析，不误判为 CallValue"""
        result = parse_param_string('x="role(a=1)"')
        assert result == {"x": "role(a=1)"}

    def test_cv06_non_call_values_unchanged(self):
        """测试非函数式值仍走字面量路径（数字/列表/字符串不变）"""
        result = parse_param_string('n=123, items=[1, 2, 3], s="hi"')
        assert result == {"n": 123, "items": [1, 2, 3], "s": "hi"}


class TestArrayWithCalls:
    """数组含函数调用 / @ 引用时按元素解析测试"""

    def test_ac01_array_of_calls(self):
        """测试数组元素为函数调用，解析为 CallValue 列表"""
        result = parse_param_string(
            'next_roles=[role(name="客服", message="a"), role(name="质检", message="b")]'
        )
        assert result == {
            "next_roles": [
                CallValue("role", {"name": "客服", "message": "a"}),
                CallValue("role", {"name": "质检", "message": "b"}),
            ]
        }

    def test_ac02_array_of_calls_newline(self):
        """测试数组元素用换行分隔的函数调用（DSL 标准写法）"""
        result = parse_param_string(
            'agents=[\nagent(name="A", task="x")\nagent(name="B", task="y")\n]'
        )
        assert result == {
            "agents": [
                CallValue("agent", {"name": "A", "task": "x"}),
                CallValue("agent", {"name": "B", "task": "y"}),
            ]
        }

    def test_ac03_mixed_array(self):
        """测试数组混合字面量与函数调用"""
        result = parse_param_string('xs=[1, role(name="x")]')
        assert result == {"xs": [1, CallValue("role", {"name": "x"})]}

    def test_ac04_pure_literal_array_unchanged(self):
        """测试纯字面量数组仍整体走字面量路径（不变）"""
        result = parse_param_string('items=[1, 2, 3], strs=["a", "b"]')
        assert result == {"items": [1, 2, 3], "strs": ["a", "b"]}

    def test_ac05_pure_dict_array_unchanged(self):
        """测试纯 JSON 字典数组仍按字面量解析（旧形式兼容）"""
        result = parse_param_string('roles=[{"role": "客服", "message": "你好"}]')
        assert result == {"roles": [{"role": "客服", "message": "你好"}]}


class TestArtifactReference:
    """@artifact(...) → ArtifactRef 解析测试"""

    def test_ar01_positional(self):
        """测试位置参数 @artifact(\"path\")"""
        result = parse_param_string('script=@artifact("sql/query.sql")')
        assert result == {"script": ArtifactRef(path="sql/query.sql")}

    def test_ar02_keyword(self):
        """测试关键字参数 @artifact(path=\"...\")"""
        result = parse_param_string('script=@artifact(path="py/run.py")')
        assert result == {"script": ArtifactRef(path="py/run.py")}

    def test_ar03_artifact_in_array(self):
        """测试数组中的 @artifact 引用"""
        result = parse_param_string('files=[@artifact("a.sql"), @artifact("b.sql")]')
        assert result == {
            "files": [ArtifactRef(path="a.sql"), ArtifactRef(path="b.sql")]
        }

    def test_ar04_unknown_ref_is_raw_string(self):
        """测试未识别的 @ 引用降级为原始字符串，不报错"""
        result = parse_param_string('x=@unknown("y")')
        assert result["x"] == '@unknown("y")'


class TestParseCommandOutput:
    """parse_command_output 指令提取测试"""

    def test_c01_single_command(self):
        """测试提取单条指令"""
        text = 'command=|<|notify(message="你好")|>|'
        result = parse_command_output(text)
        assert result == [ParsedCommand(toolname="notify", args={"message": "你好"})]

    def test_c02_multiple_commands(self):
        """测试一段文本中提取多条指令"""
        text = '|<|notify(message="hi")|>| 中间文字 |<|terminate(message="done")|>|'
        result = parse_command_output(text)
        assert len(result) == 2
        assert result[0].toolname == "notify"
        assert result[1].toolname == "terminate"

    def test_c03_plain_text(self):
        """测试无指令的纯文本返回空列表"""
        assert parse_command_output("这是一段普通文本") == []

    def test_c04_empty(self):
        """测试空字符串返回空列表"""
        assert parse_command_output("") == []

    def test_c05_command_with_surrounding_text(self):
        """测试指令前后有文字时仍能正确提取"""
        result = parse_command_output("前文 |<|func(a=1)|>| 后文")
        assert result == [ParsedCommand(toolname="func", args={"a": 1})]

    def test_c06_multiline_params(self):
        """测试多行参数（含换行）的指令解析"""
        text = '|<|assignment(next_roles=[{"role":"客服",\n"message":"hi"}])|>|'
        result = parse_command_output(text)
        assert len(result) == 1
        assert result[0].toolname == "assignment"
        assert result[0].args == {"next_roles": [{"role": "客服", "message": "hi"}]}

    def test_c08_mixed_zh_en(self):
        """测试参数含中英文混合内容"""
        text = '|<|notify(message="HP打印机兼容HP X4E75AA打印头")|>|'
        result = parse_command_output(text)
        assert result[0].args == {"message": "HP打印机兼容HP X4E75AA打印头"}

    def test_c09_url_in_message(self):
        """测试参数中保留完整 URL"""
        text = '|<|notify(message="详见 https://example.com/a/b?x=1")|>|'
        result = parse_command_output(text)
        assert result[0].args["message"] == "详见 https://example.com/a/b?x=1"

    def test_c10_malformed_no_closing(self):
        """测试格式残缺（缺少闭合）不匹配"""
        assert parse_command_output("|<|func(a=1)") == []

    def test_c11_empty_params(self):
        """测试空参数指令"""
        result = parse_command_output("|<|func()|>|")
        assert result == [ParsedCommand(toolname="func", args={})]

    def test_c12_toolname_with_digits_underscore(self):
        """测试 toolname 含数字与下划线"""
        result = parse_command_output("|<|my_func_2(a=1)|>|")
        assert result[0].toolname == "my_func_2"
        assert result[0].args == {"a": 1}
