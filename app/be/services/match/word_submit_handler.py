from datetime import datetime

from fastapi import WebSocket

from app.be.services.match.ai_turn_followups import append_ai_turn_if_needed
from app.be.services.match.broadcasters import broadcast_match_event_with_round_finished
from app.be.services.match.connection_manager import MatchConnectionManager, MatchMessage
from app.be.services.match.message_helpers import (
    is_turn_deadline_exception,
    parse_phase_id,
    word_rejection_from_exception,
)
from app.be.services.match_ai import MatchAiTurnService
from app.be.services.match_progress import MatchProgressService
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


async def handle_word_submit_message(
    *,
    manager: MatchConnectionManager,
    websocket: WebSocket,
    message: MatchMessage,
    progress_service: MatchProgressService,
    ai_turn_service: MatchAiTurnService | None,
    now: datetime,
) -> list[MatchMessage]:
    """word.submit command를 검증하고 단어 확정, timeout, AI 후속 턴을 처리합니다."""
    connection = manager.get_connection(websocket)
    if connection is None:
        raise AppException(
            code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
            details={"reason": "match_connection_missing"},
        )
    payload = message["payload"]
    phase_id = parse_phase_id(payload.get("phase_id"))
    word = payload.get("word")
    if not isinstance(word, str):
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            details={"reason": "word_required"},
        )
    try:
        event = await progress_service.submit_word(
            game_session_public_id=connection.game_session_public_id,
            phase_id=phase_id,
            participant_id=connection.participant_id,
            word=word,
            now=now,
        )
    except AppException as exc:
        if is_turn_deadline_exception(exc):
            timeout_event = await progress_service.timeout_turn_if_due(
                game_session_public_id=connection.game_session_public_id,
                phase_id=phase_id,
                now=now,
            )
            if timeout_event is None:
                return []
            broadcast_messages = await broadcast_match_event_with_round_finished(
                manager=manager,
                event=timeout_event,
            )
            await append_ai_turn_if_needed(
                manager=manager,
                ai_turn_service=ai_turn_service,
                message=timeout_event.message,
                game_session_public_id=timeout_event.game_session_public_id,
                now=now,
                broadcast_messages=broadcast_messages,
            )
            return broadcast_messages
        rejection = word_rejection_from_exception(exc)
        if rejection is None:
            raise
        reason, details = rejection
        event = await progress_service.reject_word(
            game_session_public_id=connection.game_session_public_id,
            phase_id=phase_id,
            participant_id=connection.participant_id,
            word=word,
            reason=reason,
            details=details,
            now=now,
        )
        return await broadcast_match_event_with_round_finished(
            manager=manager,
            event=event,
        )
    broadcast_messages = await broadcast_match_event_with_round_finished(
        manager=manager,
        event=event,
    )
    await append_ai_turn_if_needed(
        manager=manager,
        ai_turn_service=ai_turn_service,
        message=event.message,
        game_session_public_id=event.game_session_public_id,
        now=now,
        broadcast_messages=broadcast_messages,
    )
    return broadcast_messages
