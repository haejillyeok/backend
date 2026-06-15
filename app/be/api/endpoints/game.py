from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.be.dependencies.services import get_current_user, get_game_service
from app.be.schemas.request.game import CreateGameRoomRequest, UpdateGameRoomRequest
from app.be.schemas.response.game import (
    CreateGameRoomResponse,
    CurrentLobbyMembershipResponse,
    GameRoomListResponse,
    GameRoomSummaryResponse,
    GameSessionEntryResponse,
    GameSessionParticipantResponse,
    GameSessionTurnResponse,
    RoomJoinResponse,
    RoomLeaveResponse,
    StartGameSessionResponse,
    UpdateGameRoomResponse,
)
from app.be.services.auth import CurrentUser
from app.be.services.game import (
    GameRoomListItem,
    GameService,
    GameSessionEntryResult,
    GameSessionStartResult,
    RoomCreateResult,
    RoomJoinResult,
    RoomLeaveResult,
    RoomUpdateResult,
    build_lobby_websocket_path,
)
from app.be.services.lobby import lobby_connection_manager
from app.shared.core.observability import get_websocket_metrics
from app.shared.core.error_codes import ErrorCode
from app.shared.core.openapi import error_responses_by_status
from app.shared.core.responses import SuccessResponse, ok
from app.shared.core.timezone import kst_now


router = APIRouter(prefix="/game", tags=["game"])


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


@router.get(
    "/sessions/{game_session_public_id}/entry",
    response_model=SuccessResponse[GameSessionEntryResponse],
    status_code=status.HTTP_200_OK,
    summary="게임 세션 진입 권한 확인",
    operation_id="be_game_session_entry",
    responses=error_responses_by_status(
        codes=[
            ErrorCode.SESSION_EXPIRED,
            ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
            ErrorCode.VALIDATION_ERROR,
        ],
    ),
)
async def get_game_session_entry(
    game_session_public_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    game_service: Annotated[GameService, Depends(get_game_service)],
) -> SuccessResponse[GameSessionEntryResponse]:
    """로그인 유저가 게임 시작 시 확정된 참가자인지 확인합니다."""
    result = await game_service.authorize_entry(
        game_session_public_id=game_session_public_id,
        user_id=current_user.id,
    )
    return ok(map_entry_result(result))


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


def map_start_result(result: GameSessionStartResult) -> StartGameSessionResponse:
    """service의 시작 결과를 public API response로 변환합니다."""
    return StartGameSessionResponse(
        game_session_public_id=result.game_session_public_id,
        room_public_id=result.room_public_id,
        game_type=result.game_type,
        status=result.status,
        game_session_token=result.game_session_token,
        game_session_token_expires_at=result.game_session_token_expires_at,
        rule_config=result.rule_config,
        current_turn=(
            GameSessionTurnResponse(
                phase_id=result.current_turn.phase_id,
                round_number=result.current_turn.round_number,
                turn_number=result.current_turn.turn_number,
                actor_seat_number=result.current_turn.actor_seat_number,
                deadline_at=result.current_turn.deadline_at,
                required_start_char=result.current_turn.required_start_char,
            )
            if result.current_turn is not None
            else None
        ),
        participants=[
            GameSessionParticipantResponse(
                display_name=participant.display_name,
                seat_number=participant.seat_number,
            )
            for participant in result.participants
        ],
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


def map_entry_result(result: GameSessionEntryResult) -> GameSessionEntryResponse:
    """service의 입장 권한 결과를 public API response로 변환합니다."""
    return GameSessionEntryResponse(
        game_session_public_id=result.game_session_public_id,
        allowed=result.allowed,
        game_session_token=result.game_session_token,
        game_session_token_expires_at=result.game_session_token_expires_at,
        participant=GameSessionParticipantResponse(
            display_name=result.participant.display_name,
            seat_number=result.participant.seat_number,
        ),
    )
