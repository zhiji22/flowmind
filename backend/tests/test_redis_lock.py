"""RedisLock 的单元测试：用 monkeypatch 替换 get_redis，避免依赖真 Redis。"""
import pytest

from app.services import redis_client
from app.services.redis_client import RedisLock


class _FakeRedis:
    """最小可用的假 Redis，只实现 SET NX EX / eval / delete。

    所有方法都是 async，方便和真实 redis.asyncio 客户端互换。
    """

    def __init__(self, *, key_exists: bool = False) -> None:
        self._store = {} if not key_exists else {"lock:scheduler_tick": "prev-token"}
        self.last_set: dict | None = None

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self._store:
            return None
        self._store[key] = value
        self.last_set = {"key": key, "value": value, "ex": ex}
        return "OK"

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0

    async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        # 模拟 Lua CAS：仅当 value 匹配 token 才删
        if self._store.get(key) == token:
            self._store.pop(key, None)
            return 1
        return 0


@pytest.fixture
def patch_get_redis(monkeypatch):
    """返回一个配置函数，把 get_redis 替换为给定的假客户端。"""
    def _install(fake: _FakeRedis):
        async def _factory():
            return fake
        monkeypatch.setattr(redis_client, "get_redis", _factory)
        return fake
    return _install


class TestRedisLockAcquire:
    async def test_acquire_succeeds_when_key_absent(self, patch_get_redis) -> None:
        fake = patch_get_redis(_FakeRedis())
        async with RedisLock("scheduler_tick", ttl=30) as lock:
            assert lock.acquired is True
            assert fake.last_set == {
                "key": "lock:scheduler_tick",
                "value": lock._token,
                "ex": 30,
            }

    async def test_acquire_fails_when_key_present(self, patch_get_redis) -> None:
        patch_get_redis(_FakeRedis(key_exists=True))
        async with RedisLock("scheduler_tick", ttl=30) as lock:
            assert lock.acquired is False

    async def test_release_cleans_up_key(self, patch_get_redis) -> None:
        fake = patch_get_redis(_FakeRedis())
        async with RedisLock("scheduler_tick") as lock:
            assert lock.acquired is True
        # 退出 with 后，持有的 key 应被 CAS 删除
        assert "lock:scheduler_tick" not in fake._store

    async def test_release_does_not_delete_others_lock(self, patch_get_redis) -> None:
        """临界区执行超过 ttl 后，别的实例拿到了锁；本实例退出不应误删。"""
        fake = patch_get_redis(_FakeRedis(key_exists=False))
        lock = RedisLock("scheduler_tick", ttl=1)
        async with lock:
            # 模拟 ttl 过期 + 另一个实例拿到锁
            fake._store["lock:scheduler_tick"] = "another-owner-token"
        # 退出后另一个实例的锁应仍在
        assert fake._store.get("lock:scheduler_tick") == "another-owner-token"


class TestRedisLockDegraded:
    async def test_falls_back_to_acquired_when_redis_down(self, monkeypatch) -> None:
        """Redis 不可用时，锁降级为 acquired=True，让业务继续跑。"""
        async def _raise():
            raise RuntimeError("redis down")
        monkeypatch.setattr(redis_client, "get_redis", _raise)

        async with RedisLock("any", ttl=5) as lock:
            assert lock.acquired is True  # 降级放行
