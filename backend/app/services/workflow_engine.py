"""
工作流引擎：负责让 LLM 从自然语言生成结构化的工作流 DAG。

核心流程：
  用户自然语言 → 构造 Prompt → 调用 Qwen → 解析 JSON → 验证格式 → 存入数据库
"""
import json
from typing import Any

from app.services.llm_client import chat_completion
from app.tools.base import registry


# 指导 LLM 生成工作流 DAG 的 System Prompt
WORKFLOW_SYSTEM_PROMPT = """你是一个工作流设计专家。用户会用自然语言描述一个任务，你需要将其转化为结构化的工作流 DAG。

可用工具列表：
{tools_description}

你必须严格按以下 JSON 格式返回，不要返回任何其他内容：

{{
  "name": "工作流名称",
  "description": "工作流描述",
  "steps": [
    {{
      "id": "step_1",
      "step_type": "trigger|tool|condition|approval",
      "tool_name": "工具名称（仅tool类型需要）",
      "config": {{}},
      "next": ["下一步骤id"],
      "next_yes": ["条件为真时走（仅condition类型）"],
      "next_no": ["条件为假时走（仅condition类型）"],
      "position": {{"x": 100, "y": 100}}
    }}
  ]
}}

规则：
1. 第一个 step 的 step_type 必须是 trigger
2. trigger 的 config 可以包含 schedule（cron表达式）
3. tool 类型必须有 tool_name，且必须是可用工具之一
4. condition 类型必须有 next_yes 和 next_no
5. approval 类型用于需要人工确认的步骤
6. position 用于前端可视化布局，合理分配 x, y 坐标
7. 步骤之间通过 id 和 next/next_yes/next_no 连接，形成有向无环图（DAG）
8. 只返回 JSON，不要返回 markdown 代码块或其他文字
"""


def _build_tools_description() -> str:
    """将注册表中的工具格式化为 LLM 能理解的描述文本"""
    descriptions = []
    for tool in registry._tools.values():
        params = tool.get_parameters_schema().get("properties", {})
        param_str = ", ".join(
            f"{k}: {v.get('description', v.get('type', ''))}" for k, v in params.items()
        )

        descriptions.append(f"- {tool.name}({param_str}): {tool.description}")
    return "\n".join(descriptions)


async def generate_workflow_from_message(user_message: str) -> dict[str, Any]:
    """
    从自然语言生成工作流 DAG。

    流程：
      1. 构造包含工具列表的 System Prompt
      2. 调用 Qwen 生成 JSON
      3. 解析并验证 JSON 格式
      4. 返回结构化的工作流定义
    """
    tools_desc = _build_tools_description()
    system_prompt = WORKFLOW_SYSTEM_PROMPT.format(tools_description=tools_desc)

    # 生成工作流
    response = chat_completion(
        messages=[
            { "role": "system", "content": system_prompt },
            { "role": "user", "content": user_message },
        ],
        model = "qwen-max",
    )

    content = response.choices[0].message.content or ""

    # 如果返回json 包裹内容，提取
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    # 解析 JSON
    try:
        workflow_data = json.loads(content)
    except json.JSONDecodeError:
        raise ValueError(f"LLM 返回的内容不是合法 JSON: {content[:200]}")
    
    # 基础验证：至少要有一个步骤，第一步是trigger
    steps = workflow_data.get("steps", [])
    if not steps:
        raise ValueError("生成的工作流没有步骤")

    if steps[0].get("step_type") != "trigger":
        raise ValueError("工作流第一步必须是 trigger 类型")
    
    # 验证所有tool类型的步骤使用的工具确实存在
    available_tools = set(registry.list_names())
    for step in steps:
        if step.get("step_type") == "tool":
            tool_name = step.get("tool_name", "")
            if tool_name and tool_name not in available_tools:
                raise ValueError(f"步骤引用了不存在的工具: {tool_name}")
            
    return workflow_data



