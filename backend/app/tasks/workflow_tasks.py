"""Celery 任务定义：

  1. execute_workflow_task(workflow_id) —— 执行单个工作流
  2. tick_scheduler() —— 每 30s 心跳，扫描到期调度并入队执行

关键点：Celery 任务是同步函数，但执行引擎/DB 是 async。
为避免 asyncpg 连接跨事件循环的坑，每个任务内用 asyncio.run() 起独立循环，
并用 NullPool + 用后即 dispose 的一次性引擎。
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
# 任务 1：执行工作流
# ---------------------------------------------------------------------------


async def _execute_workflow_async(session_factory, workflow_id: uuid.UUID) -> str:
    """创建执行记录并运行工作流，返回 execution_id。

    执行前再次校验工作流存在且非删除态，避免调度派发与用户删除之间的竞态
    导致 Execution 因外键级联而插入失败/产生孤儿任务。
    """
    async with session_factory() as db:
        wf = await db.get(Workflow, workflow_id)
        if wf is None:
            logger.warning("调度触发的工作流已不存在，跳过: %s", workflow_id)
            return ""

        execution = Execution(
            workflow_id=workflow_id,
            status=ExecutionStatus.PENDING,
        )
        db.add(execution)
        await db.commit()
        await db.refresh(execution)
        exec_id = execution.id
        # 复用现有执行引擎（拓扑排序 + 工具调用 + 审批 + 事件推送）
        await execute_workflow(exec_id, db)
    return str(exec_id)


@celery_app.task(name="flowmind.execute_workflow", bind=True)
def execute_workflow_task(self, workflow_id: str) -> str:
    """执行单个工作流（被调度器或手动触发）。"""
    try:
        return _run_async(lambda sf: _execute_workflow_async(sf, uuid.UUID(workflow_id)))
    except Exception:
        logger.exception("Celery 执行工作流失败: %s", workflow_id)
        raise


# ---------------------------------------------------------------------------
# 任务 2：调度心跳（每 30s 由 Beat 触发）
# ---------------------------------------------------------------------------


async def _tick_scheduler_async(session_factory) -> int:
    """扫描所有启用的、到期的调度，入队执行并更新下次运行时间。

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

            # 入队执行（异步分发到 worker）
            execute_workflow_task.delay(str(sched.workflow_id))
            triggered += 1
            logger.info("调度触发: workflow=%s, cron=%s", sched.workflow_id, sched.cron_expr)

            # 计算并写入下次运行时间
            try:
                sched.next_run = croniter(sched.cron_expr, now).get_next(datetime)
            except Exception:
                logger.warning("无效的 cron 表达式，已禁用: %s", sched.cron_expr)
                sched.enabled = False

        await db.commit()

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
