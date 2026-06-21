"""Token 黑名单：登出后让 token 在剩余有效期内失效。

Redis 实现（跨进程/多 worker/重启都生效）：
  - revoke: SET revoked:{jti} 1 EX ttl（到 exp 自动过期清理）
  - is_revoked: EXISTS revoked:{jti}

降级：Redis 不可用时 fail-open（视为未吊销），仅记录 warning——
避免 Redis 抖动把所有人锁死在登录之外；最坏情况和「无黑名单」相同
（token 到 exp 前仍可用），token 本身有 exp 兜底。
"""

import logging
import time

from app.services.redis_client import get_redis

logger = logging.getLogger(__name__)

_KEY_PREFIX = "revoked:"


async def revoke(token_id: str, expires_at_unix: float) -> None:
    """把 token_id 加入黑名单，直到 expires_at_unix。"""
    ttl = max(1, int(expires_at_unix - time.time()))
    try:
        client = await get_redis()
        await client.set(_KEY_PREFIX + token_id, "1", ex=ttl)
    except Exception as e:
        logger.warning("Redis 吊销 token 失败 (jti=%s): %s", token_id, e)


async def is_revoked(token_id: str) -> bool:
    """token_id 是否在黑名单中。Redis 不可用时返回 False（fail-open）。"""
    try:
        client = await get_redis()
        return bool(await client.exists(_KEY_PREFIX + token_id))
    except Exception as e:
        logger.warning("Redis 查询黑名单失败 (jti=%s): %s", token_id, e)
        return False
