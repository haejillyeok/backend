from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.be.api.endpoints.game.mappers import (
    map_room_create_result,
    map_room_update_result,
)
from app.be.dependencies.services import get_current_user, get_game_service
from app.be.schemas.request.game import CreateGameRoomRequest, UpdateGameRoomRequest
from app.be.schemas.response.game import CreateGameRoomResponse, UpdateGameRoomResponse
from app.be.services.auth import CurrentUser
from app.be.services.game import GameService
from app.be.services.lobby import lobby_connection_manager
from app.shared.core.error_codes import ErrorCode
from app.shared.core.observability import get_websocket_metrics
from app.shared.core.openapi import error_responses_by_status
from app.shared.core.responses import SuccessResponse, ok


router = APIRouter()


@router.post(
    "/rooms",
    response_model=SuccessResponse[CreateGameRoomResponse],
    status_code=status.HTTP_201_CREATED,
    summary="로비 객실 생성",
    operation_id="be_game_create_room",
    responses=error_responses_by_status(
        codes=[
            ErrorCode.SESSION_EXPIRED,
            ErrorCode.VALIDATION_ERROR,
        ],
    ),
)
async def create_game_room(
    request: CreateGameRoomRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    game_service: Annotated[GameService, Depends(get_game_service)],
) -> SuccessResponse[CreateGameRoomResponse]:
    """로그인 유저를 방장으로 하는 대기 객실을 만들고 방장 멤버십을 함께 등록합니다."""
    result = await game_service.create_room(
        name=request.name,
        game_type=request.game_type,
        max_players=request.max_players,
        owner=current_user,
    )
    return ok(map_room_create_result(result))


@router.patch(
    "/rooms/{room_public_id}",
    response_model=SuccessResponse[UpdateGameRoomResponse],
    status_code=status.HTTP_200_OK,
    summary="로비 객실 설정 수정",
    operation_id="be_game_update_room",
    responses=error_responses_by_status(
        codes=[
            ErrorCode.SESSION_EXPIRED,
            ErrorCode.GAME_ROOM_NOT_FOUND,
            ErrorCode.GAME_ROOM_UPDATE_FORBIDDEN,
            ErrorCode.GAME_ROOM_NOT_UPDATEABLE,
            ErrorCode.VALIDATION_ERROR,
        ],
    ),
)
async def update_game_room(
    request: Request,
    room_public_id: UUID,
    payload: UpdateGameRoomRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    game_service: Annotated[GameService, Depends(get_game_service)],
) -> SuccessResponse[UpdateGameRoomResponse]:
    """방장이 대기 객실 설정을 수정하고 같은 객실 연결에 동기화 event를 보냅니다."""
    result = await game_service.update_room(
        room_public_id=room_public_id,
        user=current_user,
        name=payload.name,
        max_players=payload.max_players,
        rule_config=payload.rule_config.model_dump(),
    )
    response = map_room_update_result(result)
    await lobby_connection_manager.broadcast_room(
        room_public_id,
        {
            "type": "lobby.room.updated",
            "payload": response.model_dump(mode="json"),
        },
    )
    get_websocket_metrics(request.app).record_message(
        ws_route="/ws/lobby/rooms/{room_public_id}",
        ws_endpoint="lobby",
        message_type="lobby.room.updated",
        direction="outbound",
    )
    return ok(response)
