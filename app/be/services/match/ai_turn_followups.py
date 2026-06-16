from datetime import datetime

from app.be.services.match.broadcasters import broadcast_match_event_with_round_finished
from app.be.services.match.connection_manager import MatchConnectionManager, MatchMessage
from app.be.services.match.message_helpers import extract_next_turn_phase_id
from app.be.services.match_ai import MatchAiTurnService


async def append_ai_turn_if_needed(
    *,
    manager: MatchConnectionManager,
    ai_turn_service: MatchAiTurnService | None,
    message: MatchMessage,
    game_session_public_id,
    now: datetime,
    broadcast_messages: list[MatchMessage],
) -> None:
    """다음 턴이 AI이면 즉시 AI 제출을 진행하고 broadcast 메시지 목록에 추가합니다."""
    if ai_turn_service is None:
        return
    next_phase_id = extract_next_turn_phase_id(message)
    if next_phase_id is None:
        return
    ai_event = await ai_turn_service.play_ai_turn(
        game_session_public_id=game_session_public_id,
        phase_id=next_phase_id,
        now=now,
    )
    if ai_event is None:
        return
    broadcast_messages.extend(
        await broadcast_match_event_with_round_finished(
            manager=manager,
            event=ai_event,
        )
    )
