"""结构化日志配置（structlog）。

设计要点：
  - 统一接管 stdlib logging，现有 `logging.getLogger(__name__)` 无需改动即输出结构化日志
  - 开发环境：彩色控制台（可读）
  - 生产环境：JSON（便于 ELK / Loki 采集，含 request_id 等字段）
  - 通过 contextvars 注入 request_id / user_id，每条日志自动带上
"""

import logging

import structlog

from app.config import settings


def configure_logging() -> None:
    """初始化全局日志（在应用启动时调用一次）。"""
    is_prod = settings.APP_ENV == "production"

    # 所有 logger 共享的预处理链
    shared_processors = [
        # 合并 contextvars（request_id 等由此进入日志）
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # 配置 structlog 自身的 logger（structlog.get_logger()）
    structlog.configure(
        processors=shared_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 把 stdlib logging 的记录也用同一套处理器渲染
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            # 生产 JSON，开发彩色控制台
            structlog.processors.JSONRenderer()
            if is_prod
            else structlog.dev.ConsoleRenderer(colors=True),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers[:] = [handler]  # 替换默认 handler
    # 生产 INFO，开发 DEBUG
    root.setLevel(logging.DEBUG if not is_prod else logging.INFO)

    # 降低第三方库的噪音
    for noisy in ("uvicorn.access", "httpx", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
