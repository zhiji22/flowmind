import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class CreateWorkflowRequest(BaseModel):
    """用户通过自然语言创建工作流的请求"""
    message: str = Field(..., description="自然语言描述，如：每天早上9点查竞品价格")


class StepSchema(BaseModel):
    """工作流中的单个步骤"""
    id: str
    step_type: str  # trigger / tool / condition / approval
    tool_name: str | None = None
    config: dict[str, Any] | None = None
    next: list[str] = Field(default_factory=list)  # 下一步骤的 id 列表
    next_yes: list[str] = Field(default_factory=list)  # 条件为真时走
    next_no: list[str] = Field(default_factory=list)  # 条件为假时走
    position: dict[str, Any] | None = None  # 前端 React Flow 的 x, y 坐标


class UpdateWorkflowRequest(BaseModel):
    """编辑工作流（名称、DAG、步骤等）"""
    name: str | None = None
    description: str | None = None
    dag_json: dict[str, Any] | None = None


class WorkflowResponse(BaseModel):
    """返回给前端的工作流详情"""
    id: uuid.UUID
    name: str
    description: str | None
    dag_json: dict[str, Any] | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowListResponse(BaseModel):
    """工作流列表项"""
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    created_at: datetime

    model_config = { "from_attributes": True }