"""聊天 API：SSE 流式返回 Agent 的思考过程"""

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.limiter import limiter
from app.models.user import User
from app.routers.auth import get_current_user
from app.services.agent_engine import run_agent_stream

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=2000)


def _sse(event: str, data: dict) -> str:
    """把事件格式化为 SSE 文本块。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("")
@limiter.limit("10/minute")
async def chat(
    request: Request,
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    """
    SSE 流式聊天接口。

    返回 text/event-stream，逐个推送：
      event: start       → Agent 开始
      event: thought     → 思考 + 行动
      event: observation → 观察结果
      event: final       → 最终回答
      event: error       → 异常
    """

    async def event_generator():
        try:
            async for event in run_agent_stream(req.message):
                yield _sse(event["event"], event["data"])
        except Exception as e:
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",  # 禁用缓存，保证实时推送
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲（生产环境用）
            "Connection": "keep-alive",
        },
    )
