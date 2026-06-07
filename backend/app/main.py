from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base
from app.models import User, Workflow, Step, Schedule, Execution, StepExecution, ApprovalRequest
from app.routers import auth as auth_router
from app.routers import chat as chat_router
from app.routers import workflows as workflows_router
from app.routers import executions as executions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="FlowMind API",
    description="AI智能工作流平台",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat_router.router, prefix="/api/chat", tags=["chat"])
app.include_router(workflows_router.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(executions_router.router, prefix="/api/executions", tags=["executions"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "flowmind-api"}
