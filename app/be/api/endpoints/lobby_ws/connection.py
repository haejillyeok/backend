from time import perf_counter
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket

from app.be.api.endpoints.lobby_ws.connection_audit import (
    log_lobby_connect_completed,
    log_lobby_connect_failed,
    log_lobby_connect_started,
    log_lobby_disconnect_completed,
)
from app.be.api.endpoints.lobby_ws.connection_metrics import (
    record_lobby_connect,
    record_lobby_connect_error,
    record_lobby_disconnect,
    record_lobby_initial_messages,
)
from app.be.api.endpoints.lobby_ws.constants import LOBBY_WS_ENDPOINT, LOBBY_WS_ROUTE
from app.be.api.endpoints.lobby_ws.grace_leave import schedule_room_leave_after_grace
from app.be.api.endpoints.lobby_ws.message_loop import run_lobby_message_loop
from app.be.dependencies.services import get_auth_service, get_game_service
from app.be.services.auth import AuthService
from app.be.services.game import GameService
from app.be.services.lobby import lobby_connection_manager
from app.shared.core.exceptions import AppException
from app.shared.core.observability import get_websocket_metrics, start_span


router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/lobby/rooms/{room_public_id}")
async def lobby_websocket(
    room_public_id: UUID,
    websocket: WebSocket,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    game_service: Annotated[GameService, Depends(get_game_service)],
) -> None:
    """인증된 유저의 room 로비 WebSocket 연결을 열고 path의 room event를 구독합니다.

    연결 시점에 `session_token` 쿠키로 로그인 세션을 검증하고, path의 `room_public_id`에 대해
    활성 room member인지 확인합니다. 연결 후에는 해당 room event를 자동 구독합니다.
    """
    metrics = get_websocket_metrics(websocket.app)
    service_name = websocket.app.title
    peer = websocket.client.host if websocket.client else None
    connected_at = perf_counter()
    span_attributes = {
        "ws.route": LOBBY_WS_ROUTE,
        "ws.endpoint": LOBBY_WS_ENDPOINT,
    }
    log_lobby_connect_started(service_name=service_name, peer=peer)
    try:
        with start_span("WebSocket.lobby.connect", attributes=span_attributes):
            current_user = await auth_service.authenticate_session(
                websocket.cookies.get("session_token")
            )
            connection = await game_service.authorize_room_lobby_connection(
                room_public_id=room_public_id,
                user_id=current_user.id,
            )
    except AppException as exc:
        log_lobby_connect_failed(
            service_name=service_name,
            peer=peer,
            connected_at=connected_at,
            close_code=exc.websocket_close_code,
            error_code=str(exc.code),
        )
        record_lobby_connect_error(metrics, error_type=str(exc.code))
        await websocket.close(code=exc.websocket_close_code)
        return

    await lobby_connection_manager.connect(websocket, current_user, connection.room_public_id)
    log_lobby_connect_completed(
        service_name=service_name,
        peer=peer,
        connected_at=connected_at,
    )
    record_lobby_connect(metrics)
    await lobby_connection_manager.send_connected(websocket)
    if connection.snapshot is not None:
        await lobby_connection_manager.send_snapshot(websocket, connection.snapshot)
    record_lobby_initial_messages(metrics, includes_snapshot=connection.snapshot is not None)

    close_code = await run_lobby_message_loop(
        websocket=websocket,
        service_name=service_name,
        peer=peer,
        span_attributes=span_attributes,
    )
    with start_span(
        "WebSocket.lobby.disconnect",
        attributes={**span_attributes, "ws.close_code": close_code},
    ):
        disconnect = lobby_connection_manager.disconnect(websocket)
        record_lobby_disconnect(
            metrics,
            connected_at=connected_at,
            close_code=close_code,
        )
        log_lobby_disconnect_completed(
            service_name=service_name,
            peer=peer,
            connected_at=connected_at,
            close_code=close_code,
        )
        if disconnect is not None:
            schedule_room_leave_after_grace(websocket, disconnect, game_service)
