"""pytest 公共 fixtures。"""
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session")
async def client():
    """In-process ASGI 测试客户端（session 级，与 event loop 同生命周期）。

    不监听真实端口，直接驱动 FastAPI app；这样 monkeypatch 对 settings
    的改动能被路由读到（用于测试生产环境禁用逻辑）。

    session 级 + 单 event loop：避免 asyncpg 连接池跨 loop 报
    "Future attached to a different loop"。
    """
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
