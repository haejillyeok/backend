from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.agent.dependencies.services import get_stack_service
from app.agent.schemas.request.data_stack import DataStackRequest
from app.agent.schemas.response.data_stack import DataStackResponse
from app.agent.services.stack import StackService


router = APIRouter(prefix="/data", tags=["agent-data"])


@router.post(
    "/stack",
    response_model=DataStackResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def stack_words(
    payload: DataStackRequest,
    background_tasks: BackgroundTasks,
    service: Annotated[StackService, Depends(get_stack_service)],
) -> DataStackResponse:
    """단어 적재 요청을 수락하고 실제 upsert는 background task로 실행합니다."""
    execution = await service.accept(payload)
    if execution.job:
        background_tasks.add_task(service.process, execution.job)
    return execution.response
