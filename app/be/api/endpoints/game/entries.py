from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.be.api.endpoints.game.mappers import map_entry_result
from app.be.dependencies.services import get_current_user, get_game_service
from app.be.schemas.response.game import GameSessionEntryResponse
from app.be.services.auth import CurrentUser
from app.be.services.game import GameService
from app.shared.core.error_codes import ErrorCode
from app.shared.core.openapi import error_responses_by_status
from app.shared.core.responses import SuccessResponse, ok


router = APIRouter()


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
