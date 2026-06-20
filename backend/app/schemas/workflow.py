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
    # 调度信息（来自关联的 Schedule；None 表示未配置定时）
    cron_expr: str | None = None
    schedule_enabled: bool | None = None
    next_run: datetime | None = None

    model_config = {"from_attributes": True}


class WorkflowListResponse(BaseModel):
    """工作流列表项"""
    id: uuid.UUID
    name: str
    description: str | None
    status: str
    created_at: datetime
    # 调度信息（来自关联的 Schedule）
    cron_expr: str | None = None
    schedule_enabled: bool | None = None
    next_run: datetime | None = None

    model_config = { "from_attributes": True }


class ScheduleRequest(BaseModel):
    """设置定时调度的请求"""
    cron_expr: str = Field(..., description="5 段 cron 表达式，如 '0 9 * * *'")


class ScheduleResponse(BaseModel):
    """调度信息"""
    cron_expr: str | None = None
    enabled: bool | None = None
    next_run: datetime | None = None

    model_config = {"from_attributes": True}


class ScheduleToggleResponse(BaseModel):
    """切换调度状态后返回（含工作流状态，便于前端同步）"""
    enabled: bool
    cron_expr: str | None = None
    next_run: datetime | None = None
    workflow_status: str
