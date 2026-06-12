import asyncio
from datetime import UTC, datetime
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
from app.shared.core.exceptions import AppException


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
    try:
        current_user = await auth_service.authenticate_session(
            websocket.cookies.get("session_token")
        )
        connection = await game_service.authorize_room_lobby_connection(
            room_public_id=room_public_id,
            user_id=current_user.id,
        )
    except AppException as exc:
        await websocket.close(code=exc.websocket_close_code)
        return

    await lobby_connection_manager.connect(websocket, current_user, connection.room_public_id)
    await lobby_connection_manager.send_connected(websocket)
    try:
        while True:
            raw_message = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=LOBBY_HEARTBEAT_TIMEOUT_SECONDS,
            )
            message = parse_lobby_message(raw_message)
            await handle_lobby_message(
                manager=lobby_connection_manager,
                websocket=websocket,
                message=message,
            )
    except TimeoutError:
        await websocket.close(code=1001)
    except WebSocketDisconnect:
        pass
    except AppException as exc:
        await lobby_connection_manager.send_error_and_close(websocket, exc)
    finally:
        disconnect = lobby_connection_manager.disconnect(websocket)
        if disconnect is not None:
            schedule_room_leave_after_grace(websocket, disconnect)


def schedule_room_leave_after_grace(websocket: WebSocket, disconnect: LobbyDisconnect) -> None:
    """grace timeout 이후에도 복귀하지 않은 유저를 DB에서 방 퇴장 처리하도록 예약합니다."""
    sessionmaker = getattr(websocket.app.state, "db_sessionmaker", None)
    if sessionmaker is None:
        return

    async def leave_after_grace(disconnect: LobbyDisconnect) -> None:
        async with sessionmaker() as db_session:
            game_service = GameService(GameRepository(db_session))
            result = await game_service.leave_room_after_disconnect_grace(
                room_public_id=disconnect.room_public_id,
                user=disconnect.user,
                left_at=datetime.now(UTC),
            )
        if result is None:
            return
        await lobby_connection_manager.broadcast_room(
            result.room_public_id,
            {
                "type": "lobby.room.left",
                "payload": {
                    "room_public_id": result.room_public_id,
                    "user_public_id": result.user_public_id,
                    "nickname": result.nickname,
                    "left_at": result.left_at,
                },
            },
        )

    lobby_connection_manager.schedule_grace_leave(disconnect, leave_after_grace)
