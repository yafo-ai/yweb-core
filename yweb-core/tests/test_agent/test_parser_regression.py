"""解析器回归测试（yweb-core 行为快照）

使用从 y-agent ``fun_pars_test.py`` 复制的完整 LLM 输出样本，固化 ``parse_command_output``
的预期解析结果到 ``fixtures/regression_golden.json``，防止后续改动引入意外回归。

与 y-agent 的关系:
    多数样本与 y-agent ``output_rules_parser_json`` 逐条一致。但在**引号不配对的畸形
    输入**（如 func28/func30）上，yweb-core 改用引号感知的**括号平衡扫描**（为支持嵌套
    函数调用所必需），有意与 y-agent 的引号无关正则分歧——这类畸形命令不再被切出。

注意:
    本用例依赖 ``json-repair`` 修复畸形 JSON（与 y-agent 硬依赖一致）。
    未安装时跳过，避免误报（单元测试 ``test_parser.py`` 已覆盖降级路径）。
"""

import json
from pathlib import Path

import pytest

from yweb.agent import parse_command_output
from yweb.agent.parser import parser as parser_module

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "regression_golden.json"


def _load_regression_case():
    """加载回归样本与 golden 预期。"""
    data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return data["input"], data["expected"]


class TestParserRegression:
    """fun_pars_test 回归测试（yweb-core 行为快照）"""

    def test_parser_matches_golden_snapshot(self):
        """验证解析结果与固化的 yweb-core golden 快照完全一致。"""
        if parser_module.repair_json is None:
            pytest.skip("json-repair 未安装，跳过需修复畸形 JSON 的回归用例")

        text, expected = _load_regression_case()
        result = parse_command_output(text)

        assert len(result) == len(expected), (
            f"指令数量不一致: got {len(result)}, expected {len(expected)}"
        )
        for i, (r, e) in enumerate(zip(result, expected)):
            assert r.toolname == e["toolname"], f"[{i}] toolname mismatch"
            assert r.args == e["args"], f"[{i}] args mismatch for {e['toolname']}"
