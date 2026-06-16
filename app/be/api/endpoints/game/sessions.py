from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.be.api.endpoints.game.mappers import map_start_result
from app.be.dependencies.services import get_current_user, get_game_service
from app.be.schemas.response.game import StartGameSessionResponse
from app.be.services.auth import CurrentUser
from app.be.services.game import GameService
from app.be.services.lobby import lobby_connection_manager
from app.shared.core.error_codes import ErrorCode
from app.shared.core.observability import get_websocket_metrics
from app.shared.core.openapi import error_responses_by_status
from app.shared.core.responses import SuccessResponse, ok


router = APIRouter()


@router.post(
    "/rooms/{room_public_id}/start",
    response_model=SuccessResponse[StartGameSessionResponse],
    status_code=status.HTTP_200_OK,
    summary="게임 세션 시작",
    operation_id="be_game_start_session",
    responses=error_responses_by_status(
        codes=[
            ErrorCode.SESSION_EXPIRED,
            ErrorCode.GAME_ROOM_NOT_FOUND,
            ErrorCode.GAME_ROOM_START_FORBIDDEN,
            ErrorCode.GAME_ROOM_NOT_STARTABLE,
            ErrorCode.VALIDATION_ERROR,
        ],
    ),
)
async def start_game_session(
    request: Request,
    room_public_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    game_service: Annotated[GameService, Depends(get_game_service)],
) -> SuccessResponse[StartGameSessionResponse]:
    """방장이 활성 room member를 고정하고 게임 세션 진입 식별자를 발급합니다."""
    result = await game_service.start_session(
        room_public_id=room_public_id,
        user_id=current_user.id,
    )
    response = map_start_result(result)
    await lobby_connection_manager.broadcast_room(
        room_public_id,
        {
            "type": "game.started",
            "payload": response.model_dump(
                mode="json",
                exclude={"game_session_token", "game_session_token_expires_at"},
            ),
        },
    )
    get_websocket_metrics(request.app).record_message(
        ws_route="/ws/lobby/rooms/{room_public_id}",
        ws_endpoint="lobby",
        message_type="game.started",
        direction="outbound",
    )
    return ok(response)
