from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.models.user import User
from app.routers.auth import get_current_user
from app.services.agent_engine import run_agent


router = APIRouter()

class ChatRequest(BaseModel):
    message: str


class ThoughtStep(BaseModel):
    step: int
    thought: str
    action: str
    observation: str

class ChatResponse(BaseModel):
    thoughts: list[ThoughtStep]
    final_answer: str
    iterations: int


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    result = await run_agent(req.message)

    return ChatResponse(
        thoughts=result["thoughts"],
        final_answer=result["final_answer"],
        iterations=result["iterations"],
    )