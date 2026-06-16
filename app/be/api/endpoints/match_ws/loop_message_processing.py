from collections.abc import Mapping

from fastapi import WebSocket

from app.be.api.endpoints.match_ws.loop_audit import log_match_message_completed
from app.be.api.endpoints.match_ws.loop_metrics import (
    record_match_inbound_message,
    record_match_message_duration,
    record_match_outbound_messages,
)
from app.be.api.endpoints.match_ws.loop_timers import next_match_timer_after_broadcasts
from app.be.services.match import (
    MatchMessage,
    MatchTimer,
    handle_match_message,
    match_connection_manager,
)
from app.be.services.match_ai import MatchAiTurnService
from app.be.services.match_progress import MatchProgressService
from app.be.services.match_vote import MatchVoteService
from app.shared.core.observability import start_span
from app.shared.core.timezone import kst_now


async def process_match_loop_message(
    *,
    websocket: WebSocket,
    message: MatchMessage,
    current_timer: MatchTimer | None,
    metrics: object,
    match_progress_service: MatchProgressService,
    match_vote_service: MatchVoteService,
    match_ai_turn_service: MatchAiTurnService | None,
    service_name: str,
    peer: str | None,
    span_attributes: Mapping[str, str],
    started_at: float,
) -> MatchTimer | None:
    """파싱된 match WebSocket message 하나를 처리하고 다음 timer를 반환합니다.

    수신 metric, command handler 실행, outbound metric, 성공 audit을 한 흐름으로 묶어
    loop 본체가 반복/timeout/close 제어에 집중하게 합니다.
    """
    message_type = message["type"]
    record_match_inbound_message(metrics, message_type=message_type)
    with start_span(
        "WebSocket.match.message",
        attributes={**span_attributes, "ws.message.type": message_type},
    ):
        broadcast_messages = await handle_match_message(
            manager=match_connection_manager,
            websocket=websocket,
            message=message,
            progress_service=match_progress_service,
            vote_service=match_vote_service,
            ai_turn_service=match_ai_turn_service,
            now=kst_now(),
        )
    record_match_message_duration(
        metrics,
        message_type=message_type,
        started_at=started_at,
    )
    next_timer = next_match_timer_after_broadcasts(
        current_timer=current_timer,
        broadcast_messages=broadcast_messages,
    )
    record_match_outbound_messages(
        metrics,
        source_message_type=message_type,
        broadcast_messages=broadcast_messages,
    )
    log_match_message_completed(
        service_name=service_name,
        peer=peer,
        started_at=started_at,
        message_type=message_type,
        payload=message.get("payload"),
    )
    return next_timer
