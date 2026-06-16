from fastapi import WebSocket

from app.be.services.lobby.connection_manager import LobbyConnectionManager
from app.be.services.lobby.records import LobbyMessage
from app.be.services.realtime import parse_realtime_message
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


def parse_lobby_message(raw_message: str) -> LobbyMessage:
    """WebSocket text frame을 lobby JSON envelope로 파싱하고 검증합니다."""
    return parse_realtime_message(raw_message)


async def handle_lobby_message(
    *,
    manager: LobbyConnectionManager,
    websocket: WebSocket,
    message: LobbyMessage,
) -> None:
    """`/ws/lobby/rooms/{room_public_id}` WebSocket message type을 처리합니다.

    현재 공개 계약은 연결 확인용 `ping`입니다. room event 구독은 path의 room public_id로 연결할
    때 자동 등록됩니다.
    """
    if message["type"] == "ping":
        manager.record_heartbeat(websocket)
        await manager.send(websocket, {"type": "lobby.pong", "payload": message["payload"]})
        return

    raise AppException(
        code=ErrorCode.VALIDATION_ERROR,
        details={"reason": "unsupported_message_type", "type": message["type"]},
    )
