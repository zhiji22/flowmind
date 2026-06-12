"""工作流 API：创建、查询、编辑、删除工作流"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.workflow import Workflow, Step, WorkflowStatus
from app.routers.auth import get_current_user
from app.schemas.workflow import (
    CreateWorkflowRequest,
    UpdateWorkflowRequest,
    WorkflowResponse,
    WorkflowListResponse,
)
from app.services.workflow_engine import generate_workflow_from_message

router = APIRouter()


@router.get("", response_model=list[WorkflowListResponse])
async def list_workflows(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的所有工作流"""
    result = await db.execute(
        select(Workflow)
        .where(Workflow.user_id == current_user.id)
        .order_by(Workflow.updated_at.desc())
    )

    return result.scalars().all()


@router.post("", response_model=WorkflowResponse)
async def create_workflow(
    req: CreateWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    从自然语言创建工作流。

    流程：用户消息 → LLM 生成 DAG → 解析验证 → 存入数据库
    """
    # 调用 LLM 生成工作流结构
    try:
        workflow_data = await generate_workflow_from_message(req.message, current_user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 创建 Workflow 记录
    workflow = Workflow(
        user_id=current_user.id,
        name=workflow_data.get("name", "未命名工作流"),
        description=workflow_data.get("description", ""),
        dag_json=workflow_data,
        status=WorkflowStatus.DRAFT,
    )
    db.add(workflow)
    await db.flush()  # 先 flush 拿到 workflow.id

    # 为每个步骤创建 Step 记录
    steps_data = workflow_data.get("steps", [])
    for idx, step_data in enumerate(steps_data):
        config = step_data.get("config", {})
        # 把 next 关系也存进 config，执行引擎会读取
        config["next"] = step_data.get("next", [])
        config["next_yes"] = step_data.get("next_yes", [])
        config["next_no"] = step_data.get("next_no", [])

        step = Step(
            workflow_id=workflow.id,
            step_type=step_data.get("step_type", "tool"),
            tool_name=step_data.get("tool_name"),
            config=config,
            position=step_data.get("position"),
            order=idx,
        )
        db.add(step)

    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个工作流详情"""
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == current_user.id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return workflow


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: uuid.UUID,
    req: UpdateWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑工作流（名称、描述、DAG）"""
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == current_user.id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    # 只更新传入的字段
    if req.name is not None:
        workflow.name = req.name
    if req.description is not None:
        workflow.description = req.description
    if req.dag_json is not None:
        workflow.dag_json = req.dag_json

    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除工作流"""
    result = await db.execute(
        select(Workflow).where(Workflow.id == workflow_id, Workflow.user_id == current_user.id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")

    await db.delete(workflow)
    await db.commit()
    return {"message": "已删除"}





