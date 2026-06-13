"""
执行引擎：负责执行工作流 DAG。

核心流程：
  1. 从数据库加载工作流 DAG（JSON 格式的步骤列表）
  2. 拓扑排序确定执行顺序（保证依赖关系）
  3. 逐步执行每个节点：
     - trigger: 跳过（仅作为入口标记）
     - tool: 调用对应工具，记录输入输出
     - condition: 根据上一步结果判断走哪个分支
     - approval: 暂停执行，等待人工审批
  4. 更新 Execution 和 StepExecution 的状态
  5. 支持失败重试：失败的步骤可以重新执行
"""
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Execution, StepExecution, ExecutionStatus, StepExecutionStatus
from app.models.workflow import Step
from app.tools.base import registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 常量定义
# ---------------------------------------------------------------------------

MSG_TRIGGER_SUCCESS = "工作流触发成功"
MSG_WORKFLOW_COMPLETE = "工作流执行完成"
MSG_WORKFLOW_CYCLE = "工作流包含循环依赖，无法执行"
MSG_STEP_FAILED = "步骤执行失败"
MSG_TOOL_NOT_FOUND = "工具不存在"


# ---------------------------------------------------------------------------
# TypedDict 类型定义
# ---------------------------------------------------------------------------

class StepConfigDict(TypedDict, total=False):
    """步骤配置字典类型"""
    next: list[str]
    next_yes: list[str]
    next_no: list[str]
    field: str
    operator: str
    value: str


class StepDict(TypedDict, total=False):
    """步骤字典类型"""
    id: str
    step_type: str
    tool_name: str | None
    config: StepConfigDict
    next: list[str]
    next_yes: list[str]
    next_no: list[str]


# ---------------------------------------------------------------------------
# 拓扑排序
# ---------------------------------------------------------------------------

def _topological_sort(steps: list[StepDict]) -> list[StepDict]:
    """
    拓扑排序：根据步骤之间的依赖关系，确定一个合法的执行顺序。
    保证每一步在它依赖的步骤之后执行。
    """
    step_map = {s["id"]: s for s in steps}

    # 计算每个节点的入度（有多少前置步骤依赖它）
    in_degree: dict[str, int] = {s["id"]: 0 for s in steps}
    for step in steps:
        next_ids = step.get("next", []) + step.get("next_yes", []) + step.get("next_no", [])
        for nid in next_ids:
            if nid in in_degree:
                in_degree[nid] += 1

    queue = deque(sid for sid, deg in in_degree.items() if deg == 0)
    result = []

    while queue:
        current_id = queue.popleft()
        if current_id in step_map:
            result.append(step_map[current_id])

        step = step_map[current_id]
        next_ids = step.get("next", []) + step.get("next_yes", []) + step.get("next_no", [])
        for nid in next_ids:
            if nid in in_degree:
                in_degree[nid] -= 1
                if in_degree[nid] == 0:
                    queue.append(nid)

    return result


# ---------------------------------------------------------------------------
# 辅助：解析已完成的步骤输出
# ---------------------------------------------------------------------------

def _resolve_step_outputs(step_executions: list[StepExecution]) -> dict[str, Any]:
    """
    将已完成的步骤执行结果整理为 { step_id: output_data } 的字典，
    供后续步骤引用前一步的结果（如条件判断）。
    """
    outputs = {}
    for se in step_executions:
        if se.status == StepExecutionStatus.SUCCESS and se.output_data:
            outputs[str(se.step_id)] = se.output_data
    return outputs


# ---------------------------------------------------------------------------
# 从 DB Step 记录构建 DAG 字典列表
# ---------------------------------------------------------------------------

def _build_dag_steps(db_steps: list[Step]) -> list[dict]:
    """把数据库中的 Step 记录转为 DAG JSON 格式。"""
    dag_steps = []
    for s in db_steps:
        config = s.config or {}
        dag_steps.append({
            "id": str(s.id),
            "step_type": s.step_type,
            "tool_name": s.tool_name,
            "config": config,
            "next": config.get("next", []),
            "next_yes": config.get("next_yes", []),
            "next_no": config.get("next_no", []),
        })
    return dag_steps


# ---------------------------------------------------------------------------
# 单步执行：trigger
# ---------------------------------------------------------------------------

async def _execute_trigger_step(
    se: StepExecution,
) -> None:
    """trigger 类型仅作为入口标记，直接记录成功。"""
    now = datetime.now(timezone.utc)
    se.status = StepExecutionStatus.SUCCESS
    se.started_at = now
    se.finished_at = now
    se.output_data = {"message": MSG_TRIGGER_SUCCESS}


# ---------------------------------------------------------------------------
# 单步执行：tool
# ---------------------------------------------------------------------------

async def _execute_tool_step(
    step: dict,
    se: StepExecution,
    db: AsyncSession,
) -> bool:
    """
    调用注册的工具执行。

    Returns:
        True 表示应继续执行后续步骤，False 表示应终止工作流。
    """
    se.status = StepExecutionStatus.RUNNING
    se.started_at = datetime.now(timezone.utc)
    await db.commit()

    tool_name = step.get("tool_name", "")
    config = step.get("config", {})
    tool = registry.get(tool_name)

    if not tool:
        se.status = StepExecutionStatus.FAILED
        se.error_message = f"{MSG_TOOL_NOT_FOUND}: '{tool_name}'"
        se.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return False

    try:
        # 只传递工具声明的参数，忽略多余 key
        allowed_keys = set(tool.get_parameters_schema().get("properties", {}).keys())
        filtered_config = {k: v for k, v in config.items() if k in allowed_keys}
        tool_result = await tool.execute(**filtered_config)
        se.status = StepExecutionStatus.SUCCESS
        se.output_data = {"result": tool_result}
    except Exception as e:
        se.status = StepExecutionStatus.FAILED
        se.error_message = str(e)
        se.finished_at = datetime.now(timezone.utc)
        await db.commit()
        return False

    se.finished_at = datetime.now(timezone.utc)
    await db.commit()
    return True


# ---------------------------------------------------------------------------
# 单步执行：condition
# ---------------------------------------------------------------------------

async def _execute_condition_step(
    step: dict,
    se: StepExecution,
    step_exec_map: dict[str, StepExecution],
    step_map: dict[str, dict],
    db: AsyncSession,
) -> None:
    """根据前一步输出结果判断走哪个分支。"""
    se.status = StepExecutionStatus.RUNNING
    se.started_at = datetime.now(timezone.utc)
    await db.commit()

    config = step.get("config", {})
    condition_field = config.get("field", "")
    operator = config.get("operator", "contains")
    expected = config.get("value", "")

    # 获取前一步的输出结果
    all_se = list(step_exec_map.values())
    outputs = _resolve_step_outputs(all_se)
    actual_value = ""

    if condition_field.startswith("$"):
        parts = condition_field[1:].split(".")  # 只移除第一个 $ 符号
        ref_step_id = parts[0]
        if ref_step_id in outputs and len(parts) > 1:
            actual_value = str(outputs[ref_step_id].get(parts[1], ""))

    # 条件判断
    if operator == "contains":
        condition_met = expected in actual_value
    elif operator == "equals":
        condition_met = expected == actual_value
    elif operator == "gt":
        try:
            condition_met = float(actual_value) > float(expected)
        except (ValueError, TypeError):
            condition_met = False
    else:
        condition_met = False

    se.status = StepExecutionStatus.SUCCESS
    se.output_data = {
        "condition_met": condition_met,
        "actual_value": actual_value,
        "expected_value": expected,
    }
    se.finished_at = datetime.now(timezone.utc)
    await db.commit()

    # 跳过不满足条件的分支（包括传递性后继）
    branch_key = "next_yes" if not condition_met else "next_no"
    skip_roots = set(step.get(branch_key, []))
    visited: set[str] = set()
    bfs_queue = deque(skip_roots)
    while bfs_queue:
        sid = bfs_queue.popleft()
        if sid in visited or sid not in step_exec_map:
            continue
        visited.add(sid)
        step_exec_map[sid].status = StepExecutionStatus.SKIPPED
        child_step = step_map.get(sid)
        if child_step:
            for child_id in (
                child_step.get("next", [])
                + child_step.get("next_yes", [])
                + child_step.get("next_no", [])
            ):
                if child_id not in visited:
                    bfs_queue.append(child_id)
    await db.commit()


# ---------------------------------------------------------------------------
# 单步执行：approval
# ---------------------------------------------------------------------------

async def _execute_approval_step(
    step: dict,
    se: StepExecution,
    execution: Execution,
    db: AsyncSession,
) -> None:
    """暂停执行，创建审批请求记录。"""
    from app.models.execution import ApprovalRequest, ApprovalStatus

    se.status = StepExecutionStatus.RUNNING
    se.started_at = datetime.now(timezone.utc)
    await db.commit()

    approval = ApprovalRequest(
        execution_id=execution.id,
        step_id=uuid.UUID(step["id"]),
        status=ApprovalStatus.PENDING,
    )
    db.add(approval)
    await db.commit()

    execution.status = ExecutionStatus.WAITING_FOR_APPROVAL
    execution.result = {"waiting_for_approval": str(approval.id)}
    await db.commit()


# ---------------------------------------------------------------------------
# 主入口：执行工作流
# ---------------------------------------------------------------------------

async def execute_workflow(
    execution_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """
    执行一个工作流。

    参数：
        execution_id: 执行记录 ID
        db: 数据库会话
    """
    try:
        # 1. 加载执行记录
        result = await db.execute(select(Execution).where(Execution.id == execution_id))
        execution = result.scalar_one_or_none()
        if not execution:
            logger.warning(f"执行记录不存在: {execution_id}")
            return

        # 2. 加载步骤定义并构建 DAG
        step_result = await db.execute(
            select(Step).where(Step.workflow_id == execution.workflow_id).order_by(Step.order)
        )
        db_steps = step_result.scalars().all()
        dag_steps = _build_dag_steps(db_steps)
        sorted_steps = _topological_sort(dag_steps)
        if len(sorted_steps) != len(dag_steps):
            sorted_ids = {s["id"] for s in sorted_steps}
            cycle_ids = [s["id"] for s in dag_steps if s["id"] not in sorted_ids]
            execution.status = ExecutionStatus.FAILED
            execution.finished_at = datetime.now(timezone.utc)
            execution.result = {"error": MSG_WORKFLOW_CYCLE, "cycle_steps": cycle_ids}
            await db.commit()
            return

        # 3. 初始化执行状态
        execution.status = ExecutionStatus.RUNNING
        execution.started_at = datetime.now(timezone.utc)

        step_exec_map: dict[str, StepExecution] = {}
        for step in sorted_steps:
            # 幂等性检查：避免重复创建 StepExecution
            existing_result = await db.execute(
                select(StepExecution).where(
                    StepExecution.execution_id == execution.id,
                    StepExecution.step_id == uuid.UUID(step["id"]),
                )
            )
            existing_se = existing_result.scalar_one_or_none()
            if existing_se:
                step_exec_map[step["id"]] = existing_se
                logger.debug(f"步骤执行记录已存在，跳过创建: {step['id']}")
            else:
                se = StepExecution(
                    execution_id=execution.id,
                    step_id=uuid.UUID(step["id"]),
                    status=StepExecutionStatus.PENDING,
                )
                db.add(se)
                step_exec_map[step["id"]] = se

        await db.commit()

        # 构建 step_map 供 condition 步骤做分支跳过
        step_map = {s["id"]: s for s in sorted_steps}

        # 4. 逐步执行
        for step in sorted_steps:
            se = step_exec_map[step["id"]]
            step_type = step["step_type"]

            if step_type == "trigger":
                await _execute_trigger_step(se)
                await db.commit()
                continue

            if step_type == "tool":
                should_continue = await _execute_tool_step(step, se, db)
                if not should_continue:
                    execution.status = ExecutionStatus.FAILED
                    execution.finished_at = datetime.now(timezone.utc)
                    execution.result = {"error": f"{MSG_STEP_FAILED}: {step['id']}"}
                    await db.commit()
                    return
                continue

            if step_type == "condition":
                await _execute_condition_step(step, se, step_exec_map, step_map, db)
                continue

            if step_type == "approval":
                await _execute_approval_step(step, se, execution, db)
                return  # 暂停，等待审批

        # 5. 全部完成
        execution.status = ExecutionStatus.SUCCESS
        execution.finished_at = datetime.now(timezone.utc)
        execution.result = {"message": MSG_WORKFLOW_COMPLETE}
        await db.commit()

    except Exception as e:
        logger.exception(f"工作流执行异常: {execution_id}, 错误: {e}")
        try:
            # 尝试更新执行状态为失败
            result = await db.execute(select(Execution).where(Execution.id == execution_id))
            execution = result.scalar_one_or_none()
            if execution:
                execution.status = ExecutionStatus.FAILED
                execution.finished_at = datetime.now(timezone.utc)
                execution.result = {"error": str(e)}
                await db.commit()
        except Exception as inner_e:
            logger.exception(f"更新执行状态失败: {inner_e}")
