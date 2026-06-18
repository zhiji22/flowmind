"""审批相关的请求/响应模型"""
import uuid
from datetime import datetime

from pydantic import BaseModel


class ApprovalRequestResponse(BaseModel):
    """单条审批请求"""
    id: uuid.UUID
    execution_id: uuid.UUID
    step_id: uuid.UUID
    status: str
    requested_at: datetime
    resolved_at: datetime | None
    resolver_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class ApprovalResolveRequest(BaseModel):
    """通过 / 拒绝时可附带备注（暂存到 result，未来可扩展）"""
    note: str | None = None
