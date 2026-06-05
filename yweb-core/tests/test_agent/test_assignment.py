"""解析 assignment + role(...) 的最简测试。

pytest 默认捕获 print，通过时看不到输出。要看打印请用::

    python -m pytest tests/test_agent/test_assignment.py -s

或直接运行本文件::

    python tests/test_agent/test_assignment.py
"""

import sys
from pathlib import Path

# 允许 python tests/test_agent/test_assignment.py 直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from yweb.agent import CallValue, parse_command_output

LLM_OUTPUT = """command=|<|assignment(
next_roles=[
role(
name="商品参数客服"
message="提供佳能 GI-81PGBK 黑色墨水加墨步骤与操作说明"
)
role(
name="商品故障客服"
message="确认加墨过程可能的故障并给出解决方案"
)
]
)|>|"""


def test_parse_assignment_with_roles():
    cmds = parse_command_output(LLM_OUTPUT)
    assert len(cmds) == 1
    assert cmds[0].toolname == "assignment"

    roles = cmds[0].args["next_roles"]
    assert len(roles) == 2
    assert isinstance(roles[0], CallValue)
    assert roles[0].name == "role"
    assert roles[0].args["name"] == "商品参数客服"
    assert roles[0].args["message"] == "提供佳能 GI-81PGBK 黑色墨水加墨步骤与操作说明"
    assert roles[1].args["name"] == "商品故障客服"


def _print_result() -> None:
    cmds = parse_command_output(LLM_OUTPUT)
    for i, cmd in enumerate(cmds):
        print(f"[{i}] toolname = {cmd.toolname!r}")
        for key, val in cmd.args.items():
            print(f"    {key} = {val!r}")


if __name__ == "__main__":
    _print_result()
