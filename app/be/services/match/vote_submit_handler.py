from datetime import datetime

from fastapi import WebSocket

from app.be.services.match.connection_manager import MatchConnectionManager, MatchMessage
from app.be.services.match.message_helpers import (
    is_vote_deadline_exception,
    parse_target_seat_number,
)
from app.be.services.match_vote import MatchVoteService
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


async def handle_vote_submit_message(
    *,
    manager: MatchConnectionManager,
    websocket: WebSocket,
    message: MatchMessage,
    vote_service: MatchVoteService,
    now: datetime,
) -> list[MatchMessage]:
    """vote.submit command를 검증하고 투표 제출 또는 timeout 확정을 broadcast합니다."""
    connection = manager.get_connection(websocket)
    if connection is None:
        raise AppException(
            code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
            details={"reason": "match_connection_missing"},
        )
    target_seat_number = parse_target_seat_number(message["payload"].get("target_seat_number"))
    try:
        events = await vote_service.submit_vote(
            game_session_public_id=connection.game_session_public_id,
            voter_participant_id=connection.participant_id,
            target_seat_number=target_seat_number,
            now=now,
        )
    except AppException as exc:
        if not is_vote_deadline_exception(exc):
            raise
        events = await vote_service.timeout_vote(
            game_session_public_id=connection.game_session_public_id,
            now=now,
        )
    for event in events:
        await manager.broadcast_session(event.game_session_public_id, event.message)
    return [event.message for event in events]
