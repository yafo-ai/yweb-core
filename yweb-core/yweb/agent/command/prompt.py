"""指令格式提示词生成器

根据工具名、描述与指令示例，生成可供 LLM 提示词拼接的格式说明文本。
"""


class CommandPromptBuilder:
    """生成工具指令格式说明文本，供 LLM 提示词使用。"""

    @staticmethod
    def function_prompt(func_name: str, description: str, command_example: str) -> str:
        """生成工具指令的格式说明。

        Args:
            func_name: 工具/函数名。
            description: 工具介绍。
            command_example: 指令示例的内层内容（不含 ``|<|`` ``|>|`` 包裹）。

        Returns:
            格式说明文本。
        """
        prompt = f"{func_name} 工具介绍： {description}。\n"
        prompt += f"{func_name} 工具指令：command=|<|{command_example}|>|\n\n"
        return prompt
