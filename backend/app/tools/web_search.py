import asyncio
import logging
from typing import Any

from app.config import settings
from app.tools.base import BaseTool, registry

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]


async def _search_tavily(query: str) -> str:
    """Tavily 搜索（主力引擎，需要 API key）。"""
    from tavily import TavilyClient

    client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    response = client.search(query=query, max_results=5, search_depth="basic")

    if not response.get("results"):
        return f"搜索 '{query}' 没有找到结果。"

    formatted = []
    for r in response["results"]:
        formatted.append(f"- {r['title']}\n  {r['content']}\n  链接: {r['url']}")
    return "\n\n".join(formatted)


async def _search_duckduckgo(query: str) -> str:
    """DuckDuckGo 搜索（免费后备，带重试）。"""
    from duckduckgo_search import DDGS

    loop = asyncio.get_event_loop()

    for attempt in range(MAX_RETRIES):
        try:
            results = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: list(DDGS().text(query, max_results=5))),
                timeout=30,
            )

            if not results:
                return f"搜索 '{query}' 没有找到结果。"

            formatted = []
            for r in results:
                formatted.append(f"- {r['title']}\n  {r['body']}\n  链接: {r['href']}")
            return "\n\n".join(formatted)
        except asyncio.TimeoutError:
            return f"搜索 '{query}' 超时，请稍后重试。"
        except Exception as e:
            if "Ratelimit" in str(e) and attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAYS[attempt])
                continue
            raise

    raise RuntimeError("超过最大重试次数")


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "搜索互联网获取信息。当需要查找最新数据、新闻、价格、事实时使用。"

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                }
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs) -> str:
        query = kwargs.get("query", "")

        # 有 Tavily API key 则优先使用
        if settings.TAVILY_API_KEY:
            try:
                return await _search_tavily(query)
            except Exception as e:
                logger.warning("Tavily 搜索失败，切换到 DuckDuckGo: %s", e)

        # 后备：DuckDuckGo（带重试）
        try:
            return await _search_duckduckgo(query)
        except Exception as e:
            return f"搜索失败：{str(e)}"


registry.register(WebSearchTool())
