import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import engine, Base
from app.services.llm_client import close_client
from app.models import User, Workflow, Step, Schedule, Execution, StepExecution, ApprovalRequest  # noqa: F401
from app.routers import approvals as approvals_router
from app.routers import auth as auth_router
from app.routers import chat as chat_router
from app.routers import executions as executions_router
from app.routers import workflows as workflows_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    await close_client()


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


# ---------------------------------------------------------------------------
# 全局异常 handler：未捕获异常统一返回 500，并记录 request_id 便于排查
# ---------------------------------------------------------------------------

@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Unhandled exception (request_id=%s, path=%s)",
            request_id,
            request.url.path,
        )
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
