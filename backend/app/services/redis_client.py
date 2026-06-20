"""Redis 异步客户端 + 发布/订阅工具。

用途：
  1. 工作流执行时，把每个步骤的状态变更 publish 到频道
  2. WebSocket 端点 subscribe 频道，把事件实时推给前端
"""
import json
import logging
import uuid
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


class RedisLock:
    """基于 SET NX EX 的轻量分布式锁（上下文管理器形式）。

    用法::

        async with RedisLock("my_lock", ttl=30) as lock:
            if not lock.acquired:
                return  # 别的实例正在跑，直接放弃
            ...  # 临界区

    实现：
      - acquire: SET key token NX EX ttl
      - release: 用 Lua 脚本做 CAS（仅当 value 等于本实例的 token 才删），
        避免因本进程卡住超过 ttl 而误删别的实例刚拿到的锁。
    """

    _RELEASE_SCRIPT = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            return redis.call('DEL', KEYS[1])
        else
            return 0
        end
    """

    def __init__(self, key: str, ttl: int = 30) -> None:
        self.key = f"lock:{key}"
        self.ttl = ttl
        self._token = uuid.uuid4().hex
        self._acquired = False

    @property
    def acquired(self) -> bool:
        return self._acquired

    async def __aenter__(self) -> "RedisLock":
        try:
            client = await get_redis()
            self._acquired = await client.set(
                self.key, self._token, nx=True, ex=self.ttl
            ) is not None
        except Exception as e:
            # Redis 不可用时降级：放行（避免 Redis 抖动直接拖垮业务）。
            logger.warning(f"Redis 加锁失败 (key={self.key}): {e}")
            self._acquired = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if not self._acquired:
            return
        try:
            client = await get_redis()
            await client.eval(self._RELEASE_SCRIPT, 1, self.key, self._token)
        except Exception as e:
            logger.warning(f"Redis 释放锁失败 (key={self.key}): {e}")
        finally:
            self._acquired = False
        