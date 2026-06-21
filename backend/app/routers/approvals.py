"""审批 API：列出待审批、通过/拒绝。

通过审批后会把对应 StepExecution 标记为 SUCCESS（或拒绝时 FAILED），
然后再次调用执行引擎从挂起处继续工作流。
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.execution import (
    ApprovalRequest,
    ApprovalStatus,
    Execution,
    ExecutionStatus,
    StepExecution,
    StepExecutionStatus,
)
from app.models.user import User
from app.models.workflow import Step, Workflow
from app.routers.auth import get_current_user
from app.schemas.approval import ApprovalRequestResponse, ApprovalResolveRequest
from app.tasks.workflow_tasks import execute_workflow_task

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


def _to_dict(
    approval: ApprovalRequest,
    workflow: Workflow | None,
    step: Step | None,
) -> dict:
    """把 ApprovalRequest 加上工作流名、步骤类型等上下文，组装为响应 dict。"""
    return {
        "id": approval.id,
        "execution_id": approval.execution_id,
        "step_id": approval.step_id,
        "status": approval.status,
        "requested_at": approval.requested_at,
        "resolved_at": approval.resolved_at,
        "resolver_id": approval.resolver_id,
        "workflow_id": workflow.id if workflow else None,
        "workflow_name": workflow.name if workflow else None,
        "step_type": step.step_type if step else None,
        "step_config": step.config if step else None,
    }


async def _enrich_one(approval: ApprovalRequest, db: AsyncSession) -> dict:
    """单条审批附加上下文（通过/拒绝接口返回时使用）。

    用 join 一次性把 workflow 和 step 取出，避免多次往返。
    """
    result = await db.execute(
        select(Workflow, Step)
        .join(Execution, Execution.workflow_id == Workflow.id)
        .join(Step, Step.id == approval.step_id)
        .where(Execution.id == approval.execution_id)
    )
    row = result.one_or_none()
    workflow, step = row if row else (None, None)
    return _to_dict(approval, workflow, step)


async def _enrich_many(approvals: list[ApprovalRequest], db: AsyncSession) -> list[dict]:
    """批量附加上下文：一次性取出涉及的 Execution/Workflow/Step，避免 N+1 查询。"""
    if not approvals:
        return []

    execution_ids = {a.execution_id for a in approvals}
    step_ids = {a.step_id for a in approvals}

    # 一次性拉所有相关的 (execution_id, workflow)
    exec_rows = await db.execute(
        select(Execution.id, Workflow)
        .join(Workflow, Workflow.id == Execution.workflow_id)
        .where(Execution.id.in_(execution_ids))
    )
    workflow_by_exec: dict = {eid: wf for eid, wf in exec_rows.all()}

    # 一次性拉所有相关的 step
    step_rows = await db.execute(select(Step).where(Step.id.in_(step_ids)))
    step_by_id: dict = {s.id: s for s in step_rows.scalars().all()}

    return [
        _to_dict(
            a,
            workflow_by_exec.get(a.execution_id),
            step_by_id.get(a.step_id),
        )
        for a in approvals
    ]


@router.get("", response_model=list[ApprovalRequestResponse])
async def list_pending_approvals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """列出当前用户工作流中所有待审批请求（含上下文）。"""
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
    approvals = list(result.scalars().all())
    return await _enrich_many(approvals, db)


@router.post("/{approval_id}/approve", response_model=ApprovalRequestResponse)
async def approve(
    approval_id: uuid.UUID,
    body: ApprovalResolveRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """通过审批：将 step 标记为已通过，并通过 Celery 恢复工作流执行。"""
    approval = await _load_user_approval(approval_id, current_user.id, db)

    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail="该审批已被处理")

    # 标记审批通过
    now = datetime.now(UTC)
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
    note = (body.note if body else None) or ""
    if se is not None:
        se.status = StepExecutionStatus.SUCCESS
        se.output_data = {
            "approved": True,
            "resolver_id": str(current_user.id),
            **({"note": note} if note else {}),
        }
        se.finished_at = now

    # 把 execution 重新置为 RUNNING，由后台任务推进
    exe_result = await db.execute(select(Execution).where(Execution.id == approval.execution_id))
    execution = exe_result.scalar_one_or_none()
    if execution is not None and execution.status == ExecutionStatus.WAITING_FOR_APPROVAL:
        execution.status = ExecutionStatus.RUNNING
        execution.result = None

    await db.commit()
    await db.refresh(approval)

    # 通过 Celery 恢复执行（durable）
    execute_workflow_task.delay(str(approval.execution_id))

    return await _enrich_one(approval, db)


@router.post("/{approval_id}/reject", response_model=ApprovalRequestResponse)
async def reject(
    approval_id: uuid.UUID,
    body: ApprovalResolveRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """拒绝审批：审批 step 失败，整个 execution 标记为 FAILED。"""
    approval = await _load_user_approval(approval_id, current_user.id, db)

    if approval.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=400, detail="该审批已被处理")

    now = datetime.now(UTC)
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

    exe_result = await db.execute(select(Execution).where(Execution.id == approval.execution_id))
    execution = exe_result.scalar_one_or_none()
    if execution is not None:
        execution.status = ExecutionStatus.FAILED
        execution.finished_at = now
        execution.result = {"error": note, "rejected_approval_id": str(approval.id)}

    await db.commit()
    await db.refresh(approval)
    return await _enrich_one(approval, db)
