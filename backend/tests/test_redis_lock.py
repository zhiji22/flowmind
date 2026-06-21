"""RedisLock 的单元测试：用 monkeypatch 替换 get_redis，避免依赖真 Redis。"""
import asyncio
import logging

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


class _LoopBoundFakeRedis:
    """模拟真实 redis.asyncio：客户端绑定到创建时的 event loop。

    redis.asyncio 的连接池在首次使用时绑定到当前 loop；loop 一关闭，
    在别的 loop 上复用同一客户端会抛 RuntimeError('Event loop is closed')。
    本类复刻这一行为，并通过类级 _store 模拟「所有客户端共享同一台
    Redis 服务器」。
    """

    _store: dict[str, str] = {}

    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()

    def _guard(self) -> None:
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError("Event loop is closed")

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        self._guard()
        if nx and key in self._store:
            return None
        self._store[key] = value
        return "OK"

    async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        self._guard()
        if self._store.get(key) == token:
            self._store.pop(key, None)
            return 1
        return 0

    async def aclose(self) -> None:
        self._guard()


class TestRedisLockAcrossEventLoops:
    """复现 Celery 执行模型：每个任务都在独立的 asyncio.run() loop 里跑。

    全局 Redis 单例一旦绑定到已关闭的 loop，后续每次 acquire 都会抛
    'Event loop is closed' 并被降级吞掉——锁永远"成功"，互斥保护形同虚设。
    get_redis 必须能在 loop 切换后自动重建客户端。

    注意：本用例是同步函数，内部用 asyncio.run() 主动起多条独立 loop，
    与 pytest-asyncio 的 session loop 隔离开。
    """

    @pytest.fixture(autouse=True)
    def _patch_from_url(self, monkeypatch):
        """把 redis.from_url 换成 loop-bound 假客户端，并重置全局单例。"""
        _LoopBoundFakeRedis._store.clear()
        monkeypatch.setattr(
            redis_client.redis,
            "from_url",
            lambda *a, **k: _LoopBoundFakeRedis(),
        )
        monkeypatch.setattr(redis_client, "_client", None, raising=False)
        monkeypatch.setattr(redis_client, "_client_loop", None, raising=False)
        yield

    def test_lock_works_across_consecutive_event_loops(self, caplog) -> None:
        async def _acquire_and_release():
            async with RedisLock("scheduler_tick", ttl=30) as lock:
                assert lock.acquired is True
            # 正常退出后 key 必须被 CAS 释放
            assert "lock:scheduler_tick" not in _LoopBoundFakeRedis._store

        with caplog.at_level(logging.WARNING, logger="app.services.redis_client"):
            # 模拟 beat 连续派发 3 个 tick，各自落在独立 loop
            for _ in range(3):
                asyncio.run(_acquire_and_release())

        messages = [r.getMessage() for r in caplog.records]
        assert not any(
            "加锁失败" in m or "释放锁失败" in m for m in messages
        ), f"跨 loop 使用 Redis 时出现降级警告: {messages}"


class TestCloseRedis:
    """close_redis 的清理行为：正常关闭 + loop 已关闭时不抛。"""

    async def test_close_resets_client_and_loop(self, monkeypatch) -> None:
        class _FakeClient:
            def __init__(self) -> None:
                self.closed = False

            async def aclose(self) -> None:
                self.closed = True

        fake = _FakeClient()
        monkeypatch.setattr(redis_client, "_client", fake)
        monkeypatch.setattr(redis_client, "_client_loop", object())

        await redis_client.close_redis()

        assert fake.closed is True
        assert redis_client._client is None
        assert redis_client._client_loop is None

    async def test_close_swallows_loop_closed_error(self, monkeypatch) -> None:
        """绑定的 loop 已关闭时，aclose 抛错也不应让 close_redis 失败。"""

        class _BrokenClient:
            async def aclose(self) -> None:
                raise RuntimeError("Event loop is closed")

        monkeypatch.setattr(redis_client, "_client", _BrokenClient())
        monkeypatch.setattr(redis_client, "_client_loop", object())

        await redis_client.close_redis()  # 不应抛
        assert redis_client._client is None
        assert redis_client._client_loop is None
