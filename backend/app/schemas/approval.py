"""审批相关的请求/响应模型"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ApprovalRequestResponse(BaseModel):
    """单条审批请求（含上下文，便于前端展示）"""

    id: uuid.UUID
    execution_id: uuid.UUID
    step_id: uuid.UUID
    status: str
    requested_at: datetime
    resolved_at: datetime | None
    resolver_id: uuid.UUID | None

    # ---- 上下文（审批列表页展示用）----
    workflow_id: uuid.UUID | None = None
    workflow_name: str | None = None
    step_type: str | None = None
    step_config: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class ApprovalResolveRequest(BaseModel):
    """通过 / 拒绝时可附带备注（通过：写入 output_data；拒绝：写入 error_message）"""

    note: str | None = None
