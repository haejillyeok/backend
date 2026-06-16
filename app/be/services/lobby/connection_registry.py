from datetime import datetime
from uuid import UUID

from fastapi import WebSocket

from app.be.services.auth import CurrentUser
from app.be.services.lobby.records import LobbyConnection
from app.shared.core.timezone import kst_now


def register_lobby_connection(
    *,
    websocket: WebSocket,
    user: CurrentUser,
    room_public_id: UUID,
    connections: dict[WebSocket, LobbyConnection],
    user_connections: dict[UUID, set[WebSocket]],
    room_subscriptions: dict[UUID, set[WebSocket]],
    now: datetime | None = None,
) -> None:
    """인증된 로비 WebSocket을 유저/room registry에 등록합니다."""
    connections[websocket] = LobbyConnection(
        user=user,
        room_public_id=room_public_id,
        last_seen_at=now or kst_now(),
    )
    user_connections.setdefault(user.id, set()).add(websocket)
    room_subscriptions.setdefault(room_public_id, set()).add(websocket)


def remove_lobby_connection(
    *,
    websocket: WebSocket,
    connections: dict[WebSocket, LobbyConnection],
    user_connections: dict[UUID, set[WebSocket]],
    room_subscriptions: dict[UUID, set[WebSocket]],
) -> LobbyConnection | None:
    """로비 WebSocket을 모든 registry에서 제거하고 기존 연결 정보를 반환합니다."""
    connection = connections.pop(websocket, None)
    if connection is not None:
        user_websockets = user_connections.get(connection.user.id)
        if user_websockets is not None:
            user_websockets.discard(websocket)
            if not user_websockets:
                user_connections.pop(connection.user.id, None)

    empty_rooms = []
    for room_public_id, subscribers in room_subscriptions.items():
        subscribers.discard(websocket)
        if not subscribers:
            empty_rooms.append(room_public_id)
    for room_public_id in empty_rooms:
        room_subscriptions.pop(room_public_id, None)
    return connection


def record_lobby_heartbeat(
    *,
    websocket: WebSocket,
    connections: dict[WebSocket, LobbyConnection],
    now: datetime | None = None,
) -> None:
    """ping 수신 시각을 연결 registry의 heartbeat 기준으로 갱신합니다."""
    connection = connections[websocket]
    connections[websocket] = LobbyConnection(
        user=connection.user,
        room_public_id=connection.room_public_id,
        last_seen_at=now or kst_now(),
    )


def is_lobby_heartbeat_expired(
    *,
    websocket: WebSocket,
    connections: dict[WebSocket, LobbyConnection],
    now: datetime | None = None,
    timeout_seconds: int,
) -> bool:
    """마지막 heartbeat가 timeout 기준을 넘었는지 확인합니다."""
    connection = connections[websocket]
    return ((now or kst_now()) - connection.last_seen_at).total_seconds() > timeout_seconds


def has_active_room_connection(
    *,
    room_public_id: UUID,
    user_id: UUID,
    connections: dict[WebSocket, LobbyConnection],
) -> bool:
    """같은 유저가 같은 room에 여전히 active WebSocket을 갖고 있는지 확인합니다."""
    return any(
        connection.room_public_id == room_public_id and connection.user.id == user_id
        for connection in connections.values()
    )
