import asyncio
from datetime import datetime
from typing import Awaitable, Callable

from app.be.services.match.broadcasters import broadcast_match_event_with_round_finished
from app.be.services.match.connection_manager import MatchConnectionManager, MatchMessage
from app.be.services.match.message_helpers import extract_next_turn_phase_id
from app.be.services.match_ai import MatchAiTurnService


AI_EMPTY_ANSWER_RETRY_DELAY_SECONDS = 1.0
AI_EMPTY_ANSWER_MAX_RETRIES = 1


async def append_ai_turn_if_needed(
    *,
    manager: MatchConnectionManager,
    ai_turn_service: MatchAiTurnService | None,
    message: MatchMessage,
    game_session_public_id,
    now: datetime,
    broadcast_messages: list[MatchMessage],
    retry_delay_seconds: float = AI_EMPTY_ANSWER_RETRY_DELAY_SECONDS,
    max_empty_answer_retries: int = AI_EMPTY_ANSWER_MAX_RETRIES,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """다음 턴이 AI이면 즉시 AI 제출을 진행하고 broadcast 메시지 목록에 추가합니다."""
    if ai_turn_service is None:
        return
    next_phase_id = extract_next_turn_phase_id(message)
    if next_phase_id is None:
        return
    for retry_index in range(max_empty_answer_retries + 1):
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
        if not _is_empty_ai_answer_event(ai_event.message):
            return
        if retry_index >= max_empty_answer_retries:
            return
        await sleep(retry_delay_seconds)


def _is_empty_ai_answer_event(message: MatchMessage) -> bool:
    """Agent 빈 응답을 공개 실패 event로 보낸 경우 재요청 대상으로 판단합니다."""
    payload = message.get("payload")
    return (
        isinstance(payload, dict)
        and payload.get("result") == "failed"
        and payload.get("word") == ""
    )
