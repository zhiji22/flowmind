import json
from typing import Any

from app.config import settings
from app.services.llm_client import chat_completion
from app.tools.base import registry


SYSTEM_PROMPT = """你是 FlowMind 的 AI 助手。你可以使用工具来帮助用户完成任务。

工作方式：
1. 分析用户的需求
2. 如果需要使用工具，选择合适的工具并调用
3. 根据工具返回的结果，继续分析或给出最终回答
4. 如果任务需要多个步骤，依次执行

每次你都会收到之前所有步骤的上下文，请基于完整上下文来决策。
当所有步骤完成，给出最终结论时，请在回答开头加上 [FINAL]。
"""

async def run_agent(user_message: str) -> dict[str, Any]:
    """
    运行 ReAct Agent 循环。

    返回:
        {
            "thoughts": [{"step": 1, "thought": "...", "action": "...", "observation": "..."}],
            "final_answer": "...",
            "tool_calls": [{"name": "...", "arguments": {...}, "result": "..."}],
            "iterations": 3
        }
    """
    messages = [
        { "role": "system", "content": SYSTEM_PROMPT },
        { "role": "user", "content": user_message },
    ]

    # 获取所有tool
    tools = registry.get_all_schemas()
    thoughts = []
    tool_calls_log = []
    # 循环次数
    iterations = 0

    while iterations < settings.AGENT_MAX_ITERATIONS:
        iterations += 1

        response = await chat_completion(messages, tools=tools if tools else None)
        choice  = response.choices[0]

        # 没有工具了 直接回答
        if not choice.message.tool_calls:
            final_answer = choice.message.content or ""
            return {
                "thoughts": thoughts,
                "final_answer": final_answer,
                "tool_calls": tool_calls_log,
                "iterations": iterations,
            }
        
        # 大模型的回答 tool调用 加入消息历史
        messages.append(choice.message.model_dump())

        # 工具调用
        for tool_call in choice.message.tool_calls:
            tool_name = tool_call.function.name
            tool_args_str = tool_call.function.arguments

            try:
                tool_args = json.loads(tool_args_str) if tool_args_str else {}
            except json.JSONDecodeError:
                tool_args = {}

            tool = registry.get(tool_name)
            if not tool:
                result = f"错误：工具 '{tool_name}' 不存在"
            else:
                result = await tool.execute(**tool_args)
            
            # 记录工具调用日志
            tool_calls_log.append({
                "name": tool_name,
                "arguments": tool_args,
                "result": result[0:500], #防止结果太长
            })

            thoughts.append({
                "step": iterations,
                "thought": f"使用工具 {tool_name}",
                "action": f"{tool_name}({json.dumps(tool_args, ensure_ascii=False)})",
                "observation": result[:500],
            })

            # 工具执行结果塞给LLM
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    # 超出最大循环次数 直接返回
    return {
        "thoughts": thoughts,
        "final_answer": "达到最大迭代次数，任务未完成。请简化你的需求或分步提问。",
        "tool_calls": tool_calls_log,
        "iterations": iterations
    }
    