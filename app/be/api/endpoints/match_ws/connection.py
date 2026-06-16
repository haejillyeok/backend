from time import perf_counter
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket

from app.be.api.endpoints.match_ws.connection_audit import (
    log_match_connect_failed,
    log_match_connect_started,
)
from app.be.api.endpoints.match_ws.connection_metrics import (
    record_match_connect_error,
)
from app.be.api.endpoints.match_ws.connection_lifecycle import (
    accept_match_connection,
    disconnect_match_connection,
)
from app.be.api.endpoints.match_ws.constants import MATCH_WS_ENDPOINT, MATCH_WS_ROUTE
from app.be.api.endpoints.match_ws.handshake import authorize_match_handshake
from app.be.api.endpoints.match_ws.message_loop import run_match_message_loop
from app.be.dependencies.services import (
    get_auth_service,
    get_game_service,
    get_match_progress_service,
    get_match_service,
    get_match_vote_service,
    get_optional_match_ai_turn_service,
)
from app.be.services.auth import AuthService
from app.be.services.game import GameService
from app.be.services.match import MatchService
from app.be.services.match_ai import MatchAiTurnService
from app.be.services.match_progress import MatchProgressService
from app.be.services.match_vote import MatchVoteService
from app.shared.core.exceptions import AppException
from app.shared.core.observability import get_websocket_metrics, start_span


router = APIRouter(prefix="/ws", tags=["websocket"])


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
    game_session_public_id: UUID | None = Query(default=None),
    game_session_token: str | None = Query(default=None),
) -> None:
    """게임 세션 참가자의 match WebSocket 연결을 열고 현재 snapshot을 전송합니다."""
    metrics = get_websocket_metrics(websocket.app)
    service_name = websocket.app.title
    peer = websocket.client.host if websocket.client else None
    connected_at = perf_counter()
    span_attributes = {
        "ws.route": MATCH_WS_ROUTE,
        "ws.endpoint": MATCH_WS_ENDPOINT,
    }
    log_match_connect_started(service_name=service_name, peer=peer)
    try:
        with start_span("WebSocket.match.connect", attributes=span_attributes):
            handshake = await authorize_match_handshake(
                auth_service=auth_service,
                game_service=game_service,
                match_service=match_service,
                session_token=websocket.cookies.get("session_token"),
                game_session_public_id=game_session_public_id,
                game_session_token=game_session_token,
            )
    except AppException as exc:
        log_match_connect_failed(
            service_name=service_name,
            peer=peer,
            connected_at=connected_at,
            close_code=exc.websocket_close_code,
            error_code=str(exc.code),
        )
        record_match_connect_error(metrics, error_type=str(exc.code))
        await websocket.close(code=exc.websocket_close_code)
        return

    await accept_match_connection(
        websocket=websocket,
        handshake=handshake,
        metrics=metrics,
        service_name=service_name,
        peer=peer,
        connected_at=connected_at,
    )
    close_code = await run_match_message_loop(
        websocket=websocket,
        game_session_public_id=handshake.entry.game_session_public_id,
        participant=handshake.entry.participant,
        initial_snapshot=handshake.snapshot,
        match_progress_service=match_progress_service,
        match_vote_service=match_vote_service,
        match_ai_turn_service=match_ai_turn_service,
        service_name=service_name,
        peer=peer,
        span_attributes=span_attributes,
    )
    disconnect_match_connection(
        websocket=websocket,
        metrics=metrics,
        service_name=service_name,
        peer=peer,
        connected_at=connected_at,
        close_code=close_code,
        span_attributes=span_attributes,
    )
