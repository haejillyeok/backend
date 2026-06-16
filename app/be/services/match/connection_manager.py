from typing import Any
from uuid import UUID

from fastapi import WebSocket
from fastapi.encoders import jsonable_encoder
from starlette.websockets import WebSocketDisconnect

from app.be.services.game import GameSessionParticipantRecord
from app.be.services.match.connection_messages import (
    match_connected_message,
    match_snapshot_message,
)
from app.be.services.match.connection_records import MatchConnection
from app.be.services.match.snapshots import MatchSnapshotResult
from app.shared.core.exceptions import AppException


MatchMessage = dict[str, Any]


class MatchConnectionManager:
    """match WebSocket 연결과 세션별 구독 registry를 관리합니다.

    연결 identity는 `game_session_public_id + participant_id`로 고정합니다. DB의 match 상태가 최종
    사실이고, manager는 process-local 연결만 보관합니다.
    """

    def __init__(self) -> None:
        self._connections: dict[WebSocket, MatchConnection] = {}
        self._session_subscriptions: dict[UUID, set[WebSocket]] = {}

    @property
    def connection_count(self) -> int:
        """현재 match manager에 등록된 active WebSocket 연결 수를 반환합니다."""
        return len(self._connections)

    async def connect(
        self,
        websocket: WebSocket,
        *,
        game_session_public_id: UUID,
        participant_id: UUID,
        participant: GameSessionParticipantRecord,
    ) -> None:
        """인증된 match WebSocket 연결을 수락하고 세션 구독자로 등록합니다."""
        await websocket.accept()
        self._connections[websocket] = MatchConnection(
            game_session_public_id=game_session_public_id,
            participant_id=participant_id,
            participant=participant,
        )
        self._session_subscriptions.setdefault(game_session_public_id, set()).add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """match WebSocket 연결을 registry에서 제거합니다."""
        connection = self._connections.pop(websocket, None)
        if connection is None:
            return
        subscribers = self._session_subscriptions.get(connection.game_session_public_id)
        if subscribers is not None:
            subscribers.discard(websocket)
            if not subscribers:
                self._session_subscriptions.pop(connection.game_session_public_id, None)

    async def send(self, websocket: WebSocket, message: MatchMessage) -> None:
        """특정 match WebSocket 연결로 JSON envelope 메시지를 전송합니다."""
        await websocket.send_json(jsonable_encoder(message))

    def get_connection(self, websocket: WebSocket) -> MatchConnection | None:
        """WebSocket에 고정된 match 참가자 identity를 반환합니다."""
        return self._connections.get(websocket)

    async def send_error_and_close(self, websocket: WebSocket, error: AppException) -> None:
        """오류 envelope를 전송한 뒤 error definition의 WebSocket close code로 연결을 닫습니다."""
        await self.send(websocket, {"type": "error", "payload": error.to_error_payload()})
        await websocket.close(code=error.websocket_close_code)

    async def send_connected(self, websocket: WebSocket) -> None:
        """연결 직후 클라이언트가 본인 참가자 순서를 확인할 수 있는 event를 보냅니다."""
        connection = self._connections[websocket]
        await self.send(websocket, match_connected_message(connection))

    async def send_snapshot(
        self,
        websocket: WebSocket,
        snapshot: MatchSnapshotResult,
    ) -> None:
        """연결 직후 또는 재접속 시 현재 match 화면 복구 snapshot을 보냅니다."""
        await self.send(websocket, match_snapshot_message(snapshot))

    async def broadcast_session(self, game_session_public_id: UUID, message: MatchMessage) -> None:
        """특정 game session에 연결된 모든 match WebSocket에 event를 전송합니다."""
        for websocket in list(self._session_subscriptions.get(game_session_public_id, set())):
            try:
                await self.send(websocket, message)
            except (RuntimeError, WebSocketDisconnect):
                self.disconnect(websocket)


match_connection_manager = MatchConnectionManager()
