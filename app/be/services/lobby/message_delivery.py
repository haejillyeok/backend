from collections.abc import Callable
from uuid import UUID

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocketDisconnect

from app.be.services.lobby.records import LobbyMessage
from app.shared.core.exceptions import AppException


async def send_lobby_message(websocket: WebSocket, message: LobbyMessage) -> None:
    """특정 로비 WebSocket으로 JSON envelope 메시지를 전송합니다."""
    await websocket.send_json(jsonable_encoder(message))


async def send_lobby_error_and_close(websocket: WebSocket, error: AppException) -> None:
    """오류 envelope를 전송한 뒤 오류 정의에 맞는 WebSocket close code로 닫습니다."""
    await send_lobby_message(websocket, {"type": "error", "payload": error.to_error_payload()})
    await websocket.close(code=error.websocket_close_code)


async def broadcast_lobby_room(
    *,
    room_public_id: UUID,
    message: LobbyMessage,
    room_subscriptions: dict[UUID, set[WebSocket]],
    disconnect_stale_websocket: Callable[[WebSocket], object],
) -> None:
    """room 구독자에게 이벤트를 전송하고, 이미 닫힌 연결은 registry에서 제거합니다."""
    for websocket in list(room_subscriptions.get(room_public_id, set())):
        try:
            await send_lobby_message(websocket, message)
        except (RuntimeError, WebSocketDisconnect):
            disconnect_stale_websocket(websocket)
