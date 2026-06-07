"""执行 API：触发工作流执行、查询执行状态、重试失败步骤"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.execution import Execution, ExecutionStatus
from app.models.user import User
from app.models.workflow import Workflow
from app.routers.auth import get_current_user
from app.schemas.execution import ExecutionResponse
from app.services.execution_engine import execute_workflow

router = APIRouter()


@router.post("/{workflow_id}", response_model=ExecutionResponse)
async def trigger_execution(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    触发工作流执行。

    创建一条 Execution 记录，然后调用执行引擎。
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

    # 执行工作流（当前是同步执行，后续 Step 8 会改为异步）
    await execute_workflow(execution.id, db)

    # 重新加载执行记录（含更新后的状态）
    await db.refresh(execution)
    return execution


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询执行详情，包含每个步骤的状态"""
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
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
    """
    重试失败的执行。

    找到失败的步骤，重置状态，重新执行。
    """
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")

    if execution.status != ExecutionStatus.FAILED:
        raise HTTPException(status_code=400, detail="只能重试失败的工作流")

    # 重置执行状态
    execution.status = ExecutionStatus.PENDING
    execution.finished_at = None
    execution.result = None
    await db.commit()

    # 重新执行
    await execute_workflow(execution.id, db)

    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    return result.scalar_one()