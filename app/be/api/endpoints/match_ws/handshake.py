from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.be.services.auth import AuthService
from app.be.services.game import GameSessionEntryResult, GameService
from app.be.services.match import MatchService
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


@dataclass(frozen=True)
class MatchHandshakeResult:
    """match WebSocket 연결 인증 후 message loop에 넘길 초기 상태입니다."""

    entry: GameSessionEntryResult
    participant_id: UUID
    snapshot: Any


async def authorize_match_handshake(
    *,
    auth_service: AuthService,
    game_service: GameService,
    match_service: MatchService,
    session_token: str | None,
    game_session_public_id: UUID | None,
    game_session_token: str | None,
) -> MatchHandshakeResult:
    """로그인 쿠키 또는 재접속 토큰으로 match WebSocket 참가 권한과 snapshot을 확인합니다."""
    if game_session_token:
        entry = await game_service.authorize_resume_token(game_session_token)
    elif game_session_public_id is not None:
        current_user = await auth_service.authenticate_session(session_token)
        entry = await game_service.authorize_entry(
            game_session_public_id=game_session_public_id,
            user_id=current_user.id,
        )
    else:
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            details={"reason": "missing_match_identity"},
        )

    participant_id = entry.participant.participant_id
    if participant_id is None:
        raise AppException(
            code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
            details={"reason": "participant_id_missing"},
        )
    snapshot = await match_service.get_snapshot(
        game_session_public_id=entry.game_session_public_id,
        participant_id=participant_id,
    )
    return MatchHandshakeResult(
        entry=entry,
        participant_id=participant_id,
        snapshot=snapshot,
    )
