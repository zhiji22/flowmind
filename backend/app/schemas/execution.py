"""执行相关的请求/响应模型"""
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class StepExecutionResponse(BaseModel):
    """单个步骤的执行结果"""
    id: uuid.UUID
    step_id: uuid.UUID
    status: str
    input_data: dict[str, Any] | None
    output_data: dict[str, Any] | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ExecutionResponse(BaseModel):
    """工作流执行的完整状态"""
    id: uuid.UUID
    workflow_id: uuid.UUID
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    result: dict[str, Any] | None
    step_executions: list[StepExecutionResponse] = []

    model_config = {"from_attributes": True}