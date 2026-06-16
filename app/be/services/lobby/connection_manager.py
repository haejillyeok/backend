from datetime import datetime
from uuid import UUID

from fastapi import WebSocket

from app.be.services.auth import CurrentUser
from app.be.services.game import RoomLobbySnapshotResult
from app.be.services.lobby.connection_messages import (
    lobby_connected_message,
    lobby_snapshot_message,
)
from app.be.services.lobby.connection_registry import (
    has_active_room_connection,
    is_lobby_heartbeat_expired,
    record_lobby_heartbeat,
    register_lobby_connection,
    remove_lobby_connection,
)
from app.be.services.lobby.constants import (
    LOBBY_DISCONNECT_GRACE_SECONDS,
    LOBBY_HEARTBEAT_TIMEOUT_SECONDS,
)
from app.be.services.lobby.grace_leave_tasks import (
    cancel_pending_grace_leave,
    schedule_grace_leave_task,
)
from app.be.services.lobby.records import (
    GraceLeaveCallback,
    LobbyConnection,
    LobbyDisconnect,
    LobbyMessage,
)
from app.be.services.lobby.message_delivery import (
    broadcast_lobby_room,
    send_lobby_error_and_close,
    send_lobby_message,
)
from app.shared.core.exceptions import AppException


class LobbyConnectionManager:
    """로비 WebSocket 연결, 유저 identity, room 구독 registry를 관리합니다.

    주요 입력은 인증된 `CurrentUser`, FastAPI `WebSocket`, room public_id입니다. 연결 수락,
    path 기반 room 구독 등록, JSON event 송신이 부작용입니다. room membership 자체는 DB의
    `game.room_members`가 최종 사실이고, 이 manager는 process-local 연결 상태만 보관합니다.
    """

    def __init__(self) -> None:
        self._connections: dict[WebSocket, LobbyConnection] = {}
        self._user_connections: dict[UUID, set[WebSocket]] = {}
        self._room_subscriptions: dict[UUID, set[WebSocket]] = {}
        self._pending_grace_leaves = {}

    @property
    def connection_count(self) -> int:
        """현재 로비 manager에 등록된 active WebSocket 연결 수를 반환합니다."""
        return len(self._connections)

    def room_subscription_count(self, room_public_id: UUID) -> int:
        """특정 room을 구독 중인 active WebSocket 연결 수를 반환합니다."""
        return len(self._room_subscriptions.get(room_public_id, set()))

    @property
    def pending_grace_leave_count(self) -> int:
        """grace time 만료를 기다리는 퇴장 처리 task 수를 반환합니다."""
        return len(self._pending_grace_leaves)

    async def connect(
        self,
        websocket: WebSocket,
        user: CurrentUser,
        room_public_id: UUID,
        *,
        now: datetime | None = None,
    ) -> None:
        """인증된 room 로비 WebSocket 연결을 수락하고 path의 room 구독자로 등록합니다."""
        await websocket.accept()
        cancel_pending_grace_leave(
            room_public_id=room_public_id,
            user_id=user.id,
            pending_grace_leaves=self._pending_grace_leaves,
        )
        register_lobby_connection(
            websocket=websocket,
            user=user,
            room_public_id=room_public_id,
            connections=self._connections,
            user_connections=self._user_connections,
            room_subscriptions=self._room_subscriptions,
            now=now,
        )

    def disconnect(self, websocket: WebSocket) -> LobbyDisconnect | None:
        """로비 WebSocket 연결을 정리하고 grace 퇴장 후보를 반환합니다."""
        connection = remove_lobby_connection(
            websocket=websocket,
            connections=self._connections,
            user_connections=self._user_connections,
            room_subscriptions=self._room_subscriptions,
        )
        if connection is None:
            return None
        if self._has_active_room_connection(
            room_public_id=connection.room_public_id,
            user_id=connection.user.id,
        ):
            return None
        return LobbyDisconnect(
            user=connection.user,
            room_public_id=connection.room_public_id,
        )

    def record_heartbeat(self, websocket: WebSocket, *, now: datetime | None = None) -> None:
        """ping을 받은 시각을 connection heartbeat 기준으로 기록합니다."""
        record_lobby_heartbeat(websocket=websocket, connections=self._connections, now=now)

    def is_heartbeat_expired(
        self,
        websocket: WebSocket,
        *,
        now: datetime | None = None,
        timeout_seconds: int = LOBBY_HEARTBEAT_TIMEOUT_SECONDS,
    ) -> bool:
        """마지막 ping 이후 timeout 기준을 넘었는지 반환합니다."""
        return is_lobby_heartbeat_expired(
            websocket=websocket,
            connections=self._connections,
            now=now,
            timeout_seconds=timeout_seconds,
        )

    def schedule_grace_leave(
        self,
        disconnect: LobbyDisconnect,
        leave_after_grace: GraceLeaveCallback,
        *,
        grace_seconds: float = LOBBY_DISCONNECT_GRACE_SECONDS,
    ) -> None:
        """grace time 안에 같은 유저가 같은 room으로 재연결하지 않으면 퇴장 콜백을 실행합니다."""
        schedule_grace_leave_task(
            disconnect=disconnect,
            leave_after_grace=leave_after_grace,
            grace_seconds=grace_seconds,
            has_active_room_connection=self._has_active_room_connection,
            pending_grace_leaves=self._pending_grace_leaves,
        )

    async def send(self, websocket: WebSocket, message: LobbyMessage) -> None:
        """특정 로비 WebSocket 연결로 JSON envelope 메시지를 전송합니다."""
        await send_lobby_message(websocket, message)

    async def send_error_and_close(self, websocket: WebSocket, error: AppException) -> None:
        """오류 envelope를 전송한 뒤 error definition의 WebSocket close code로 연결을 닫습니다."""
        await send_lobby_error_and_close(websocket, error)

    async def send_connected(self, websocket: WebSocket) -> None:
        """연결 직후 클라이언트가 room 구독과 user identity를 확인할 수 있는 event를 보냅니다."""
        connection = self._connections[websocket]
        await self.send(websocket, lobby_connected_message(connection))

    async def send_snapshot(self, websocket: WebSocket, snapshot: RoomLobbySnapshotResult) -> None:
        """연결 직후 room 화면을 초기화할 활성 멤버 snapshot event를 보냅니다."""
        await self.send(websocket, lobby_snapshot_message(snapshot))

    async def broadcast_room(self, room_public_id: UUID, message: LobbyMessage) -> None:
        """특정 room 구독자에게 같은 JSON envelope event를 전송합니다."""
        await broadcast_lobby_room(
            room_public_id=room_public_id,
            message=message,
            room_subscriptions=self._room_subscriptions,
            disconnect_stale_websocket=self.disconnect,
        )

    def _has_active_room_connection(self, *, room_public_id: UUID, user_id: UUID) -> bool:
        return has_active_room_connection(
            room_public_id=room_public_id,
            user_id=user_id,
            connections=self._connections,
        )
