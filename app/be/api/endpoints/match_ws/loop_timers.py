from datetime import datetime
from uuid import UUID

from app.be.services.match import (
    MatchTimer,
    MatchTurnTimer,
    MatchVotingTimer,
    match_connection_manager,
    next_match_timer_from_message,
    process_match_turn_timeout,
    process_match_vote_timeout,
)
from app.be.services.match_ai import MatchAiTurnService
from app.be.services.match_progress import MatchProgressService
from app.be.services.match_vote import MatchVoteService


async def process_due_match_timeout(
    *,
    match_timer: MatchTimer | None,
    match_progress_service: MatchProgressService,
    match_vote_service: MatchVoteService,
    match_ai_turn_service: MatchAiTurnService | None,
    game_session_public_id: UUID,
    now: datetime,
) -> MatchTimer | None:
    """현재 timer deadline이 지났으면 서버 권위 timeout 처리를 실행합니다."""
    if match_timer is None or now < match_timer.deadline_at:
        raise TimeoutError
    if isinstance(match_timer, MatchTurnTimer):
        return await process_match_turn_timeout(
            manager=match_connection_manager,
            progress_service=match_progress_service,
            ai_turn_service=match_ai_turn_service,
            game_session_public_id=game_session_public_id,
            phase_id=match_timer.phase_id,
            now=now,
        )
    if isinstance(match_timer, MatchVotingTimer):
        return await process_match_vote_timeout(
            manager=match_connection_manager,
            vote_service=match_vote_service,
            game_session_public_id=game_session_public_id,
            now=now,
        )
    raise TimeoutError


def next_match_timer_after_broadcasts(
    *,
    current_timer: MatchTimer | None,
    broadcast_messages: list[dict],
) -> MatchTimer | None:
    """broadcast message 목록을 반영해 다음 wait timeout 기준 timer를 계산합니다."""
    match_timer = current_timer
    for broadcast_message in broadcast_messages:
        next_match_timer = next_match_timer_from_message(broadcast_message)
        if next_match_timer is not None:
            match_timer = next_match_timer
        elif broadcast_message.get("payload", {}).get("next_status") is not None:
            match_timer = None
        elif broadcast_message.get("type") == "match.result.published":
            match_timer = None
    return match_timer
