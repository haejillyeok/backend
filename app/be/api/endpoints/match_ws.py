import asyncio
from time import perf_counter
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from app.be.dependencies.database import get_db_session
from app.be.dependencies.services import (
    get_auth_service,
    get_game_service,
    get_optional_match_ai_turn_service,
    get_match_progress_service,
    get_match_service,
    get_match_vote_service,
)
from app.be.services.auth import AuthService
from app.be.services.game import GameService
from app.be.services.match import (
    MatchService,
    MatchTurnTimer,
    MatchVotingTimer,
    current_match_timer_from_snapshot,
    handle_match_message,
    match_connection_manager,
    next_match_timer_from_message,
    parse_match_message,
    process_match_turn_timeout,
    process_match_vote_timeout,
    seconds_until_match_wait_timeout,
)
from app.be.services.match_ai import MatchAiTurnService
from app.be.services.match_progress import MatchProgressService
from app.be.services.match_vote import MatchVoteService
from app.shared.core.audit import AuditEvent, log_audit_event
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException
from app.shared.core.observability import get_websocket_metrics, start_span
from app.shared.core.timezone import kst_now


router = APIRouter(prefix="/ws", tags=["websocket"])
MATCH_WS_ROUTE = "/ws/match"
MATCH_WS_ENDPOINT = "match"


@router.websocket("/match")
async def match_websocket(
    websocket: WebSocket,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    game_service: Annotated[GameService, Depends(get_game_service)],
    match_service: Annotated[MatchService, Depends(get_match_service)],
    match_progress_service: Annotated[
        MatchProgressService,
        Depends(get_match_progress_service),
    ],
    match_vote_service: Annotated[
        MatchVoteService,
        Depends(get_match_vote_service),
    ],
    match_ai_turn_service: Annotated[
        MatchAiTurnService | None,
        Depends(get_optional_match_ai_turn_service),
    ],
    db_session: Annotated[AsyncSession, Depends(get_db_session)],
    game_session_public_id: UUID | None = Query(default=None),
    game_session_token: str | None = Query(default=None),
) -> None:
    """게임 세션 참가자의 match WebSocket 연결을 열고 현재 snapshot을 전송합니다."""
    metrics = get_websocket_metrics(websocket.app)
    service_name = websocket.app.title
    peer = websocket.client.host if websocket.client else None
    close_code = 1000
    connected_at = perf_counter()
    span_attributes = {
        "ws.route": MATCH_WS_ROUTE,
        "ws.endpoint": MATCH_WS_ENDPOINT,
    }
    log_audit_event(
        AuditEvent(
            protocol="websocket",
            phase="started",
            service=service_name,
            operation="CONNECT /ws/match",
            peer=peer,
        )
    )
    try:
        with start_span("WebSocket.match.connect", attributes=span_attributes):
            if game_session_token:
                entry = await game_service.authorize_resume_token(game_session_token)
            elif game_session_public_id is not None:
                current_user = await auth_service.authenticate_session(
                    websocket.cookies.get("session_token")
                )
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
            # WebSocket loop가 오래 유지되어도 인증/권한 확인용 transaction은 붙잡지 않습니다.
            await db_session.rollback()
    except AppException as exc:
        log_audit_event(
            AuditEvent(
                protocol="websocket",
                phase="failed",
                service=service_name,
                operation="CONNECT /ws/match",
                status_code=str(exc.websocket_close_code),
                duration_ms=(perf_counter() - connected_at) * 1000,
                peer=peer,
                error_code=str(exc.code),
            )
        )
        metrics.record_error(
            ws_route=MATCH_WS_ROUTE,
            ws_endpoint=MATCH_WS_ENDPOINT,
            error_type=str(exc.code),
        )
        await websocket.close(code=exc.websocket_close_code)
        return

    await match_connection_manager.connect(
        websocket,
        game_session_public_id=entry.game_session_public_id,
        participant_id=participant_id,
        participant=entry.participant,
    )
    log_audit_event(
        AuditEvent(
            protocol="websocket",
            phase="completed",
            service=service_name,
            operation="CONNECT /ws/match",
            status_code="101",
            duration_ms=(perf_counter() - connected_at) * 1000,
            peer=peer,
        )
    )
    metrics.record_connect(ws_route=MATCH_WS_ROUTE, ws_endpoint=MATCH_WS_ENDPOINT)
    await match_connection_manager.send_connected(websocket)
    metrics.record_message(
        ws_route=MATCH_WS_ROUTE,
        ws_endpoint=MATCH_WS_ENDPOINT,
        message_type="match.connected",
        direction="outbound",
    )
    await match_connection_manager.send_snapshot(websocket, snapshot)
    metrics.record_message(
        ws_route=MATCH_WS_ROUTE,
        ws_endpoint=MATCH_WS_ENDPOINT,
        message_type="match.snapshot",
        direction="outbound",
    )
    match_timer = current_match_timer_from_snapshot(snapshot)
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
                if match_timer is not None and now >= match_timer.deadline_at:
                    if isinstance(match_timer, MatchTurnTimer):
                        match_timer = await process_match_turn_timeout(
                            manager=match_connection_manager,
                            progress_service=match_progress_service,
                            ai_turn_service=match_ai_turn_service,
                            game_session_public_id=entry.game_session_public_id,
                            phase_id=match_timer.phase_id,
                            now=now,
                        )
                        continue
                    if isinstance(match_timer, MatchVotingTimer):
                        match_timer = await process_match_vote_timeout(
                            manager=match_connection_manager,
                            vote_service=match_vote_service,
                            game_session_public_id=entry.game_session_public_id,
                            now=now,
                        )
                        continue
                raise
            message_started_at = perf_counter()
            message = parse_match_message(raw_message)
            message_type = message["type"]
            message_payload = message.get("payload")
            metrics.record_message(
                ws_route=MATCH_WS_ROUTE,
                ws_endpoint=MATCH_WS_ENDPOINT,
                message_type=message["type"],
                direction="inbound",
            )
            with start_span(
                "WebSocket.match.message",
                attributes={**span_attributes, "ws.message.type": message["type"]},
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
            metrics.record_message_duration(
                ws_route=MATCH_WS_ROUTE,
                ws_endpoint=MATCH_WS_ENDPOINT,
                message_type=message["type"],
                duration_seconds=perf_counter() - message_started_at,
            )
            for broadcast_message in broadcast_messages:
                next_match_timer = next_match_timer_from_message(broadcast_message)
                if next_match_timer is not None:
                    match_timer = next_match_timer
                elif broadcast_message.get("payload", {}).get("next_status") is not None:
                    match_timer = None
                elif broadcast_message.get("type") == "match.result.published":
                    match_timer = None
            if message["type"] == "ping":
                metrics.record_message(
                    ws_route=MATCH_WS_ROUTE,
                    ws_endpoint=MATCH_WS_ENDPOINT,
                    message_type="match.pong",
                    direction="outbound",
                )
            for broadcast_message in broadcast_messages:
                broadcast_message_type = broadcast_message.get("type")
                if not isinstance(broadcast_message_type, str):
                    continue
                metrics.record_message(
                    ws_route=MATCH_WS_ROUTE,
                    ws_endpoint=MATCH_WS_ENDPOINT,
                    message_type=broadcast_message_type,
                    direction="outbound",
                )
            log_audit_event(
                AuditEvent(
                    protocol="websocket",
                    phase="completed",
                    service=service_name,
                    operation="MESSAGE /ws/match",
                    status_code="200",
                    duration_ms=(perf_counter() - message_started_at) * 1000,
                    peer=peer,
                    message_type=message_type,
                    direction="inbound",
                    payload=message_payload,
                )
            )
    except TimeoutError:
        close_code = 1001
        metrics.record_error(
            ws_route=MATCH_WS_ROUTE,
            ws_endpoint=MATCH_WS_ENDPOINT,
            error_type="heartbeat_timeout",
        )
        await websocket.close(code=1001)
    except WebSocketDisconnect as exc:
        close_code = exc.code
    except AppException as exc:
        close_code = exc.websocket_close_code
        log_audit_event(
            AuditEvent(
                protocol="websocket",
                phase="failed",
                service=service_name,
                operation="MESSAGE /ws/match",
                status_code=str(exc.websocket_close_code),
                duration_ms=(
                    (perf_counter() - message_started_at) * 1000
                    if message_started_at is not None
                    else None
                ),
                peer=peer,
                error_code=str(exc.code),
                message_type=message_type,
                direction="inbound",
                payload=message_payload,
            )
        )
        metrics.record_error(
            ws_route=MATCH_WS_ROUTE,
            ws_endpoint=MATCH_WS_ENDPOINT,
            error_type=str(exc.code),
        )
        await match_connection_manager.send_error_and_close(websocket, exc)
    finally:
        with start_span(
            "WebSocket.match.disconnect",
            attributes={**span_attributes, "ws.close_code": close_code},
        ):
            match_connection_manager.disconnect(websocket)
            metrics.record_disconnect(
                ws_route=MATCH_WS_ROUTE,
                ws_endpoint=MATCH_WS_ENDPOINT,
                close_code=close_code,
            )
            metrics.record_duration(
                ws_route=MATCH_WS_ROUTE,
                ws_endpoint=MATCH_WS_ENDPOINT,
                duration_seconds=perf_counter() - connected_at,
                close_code=close_code,
            )
            log_audit_event(
                AuditEvent(
                    protocol="websocket",
                    phase="completed",
                    service=service_name,
                    operation="DISCONNECT /ws/match",
                    status_code=str(close_code),
                    duration_ms=(perf_counter() - connected_at) * 1000,
                    peer=peer,
                )
            )
