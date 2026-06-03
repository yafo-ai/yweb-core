"""Prompt 生成器测试

覆盖 CommandPromptBuilder 各方法的输出正确性。
"""

from yweb.agent import CommandPromptBuilder


class TestAssignmentPrompt:
    """assignment_prompt 测试"""

    def test_pt01_normal(self):
        """测试多角色时输出角色表格与 assignment 指令格式"""
        roles = [
            {"role": "客服", "description": "处理咨询"},
            {"role": "质检", "description": "质量检查"},
        ]
        out = CommandPromptBuilder.assignment_prompt(roles)
        assert "可选角色列表" in out
        assert "| 客服 | 处理咨询 |" in out
        assert "| 质检 | 质量检查 |" in out
        assert "command=|<|assignment(" in out

    def test_pt02_single_role(self):
        """测试单角色时不生成说明（返回空字符串）"""
        roles = [{"role": "客服", "description": "处理咨询"}]
        assert CommandPromptBuilder.assignment_prompt(roles) == ""

    def test_pt05_custom_prompt_override(self):
        """测试自定义文案替换默认工具说明，但保留角色表格"""
        roles = [
            {"role": "客服", "description": "处理咨询"},
            {"role": "质检", "description": "质量检查"},
        ]
        out = CommandPromptBuilder.assignment_prompt(roles, custom_prompt="自定义指派说明")
        assert "自定义指派说明" in out
        assert "assignment 工具介绍" not in out
        assert "| 客服 | 处理咨询 |" in out

    def test_pt07_chinese_roles(self):
        """测试中文角色名输出正确"""
        roles = [
            {"role": "退款专员", "description": "处理退款"},
            {"role": "售后经理", "description": "审批"},
        ]
        out = CommandPromptBuilder.assignment_prompt(roles)
        assert "退款专员" in out
        assert "售后经理" in out

    def test_pt08_empty_roles(self):
        """测试空角色列表返回空字符串"""
        assert CommandPromptBuilder.assignment_prompt([]) == ""


class TestWriteVarPrompt:
    """write_var_prompt 测试"""

    def test_pt03_normal(self):
        """测试输出变量 schema 与 write_var 指令格式"""
        out = CommandPromptBuilder.write_var_prompt('answer="填写答案"')
        assert 'answer="填写答案"' in out
        assert "command=|<|write_var(" in out

    def test_custom_prompt_override(self):
        """测试自定义模板（含 variables_json 占位符）替换默认文案"""
        out = CommandPromptBuilder.write_var_prompt(
            "schema_text", custom_prompt="变量定义：{variables_json}"
        )
        assert "变量定义：schema_text" in out
        assert "write_var 工具介绍" not in out


class TestFunctionPrompt:
    """function_prompt 测试"""

    def test_pt04_normal(self):
        """测试输出工具介绍与工具指令格式"""
        out = CommandPromptBuilder.function_prompt(
            "rag_search",
            "知识库检索工具",
            'rag_search(querys=["问题"])',
        )
        assert "rag_search 工具介绍" in out
        assert "知识库检索工具" in out
        assert 'command=|<|rag_search(querys=["问题"])|>|' in out


class TestReactPrompt:
    """react_prompt 测试"""

    def test_pt06_normal(self):
        """测试输出含步骤信息（第 n 轮/共 m 轮）与常规引导"""
        out = CommandPromptBuilder.react_prompt(step=1, max_times=3)
        assert "第 1 轮" in out
        assert "共 3 轮" in out
        assert "【思考】" in out
        assert "【工具指令】" in out

    def test_react_last_round_end_guide(self):
        """测试末轮输出强制结束引导"""
        out = CommandPromptBuilder.react_prompt(step=3, max_times=3)
        assert "请停止推理查询" in out

    def test_react_custom_parts(self):
        """测试自定义片段覆盖默认文案"""
        out = CommandPromptBuilder.react_prompt(
            step=1, max_times=3, parts={"header": "HEADER\n", "guide": "GUIDE"}
        )
        assert out == "HEADER\nGUIDE"
