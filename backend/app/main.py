import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import Base, engine
from app.limiter import limiter
from app.logging_config import configure_logging
from app.models import (  # noqa: F401
    ApprovalRequest,
    Execution,
    Schedule,
    Step,
    StepExecution,
    User,
    Workflow,
)
from app.routers import approvals as approvals_router
from app.routers import auth as auth_router
from app.routers import chat as chat_router
from app.routers import executions as executions_router
from app.routers import workflows as workflows_router
from app.services.llm_client import close_client
from app.services.redis_client import close_redis

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：初始化结构化日志
    configure_logging()
    logger.info("应用启动", env=settings.APP_ENV)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

    # 关闭：优雅释放连接（DB、LLM、Redis）
    logger.info("应用关闭中，开始释放资源")
    await engine.dispose()
    await close_client()
    await close_redis()
    logger.info("资源已释放，应用已停止")


app = FastAPI(
    title="FlowMind API",
    description="AI智能工作流平台",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# 限流：注册 limiter + 429 处理器（具体限额在各端点用 @limiter.limit 装饰）
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# 全局异常 handler：未捕获异常统一返回 500，并记录 request_id 便于排查
# ---------------------------------------------------------------------------


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    # 绑定到日志上下文，本次请求内所有日志自动带 request_id
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_exception", path=request.url.path, request_id=request_id)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "服务器内部错误",
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )
    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat_router.router, prefix="/api/chat", tags=["chat"])
app.include_router(workflows_router.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(executions_router.router, prefix="/api/executions", tags=["executions"])
app.include_router(approvals_router.router, prefix="/api/approvals", tags=["approvals"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "flowmind-api"}
