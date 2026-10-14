"""指令解析层测试

覆盖 split_param_expressions / parse_param_string / parse_command_output。
"""

import pytest

from yweb.agent.command import ArtifactRef, CallValue, ParsedCommand
from yweb.agent.command.parser import (
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


class TestTolerance:
    """容错行为测试：覆盖 AI 输出格式偏差时解析器的兼容能力"""

    # ===== 命令包络层容错 =====

    def test_tol_whitespace_after_open_marker(self):
        """<| 和函数名之间有空白仍能解析"""
        result = parse_command_output("<|  func(a=1)|>")
        assert result == [ParsedCommand(toolname="func", args={"a": 1})]

    def test_tol_whitespace_before_close_marker(self):
        """) 和 |> 之间有空白仍能解析"""
        result = parse_command_output("<|func(a=1)  |>")
        assert result == [ParsedCommand(toolname="func", args={"a": 1})]

    def test_tol_whitespace_between_name_and_paren(self):
        """函数名和 ( 之间有空白仍能解析"""
        result = parse_command_output("<|func  (a=1)|>")
        assert result == [ParsedCommand(toolname="func", args={"a": 1})]

    def test_tol_tail_with_extra_pipe(self):
        """|>| 格式（多一个 |）能解析"""
        result = parse_command_output("|<|func(a=1)|>|")
        assert result == [ParsedCommand(toolname="func", args={"a": 1})]

    def test_tol_tail_without_extra_pipe(self):
        """|> 格式（不带尾 |）也能解析"""
        result = parse_command_output("|<|func(a=1)|>")
        assert result == [ParsedCommand(toolname="func", args={"a": 1})]

    def test_tol_no_leading_pipe(self):
        """<|func()|> 省略前导 | 也能解析"""
        result = parse_command_output('<|notify(message="hi")|>')
        assert result == [ParsedCommand(toolname="notify", args={"message": "hi"})]

    def test_tol_command_prefix_optional(self):
        """command= 前缀可省略"""
        r1 = parse_command_output('command=|<|func(a=1)|>|')
        r2 = parse_command_output('|<|func(a=1)|>')
        assert r1 == r2

    # ===== 参数解析层容错 =====

    def test_tol_spaces_around_equals(self):
        """key = value 等号前后有空白仍能解析"""
        result = parse_param_string('name  =  "hello"')
        assert result == {"name": "hello"}

    def test_tol_spaces_around_value(self):
        """值前后有多余空白会被 strip"""
        result = parse_param_string('name=  "hello"  ')
        assert result == {"name": "hello"}

    def test_tol_empty_value(self):
        """key= 后面为空，返回空字符串"""
        result = parse_param_string("key=")
        assert result == {"key": ""}

    def test_tol_invalid_key_skipped(self):
        """非法键名静默跳过，不影响后续合法参数"""
        result = parse_param_string('123bad="x", good="y"')
        assert result == {"good": "y"}

    # ===== 字面量解析降级容错 =====

    def test_tol_literal_fallback_quoted_malformed(self):
        """带引号但内容不合法时，降级为去引号的原始内容"""
        result = parse_param_string(r'x="hello\xworld"')
        assert result["x"] == r"hello\xworld"

    def test_tol_literal_fallback_unquoted_raw(self):
        """无引号且无法 literal_eval 的值，保留原始字符串"""
        result = parse_param_string("x=abc_xyz")
        assert result == {"x": "abc_xyz"}

    def test_tol_literal_fallback_unquoted_with_chinese(self):
        """无引号的中文裸字符串，保留原始字符串"""
        result = parse_param_string("x=你好世界")
        assert result == {"x": "你好世界"}

    # ===== 分隔符容错 =====

    def test_tol_trailing_comma_ignored(self):
        """尾随逗号不产生空项"""
        result = parse_param_string('a=1, b=2,')
        assert result == {"a": 1, "b": 2}

    def test_tol_multiple_blank_lines(self):
        """连续空行不产生空项"""
        result = parse_param_string('a=1\n\n\nb=2\n\n')
        assert result == {"a": 1, "b": 2}

    def test_tol_comma_and_newline_mixed(self):
        """逗号和换行混用都能正确分隔"""
        result = parse_param_string('a=1,\nb=2\nc=3')
        assert result == {"a": 1, "b": 2, "c": 3}


class TestUnquotedValueWithComma:
    """未加引号的值内含逗号时不丢失后半截"""

    def test_unquoted_value_keeps_comma_tail(self):
        """value=A, B 完整保留为 "A, B"，不再切出 B 后丢弃"""
        result = parse_param_string('field="content", value=A, B')
        assert result == {"field": "content", "value": "A, B"}

    def test_unquoted_chinese_value_keeps_comma_tail(self):
        """中文裸值含英文逗号同样完整保留"""
        result = parse_param_string('value=打印机坏了, 需要维修')
        assert result == {"value": "打印机坏了, 需要维修"}

    def test_quoted_value_still_splits(self):
        """引号收尾的值之后，分隔符仍按分隔符处理"""
        result = parse_param_string('field="a", value="b"')
        assert result == {"field": "a", "value": "b"}

    def test_split_default_mode_unchanged(self):
        """split_param_expressions 默认不启用前瞻，逐个分隔符都切分"""
        assert split_param_expressions("value=A, B") == ["value=A", "B"]

    def test_split_lookahead_mode_merges(self):
        """启用前瞻后，未跟 key= 的分隔符并入前一个值"""
        assert split_param_expressions("value=A, B", kv_lookahead=True) == ["value=A, B"]

    def test_array_elements_still_split(self):
        """数组元素靠换行分隔（元素后跟 ( 而非 =），前瞻不影响其切分"""
        result = parse_param_string(
            'patches=[setValue(field="a", value=1)\nsetValue(field="b", value=2)]'
        )
        assert result == {
            "patches": [
                CallValue(name="setValue", args={"field": "a", "value": 1}),
                CallValue(name="setValue", args={"field": "b", "value": 2}),
            ]
        }


class TestUnparsedReport:
    """未解析表达式回报通道：不再静默丢弃"""

    def test_positional_arg_reported(self):
        """漏写 key= 的位置参数记入 unparsed，而非静默消失"""
        result = parse_command_output('command=|<|set_form([setValue(field="a", value=1)])|>|')
        assert len(result) == 1
        assert result[0].args == {}
        assert result[0].unparsed == ['[setValue(field="a", value=1)]']

    def test_brace_object_array_reported(self):
        """花括号对象数组解析不出结构，记入 unparsed"""
        result = parse_command_output('command=|<|set_form(patches=[{type="setValue"}])|>|')
        assert len(result) == 1
        assert result[0].unparsed == ['[{type="setValue"}]']

    def test_nested_positional_arg_reported(self):
        """嵌套函数调用内部的位置参数也回报"""
        result = parse_command_output('command=|<|set_form(patches=[setValue(field="a", 1)])|>|')
        assert len(result) == 1
        assert result[0].unparsed == ["1"]

    def test_invalid_key_reported(self):
        """非法键名的表达式记入 unparsed"""
        result = parse_command_output('command=|<|f(123bad="x", good="y")|>|')
        assert result[0].args == {"good": "y"}
        assert result[0].unparsed == ['123bad="x"']

    def test_valid_command_reports_nothing(self):
        """合法指令的 unparsed 为空"""
        result = parse_command_output(
            'command=|<|set_form(patches=[setValue(field="a", value=1)])|>|'
        )
        assert result[0].args == {
            "patches": [CallValue(name="setValue", args={"field": "a", "value": 1})]
        }
        assert result[0].unparsed == []

    def test_unquoted_bare_string_not_reported(self):
        """无引号裸字符串是协议允许的容错写法，不记入 unparsed"""
        result = parse_command_output('command=|<|f(x=年假, y=abc_xyz)|>|')
        assert result[0].args == {"x": "年假", "y": "abc_xyz"}
        assert result[0].unparsed == []

    def test_artifact_positional_not_reported(self):
        """@artifact("path") 的位置参数是合法写法，不误报"""
        result = parse_command_output('command=|<|f(x=@artifact("sql/q.sql"))|>|')
        assert result[0].args == {"x": ArtifactRef(path="sql/q.sql")}
        assert result[0].unparsed == []

    def test_parse_param_string_without_sink_unchanged(self):
        """不传 unparsed 时保持原行为：丢弃且不留痕迹"""
        result = parse_param_string('123bad="x", good="y"')
        assert result == {"good": "y"}

    def test_parse_param_string_with_sink(self):
        """传入 unparsed 时按出现顺序追加"""
        sink: list[str] = []
        result = parse_param_string('123bad="x", good="y"', unparsed=sink)
        assert result == {"good": "y"}
        assert sink == ['123bad="x"']
