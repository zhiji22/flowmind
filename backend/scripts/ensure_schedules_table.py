"""老数据库补 schedules 表（项目无 Alembic，靠 CREATE TABLE IF NOT EXISTS 兜底）。

用法::

    python -m scripts.ensure_schedules_table

背景：新部署依赖 main.py 的 Base.metadata.create_all 自动建表；但
对已经存在的生产库，create_all 只会补缺失的表，不会修改已有表，
schedules 表若缺失会让 set_schedule 直接 500。此脚本以幂等 DDL
补上该表，安全可重复执行。
"""
import asyncio

from sqlalchemy import text

from app.database import engine


_DDL = """
CREATE TABLE IF NOT EXISTS schedules (
    id          UUID PRIMARY KEY,
    workflow_id UUID NOT NULL UNIQUE REFERENCES workflows(id) ON DELETE CASCADE,
    cron_expr   VARCHAR(100) NOT NULL,
    next_run    TIMESTAMPTZ,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE
);
"""


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text(_DDL))
    await engine.dispose()
    print("OK: schedules 表已就绪")


if __name__ == "__main__":
    asyncio.run(main())
