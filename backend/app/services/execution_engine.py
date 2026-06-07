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
import json 
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import Execution, StepExecution, ExecutionStatus, StepExecutionStatus
from app.models.workflow import Step
from app.tools.base import registry


def _topological_sort(steps: list[dict]) -> list[dict]:
    """
    拓扑排序：根据步骤之间的依赖关系，确定一个合法的执行顺序。
    保证每一步在它依赖的步骤之后执行。
    """
    step_map = { s["id"]: s for s in steps }

    # 计算每个节点的入度（有多少前置步骤依赖它）
    in_degree: dict[str, int] = {s["id"]: 0 for s in steps}
    for step in steps:
        # 获取当前步骤的所有后继节点
        next_ids = step.get("next", []) + step.get("next_year", []) + step.get("next_no", [])
        for nid in next_ids:
            if nid in in_degree:
                in_degree[nid] += 1

    # 入读为 0 的节点可以先执行
    queue = [sid for sid, deg in in_degree.items() if deg ==0]
    result = []

    while queue:
        # 取出当前无依赖的步骤
        current_id = queue.pop(0)
        if current_id in step_map:
            result.append(step_map[current_id])

        # 执行完后，减少后继节点的入度
        step = step_map[current_id]
        next_ids = step.get("next", []) + step.get("next_yes", []) + step.get("next_no", [])
        for nid in next_ids:
            if nid in in_degree:
                in_degree[nid] -= 1
                if in_degree[nid] == 0:
                    queue.append(nid)

    return result


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


async def execute_workflow(
    execution_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """
    执行一个工作流。

    参数：
        execution_id: 执行记录 ID
        db: 数据库会话

    流程：
        1. 加载执行记录和对应的工作流 DAG
        2. 拓扑排序确定执行顺序
        3. 逐个执行步骤
        4. 遇到 approval 类型时暂停
        5. 全部完成后更新状态
    """
    # 加载执行记录
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    execution = result.scalar_one_or_none()
    if not execution:
        return
    
    # 加载工作流的步骤定义
    step_result = await db.execute(
        select(Step).where(Step.workflow_id == execution.workflow_id).order_by(Step.order)
    )
    db_steps = step_result.scalars().all()

    # 把数据库中的Step转为DAG JSON格式（如果 dag_json 为空则用 steps 表重建）
    dag_steps = []
    for s in db_steps:
        step_dict = {
            "id": str(s.id),
            "step_type": s.step_type,
            "tool_name": s.tool_name,
            "config": s.config or {},
        }
        # 从config中取next关系
        config = s.config or {}
        step_dict["next"] = config.get("next", [])
        step_dict["next_yes"] = config.get("next_yes", [])
        step_dict["next_no"] = config.get("next_no", [])
        dag_steps.append(step_dict)

    # 拓扑排序
    sorted_steps = _topological_sort(dag_steps)

    # 更新执行状态为 running
    execution.status = ExecutionStatus.RUNNING
    execution.started_at = datetime.utcnow()
 
    # 为每个步骤创建StepExecution记录（初始状态pending)
    step_exec_map: dict[str, StepExecution] = {}
    for step in sorted_steps:
        se = StepExecution(
            execution_id=execution.id,
            step_id=uuid.UUID(step["id"]),
            status=StepExecutionStatus.PENDING,
        )
        db.add(se)
        step_exec_map[step["id"]] = se

    await db.commit()

    # 逐步执行
    for step in sorted_steps:
        se = step_exec_map[step["id"]]
        step_type = step["step_type"]

        # trigger类型：仅作为入口，直接标记成功
        if step_type == "trigger":
            se.status = StepExecutionStatus.SUCCESS
            se.started_at = datetime.utcnow()
            se.finished_at = datetime.utcnow()
            se.output_data = {"message": "工作流触发成功"}

            await db.commit()
            continue

        # --- tool 类型：调用注册的工具 ---
        if step_type == "tool":
            se.status = StepExecutionStatus.RUNNING
            se.started_at = datetime.utcnow()
            await db.commit()

            tool_name = step.get("tool_name", "")
            config = step.get("config", {})
            tool = registry.get(tool_name)

            if not tool:
                # 工具不存在，标记失败
                se.status = StepExecutionStatus.FAILED
                se.error_message = f"工具 '{tool_name}' 不存在"
                se.finished_at = datetime.utcnow()
                await db.commit()
                execution.status = ExecutionStatus.FAILED
                execution.finished_at = datetime.utcnow()
                execution.result = {"error": f"步骤 {step['id']} 失败: 工具不存在"}
                await db.commit()
                return

            try:
                # 执行工具
                tool_result = await tool.execute(**config)
                se.status = StepExecutionStatus.SUCCESS
                se.output_data = {"result": tool_result}
            except Exception as e:
                se.status = StepExecutionStatus.FAILED
                se.error_message = str(e)

            se.finished_at = datetime.utcnow()

            await db.commit()
            continue

         # --- condition 类型：根据前一步结果判断分支 ---
        if step_type == "condition":
            se.status = StepExecutionStatus.RUNNING
            se.started_at = datetime.utcnow()
            await db.commit()

            config = step.get("config", {})
            condition_field = config.get("field", "")
            operator = config.get("operator", "contains")
            expected = config.get("value", "")

            # 获取前一步的输出结果
            all_se = list(step_exec_map.values())
            outputs = _resolve_step_outputs(all_se)
            actual_value = ""

            # field 格式：$step_id.result，用于引用前一步输出
            if condition_field.startswith("$"):
                parts = condition_field.lstrip("$").split(".")
                ref_step_id = parts[0]
                if ref_step_id in outputs and len(parts) > 1:
                    actual_value = str(outputs[ref_step_id].get(parts[1], ""))

            # 条件判断
            if operator == "contains":
                condition_met = expected in actual_value
            elif operator == "equals":
                condition_met = expected == actual_value
            elif operator == "gt":
                condition_met = float(actual_value) > float(expected)
            else:
                condition_met = False

            se.status = StepExecutionStatus.SUCCESS
            se.output_data = {
                "condition_met": condition_met,
                "actual_value": actual_value,
                "expected_value": expected,
            }
            se.finished_at = datetime.utcnow()
            await db.commit()

            # 如果条件不满足，跳过 next_yes 后面的步骤
            if not condition_met:
                skip_ids = set(step.get("next_yes", []))
                for sid in skip_ids:
                    if sid in step_exec_map:
                        step_exec_map[sid].status = StepExecutionStatus.SKIPPED
                await db.commit()
            else:
                skip_ids = set(step.get("next_no", []))
                for sid in skip_ids:
                    if sid in step_exec_map:
                        step_exec_map[sid].status = StepExecutionStatus.SKIPPED
                await db.commit()
            continue

        # --- approval 类型：暂停等待人工审批 ---
        if step_type == "approval":
            se.status = StepExecutionStatus.RUNNING
            se.started_at = datetime.utcnow()
            await db.commit()

            # 创建审批请求记录，后续由审批 API 触发继续执行
            from app.models.execution import ApprovalRequest, ApprovalStatus
            approval = ApprovalRequest(
                execution_id=execution.id,
                step_id=uuid.UUID(step["id"]),
                status=ApprovalStatus.PENDING,
            )
            db.add(approval)
            await db.commit()

            # 暂停执行，等待审批
            execution.status = ExecutionStatus.RUNNING
            execution.result = {"waiting_for_approval": str(approval.id)}
            await db.commit()
            return
        
    # 所有步骤执行完成
    execution.status = ExecutionStatus.SUCCESS
    execution.finished_at = datetime.utcnow()
    execution.result = {"message": "工作流执行完成"}
    await db.commit()

