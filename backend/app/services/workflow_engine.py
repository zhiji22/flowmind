"""
工作流引擎：负责让 LLM 从自然语言生成结构化的工作流 DAG。

核心流程：
  用户自然语言 → 构造 Prompt → 调用 Qwen → 解析 JSON → 验证格式 → 存入数据库
"""
import json
from typing import Any

from app.models.workflow import StepType
from app.services.llm_client import chat_completion
from app.tools.base import registry

# Keys that should never appear in a step config (prevent injection)
_DANGEROUS_CONFIG_KEYS = frozenset({"__class__", "__dict__", "__module__", "eval", "exec", "compile", "__import__"})

# Allowed step_type values
_VALID_STEP_TYPES = frozenset(st.value for st in StepType)


def _check_dangerous_keys(obj: Any, path: str) -> None:
    """递归检查字典和列表中所有层级的危险 key。"""
    if isinstance(obj, list):
        for i, item in enumerate(obj):
            _check_dangerous_keys(item, f"{path}[{i}]")
        return
    if not isinstance(obj, dict):
        return
    dangerous = _DANGEROUS_CONFIG_KEYS & obj.keys()
    if dangerous:
        raise ValueError(f"{path} 包含不允许的 key: {dangerous}")
    for k, v in obj.items():
        _check_dangerous_keys(v, f"{path}.{k}")


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
9. 当工作流涉及发送邮件时，收件人地址使用用户的邮箱：{user_email}
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


async def generate_workflow_from_message(user_message: str, user_email: str = "") -> dict[str, Any]:
    """
    从自然语言生成工作流 DAG。

    流程：
      1. 构造包含工具列表的 System Prompt
      2. 调用 Qwen 生成 JSON
      3. 解析并验证 JSON 格式
      4. 返回结构化的工作流定义
    """
    tools_desc = _build_tools_description()
    system_prompt = WORKFLOW_SYSTEM_PROMPT.format(
        tools_description=tools_desc,
        user_email=user_email or "user@example.com",
    )

    # 生成工作流
    response = await chat_completion(
        messages=[
            { "role": "system", "content": system_prompt },
            { "role": "user", "content": user_message },
        ],
        model="qwen-plus",
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
        # 验证 step_type 是合法枚举值
        step_type = step.get("step_type", "")
        if step_type not in _VALID_STEP_TYPES:
            raise ValueError(f"步骤包含非法的 step_type: {step_type}")

        if step_type == "tool":
            tool_name = step.get("tool_name", "")
            if tool_name and tool_name not in available_tools:
                raise ValueError(f"步骤引用了不存在的工具: {tool_name}")

        # 清理 config 中的危险 key（递归检查）
        config = step.get("config", {})
        if isinstance(config, dict):
            _check_dangerous_keys(config, "config")
            
    return workflow_data



