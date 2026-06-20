"""调度管理工具：cron 表达式校验、下次运行时间计算、注册/暂停调度。"""
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Schedule


def is_valid_cron(cron_expr: str) -> bool:
    """校验 5 段 cron 表达式是否合法（分 时 日 月 周）。

    显式拒绝 6/7 段（带秒/年）的表达式：croniter 本身接受这些，
    但项目文档（schema docstring、400 错误信息）都承诺 5 段，
    如果放行会让 LLM 偶尔生成 6 段 cron 后无法被前端正确解析展示。
    """
    if not cron_expr or not isinstance(cron_expr, str):
        return False
    if len(cron_expr.split()) != 5:
        return False
    try:
        croniter(cron_expr, datetime.now(timezone.utc))
        return True
    except Exception:
        return False


def compute_next_run(cron_expr: str, base: datetime | None = None) -> datetime:
    """根据 cron 表达式计算下一次运行时间（UTC）。"""
    base = base or datetime.now(timezone.utc)
    # base 为 tz-aware 时，croniter 返回的 datetime 也是 tz-aware
    return croniter(cron_expr, base).get_next(datetime)


async def upsert_schedule(
    db: AsyncSession,
    workflow_id,
    cron_expr: str,
    enabled: bool = True,
) -> Schedule:
    """创建或更新工作流的调度（Schedule 与 Workflow 是 1:1）。"""
    result = await db.execute(
        select(Schedule).where(Schedule.workflow_id == workflow_id)
    )
    sched = result.scalar_one_or_none()

    next_run = compute_next_run(cron_expr) if enabled else None

    if sched is None:
        sched = Schedule(
            workflow_id=workflow_id,
            cron_expr=cron_expr,
            enabled=enabled,
            next_run=next_run,
        )
        db.add(sched)
    else:
        sched.cron_expr = cron_expr
        sched.enabled = enabled
        sched.next_run = next_run

    await db.flush()
    return sched