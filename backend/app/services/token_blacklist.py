"""Token 黑名单：登出后让 token 在剩余有效期内失效。

简单内存实现：
  - 单进程内有效（多 worker / 重启会丢失，但 token 自身有 exp，最坏情况是被盗 token 在过期前仍可用）
  - 生产环境应改为 Redis（Set + TTL 过期），接口保持一致即可平滑切换
"""
import time
from threading import Lock
from typing import Final

_lock = Lock()
# jti / token_hash -> 该条目何时过期（Unix 秒）；过期后由 _gc 清理
_blacklist: dict[str, float] = {}

# 每多少次 add 触发一次 GC
_GC_EVERY: Final[int] = 64
_gc_counter = 0


def _gc_locked() -> None:
    now = time.time()
    expired = [k for k, exp in _blacklist.items() if exp <= now]
    for k in expired:
        _blacklist.pop(k, None)


def revoke(token_id: str, expires_at_unix: float) -> None:
    """把 token_id 加入黑名单，直到 expires_at_unix。"""
    global _gc_counter
    with _lock:
        _blacklist[token_id] = expires_at_unix
        _gc_counter += 1
        if _gc_counter % _GC_EVERY == 0:
            _gc_locked()


def is_revoked(token_id: str) -> bool:
    with _lock:
        exp = _blacklist.get(token_id)
        if exp is None:
            return False
        if exp <= time.time():
            _blacklist.pop(token_id, None)
            return False
        return True
