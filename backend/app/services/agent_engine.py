import json
from collections.abc import AsyncIterator
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
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
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
        choice = response.choices[0]

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
            tool_calls_log.append(
                {
                    "name": tool_name,
                    "arguments": tool_args,
                    "result": result[0:500],  # 防止结果太长
                }
            )

            thoughts.append(
                {
                    "step": iterations,
                    "thought": f"使用工具 {tool_name}",
                    "action": f"{tool_name}({json.dumps(tool_args, ensure_ascii=False)})",
                    "observation": result[:500],
                }
            )

            # 工具执行结果塞给LLM
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    # 超出最大循环次数 直接返回
    return {
        "thoughts": thoughts,
        "final_answer": "达到最大迭代次数，任务未完成。请简化你的需求或分步提问。",
        "tool_calls": tool_calls_log,
        "iterations": iterations,
    }


async def run_agent_stream(user_message: str) -> AsyncIterator[dict[str, Any]]:
    """
    流式版 ReAct Agent：每完成一个阶段就 yield 一个事件。

    事件类型：
      - start:       Agent 开始
      - thought:     决定调用某个工具（思考 + 行动）
      - observation: 工具执行结果
      - final:       最终回答
      - error:       发生异常
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    tools = registry.get_all_schemas()
    iterations = 0

    yield {"event": "start", "data": {"message": "Agent 开始思考"}}

    while iterations < settings.AGENT_MAX_ITERATIONS:
        iterations += 1

        try:
            response = await chat_completion(messages, tools=tools if tools else None)
        except Exception as e:
            yield {"event": "error", "data": {"message": f"模型调用失败: {e}"}}
            return

        choice = response.choices[0]

        # 没有工具调用 → 最终回答
        if not choice.message.tool_calls:
            final_answer = choice.message.content or ""
            yield {
                "event": "final",
                "data": {"answer": final_answer, "iterations": iterations},
            }
            return

        messages.append(choice.message.model_dump())

        # 逐个执行工具，每步都推送事件
        for tool_call in choice.message.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = (
                    json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                )
            except json.JSONDecodeError:
                tool_args = {}

            # 推送思考 + 行动（observation 暂为空，前端可先显示思考过程）
            yield {
                "event": "thought",
                "data": {
                    "step": iterations,
                    "thought": f"我需要使用工具 {tool_name} 来获取信息",
                    "action": f"{tool_name}({json.dumps(tool_args, ensure_ascii=False)})",
                    "observation": "",
                },
            }

            # 执行工具
            tool = registry.get(tool_name)
            if not tool:
                result = f"错误：工具 '{tool_name}' 不存在"
            else:
                try:
                    result = await tool.execute(**tool_args)
                except Exception as e:
                    result = f"工具执行出错: {e}"

            # 推送观察结果
            yield {
                "event": "observation",
                "data": {
                    "step": iterations,
                    "observation": result[:500],
                },
            }

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    # 超过最大迭代次数
    yield {
        "event": "final",
        "data": {"answer": "达到最大迭代次数，任务未完成。", "iterations": iterations},
    }
