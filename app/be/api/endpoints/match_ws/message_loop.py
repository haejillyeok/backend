import asyncio
from time import perf_counter
from uuid import UUID

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.be.api.endpoints.match_ws.loop_audit import log_match_message_failed
from app.be.api.endpoints.match_ws.loop_metrics import (
    record_match_loop_error,
)
from app.be.api.endpoints.match_ws.loop_message_processing import process_match_loop_message
from app.be.api.endpoints.match_ws.loop_timers import (
    process_due_match_timeout,
)
from app.be.services.game import GameSessionParticipantRecord
from app.be.services.match import (
    current_match_timer_from_snapshot,
    match_connection_manager,
    parse_match_message,
    seconds_until_match_wait_timeout,
)
from app.be.services.match_ai import MatchAiTurnService
from app.be.services.match_progress import MatchProgressService
from app.be.services.match_vote import MatchVoteService
from app.shared.core.exceptions import AppException
from app.shared.core.observability import get_websocket_metrics
from app.shared.core.timezone import kst_now


async def run_match_message_loop(
    *,
    websocket: WebSocket,
    game_session_public_id: UUID,
    participant: GameSessionParticipantRecord,
    initial_snapshot: dict,
    match_progress_service: MatchProgressService,
    match_vote_service: MatchVoteService,
    match_ai_turn_service: MatchAiTurnService | None,
    service_name: str,
    peer: str | None,
    span_attributes: dict[str, str],
) -> int:
    """match WebSocket 수신 loop를 실행하고 최종 close code를 반환합니다.

    endpoint는 연결 인증과 lifecycle wiring만 맡고, 이 함수가 client message 처리, timeout 처리,
    outbound metric, message audit을 담당합니다.
    """
    metrics = get_websocket_metrics(websocket.app)
    close_code = 1000
    match_timer = current_match_timer_from_snapshot(initial_snapshot)
    message_started_at: float | None = None
    message_type: str | None = None
    message_payload: object | None = None
    try:
        while True:
            now = kst_now()
            receive_timeout = seconds_until_match_wait_timeout(match_timer, now=now)
            try:
                raw_message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=receive_timeout,
                )
            except TimeoutError:
                now = kst_now()
                match_timer = await process_due_match_timeout(
                    match_timer=match_timer,
                    match_progress_service=match_progress_service,
                    match_vote_service=match_vote_service,
                    match_ai_turn_service=match_ai_turn_service,
                    game_session_public_id=game_session_public_id,
                    now=now,
                )
                continue
            message_started_at = perf_counter()
            message = parse_match_message(raw_message)
            message_type = message["type"]
            message_payload = message.get("payload")
            match_timer = await process_match_loop_message(
                websocket=websocket,
                message=message,
                current_timer=match_timer,
                metrics=metrics,
                match_progress_service=match_progress_service,
                match_vote_service=match_vote_service,
                match_ai_turn_service=match_ai_turn_service,
                service_name=service_name,
                peer=peer,
                span_attributes=span_attributes,
                started_at=message_started_at,
            )
    except TimeoutError:
        close_code = 1001
        record_match_loop_error(metrics, error_type="heartbeat_timeout")
        await websocket.close(code=1001)
    except WebSocketDisconnect as exc:
        close_code = exc.code
    except AppException as exc:
        close_code = exc.websocket_close_code
        log_match_message_failed(
            service_name=service_name,
            peer=peer,
            started_at=message_started_at,
            error_code=str(exc.code),
            close_code=exc.websocket_close_code,
            message_type=message_type,
            payload=message_payload,
        )
        record_match_loop_error(metrics, error_type=str(exc.code))
        await match_connection_manager.send_error_and_close(websocket, exc)
    return close_code
