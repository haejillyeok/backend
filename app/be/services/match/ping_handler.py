from datetime import datetime

from fastapi import WebSocket

from app.be.services.match.connection_manager import MatchConnectionManager, MatchMessage


async def handle_ping_message(
    *,
    manager: MatchConnectionManager,
    websocket: WebSocket,
    message: MatchMessage,
    now: datetime,
) -> list[MatchMessage]:
    """match ping message에 server_time을 더해 pong을 전송합니다."""
    payload = dict(message["payload"])
    payload["server_time"] = now
    await manager.send(websocket, {"type": "match.pong", "payload": payload})
    return []
