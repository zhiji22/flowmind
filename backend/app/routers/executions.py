"""执行 API：触发工作流执行、查询执行状态、重试失败步骤"""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.models.execution import Execution, ExecutionStatus, StepExecution
from app.models.user import User
from app.models.workflow import Workflow
from app.routers.auth import get_current_user
from app.schemas.execution import ExecutionResponse
from app.services.execution_engine import execute_workflow

router = APIRouter()


async def _run_execution_in_background(execution_id: uuid.UUID) -> None:
    """在独立 session 中执行工作流，避免占用 HTTP request 的 session。"""
    async with async_session() as db:
        await execute_workflow(execution_id, db)


@router.post("/{workflow_id}", response_model=ExecutionResponse)
async def trigger_execution(
    workflow_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    触发工作流执行。

    创建一条 Execution 记录后立即返回，工作流执行在后台进行；
    前端通过 GET /api/executions/{id} 轮询状态。
    """
    # 验证工作流存在且属于当前用户
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == current_user.id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    # 创建执行记录
    execution = Execution(
        workflow_id=workflow_id,
        status=ExecutionStatus.PENDING,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    # 后台执行工作流（不阻塞 HTTP worker）
    background_tasks.add_task(_run_execution_in_background, execution.id)

    return execution


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询执行详情，包含每个步骤的状态"""
    result = await db.execute(
        select(Execution)
        .join(Workflow, Execution.workflow_id == Workflow.id)
        .where(Execution.id == execution_id, Workflow.user_id == current_user.id)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return execution


@router.post("/{execution_id}/retry", response_model=ExecutionResponse)
async def retry_execution(
    execution_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    重试失败的执行：清理 step_executions 后在后台重新执行。
    """
    result = await db.execute(
        select(Execution)
        .join(Workflow, Execution.workflow_id == Workflow.id)
        .where(Execution.id == execution_id, Workflow.user_id == current_user.id)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")

    if execution.status != ExecutionStatus.FAILED:
        raise HTTPException(status_code=400, detail="只能重试失败的工作流")

    # 重置执行状态
    execution.status = ExecutionStatus.PENDING
    execution.finished_at = None
    execution.result = None

    # 清理旧的步骤执行记录，避免重复
    await db.execute(
        delete(StepExecution).where(StepExecution.execution_id == execution.id)
    )
    await db.commit()
    await db.refresh(execution)

    # 后台重新执行
    background_tasks.add_task(_run_execution_in_background, execution.id)

    return execution
