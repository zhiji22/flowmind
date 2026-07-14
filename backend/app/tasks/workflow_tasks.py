"""Celery 任务定义：

  1. execute_workflow_task(execution_id) —— 运行一条已存在的 Execution
  2. tick_scheduler() —— 每 30s 心跳，扫描到期调度，建 Execution 并入队执行

关键点：Celery 任务是同步函数，但执行引擎/DB 是 async。
为避免 asyncpg 连接跨事件循环的坑，每个任务内用 asyncio.run() 起独立循环，
并用 NullPool + 用后即 dispose 的一次性引擎。

execute_workflow_task 接收 execution_id（而非 workflow_id）：手动触发/重试/
审批恢复由各 router 先建好 Execution 再入队，调度器同理先建 Execution。
统一签名后，前端在触发时拿到的 execution_id 立即可用于轮询。
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.execution import Execution, ExecutionStatus
from app.models.workflow import Schedule, Workflow, WorkflowStatus
from app.services.execution_engine import execute_workflow
from app.services.redis_client import RedisLock
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro_factory):
    """在全新事件循环里运行协程；用一次性 NullPool 引擎，结束即 dispose。

    coro_factory(Session) -> coroutine：接收一个 session 工厂。

    关键：引擎的创建与 dispose 必须在同一个事件循环里，否则 asyncpg
    连接会因绑定的 loop 已关闭而抛 "attached to a different loop"。
    """

    async def _runner():
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            return await coro_factory(session_factory)
        finally:
            await engine.dispose()

    return asyncio.run(_runner())


# ---------------------------------------------------------------------------
# 任务 1：运行一条已存在的 Execution
# ---------------------------------------------------------------------------


async def _execute_workflow_async(session_factory, execution_id: uuid.UUID) -> str:
    """运行一条已存在的 Execution（拓扑排序 + 工具调用 + 审批 + 事件推送）。"""
    async with session_factory() as db:
        await execute_workflow(execution_id, db)
    return str(execution_id)


@celery_app.task(name="flowmind.execute_workflow", bind=True)
def execute_workflow_task(self, execution_id: str) -> str:
    """运行一条已存在的 Execution（手动触发 / 重试 / 审批恢复 / 调度均走此入口）。"""
    try:
        return _run_async(lambda sf: _execute_workflow_async(sf, uuid.UUID(execution_id)))
    except Exception:
        logger.exception("Celery 执行工作流失败: %s", execution_id)
        raise


# ---------------------------------------------------------------------------
# 任务 2：调度心跳（每 30s 由 Beat 触发）
# ---------------------------------------------------------------------------


async def _tick_scheduler_async(session_factory) -> int:
    """扫描所有启用的、到期的调度，建 Execution 并入队执行、更新下次运行时间。

    必须在 RedisLock 保护下运行：beat 每 30s 派发一次，worker 并发=2，
    若某次 tick 超过 30s，下一次 tick 会落到另一个并发槽同时跑，
    导致同一调度被重复入队。
    """
    now = datetime.now(UTC)
    triggered = 0

    async with session_factory() as db:
        result = await db.execute(select(Schedule).where(Schedule.enabled.is_(True)))
        schedules = result.scalars().all()

        for sched in schedules:
            # next_run 为空（刚启用）或已到期 → 触发
            if sched.next_run is not None and sched.next_run > now:
                continue

            # 确认工作流仍是 active 状态
            wf = await db.get(Workflow, sched.workflow_id)
            if wf is None or wf.status != WorkflowStatus.ACTIVE:
                continue

            # 先建 Execution 行并提交，再把 execution_id 入队（与手动触发一致）。
            # 必须在 delay 之前 commit：Celery worker 在独立连接里查询，
            # READ COMMITTED 下未提交的行不可见，否则引擎会因查不到 Execution
            # 而静默 return，导致调度触发的工作流被无声丢弃。
            execution = Execution(
                workflow_id=sched.workflow_id,
                status=ExecutionStatus.PENDING,
            )
            db.add(execution)
            await db.flush()  # 拿到 execution.id

            # 计算并写入下次运行时间（与 Execution 同事务提交，避免重复触发）
            try:
                sched.next_run = croniter(sched.cron_expr, now).get_next(datetime)
            except Exception:
                logger.warning("无效的 cron 表达式，已禁用: %s", sched.cron_expr)
                sched.enabled = False

            await db.commit()  # 提交后 worker 才能看到这行 Execution

            execute_workflow_task.delay(str(execution.id))
            triggered += 1
            logger.info(
                "调度触发: workflow=%s, execution=%s, cron=%s",
                sched.workflow_id,
                execution.id,
                sched.cron_expr,
            )

    return triggered


@celery_app.task(name="flowmind.tick_scheduler")
def tick_scheduler() -> int:
    """调度心跳：扫描到期的工作流并触发执行。返回本次触发数量。

    用 Redis 锁保证同一时刻只有一个 tick 在跑；拿不到锁直接放弃本次
    （下次 beat 会再派发），避免并发 tick 重复入队执行。

    TTL 取 beat 间隔（30s）的 2 倍：单个 tick 偶发慢一次（DB 抖动、调度
    批量到期）不应让下一次 beat 抢到锁并发跑，留出 30s 缓冲足够覆盖。
    """

    async def _with_lock(sf) -> int:
        async with RedisLock("scheduler_tick", ttl=60) as lock:
            if not lock.acquired:
                logger.info("上一次 tick 仍在运行，跳过本次心跳")
                return 0
            return await _tick_scheduler_async(sf)

    try:
        return _run_async(_with_lock)
    except Exception:
        logger.exception("调度器 tick 失败")
        raise
