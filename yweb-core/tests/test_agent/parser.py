"""闭环测试：大模型只输出函数式 command DSL → parse_command_output。

用法（yweb-core 目录下）::

    $env:LLM_API_KEY="sk-..."
    python tests/test_agent/parser.py

测试场景：assignment + next_roles + role(...)（禁止 JSON 对象数组）。
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from yweb.agent import CallValue, CommandPromptBuilder, parse_command_output

name = os.environ.get("LLM_MODEL_NAME", "deepseek-v4-pro")
url = os.environ.get("LLM_API_BASE", "https://api.deepseek.com/v1").rstrip("/")
key = os.environ.get("LLM_API_KEY", "")

USER_QUESTION = "用户询问如何加墨，佳能 GI-81PGBK 黑色墨水"

# 推荐 DSL 示例（内层，由 CommandPromptBuilder 包上 command=|<| ... |>|）
_ASSIGNMENT_INNER = """assignment(
next_roles=[
role(
name="商品参数客服"
message="提供佳能 GI-81PGBK 加墨步骤与操作说明"
)
role(
name="商品故障客服"
message="确认加墨过程可能的故障并给出解决方案"
)
]
)"""

TOOL_PROMPTS = CommandPromptBuilder.function_prompt(
    "assignment",
    "批量调用工具并传入多个参数项",
    _ASSIGNMENT_INNER,
)

SYSTEM_PROMPT = """你只能输出 command DSL，禁止 JSON、Markdown、自然语言、禁止 {"role":...} 对象数组。

唯一规则（整段输出有且仅有一条 command）::

command=|<|函数名(
参数名=值
)|>|

- 函数用 ()，数组用 []，如 next_roles=[...]
- 内部对象必须是函数：role(name="..." 换行 message="...")，不要用 {"role":"..."}
- 数组元素之间、函数参数之间：优先换行，也允许逗号
- 长文本用 @artifact("path")，不要内联 SQL/Python

错误示例（禁止）::
next_roles=[{"role":"客服","message":"..."}]

正确示例（必须）::
next_roles=[
role(
name="客服"
message="..."
)
]"""

USER_PROMPT = f"""用户问题：
{USER_QUESTION}

{TOOL_PROMPTS}
请根据用户问题输出一条 assignment 指令，按上面「正确示例」的函数式写法填写 next_roles 中每个 role 的 message。
只输出 command=|<|assignment(...)|>|，不要其它文字。"""


def call_llm() -> str:
    if not key.strip():
        raise SystemExit("请设置环境变量 LLM_API_KEY")

    try:
        import httpx
    except ImportError as e:
        raise SystemExit("需要 httpx: pip install httpx") from e

    resp = httpx.post(
        f"{url}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT},
            ],
            "temperature": 0.2,
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    return (resp.json()["choices"][0]["message"]["content"] or "").strip()


def main() -> None:
    print(f"model: {name}\nurl:   {url}\n")
    print("=== 期望形态（函数式 assignment）===")
    print(f"command=|<|{_ASSIGNMENT_INNER}|>|")
    print()

    raw = call_llm()
    print("=== 模型输出 ===")
    print(raw)
    print()

    commands = parse_command_output(raw)
    print(f"=== 解析结果（{len(commands)} 条 ParsedCommand）===")
    print("说明: role(...) 在内存里是 CallValue 对象，不是模型文本里的字段；下面用 Python repr 展示。")
    if not commands:
        print("解析失败")
        sys.exit(1)

    for i, cmd in enumerate(commands):
        print(f"\n[{i}] toolname = {cmd.toolname!r}")
        for key, val in cmd.args.items():
            print(f"    {key} = {val!r}")

    cmd = commands[0]
    roles = cmd.args.get("next_roles")
    if not isinstance(roles, list) or not roles:
        print("\n[检查] next_roles 缺失或为空")
        sys.exit(1)
    for i, item in enumerate(roles):
        if isinstance(item, CallValue) and item.name == "role":
            print(f"[检查] role[{i}] OK: name={item.args.get('name')!r}")
        elif isinstance(item, dict):
            print(f"[检查] role[{i}] 仍是 JSON dict，应改为 role(...) 函数式")
            sys.exit(1)
        else:
            print(f"[检查] role[{i}] 类型异常: {item!r}")


if __name__ == "__main__":
    main()
