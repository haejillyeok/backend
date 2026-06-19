from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.be.api.endpoints.game.mappers import map_room_join_result, map_room_leave_result
from app.be.dependencies.services import get_current_user, get_game_service
from app.be.schemas.response.game import RoomJoinResponse, RoomLeaveResponse
from app.be.services.auth import CurrentUser
from app.be.services.game import GameService
from app.be.services.lobby import lobby_connection_manager
from app.shared.core.error_codes import ErrorCode
from app.shared.core.observability import get_websocket_metrics
from app.shared.core.openapi import error_responses_by_status
from app.shared.core.responses import SuccessResponse, ok
from app.shared.core.timezone import kst_now


router = APIRouter()


@router.post(
    "/rooms/quick-join",
    response_model=SuccessResponse[RoomJoinResponse],
    status_code=status.HTTP_200_OK,
    summary="로비 객실 빠른입장",
    operation_id="be_game_quick_join_room",
    responses=error_responses_by_status(
        codes=[
            ErrorCode.SESSION_EXPIRED,
            ErrorCode.GAME_ROOM_NOT_JOINABLE,
            ErrorCode.VALIDATION_ERROR,
        ],
    ),
)
async def quick_join_game_room(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    game_service: Annotated[GameService, Depends(get_game_service)],
) -> SuccessResponse[RoomJoinResponse]:
    """로그인 유저를 참여 가능한 대기 객실에 빠르게 입장시키고 필요하면 새 객실을 만듭니다."""
    result = await game_service.quick_join_room(user=current_user)
    response = map_room_join_result(result)
    if not result.created_room:
        await lobby_connection_manager.broadcast_room(
            result.room_public_id,
            {
                "type": "lobby.room.joined",
                "payload": response.model_dump(mode="json"),
            },
        )
        get_websocket_metrics(request.app).record_message(
            ws_route="/ws/lobby/rooms/{room_public_id}",
            ws_endpoint="lobby",
            message_type="lobby.room.joined",
            direction="outbound",
        )
    return ok(response)


@router.post(
    "/rooms/{room_public_id}/join",
    response_model=SuccessResponse[RoomJoinResponse],
    status_code=status.HTTP_200_OK,
    summary="로비 객실 참여",
    operation_id="be_game_join_room",
    responses=error_responses_by_status(
        codes=[
            ErrorCode.SESSION_EXPIRED,
            ErrorCode.GAME_ROOM_NOT_FOUND,
            ErrorCode.GAME_ROOM_NOT_JOINABLE,
            ErrorCode.VALIDATION_ERROR,
        ],
    ),
)
async def join_game_room(
    request: Request,
    room_public_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    game_service: Annotated[GameService, Depends(get_game_service)],
) -> SuccessResponse[RoomJoinResponse]:
    """로그인 유저를 대기 중인 객실 멤버로 참여시키고 로비 구독자에게 알립니다."""
    result = await game_service.join_room(room_public_id=room_public_id, user=current_user)
    response = map_room_join_result(result)
    if not result.already_member:
        await lobby_connection_manager.broadcast_room(
            room_public_id,
            {
                "type": "lobby.room.joined",
                "payload": response.model_dump(mode="json"),
            },
        )
        get_websocket_metrics(request.app).record_message(
            ws_route="/ws/lobby/rooms/{room_public_id}",
            ws_endpoint="lobby",
            message_type="lobby.room.joined",
            direction="outbound",
        )
    return ok(response)


@router.post(
    "/rooms/{room_public_id}/leave",
    response_model=SuccessResponse[RoomLeaveResponse],
    status_code=status.HTTP_200_OK,
    summary="로비 객실 퇴장",
    operation_id="be_game_leave_room",
    responses=error_responses_by_status(
        codes=[
            ErrorCode.SESSION_EXPIRED,
            ErrorCode.GAME_ROOM_NOT_FOUND,
            ErrorCode.GAME_ROOM_ENTRY_FORBIDDEN,
            ErrorCode.GAME_ROOM_NOT_JOINABLE,
            ErrorCode.VALIDATION_ERROR,
        ],
    ),
)
async def leave_game_room(
    request: Request,
    room_public_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    game_service: Annotated[GameService, Depends(get_game_service)],
) -> SuccessResponse[RoomLeaveResponse]:
    """로그인 유저를 대기 객실에서 퇴장시키고 같은 방 구독자에게 알립니다."""
    result = await game_service.leave_room(
        room_public_id=room_public_id,
        user=current_user,
        left_at=kst_now(),
    )
    response = map_room_leave_result(result)
    await lobby_connection_manager.broadcast_room(
        room_public_id,
        {
            "type": "lobby.room.left",
            "payload": response.model_dump(mode="json"),
        },
    )
    get_websocket_metrics(request.app).record_message(
        ws_route="/ws/lobby/rooms/{room_public_id}",
        ws_endpoint="lobby",
        message_type="lobby.room.left",
        direction="outbound",
    )
    return ok(response)
