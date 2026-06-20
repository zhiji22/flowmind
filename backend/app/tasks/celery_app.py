"""Celery 应用：异步任务队列 + 定时调度。

  - broker / backend 都用 Redis
  - Beat 每 30s 触发一次调度心跳（tick_scheduler）
  - 任务在 worker 进程中执行（与 api 进程隔离）
"""
from app.config import settings
from celery import Celery # pyright: ignore[reportMissingImports]


# include 确保任务模块被导入、任务名被注册
celery_app = Celery(
    "flowmind",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.workflow_tasks"],
)

celery_app.conf.update(
    # 序列化
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # 时区统一UTC（与数据库一致）
    timezone="UTC",
    enable_utc=True,
    # 启动时重试连接 broker（Redis 未就绪时不崩）
    broker_connection_retry_on_startup=True,
    # 任务结果保留时间（1 天后自动清理）
    result_expires=86400,
)

# Beat 定时任务表：每 30 秒扫描一次到期的工作流
celery_app.conf.beat_schedule = {
    "scheduler-tick": {
        "task": "flowmind.tick_scheduler",
        "schedule": 30.0,
    },
}