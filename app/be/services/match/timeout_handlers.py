from datetime import datetime
from uuid import UUID

from app.be.services.match.connection_manager import MatchConnectionManager
from app.be.services.match.ai_turn_followups import append_ai_turn_if_needed
from app.be.services.match.round_events import broadcast_match_event_with_round_finished
from app.be.services.match.timers import (
    MatchTimer,
    MatchTurnTimer,
    next_match_timer_from_message,
)
from app.be.services.match_ai import MatchAiTurnService
from app.be.services.match_progress import MatchProgressService
from app.be.services.match_vote import MatchVoteService
from app.shared.core.timezone import kst_now


async def process_match_turn_timeout(
    *,
    manager: MatchConnectionManager,
    progress_service: MatchProgressService,
    ai_turn_service: MatchAiTurnService | None,
    game_session_public_id: UUID,
    phase_id: UUID,
    now: datetime,
) -> MatchTimer | None:
    """현재 턴 timeout을 확정하고 broadcast한 뒤 다음 턴 timer를 반환합니다."""
    event = await progress_service.timeout_turn_if_due(
        game_session_public_id=game_session_public_id,
        phase_id=phase_id,
        now=now,
    )
    if event is None:
        return None
    broadcast_messages = await broadcast_match_event_with_round_finished(
        manager=manager,
        event=event,
        now=now,
    )
    next_timer = next_match_timer_from_message(event.message)
    if ai_turn_service is not None and isinstance(next_timer, MatchTurnTimer):
        await append_ai_turn_if_needed(
            manager=manager,
            ai_turn_service=ai_turn_service,
            message=event.message,
            game_session_public_id=event.game_session_public_id,
            now=kst_now(),
            broadcast_messages=broadcast_messages,
        )
        next_timer = _next_timer_after_ai_messages(
            current_timer=next_timer,
            broadcast_messages=broadcast_messages,
        )
    return next_timer


def _next_timer_after_ai_messages(
    *,
    current_timer: MatchTimer | None,
    broadcast_messages: list[dict],
) -> MatchTimer | None:
    """AI 후속 broadcast 결과를 반영해 다음 서버 timer를 계산합니다."""
    next_timer = current_timer
    for message in broadcast_messages:
        message_timer = next_match_timer_from_message(message)
        if message_timer is not None:
            next_timer = message_timer
    return next_timer


async def process_match_vote_timeout(
    *,
    manager: MatchConnectionManager,
    vote_service: MatchVoteService,
    game_session_public_id: UUID,
    now: datetime,
) -> None:
    """투표 timeout을 확정하고 반환된 event들을 broadcast합니다."""
    events = await vote_service.timeout_vote(
        game_session_public_id=game_session_public_id,
        now=now,
    )
    for event in events:
        await manager.broadcast_session(event.game_session_public_id, event.message)
    return None
