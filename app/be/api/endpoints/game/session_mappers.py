from app.be.schemas.response.game import (
    GameSessionParticipantResponse,
    GameSessionTurnResponse,
    StartGameSessionResponse,
)
from app.be.services.game import GameSessionStartResult


def _server_time():
    from app.be.api.endpoints.game import mappers

    return mappers.kst_now()


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
        server_time=_server_time(),
        current_turn=(
            GameSessionTurnResponse(
                phase_id=result.current_turn.phase_id,
                round_number=result.current_turn.round_number,
                turn_number=result.current_turn.turn_number,
                actor_seat_number=result.current_turn.actor_seat_number,
                started_at=result.current_turn.started_at,
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
