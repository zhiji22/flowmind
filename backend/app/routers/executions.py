"""执行 API：触发执行、查询状态、重试。

执行通过 Celery 任务队列进行（durable：worker 回收/重启不丢失任务），
并发安全由执行引擎内的 advisory lock 保证（见 execution_engine）。
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.execution import ApprovalRequest, Execution, ExecutionStatus, StepExecution
from app.models.user import User
from app.models.workflow import Workflow
from app.routers.auth import get_current_user
from app.schemas.execution import ExecutionResponse
from app.tasks.workflow_tasks import execute_workflow_task

router = APIRouter()


@router.post("/{workflow_id}", response_model=ExecutionResponse)
async def trigger_execution(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    触发工作流执行。

    创建一条 Execution 记录后立即返回，实际执行通过 Celery 任务异步进行；
    前端通过 GET /api/executions/{id} 轮询状态。
    """
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == current_user.id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    execution = Execution(
        workflow_id=workflow_id,
        status=ExecutionStatus.PENDING,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    # 丢给 Celery worker 执行（durable，不随 HTTP worker 生命周期消失）
    execute_workflow_task.delay(str(execution.id))

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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重试失败的执行：清理 step_executions 后通过 Celery 重新执行。"""
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

    execution.status = ExecutionStatus.PENDING
    execution.finished_at = None
    execution.result = None

    # 清理旧的步骤执行记录与待审批记录，避免重复执行 / 审批恢复时命中残留的 PENDING 审批而死锁
    await db.execute(delete(StepExecution).where(StepExecution.execution_id == execution.id))
    await db.execute(delete(ApprovalRequest).where(ApprovalRequest.execution_id == execution.id))
    await db.commit()
    await db.refresh(execution)

    execute_workflow_task.delay(str(execution.id))

    return execution
