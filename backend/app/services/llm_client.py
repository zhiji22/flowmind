import asyncio
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletion

from app.config import settings

_client: AsyncOpenAI | None = None
_lock = asyncio.Lock()


async def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        async with _lock:
            if _client is None:
                _client = AsyncOpenAI(
                    api_key=settings.DASHSCOPE_API_KEY,
                    base_url=settings.LLM_BASE_URL,
                    timeout=60.0,
                )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


class LLMError(Exception):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    pass


class LLMServiceError(LLMError):
    pass


async def chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> ChatCompletion:
    client = await get_client()
    kwargs: dict[str, Any] = {
        "model": model or settings.LLM_MODEL_DEFAULT,
        "messages": messages,
    }

    if tools:
        kwargs["tools"] = tools

    try:
        return await client.chat.completions.create(**kwargs)
    except APITimeoutError as e:
        raise LLMTimeoutError("LLM 请求超时") from e
    except RateLimitError as e:
        raise LLMRateLimitError("LLM 请求频率超限") from e
    except APIConnectionError as e:
        raise LLMServiceError("无法连接 LLM 服务") from e
    except APIError as e:
        raise LLMServiceError(f"LLM 服务错误: {e.message}") from e


async def chat_completion_stream(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str | None = None,
):
    """流式调用 LLM，返回 async generator 逐块产出响应。"""
    client = await get_client()
    kwargs: dict[str, Any] = {
        "model": model or settings.LLM_MODEL_DEFAULT,
        "messages": messages,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools

    try:
        stream = await client.chat.completions.create(**kwargs)
    except APITimeoutError as e:
        raise LLMTimeoutError("LLM 请求超时") from e
    except RateLimitError as e:
        raise LLMRateLimitError("LLM 请求频率超限") from e
    except APIConnectionError as e:
        raise LLMServiceError("无法连接 LLM 服务") from e
    except APIError as e:
        raise LLMServiceError(f"LLM 服务错误: {e.message}") from e

    async for chunk in stream:
        yield chunk
