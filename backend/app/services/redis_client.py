"""Redis 异步客户端 + 发布/订阅工具。

用途：
  1. 工作流执行时，把每个步骤的状态变更 publish 到频道
  2. WebSocket 端点 subscribe 频道，把事件实时推给前端
"""
import json
import logging
from typing import Any, AsyncIterator

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

# 全局 Redis 客户端（单例）
_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """获取全局 Redis 客户端，懒加载。"""
    global _client
    if _client is None:
        _client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,  # 返回字符串而不是 bytes
        )
    return _client


async def close_redis() -> None:
    """关闭 Redis 连接（应用退出时调用）。"""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def publish_event(channel: str, data: dict[str, Any]) -> None:
    """向频道发布一条 JSON 事件。

    Redis 不可用时只记录日志，不影响业务流程（降级处理）。
    """
    try:
        client = await get_redis()
        await client.publish(
            channel,
            json.dumps(data, ensure_ascii=False, default=str),
        )
    except Exception as e:
        logger.warning(f"Redis 发布事件失败 (channel={channel}): {e}")


async def subscribe(channel: str) -> AsyncIterator[dict[str, Any]]:
    """订阅频道，逐条 yield 解析后的事件字典。

    调用方（WebSocket）断开时自动取消订阅。
    """
    client = await get_redis()
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            # 只处理实际消息，跳过订阅确认等
            if message.get("type") == "message":
                try:
                    yield json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        