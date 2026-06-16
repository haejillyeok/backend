import asyncio
from datetime import datetime
from typing import Awaitable, Callable

from app.be.services.match.connection_manager import MatchConnectionManager, MatchMessage
from app.be.services.match.round_event_messages import (
    round_finished_message_from_turn_resolved,
    round_started_message_from_turn_resolved,
)
from app.be.services.match.round_event_timing import seconds_until_round_started
from app.be.services.match_progress import MatchBroadcastEvent
from app.shared.core.timezone import kst_now


async def broadcast_match_event_with_round_finished(
    *,
    manager: MatchConnectionManager,
    event: MatchBroadcastEvent,
    now: datetime | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> list[MatchMessage]:
    """진행 event를 broadcast하고, 라운드 종료가 포함되면 별도 event를 이어서 전송합니다."""
    await manager.broadcast_session(event.game_session_public_id, event.message)
    messages = [event.message]
    round_finished_message = round_finished_message_from_turn_resolved(event.message)
    if round_finished_message is not None:
        await manager.broadcast_session(event.game_session_public_id, round_finished_message)
        messages.append(round_finished_message)
    round_started_message = round_started_message_from_turn_resolved(event.message)
    if round_started_message is not None:
        delay_seconds = seconds_until_round_started(round_started_message, now=now or kst_now())
        if delay_seconds > 0:
            await sleep(delay_seconds)
        await manager.broadcast_session(event.game_session_public_id, round_started_message)
        messages.append(round_started_message)
    return messages
