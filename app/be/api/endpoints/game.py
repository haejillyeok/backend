from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.be.dependencies.services import get_current_user, get_game_service
from app.be.schemas.response.game import (
    GameSessionEntryResponse,
    GameSessionParticipantResponse,
    StartGameSessionResponse,
)
from app.be.services.auth import CurrentUser
from app.be.services.game import (
    GameService,
    GameSessionEntryResult,
    GameSessionStartResult,
)
from app.shared.core.error_codes import ErrorCode
from app.shared.core.openapi import error_responses_by_status
from app.shared.core.responses import SuccessResponse, ok


router = APIRouter(prefix="/game", tags=["game"])


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
    room_public_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    game_service: Annotated[GameService, Depends(get_game_service)],
) -> SuccessResponse[StartGameSessionResponse]:
    """방장이 활성 room member를 고정하고 게임 세션 진입 식별자를 발급합니다."""
    result = await game_service.start_session(
        room_public_id=room_public_id,
        user_id=current_user.id,
    )
    return ok(map_start_result(result))


@router.get(
    "/sessions/{session_public_id}/entry",
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
    session_public_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    game_service: Annotated[GameService, Depends(get_game_service)],
) -> SuccessResponse[GameSessionEntryResponse]:
    """로그인 유저가 게임 시작 시 확정된 참가자인지 확인합니다."""
    result = await game_service.authorize_entry(
        session_public_id=session_public_id,
        user_id=current_user.id,
    )
    return ok(map_entry_result(result))


def map_start_result(result: GameSessionStartResult) -> StartGameSessionResponse:
    """service의 시작 결과를 public API response로 변환합니다."""
    return StartGameSessionResponse(
        session_public_id=result.session_public_id,
        room_public_id=result.room_public_id,
        game_type=result.game_type,
        status=result.status,
        participants=[
            GameSessionParticipantResponse(
                participant_type=participant.participant_type,
                display_name=participant.display_name,
                seat_number=participant.seat_number,
                is_uninvited_guest=participant.is_uninvited_guest,
            )
            for participant in result.participants
        ],
    )


def map_entry_result(result: GameSessionEntryResult) -> GameSessionEntryResponse:
    """service의 입장 권한 결과를 public API response로 변환합니다."""
    return GameSessionEntryResponse(
        session_public_id=result.session_public_id,
        allowed=result.allowed,
        participant=GameSessionParticipantResponse(
            participant_type=result.participant.participant_type,
            display_name=result.participant.display_name,
            seat_number=result.participant.seat_number,
            is_uninvited_guest=result.participant.is_uninvited_guest,
        ),
    )
