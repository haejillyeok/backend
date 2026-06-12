from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder

from app.be.services.auth import CurrentUser
from app.be.services.realtime import parse_realtime_message
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


LobbyMessage = dict[str, Any]
LOBBY_HEARTBEAT_TIMEOUT_SECONDS = 45
LOBBY_DISCONNECT_GRACE_SECONDS = 90


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class LobbyConnection:
    user: CurrentUser
    room_public_id: UUID
    last_seen_at: datetime


@dataclass(frozen=True)
class LobbyDisconnect:
    user: CurrentUser
    room_public_id: UUID


GraceLeaveCallback = Callable[[LobbyDisconnect], Awaitable[None]]


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
        self._pending_grace_leaves: dict[tuple[UUID, UUID], asyncio.Task] = {}

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
        self._cancel_pending_grace_leave(room_public_id=room_public_id, user_id=user.id)
        self._connections[websocket] = LobbyConnection(
            user=user,
            room_public_id=room_public_id,
            last_seen_at=now or _utc_now(),
        )
        self._user_connections.setdefault(user.id, set()).add(websocket)
        self._room_subscriptions.setdefault(room_public_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket) -> LobbyDisconnect | None:
        """로비 WebSocket 연결을 정리하고 grace 퇴장 후보를 반환합니다."""
        connection = self._connections.pop(websocket, None)
        if connection is not None:
            user_connections = self._user_connections.get(connection.user.id)
            if user_connections is not None:
                user_connections.discard(websocket)
                if not user_connections:
                    self._user_connections.pop(connection.user.id, None)

        empty_rooms = []
        for room_public_id, subscribers in self._room_subscriptions.items():
            subscribers.discard(websocket)
            if not subscribers:
                empty_rooms.append(room_public_id)
        for room_public_id in empty_rooms:
            self._room_subscriptions.pop(room_public_id, None)
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
        connection = self._connections[websocket]
        self._connections[websocket] = LobbyConnection(
            user=connection.user,
            room_public_id=connection.room_public_id,
            last_seen_at=now or _utc_now(),
        )

    def is_heartbeat_expired(
        self,
        websocket: WebSocket,
        *,
        now: datetime | None = None,
        timeout_seconds: int = LOBBY_HEARTBEAT_TIMEOUT_SECONDS,
    ) -> bool:
        """마지막 ping 이후 timeout 기준을 넘었는지 반환합니다."""
        connection = self._connections[websocket]
        return ((now or _utc_now()) - connection.last_seen_at).total_seconds() > timeout_seconds

    def schedule_grace_leave(
        self,
        disconnect: LobbyDisconnect,
        leave_after_grace: GraceLeaveCallback,
        *,
        grace_seconds: float = LOBBY_DISCONNECT_GRACE_SECONDS,
    ) -> None:
        """grace time 안에 같은 유저가 같은 room으로 재연결하지 않으면 퇴장 콜백을 실행합니다."""
        key = self._grace_leave_key(
            room_public_id=disconnect.room_public_id,
            user_id=disconnect.user.id,
        )
        self._cancel_pending_grace_leave(
            room_public_id=disconnect.room_public_id,
            user_id=disconnect.user.id,
        )

        async def run_grace_leave() -> None:
            try:
                await asyncio.sleep(grace_seconds)
                if self._has_active_room_connection(
                    room_public_id=disconnect.room_public_id,
                    user_id=disconnect.user.id,
                ):
                    return
                await leave_after_grace(disconnect)
            except asyncio.CancelledError:
                return
            finally:
                self._pending_grace_leaves.pop(key, None)

        self._pending_grace_leaves[key] = asyncio.create_task(run_grace_leave())

    async def send(self, websocket: WebSocket, message: LobbyMessage) -> None:
        """특정 로비 WebSocket 연결로 JSON envelope 메시지를 전송합니다."""
        await websocket.send_json(jsonable_encoder(message))

    async def send_error_and_close(self, websocket: WebSocket, error: AppException) -> None:
        """오류 envelope를 전송한 뒤 error definition의 WebSocket close code로 연결을 닫습니다."""
        await self.send(websocket, {"type": "error", "payload": error.to_error_payload()})
        await websocket.close(code=error.websocket_close_code)

    async def send_connected(self, websocket: WebSocket) -> None:
        """연결 직후 클라이언트가 room 구독과 user identity를 확인할 수 있는 event를 보냅니다."""
        connection = self._connections[websocket]
        await self.send(
            websocket,
            {
                "type": "lobby.room.connected",
                "payload": {
                    "room_public_id": connection.room_public_id,
                    "user": {
                        "public_id": connection.user.public_id,
                        "account_id": connection.user.account_id,
                        "nickname": connection.user.nickname,
                    },
                },
            },
        )

    async def broadcast_room(self, room_public_id: UUID, message: LobbyMessage) -> None:
        """특정 room 구독자에게 같은 JSON envelope event를 전송합니다."""
        for websocket in list(self._room_subscriptions.get(room_public_id, set())):
            await self.send(websocket, message)

    def _has_active_room_connection(self, *, room_public_id: UUID, user_id: UUID) -> bool:
        return any(
            connection.room_public_id == room_public_id and connection.user.id == user_id
            for connection in self._connections.values()
        )

    def _cancel_pending_grace_leave(self, *, room_public_id: UUID, user_id: UUID) -> None:
        key = self._grace_leave_key(room_public_id=room_public_id, user_id=user_id)
        pending = self._pending_grace_leaves.pop(key, None)
        if pending is not None:
            pending.cancel()

    def _grace_leave_key(self, *, room_public_id: UUID, user_id: UUID) -> tuple[UUID, UUID]:
        return room_public_id, user_id


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


lobby_connection_manager = LobbyConnectionManager()
