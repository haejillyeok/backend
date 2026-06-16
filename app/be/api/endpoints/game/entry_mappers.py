from app.be.schemas.response.game import (
    GameSessionEntryResponse,
    GameSessionParticipantResponse,
)
from app.be.services.game import GameSessionEntryResult


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
