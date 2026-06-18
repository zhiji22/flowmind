"""DEV 专用 /reset-password 接口测试。"""
import pytest
from sqlalchemy import delete

from app.config import settings
from app.database import async_session
from app.models.user import User

# 所有测试共享 session 级 event loop，避免 asyncpg 连接池跨 loop 报错
pytestmark = pytest.mark.asyncio(loop_scope="session")

TEST_EMAIL = "reset_test@example.com"
OLD_PW = "OldPass123!"
NEW_PW = "NewPass999!"


async def _cleanup(email: str) -> None:
    async with async_session() as s:
        await s.execute(delete(User).where(User.email == email))
        await s.commit()


async def test_reset_password_success(client):
    """重置成功后：新密码可登录，旧密码失效。"""
    await _cleanup(TEST_EMAIL)  # 防止历史残留导致注册 400
    r = await client.post(
        "/api/auth/register", json={"email": TEST_EMAIL, "password": OLD_PW}
    )
    assert r.status_code == 200, r.text
    try:
        # 前置：旧密码可登录
        assert (
            await client.post(
                "/api/auth/login", json={"email": TEST_EMAIL, "password": OLD_PW}
            )
        ).status_code == 200

        # 重置
        r2 = await client.post(
            "/api/auth/reset-password",
            json={"email": TEST_EMAIL, "new_password": NEW_PW},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json() == {"message": "密码已重置"}

        # 新密码可登录
        assert (
            await client.post(
                "/api/auth/login", json={"email": TEST_EMAIL, "password": NEW_PW}
            )
        ).status_code == 200

        # 旧密码失效
        assert (
            await client.post(
                "/api/auth/login", json={"email": TEST_EMAIL, "password": OLD_PW}
            )
        ).status_code == 401
    finally:
        await _cleanup(TEST_EMAIL)


async def test_reset_password_user_not_found(client):
    """重置不存在的用户 → 404。"""
    r = await client.post(
        "/api/auth/reset-password",
        json={"email": "no_such_user@example.com", "new_password": NEW_PW},
    )
    assert r.status_code == 404


async def test_reset_password_weak_password_rejected(client):
    """新密码短于 8 位 → schema 校验 422（不触及路由逻辑）。"""
    r = await client.post(
        "/api/auth/reset-password",
        json={"email": TEST_EMAIL, "new_password": "123"},
    )
    assert r.status_code == 422


async def test_reset_password_disabled_in_production(client, monkeypatch):
    """生产环境（APP_ENV=production）→ 接口禁用，返回 404。"""
    monkeypatch.setattr(settings, "APP_ENV", "production")
    r = await client.post(
        "/api/auth/reset-password",
        json={"email": TEST_EMAIL, "new_password": NEW_PW},
    )
    assert r.status_code == 404


@pytest.mark.parametrize(
    "env, expected_live",
    [
        ("development", True),
        ("test", True),
        ("production", False),
        ("staging", False),
        ("", False),
        ("PRODUCTION", False),  # 大小写：不应被当作可放行值
        ("dev-typo", False),
    ],
)
async def test_env_gate_fail_closed(client, monkeypatch, env, expected_live):
    """环境闸门 fail-closed：仅 development/test 放行，其余一律 404。"""
    monkeypatch.setattr(settings, "APP_ENV", env)
    r = await client.post(
        "/api/auth/reset-password",
        json={"email": "gate_probe@example.com", "new_password": NEW_PW},
    )
    assert r.status_code == 404
    if expected_live:
        # 放行：走路由逻辑，对不存在用户返回“用户不存在”
        assert r.json()["detail"] == "用户不存在"
    else:
        # 拦截：被闸门挡下，返回 “Not Found”
        assert r.json()["detail"] == "Not Found"
