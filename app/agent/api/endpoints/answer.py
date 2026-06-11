from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends

from app.agent.dependencies.services import get_agent_service
from app.agent.schemas.request.answer import AgentAnswerRequest
from app.agent.schemas.response.answer import AgentAnswerResponse
from app.agent.services.answer import AgentService


router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/answer", response_model=AgentAnswerResponse)
async def answer(
    payload: AgentAnswerRequest,
    background_tasks: BackgroundTasks,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentAnswerResponse:
    """검증된 Qdrant 후보에서 AI 답변을 선택합니다."""
    execution = await service.answer(payload)
    if execution.usage_word:
        background_tasks.add_task(service.record_usage, execution.usage_word)
    return execution.response
