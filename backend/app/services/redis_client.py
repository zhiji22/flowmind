"""Redis 异步客户端 + 发布/订阅工具。

用途：
  1. 工作流执行时，把每个步骤的状态变更 publish 到频道
  2. WebSocket 端点 subscribe 频道，把事件实时推给前端
"""
import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

# 全局 Redis 客户端（按事件循环归属缓存）
_client: redis.Redis | None = None
# _client 绑定的 event loop；loop 切换（Celery 每个任务一个 asyncio.run）
# 时必须重建客户端，否则连接池还挂在已关闭的旧 loop 上。
_client_loop: asyncio.AbstractEventLoop | None = None


async def _safe_aclose(client: redis.Redis | None) -> None:
    """安全关闭 Redis 客户端：吞掉 loop 已关闭等异常。

    旧客户端绑定的 loop 可能已关闭，aclose 时会再抛一次 RuntimeError；
    清理路径不应让这种异常冒泡，否则会屏蔽后续的重建或退出流程。
    """
    if client is None:
        return
    try:
        await client.aclose()
    except Exception as e:
        logger.debug("关闭 Redis 客户端时忽略异常: %s", e)


async def get_redis() -> redis.Redis:
    """获取当前事件循环专属的 Redis 客户端。

    redis.asyncio 的连接池在首次使用时绑定到当前 event loop。Celery 任务
    每次都在全新的 asyncio.run() loop 里执行，loop 一结束连接即作废；若
    复用全局单例，下一次调用会抛 "Event loop is closed"。因此按 loop 归属
    缓存：检测到 loop 切换（前一个 loop 已关闭）就丢弃旧客户端并重建。

    API / WebSocket 进程是单条长生命周期 loop，始终命中缓存，行为不变。

    注意：同一 loop 内并发协程同时触发重建时，理论上存在「多个协程各自
    重建、最后一个覆盖前面、前面建的客户端泄漏」的竞态。当前调用路径
    不会触发——Celery 每个 task 内对 RedisLock 是串行的；API/WebSocket
    在 loop 启动后即命中缓存。若未来引入并发触发的场景，需要补互斥：
    注意 module-level 构造的 asyncio.Lock 同样会绑定到首次 await 的 loop，
    必须跟随 _client_loop 一起重建。
    """
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        await _safe_aclose(_client)
        _client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,  # 返回字符串而不是 bytes
        )
        _client_loop = loop
    return _client


async def close_redis() -> None:
    """关闭 Redis 连接（应用退出时调用）。

    即使绑定的 loop 已关闭也要安全清空全局状态——退出路径里任何异常
    都不应阻塞后续清理。
    """
    global _client, _client_loop
    await _safe_aclose(_client)
    _client = None
    _client_loop = None


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
        