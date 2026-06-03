"""指令格式提示词生成器

把各类指令的格式说明生成为文本，供 LLM 提示词使用。

设计原则:
    ``CommandPromptBuilder`` 只负责**文本生成**，不感知节点、图、LLM 的存在。
    消费者传入角色列表/变量说明/函数信息，拿回格式化文本，自行拼接到提示词中。
"""

from typing import Dict, List, Optional


class CommandPromptBuilder:
    """生成指令格式说明文本，供 LLM 提示词使用。"""

    @staticmethod
    def assignment_prompt(roles: List[Dict[str, str]], custom_prompt: str = "") -> str:
        """生成 ``assignment`` 指令的格式说明。

        Args:
            roles: 可选角色列表，每项形如 ``{"role": "角色名", "description": "角色职责"}``。
            custom_prompt: 自定义说明文案，非空时替换默认的工具介绍+指令格式（角色表格仍保留）。

        Returns:
            格式说明文本。角色数 <= 1 时返回空字符串（无需选择，不生成说明）。
        """
        if len(roles) <= 1:
            return ""

        prompt = "可选角色列表：\n"
        prompt += "| 角色 | 角色职责 |\n"
        prompt += "|-|-|\n"
        for role in roles:
            prompt += f"| {role.get('role', '')} | {role.get('description', '')} |\n"
        prompt += "\n\n"

        if custom_prompt:
            prompt += custom_prompt + "\n\n"
        else:
            prompt += "assignment 工具介绍：用于从“可选角色列表”中筛选出适宜的角色，进行处理下一步任务。\n"
            prompt += (
                'assignment 工具指令：command=|<|assignment(next_roles=[{"role":"填写选择的角色",'
                '"message":"填写角色的任务内容"},\n{"role":"填写选择的角色","message":"填写角色的任务内容"}])|>|\n\n'
            )
            prompt += "\n"
        return prompt

    @staticmethod
    def write_var_prompt(variables_json: str, custom_prompt: str = "") -> str:
        """生成 ``write_var`` 指令的格式说明。

        Args:
            variables_json: 变量 schema 的格式化字符串。
            custom_prompt: 自定义说明模板，非空时使用，需包含 ``{variables_json}`` 占位符。

        Returns:
            格式说明文本。
        """
        if custom_prompt:
            return custom_prompt.format(variables_json=variables_json) + "\n\n"

        prompt = "write_var 工具介绍：用于将答案/结果/输出内容存储到特殊的位置。\n "
        prompt += f"write_var 工具指令：command=|<|write_var({variables_json})|>|\n\n"
        prompt += "\n"
        return prompt

    @staticmethod
    def function_prompt(func_name: str, description: str, command_example: str) -> str:
        """生成自定义函数指令的格式说明。

        Args:
            func_name: 函数名。
            description: 函数介绍。
            command_example: 指令示例的内层内容（不含 ``|<|`` ``|>|`` 包裹）。

        Returns:
            格式说明文本。
        """
        prompt = f"{func_name} 工具介绍： {description}。\n"
        prompt += f"{func_name} 工具指令：command=|<|{command_example}|>|\n\n"
        return prompt

    @staticmethod
    def react_prompt(
        step: int,
        max_times: int,
        parts: Optional[Dict[str, str]] = None,
    ) -> str:
        """生成 ReAct 推理引导文本。

        Args:
            step: 当前推理轮次（从 1 开始）。
            max_times: 最大推理轮次。
            parts: 可选的自定义文案片段，支持键：
                ``"header"``（轮次说明）、``"guide"``（常规引导）、
                ``"end_guide"``（末轮强制结束引导）。

        Returns:
            引导文本。``step >= max_times`` 时输出强制结束引导，否则输出常规引导。
        """
        parts = parts or {}
        prompt = parts.get("header") or f"第 {step} 轮推理（共 {max_times} 轮）：\n\n"

        if step >= max_times:
            end_guide = parts.get("end_guide")
            if end_guide:
                prompt += end_guide
            else:
                prompt += "请停止推理查询，使用以上信息回答问题，按照以下格式输出：\n"
                prompt += "【思考】：填写你分析的问题答案\n"
                prompt += '【工具指令】：填写最终回答工具指令，工具指令必须以"command=|<|"开始，以"|>|"结束\n'
        else:
            guide = parts.get("guide")
            if guide:
                prompt += guide
            else:
                prompt += "分析以上信息并进行思考，按照以下格式输出：\n"
                prompt += "【思考】：填写你的分析过程\n"
                prompt += '【工具指令】：填写你使用的工具指令，工具指令必须以"command=|<|"开始，以"|>|"结束\n'
        return prompt
