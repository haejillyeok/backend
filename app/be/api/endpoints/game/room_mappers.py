from app.be.schemas.response.game import (
    CreateGameRoomResponse,
    GameRoomSummaryResponse,
    RoomJoinResponse,
    RoomLeaveResponse,
    UpdateGameRoomResponse,
)
from app.be.services.game import (
    GameRoomListItem,
    RoomCreateResult,
    RoomJoinResult,
    RoomLeaveResult,
    RoomUpdateResult,
    build_lobby_websocket_path,
)


def map_room_list_item(result: GameRoomListItem) -> GameRoomSummaryResponse:
    """service의 room 목록 item을 public API response로 변환합니다."""
    return GameRoomSummaryResponse(
        room_public_id=result.room_public_id,
        name=result.name,
        game_type=result.game_type,
        status=result.status,
        max_players=result.max_players,
        member_count=result.member_count,
        is_current_user_member=result.is_current_user_member,
        is_current_user_owner=result.is_current_user_owner,
        lobby_websocket_path=build_lobby_websocket_path(result.room_public_id),
    )


def map_room_create_result(result: RoomCreateResult) -> CreateGameRoomResponse:
    """service의 room 생성 결과를 public API response로 변환합니다."""
    return CreateGameRoomResponse(
        room_public_id=result.room_public_id,
        name=result.name,
        game_type=result.game_type,
        status=result.status,
        max_players=result.max_players,
        member_count=result.member_count,
        created_at=result.created_at,
    )


def map_room_update_result(result: RoomUpdateResult) -> UpdateGameRoomResponse:
    """service의 room 설정 수정 결과를 public API response와 WebSocket payload로 변환합니다."""
    return UpdateGameRoomResponse(
        room_public_id=result.room_public_id,
        name=result.name,
        game_type=result.game_type,
        status=result.status,
        max_players=result.max_players,
        rule_config=result.rule_config,
    )


def map_room_join_result(result: RoomJoinResult) -> RoomJoinResponse:
    """service의 room 참여 결과를 public API response로 변환합니다."""
    return RoomJoinResponse(
        room_public_id=result.room_public_id,
        user_public_id=result.user_public_id,
        nickname=result.nickname,
        joined_at=result.joined_at,
        already_member=result.already_member,
        created_room=result.created_room,
        lobby_websocket_path=build_lobby_websocket_path(result.room_public_id),
    )


def map_room_leave_result(result: RoomLeaveResult) -> RoomLeaveResponse:
    """service의 room 퇴장 결과를 public API response로 변환합니다."""
    return RoomLeaveResponse(
        room_public_id=result.room_public_id,
        user_public_id=result.user_public_id,
        nickname=result.nickname,
        left_at=result.left_at,
        remaining_member_count=result.remaining_member_count,
        new_owner_user_public_id=result.new_owner_user_public_id,
        new_owner_nickname=result.new_owner_nickname,
        room_closed=result.room_closed,
    )
