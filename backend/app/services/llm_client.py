from typing import Any, AsyncGenerator
from openai import OpenAI

from app.config import settings


def get_client() -> OpenAI:
    return OpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url=settings.LLM_BASE_URL
    )

def chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> Any:
    """同步调用LLM，返回完整的响应。"""
    client = get_client()
    kwargs: dict[str, Any] = {
        "model": model or settings.LLM_MODEL_DEFAULT,
        "messages": messages,
    }

    if tools:
        kwargs["tools"] = tools
    
    return client.chat.completions.create(**kwargs)


def chat_completion_stream(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> Any:
    """流式调用 LLM，返回 stream 迭代器。"""
    client = get_client()
    kwargs: dict[str, Any] = {
        "model": model or settings.LLM_MODEL_DEFAULT,
        "messages": messages,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
    return client.chat.completions.create(**kwargs)