import asyncio
from time import perf_counter
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.be.dependencies.services import get_auth_service, get_game_service
from app.be.repository.game import GameRepository
from app.be.services.auth import AuthService
from app.be.services.game import GameService
from app.be.services.lobby import (
    LOBBY_HEARTBEAT_TIMEOUT_SECONDS,
    LobbyDisconnect,
    handle_lobby_message,
    lobby_connection_manager,
    parse_lobby_message,
)
from app.shared.core.observability import get_websocket_metrics, start_span
from app.shared.core.exceptions import AppException
from app.shared.core.timezone import kst_now, to_kst_isoformat


router = APIRouter(prefix="/ws", tags=["websocket"])
LOBBY_WS_ROUTE = "/ws/lobby/rooms/{room_public_id}"
LOBBY_WS_ENDPOINT = "lobby"


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
    close_code = 1000
    connected_at = perf_counter()
    span_attributes = {
        "ws.route": LOBBY_WS_ROUTE,
        "ws.endpoint": LOBBY_WS_ENDPOINT,
    }
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
        metrics.record_error(
            ws_route=LOBBY_WS_ROUTE,
            ws_endpoint=LOBBY_WS_ENDPOINT,
            error_type=str(exc.code),
        )
        await websocket.close(code=exc.websocket_close_code)
        return

    await lobby_connection_manager.connect(websocket, current_user, connection.room_public_id)
    metrics.record_connect(ws_route=LOBBY_WS_ROUTE, ws_endpoint=LOBBY_WS_ENDPOINT)
    await lobby_connection_manager.send_connected(websocket)
    metrics.record_message(
        ws_route=LOBBY_WS_ROUTE,
        ws_endpoint=LOBBY_WS_ENDPOINT,
        message_type="lobby.room.connected",
        direction="outbound",
    )
    if connection.snapshot is not None:
        await lobby_connection_manager.send_snapshot(websocket, connection.snapshot)
        metrics.record_message(
            ws_route=LOBBY_WS_ROUTE,
            ws_endpoint=LOBBY_WS_ENDPOINT,
            message_type="lobby.room.snapshot",
            direction="outbound",
        )
    try:
        while True:
            raw_message = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=LOBBY_HEARTBEAT_TIMEOUT_SECONDS,
            )
            message = parse_lobby_message(raw_message)
            metrics.record_message(
                ws_route=LOBBY_WS_ROUTE,
                ws_endpoint=LOBBY_WS_ENDPOINT,
                message_type=message["type"],
                direction="inbound",
            )
            with start_span(
                "WebSocket.lobby.message",
                attributes={**span_attributes, "ws.message.type": message["type"]},
            ):
                await handle_lobby_message(
                    manager=lobby_connection_manager,
                    websocket=websocket,
                    message=message,
                )
            if message["type"] == "ping":
                metrics.record_message(
                    ws_route=LOBBY_WS_ROUTE,
                    ws_endpoint=LOBBY_WS_ENDPOINT,
                    message_type="lobby.pong",
                    direction="outbound",
                )
    except TimeoutError:
        close_code = 1001
        metrics.record_error(
            ws_route=LOBBY_WS_ROUTE,
            ws_endpoint=LOBBY_WS_ENDPOINT,
            error_type="heartbeat_timeout",
        )
        await websocket.close(code=1001)
    except WebSocketDisconnect as exc:
        close_code = exc.code
        pass
    except AppException as exc:
        close_code = exc.websocket_close_code
        metrics.record_error(
            ws_route=LOBBY_WS_ROUTE,
            ws_endpoint=LOBBY_WS_ENDPOINT,
            error_type=str(exc.code),
        )
        await lobby_connection_manager.send_error_and_close(websocket, exc)
    finally:
        with start_span(
            "WebSocket.lobby.disconnect",
            attributes={**span_attributes, "ws.close_code": close_code},
        ):
            disconnect = lobby_connection_manager.disconnect(websocket)
            metrics.record_disconnect(
                ws_route=LOBBY_WS_ROUTE,
                ws_endpoint=LOBBY_WS_ENDPOINT,
                close_code=close_code,
            )
            metrics.record_duration(
                ws_route=LOBBY_WS_ROUTE,
                ws_endpoint=LOBBY_WS_ENDPOINT,
                duration_seconds=perf_counter() - connected_at,
                close_code=close_code,
            )
            if disconnect is not None:
                schedule_room_leave_after_grace(websocket, disconnect)


def schedule_room_leave_after_grace(websocket: WebSocket, disconnect: LobbyDisconnect) -> None:
    """grace timeout 이후에도 복귀하지 않은 유저를 DB에서 방 퇴장 처리하도록 예약합니다."""
    sessionmaker = getattr(websocket.app.state, "db_sessionmaker", None)
    if sessionmaker is None:
        return

    async def leave_after_grace(disconnect: LobbyDisconnect) -> None:
        with start_span(
            "WebSocket.lobby.grace_leave",
            attributes={
                "ws.route": LOBBY_WS_ROUTE,
                "ws.endpoint": LOBBY_WS_ENDPOINT,
            },
        ):
            async with sessionmaker() as db_session:
                game_service = GameService(GameRepository(db_session))
                result = await game_service.leave_room_after_disconnect_grace(
                    room_public_id=disconnect.room_public_id,
                    user=disconnect.user,
                    left_at=kst_now(),
                )
        if result is None:
            return
        await lobby_connection_manager.broadcast_room(
            result.room_public_id,
            {
                "type": "lobby.room.left",
                "payload": {
                    "room_public_id": str(result.room_public_id),
                    "user_public_id": str(result.user_public_id),
                    "nickname": result.nickname,
                    "left_at": to_kst_isoformat(result.left_at),
                    "remaining_member_count": result.remaining_member_count,
                    "new_owner_user_public_id": (
                        str(result.new_owner_user_public_id)
                        if result.new_owner_user_public_id
                        else None
                    ),
                    "new_owner_nickname": result.new_owner_nickname,
                    "room_closed": result.room_closed,
                },
            },
        )
        metrics = get_websocket_metrics(websocket.app)
        metrics.record_message(
            ws_route=LOBBY_WS_ROUTE,
            ws_endpoint=LOBBY_WS_ENDPOINT,
            message_type="lobby.room.left",
            direction="outbound",
        )

    lobby_connection_manager.schedule_grace_leave(disconnect, leave_after_grace)
