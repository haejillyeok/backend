from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.be.api.endpoints.game.mappers import map_room_list_item
from app.be.dependencies.services import get_current_user, get_game_service
from app.be.schemas.response.game import (
    CurrentLobbyMembershipResponse,
    GameRoomListResponse,
)
from app.be.services.auth import CurrentUser
from app.be.services.game import GameService
from app.shared.core.error_codes import ErrorCode
from app.shared.core.openapi import error_responses_by_status
from app.shared.core.responses import SuccessResponse, ok


router = APIRouter()


@router.get(
    "/rooms",
    response_model=SuccessResponse[GameRoomListResponse],
    status_code=status.HTTP_200_OK,
    summary="로비 객실 목록 조회",
    operation_id="be_game_list_rooms",
    responses=error_responses_by_status(
        codes=[
            ErrorCode.SESSION_EXPIRED,
            ErrorCode.VALIDATION_ERROR,
        ],
    ),
)
async def list_game_rooms(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    game_service: Annotated[GameService, Depends(get_game_service)],
) -> SuccessResponse[GameRoomListResponse]:
    """로그인 유저가 로비에서 선택할 수 있는 객실 목록을 조회합니다."""
    result = await game_service.list_rooms(user_id=current_user.id)
    return ok(
        GameRoomListResponse(
            rooms=[map_room_list_item(room) for room in result.rooms],
            current_membership=(
                CurrentLobbyMembershipResponse(
                    room_public_id=result.current_membership.room_public_id,
                    name=result.current_membership.name,
                    game_type=result.current_membership.game_type,
                    status=result.current_membership.status,
                    max_players=result.current_membership.max_players,
                    member_count=result.current_membership.member_count,
                    is_owner=result.current_membership.is_owner,
                    lobby_websocket_path=result.current_membership.lobby_websocket_path,
                )
                if result.current_membership is not None
                else None
            ),
        )
    )
