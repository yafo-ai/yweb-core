"""Prompt 生成器测试

覆盖 CommandPromptBuilder 通用工具指令格式拼接。
"""

from yweb.agent import CommandPromptBuilder


class TestFunctionPrompt:
    """function_prompt 测试"""

    def test_pt04_normal(self):
        """测试输出工具介绍与工具指令格式"""
        out = CommandPromptBuilder.function_prompt(
            "rag_search",
            "知识库检索工具",
            'rag_search(querys=["问题"])',
        )
        print(f"out: {out}")
        assert "rag_search 工具介绍" in out
        assert "知识库检索工具" in out
        assert 'command=|<|rag_search(querys=["问题"])|>|' in out

    def test_empty_args_command(self):
        """测试无参数工具指令拼接"""
        out = CommandPromptBuilder.function_prompt("ping", "健康检查", "ping()")
        assert "ping 工具介绍" in out
        assert "command=|<|ping()|>|" in out
