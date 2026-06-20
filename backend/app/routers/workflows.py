"""工作流 API：创建、查询、编辑、删除 + 定时调度管理"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.models.user import User
from app.models.workflow import Workflow, Step, Schedule, WorkflowStatus
from app.routers.auth import get_current_user
from app.schemas.workflow import (
    CreateWorkflowRequest,
    UpdateWorkflowRequest,
    WorkflowResponse,
    WorkflowListResponse,
    ScheduleRequest,
    ScheduleResponse,
    ScheduleToggleResponse,
)
from app.services.llm_client import LLMError
from app.services.scheduler import is_valid_cron, upsert_schedule, compute_next_run
from app.services.workflow_engine import generate_workflow_from_message

router = APIRouter()


async def _load_user_workflow(
    workflow_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Workflow:
    """加载属于当前用户的工作流；不存在则 404。

    预加载 schedule：response schema（WorkflowResponse/WorkflowListResponse）
    会读 cron_expr/schedule_enabled/next_run 计算属性，async 上下文里
    触发 lazy load 会抛 MissingGreenlet。
    """
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.schedule))
        .where(Workflow.id == workflow_id, Workflow.user_id == user_id)
    )
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return workflow


@router.get("", response_model=list[WorkflowListResponse])
async def list_workflows(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的所有工作流（预加载 schedule，便于展示定时状态）"""
    result = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.schedule))
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
    """从自然语言创建工作流：消息 → LLM 生成 DAG → 存库 → 自动注册调度。"""
    try:
        workflow_data = await generate_workflow_from_message(req.message, current_user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LLMError as e:
        raise HTTPException(status_code=503, detail=f"LLM 服务暂时不可用: {e}")

    workflow = Workflow(
        user_id=current_user.id,
        name=workflow_data.get("name", "未命名工作流"),
        description=workflow_data.get("description", ""),
        dag_json=workflow_data,
        status=WorkflowStatus.DRAFT,
    )
    db.add(workflow)
    await db.flush()

    # 为每个步骤创建 Step 记录
    steps_data = workflow_data.get("steps", [])
    for idx, step_data in enumerate(steps_data):
        config = step_data.get("config", {}) or {}
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

    # 检测触发器中的 cron 调度，自动注册定时任务
    for step_data in steps_data:
        if step_data.get("step_type") != "trigger":
            continue
        cfg = step_data.get("config", {}) or {}
        cron = cfg.get("schedule") or cfg.get("cron")
        if cron and is_valid_cron(cron):
            await upsert_schedule(db, workflow.id, cron, enabled=True)
            workflow.status = WorkflowStatus.ACTIVE
            break

    await db.commit()
    # 重新带 schedule 查一次，避免响应序列化时 lazy load 触发 MissingGreenlet
    refreshed = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.schedule))
        .where(Workflow.id == workflow.id)
    )
    return refreshed.scalar_one()


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单个工作流详情"""
    workflow = await _load_user_workflow(workflow_id, current_user.id, db)
    return workflow


def _extract_trigger_cron(dag_json: Any) -> str | None:
    """从 dag_json 中提取 trigger 步骤的 cron 表达式。

    dag_json 实际结构是 dict（含 name/description/steps 等键，与
    generate_workflow_from_message 返回值一致）；为了向后兼容旧的
    "纯 steps 列表"输入，也接受 list。trigger.config.schedule 或
    trigger.config.cron 都视为 cron。返回第一个匹配到的合法 cron，否则 None。
    """
    steps: Any
    if isinstance(dag_json, dict):
        steps = dag_json.get("steps")
    elif isinstance(dag_json, list):
        steps = dag_json
    else:
        return None

    if not isinstance(steps, list):
        return None

    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("step_type") != "trigger":
            continue
        cfg = step.get("config") or {}
        if not isinstance(cfg, dict):
            continue
        cron = cfg.get("schedule") or cfg.get("cron")
        if cron and is_valid_cron(cron):
            return cron
    return None


def _write_cron_to_dag(dag_json: Any, cron_expr: str) -> Any:
    """把 cron 写回 dag_json 中第一个 trigger 步骤的 config.schedule。

    用于 set_schedule / toggle 后让 dag_json 与 Schedule 表保持一致，
    避免"调度真相源分裂"。返回更新后的 dag_json（dict 则原地更新并返回）。

    - dag_json 是 dict → 操作其 steps 列表
    - dag_json 是 list → 直接当作 steps 列表
    - 其它情况 → 原样返回（不抛错，调用方需保证类型）
    """
    if isinstance(dag_json, dict):
        steps = dag_json.get("steps")
        if not isinstance(steps, list):
            return dag_json
    elif isinstance(dag_json, list):
        steps = dag_json
    else:
        return dag_json

    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("step_type") != "trigger":
            continue
        cfg = step.get("config")
        if not isinstance(cfg, dict):
            cfg = {}
            step["config"] = cfg
        cfg["schedule"] = cron_expr
        # cron 是 schedule 的旧别名，一并清掉避免歧义
        cfg.pop("cron", None)
        break

    return dag_json


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: uuid.UUID,
    req: UpdateWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑工作流（名称、描述、DAG）。

    DAG 改动会触发 Schedule 同步：新 DAG 里有合法 cron → upsert Schedule；
    新 DAG 里不再有 cron → 禁用已有 Schedule（保留行，便于审计/恢复）。
    避免 Schedule 表与 DAG 真相源脱节导致"改了 cron 但调度还按旧 cron 跑"。
    """
    workflow = await _load_user_workflow(workflow_id, current_user.id, db)

    if req.name is not None:
        workflow.name = req.name
    if req.description is not None:
        workflow.description = req.description
    if req.dag_json is not None:
        workflow.dag_json = req.dag_json
        # 同步 Schedule：DAG 是调度的真相源之一，避免二者脱节
        new_cron = _extract_trigger_cron(req.dag_json)
        existing_result = await db.execute(
            select(Schedule).where(Schedule.workflow_id == workflow.id)
        )
        existing = existing_result.scalar_one_or_none()

        if new_cron:
            # 保留已有 enabled 状态（用户可能暂停过），只更新 cron + 重算 next_run
            was_enabled = existing.enabled if existing else workflow.status == WorkflowStatus.ACTIVE
            await upsert_schedule(db, workflow.id, new_cron, enabled=was_enabled)
        elif existing:
            # DAG 不再含 cron：禁用 Schedule（不删除，保留历史 cron 方便排查）
            existing.enabled = False
            existing.next_run = None

    await db.commit()
    # 重新带 schedule 查一次，避免响应序列化时 lazy load 触发 MissingGreenlet
    refreshed = await db.execute(
        select(Workflow)
        .options(selectinload(Workflow.schedule))
        .where(Workflow.id == workflow.id)
    )
    return refreshed.scalar_one()


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除工作流（关联的 Schedule 会级联删除）"""
    workflow = await _load_user_workflow(workflow_id, current_user.id, db)
    await db.delete(workflow)
    await db.commit()
    return {"message": "已删除"}


# ---------------------------------------------------------------------------
# 定时调度管理
# ---------------------------------------------------------------------------

@router.post("/{workflow_id}/schedule", response_model=ScheduleResponse)
async def set_schedule(
    workflow_id: uuid.UUID,
    req: ScheduleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """设置/更新工作流的 cron 定时（启用后立即生效，等待下次心跳触发）。

    cron 同时写回 dag_json 的 trigger.config.schedule，保持 Schedule 表
    与 DAG 这两个"调度真相源"一致——否则用户之后任何一次 DAG 编辑都会
    因为 DAG 里没有 cron 而触发已有 Schedule 被禁用。
    """
    workflow = await _load_user_workflow(workflow_id, current_user.id, db)

    if not is_valid_cron(req.cron_expr):
        raise HTTPException(status_code=400, detail="无效的 cron 表达式（应为 5 段：分 时 日 月 周）")

    sched = await upsert_schedule(db, workflow.id, req.cron_expr, enabled=True)
    workflow.status = WorkflowStatus.ACTIVE

    if isinstance(workflow.dag_json, dict):
        # 原地更新；SQLAlchemy 默认不会追踪 JSON 字段内部变更，需显式标记脏
        _write_cron_to_dag(workflow.dag_json, req.cron_expr)
        flag_modified(workflow, "dag_json")

    await db.commit()
    await db.refresh(sched)
    return sched


@router.post("/{workflow_id}/schedule/toggle", response_model=ScheduleToggleResponse)
async def toggle_schedule(
    workflow_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """暂停/恢复定时调度，并同步工作流状态（active ↔ paused）。"""
    workflow = await _load_user_workflow(workflow_id, current_user.id, db)

    result = await db.execute(
        select(Schedule).where(Schedule.workflow_id == workflow.id)
    )
    sched = result.scalar_one_or_none()
    if not sched:
        raise HTTPException(status_code=400, detail="该工作流未配置定时调度")

    sched.enabled = not sched.enabled
    sched.next_run = compute_next_run(sched.cron_expr) if sched.enabled else None
    workflow.status = WorkflowStatus.ACTIVE if sched.enabled else WorkflowStatus.PAUSED

    await db.commit()
    await db.refresh(sched)

    return ScheduleToggleResponse(
        enabled=sched.enabled,
        cron_expr=sched.cron_expr,
        next_run=sched.next_run,
        workflow_status=workflow.status,
    )
