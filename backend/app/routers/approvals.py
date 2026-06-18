"""审批 API：列出待审批、通过/拒绝。

通过审批后会把对应 StepExecution 标记为 SUCCESS（或拒绝时 FAILED），
然后再次调用执行引擎从挂起处继续工作流。
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.models.execution import (
    ApprovalRequest,
    ApprovalStatus,
    Execution,
    ExecutionStatus,
    StepExecution,
    StepExecutionStatus,
)
from app.models.user import User
from app.models.workflow import Workflow
from app.routers.auth import get_current_user
from app.schemas.approval import ApprovalRequestResponse, ApprovalResolveRequest
from app.services.execution_engine import execute_workflow

router = APIRouter()


async def _load_user_approval(
    approval_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> ApprovalRequest:
    """加载属于当前用户的审批请求；不存在则 404。"""
    result = await db.execute(
        select(ApprovalRequest)
        .join(Execution, ApprovalRequest.execution_id == Execution.id)
        .join(Workflow, Execution.workflow_id == Workflow.id)
        .where(ApprovalRequest.id == approval_id, Workflow.user_id == user_id)
    )
    approval = result.scalar_one_or_none()
    if not approval:
        raise HTTPException(status_code=404, detail="审批请求不存在")
    return approval


@router.get("", response_model=list[ApprovalRequestResponse])
async def list_pending_approvals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalRequest]:
    """列出当前用户工作流中所有待审批请求。"""
    result = await db.execute(
        select(ApprovalRequest)
        .join(Execution, ApprovalRequest.execution_id == Execution.id)
        .join(Workflow, Execution.workflow_id == Workflow.id)
        .where(
            Workflow.user_id == current_user.id,
            ApprovalRequest.status == ApprovalStatus.PENDING,
        )
        .order_by(ApprovalRequest.requested_at.desc())
    )
    return list(result.scalars().all())


async def _resume_execution_in_background(execution_id: uuid.UUID) -> None:
    """开新 session 调用执行引擎；避免与 HTTP request session 互相干扰。"""
    async with async_session() as db:
        await execute_workflow(execution_id, db)


@router.post("/{approval_id}/approve", response_model=ApprovalRequestResponse)
async def approve(
    approval_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _body: ApprovalResolveRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequest:
    """通过审批：将 step 标记为已通过，并在后台恢复工作流执行。"""
    approval = await _load_user_approval(approval_id, current_user.id, db)

    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail="该审批已被处理")

    # 标记审批通过
    now = datetime.now(timezone.utc)
    approval.status = ApprovalStatus.APPROVED
    approval.resolved_at = now
    approval.resolver_id = current_user.id

    # 找到对应 StepExecution，标记 approved=True，让 execution_engine 跳过它
    se_result = await db.execute(
        select(StepExecution).where(
            StepExecution.execution_id == approval.execution_id,
            StepExecution.step_id == approval.step_id,
        )
    )
    se = se_result.scalar_one_or_none()
    if se is not None:
        se.status = StepExecutionStatus.SUCCESS
        se.output_data = {"approved": True, "resolver_id": str(current_user.id)}
        se.finished_at = now

    # 把 execution 重新置为 RUNNING，由后台任务推进
    exe_result = await db.execute(
        select(Execution).where(Execution.id == approval.execution_id)
    )
    execution = exe_result.scalar_one_or_none()
    if execution is not None and execution.status == ExecutionStatus.WAITING_FOR_APPROVAL:
        execution.status = ExecutionStatus.RUNNING
        execution.result = None

    await db.commit()
    await db.refresh(approval)

    # 后台恢复执行
    background_tasks.add_task(_resume_execution_in_background, approval.execution_id)

    return approval


@router.post("/{approval_id}/reject", response_model=ApprovalRequestResponse)
async def reject(
    approval_id: uuid.UUID,
    body: ApprovalResolveRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequest:
    """拒绝审批：审批 step 失败，整个 execution 标记为 FAILED。"""
    approval = await _load_user_approval(approval_id, current_user.id, db)

    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail="该审批已被处理")

    now = datetime.now(timezone.utc)
    approval.status = ApprovalStatus.REJECTED
    approval.resolved_at = now
    approval.resolver_id = current_user.id

    se_result = await db.execute(
        select(StepExecution).where(
            StepExecution.execution_id == approval.execution_id,
            StepExecution.step_id == approval.step_id,
        )
    )
    se = se_result.scalar_one_or_none()
    note = (body.note if body else None) or "审批被拒绝"
    if se is not None:
        se.status = StepExecutionStatus.FAILED
        se.error_message = note
        se.finished_at = now

    exe_result = await db.execute(
        select(Execution).where(Execution.id == approval.execution_id)
    )
    execution = exe_result.scalar_one_or_none()
    if execution is not None:
        execution.status = ExecutionStatus.FAILED
        execution.finished_at = now
        execution.result = {"error": note, "rejected_approval_id": str(approval.id)}

    await db.commit()
    await db.refresh(approval)
    return approval
