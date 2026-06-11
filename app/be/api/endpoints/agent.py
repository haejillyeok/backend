from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.be.dependencies.services import get_agent_health_client
from app.be.schemas.response.health import HealthResponse
from app.shared.clients.agent import AgentClientError, AgentHealthClient
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException
from app.shared.core.openapi import error_responses_by_status
from app.shared.core.responses import SuccessResponse, ok


router = APIRouter(prefix="/agent", tags=["agent"])


@router.get(
    "/health",
    response_model=SuccessResponse[HealthResponse],
    status_code=status.HTTP_200_OK,
    summary="Agent 헬스 체크",
    operation_id="be_agent_health_check",
    responses=error_responses_by_status(
        codes=[
            ErrorCode.AGENT_HEALTH_UNAVAILABLE,
            ErrorCode.AGENT_CLIENT_NOT_CONFIGURED,
        ],
    ),
)
async def agent_health_check(
    client: Annotated[AgentHealthClient, Depends(get_agent_health_client)],
) -> SuccessResponse[HealthResponse]:
    """BE에서 Agent `/api/v1/health`를 호출해 Agent 상태를 반환합니다."""
    try:
        health = await client.get_health()
    except AgentClientError as exc:
        raise AppException(
            code=ErrorCode.AGENT_HEALTH_UNAVAILABLE,
            details={"agent_status_code": exc.status_code},
        ) from exc

    return ok(HealthResponse(status=health.status))
