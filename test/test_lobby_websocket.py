import asyncio
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.websockets import WebSocketDisconnect
from fastapi.testclient import TestClient

from app.be.api.endpoints import lobby_ws
from app.be.api.endpoints import game as game_endpoint
from app.be.dependencies.database import get_db_session
from app.be.dependencies.services import get_auth_service, get_current_user, get_game_service
from app.be.main import create_app
from app.be.services.auth import CurrentUser, SessionExpiredError
from app.be.services.game import (
    RoomJoinResult,
    RoomLobbyConnectionResult,
    RoomLobbyMemberSnapshot,
    RoomLobbySnapshotResult,
)
from app.be.services.lobby import LobbyConnectionManager, lobby_connection_manager


KST = ZoneInfo("Asia/Seoul")


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.sent_json: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict) -> None:
        self.sent_json.append(message)


class BrokenSendWebSocket(FakeWebSocket):
    async def send_json(self, message: dict) -> None:
        raise RuntimeError("websocket is already closed")


class FakeWebSocketMetrics:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def record_connect(self, **kwargs) -> None:
        self.calls.append(("connect", kwargs))

    def record_message(self, **kwargs) -> None:
        self.calls.append(("message", kwargs))

    def record_error(self, **kwargs) -> None:
        self.calls.append(("error", kwargs))

    def record_disconnect(self, **kwargs) -> None:
        self.calls.append(("disconnect", kwargs))

    def record_duration(self, **kwargs) -> None:
        self.calls.append(("duration", kwargs))


class FakeDbSession:
    def __init__(self) -> None:
        self.rolled_back = False

    async def rollback(self) -> None:
        self.rolled_back = True


def use_fake_db_session(app, db_session: FakeDbSession | None = None) -> FakeDbSession:
    """WebSocket 테스트에서 인증/권한 확인 transaction 종료 여부를 관찰할 fake session을 주입합니다."""
    fake_db_session = db_session or FakeDbSession()

    async def fake_db_session_dependency():
        yield fake_db_session

    app.dependency_overrides[get_db_session] = fake_db_session_dependency
    return fake_db_session


class FakeSpan:
    def __init__(self, names: list[str], name: str) -> None:
        self.names = names
        self.name = name

    def __enter__(self):
        self.names.append(self.name)
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False


def current_user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="초보자",
    )


def build_lobby_snapshot(
    *,
    room_public_id: UUID,
    owner: CurrentUser,
    joined_at: datetime | None = None,
) -> RoomLobbySnapshotResult:
    """WebSocket 연결 테스트에서 사용할 최소 room snapshot을 만듭니다."""
    return RoomLobbySnapshotResult(
        room_public_id=room_public_id,
        owner_user_public_id=owner.public_id,
        members=[
            RoomLobbyMemberSnapshot(
                user_public_id=owner.public_id,
                nickname=owner.nickname,
                is_owner=True,
                joined_at=joined_at or datetime(2026, 6, 12, tzinfo=KST),
            )
        ],
    )


class FakeAuthService:
    def __init__(self, user: CurrentUser) -> None:
        self.user = user

    async def authenticate_session(self, session_token: str | None) -> CurrentUser:
        if session_token != "valid-session":
            raise SessionExpiredError
        return self.user


def test_lobby_websocket_rejects_missing_session_cookie() -> None:
    user = current_user()

    class FakeGameService:
        async def authorize_room_lobby_connection(self, **kwargs) -> RoomLobbyConnectionResult:
            raise AssertionError("세션 인증 실패 전에는 room 권한을 확인하지 않습니다.")

    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/lobby/rooms/{uuid4()}"):
            pass

    assert exc_info.value.code == 1008
    assert lobby_connection_manager.connection_count == 0


def test_room_lobby_websocket_connects_with_path_room_id_and_cleans_up() -> None:
    user = current_user()
    room_public_id = uuid4()
    other_user_public_id = uuid4()
    joined_at = datetime(2026, 6, 12, tzinfo=KST)

    class FakeGameService:
        async def authorize_room_lobby_connection(
            self,
            *,
            room_public_id: UUID,
            user_id: UUID,
        ) -> RoomLobbyConnectionResult:
            assert user_id == user.id
            return RoomLobbyConnectionResult(
                room_public_id=room_public_id,
                snapshot=RoomLobbySnapshotResult(
                    room_public_id=room_public_id,
                    owner_user_public_id=user.public_id,
                    members=[
                        RoomLobbyMemberSnapshot(
                            user_public_id=user.public_id,
                            nickname=user.nickname,
                            is_owner=True,
                            joined_at=joined_at,
                        ),
                        RoomLobbyMemberSnapshot(
                            user_public_id=other_user_public_id,
                            nickname="손님",
                            is_owner=False,
                            joined_at=joined_at + timedelta(minutes=1),
                        ),
                    ],
                ),
            )

    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(f"/ws/lobby/rooms/{room_public_id}") as websocket:
        assert websocket.receive_json() == {
            "type": "lobby.room.connected",
            "payload": {
                "room_public_id": str(room_public_id),
                "user": {
                    "public_id": str(user.public_id),
                    "account_id": user.account_id,
                    "nickname": user.nickname,
                },
            },
        }
        assert websocket.receive_json() == {
            "type": "lobby.room.snapshot",
            "payload": {
                "room_public_id": str(room_public_id),
                "owner_user_public_id": str(user.public_id),
                "members": [
                    {
                        "user_public_id": str(user.public_id),
                        "nickname": user.nickname,
                        "is_owner": True,
                        "joined_at": "2026-06-12T00:00:00+09:00",
                    },
                    {
                        "user_public_id": str(other_user_public_id),
                        "nickname": "손님",
                        "is_owner": False,
                        "joined_at": "2026-06-12T00:01:00+09:00",
                    },
                ],
            },
        }
        assert lobby_connection_manager.connection_count == 1
        assert lobby_connection_manager.room_subscription_count(room_public_id) == 1

        websocket.send_json({"type": "ping", "payload": {"client_time": "now"}})
        assert websocket.receive_json() == {
            "type": "lobby.pong",
            "payload": {"client_time": "now"},
        }

    assert lobby_connection_manager.connection_count == 0
    assert lobby_connection_manager.room_subscription_count(room_public_id) == 0


def test_room_lobby_websocket_closes_auth_transaction_before_accept(monkeypatch) -> None:
    user = current_user()
    room_public_id = uuid4()
    db_session = FakeDbSession()
    rollback_state_at_connect: list[bool] = []
    original_connect = lobby_connection_manager.connect

    class FakeGameService:
        async def authorize_room_lobby_connection(
            self,
            *,
            room_public_id: UUID,
            user_id: UUID,
        ) -> RoomLobbyConnectionResult:
            return RoomLobbyConnectionResult(
                room_public_id=room_public_id,
                snapshot=build_lobby_snapshot(room_public_id=room_public_id, owner=user),
            )

    async def record_connect(websocket, user, room_public_id, **kwargs):
        rollback_state_at_connect.append(db_session.rolled_back)
        await original_connect(websocket, user, room_public_id, **kwargs)

    monkeypatch.setattr(lobby_connection_manager, "connect", record_connect)
    app = create_app()
    use_fake_db_session(app, db_session)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(f"/ws/lobby/rooms/{room_public_id}") as websocket:
        assert websocket.receive_json()["type"] == "lobby.room.connected"
        assert websocket.receive_json()["type"] == "lobby.room.snapshot"

    assert rollback_state_at_connect == [True]


def test_room_lobby_websocket_records_apm_metrics_and_spans(monkeypatch) -> None:
    user = current_user()
    room_public_id = uuid4()
    metrics = FakeWebSocketMetrics()
    span_names: list[str] = []

    class FakeGameService:
        async def authorize_room_lobby_connection(
            self,
            *,
            room_public_id: UUID,
            user_id: UUID,
        ) -> RoomLobbyConnectionResult:
            return RoomLobbyConnectionResult(
                room_public_id=room_public_id,
                snapshot=build_lobby_snapshot(room_public_id=room_public_id, owner=user),
            )

    monkeypatch.setattr(
        lobby_ws,
        "start_span",
        lambda name, attributes=None: FakeSpan(span_names, name),
    )
    app = create_app()
    use_fake_db_session(app)
    app.state.websocket_metrics = metrics
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(f"/ws/lobby/rooms/{room_public_id}") as websocket:
        assert websocket.receive_json()["type"] == "lobby.room.connected"
        assert websocket.receive_json()["type"] == "lobby.room.snapshot"
        websocket.send_json({"type": "ping", "payload": {"client_time": "now"}})
        websocket.receive_json()

    message_calls = [call for call in metrics.calls if call[0] == "message"]
    assert (
        "connect",
        {"ws_route": lobby_ws.LOBBY_WS_ROUTE, "ws_endpoint": "lobby"},
    ) in metrics.calls
    assert message_calls[0][1]["message_type"] == "lobby.room.connected"
    assert message_calls[0][1]["direction"] == "outbound"
    assert message_calls[1][1]["message_type"] == "lobby.room.snapshot"
    assert message_calls[1][1]["direction"] == "outbound"
    assert message_calls[2][1]["message_type"] == "ping"
    assert message_calls[2][1]["direction"] == "inbound"
    assert message_calls[3][1]["message_type"] == "lobby.pong"
    assert message_calls[3][1]["direction"] == "outbound"
    assert any(call[0] == "disconnect" for call in metrics.calls)
    assert any(call[0] == "duration" for call in metrics.calls)
    assert "WebSocket.lobby.connect" in span_names
    assert "WebSocket.lobby.message" in span_names
    assert "WebSocket.lobby.disconnect" in span_names


def test_room_lobby_websocket_closes_when_heartbeat_timeout_passes(monkeypatch) -> None:
    user = current_user()
    room_public_id = uuid4()

    class FakeGameService:
        async def authorize_room_lobby_connection(
            self,
            *,
            room_public_id: UUID,
            user_id: UUID,
        ) -> RoomLobbyConnectionResult:
            return RoomLobbyConnectionResult(
                room_public_id=room_public_id,
                snapshot=build_lobby_snapshot(room_public_id=room_public_id, owner=user),
            )

    monkeypatch.setattr(lobby_ws, "LOBBY_HEARTBEAT_TIMEOUT_SECONDS", 0.01)
    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(f"/ws/lobby/rooms/{room_public_id}") as websocket:
        assert websocket.receive_json()["type"] == "lobby.room.connected"
        maybe_snapshot = websocket.receive_json()
        assert maybe_snapshot["type"] == "lobby.room.snapshot"
        with pytest.raises(WebSocketDisconnect) as exc_info:
            websocket.receive_text()

    assert exc_info.value.code == 1001
    assert lobby_connection_manager.connection_count == 0


async def test_lobby_manager_records_ping_as_heartbeat() -> None:
    manager = LobbyConnectionManager()
    user = current_user()
    room_public_id = uuid4()
    websocket = FakeWebSocket()
    connected_at = datetime(2026, 6, 12, tzinfo=KST)
    ping_at = connected_at + timedelta(seconds=15)

    await manager.connect(websocket, user, room_public_id, now=connected_at)
    manager.record_heartbeat(websocket, now=ping_at)

    assert (
        manager.is_heartbeat_expired(
            websocket,
            now=ping_at + timedelta(seconds=44),
            timeout_seconds=45,
        )
        is False
    )
    assert (
        manager.is_heartbeat_expired(
            websocket,
            now=ping_at + timedelta(seconds=46),
            timeout_seconds=45,
        )
        is True
    )


async def test_lobby_manager_runs_grace_leave_after_disconnected_user_does_not_return() -> None:
    manager = LobbyConnectionManager()
    user = current_user()
    room_public_id = uuid4()
    websocket = FakeWebSocket()
    leave_calls = []

    async def leave_after_grace(disconnect) -> None:
        leave_calls.append((disconnect.room_public_id, disconnect.user.id))

    await manager.connect(websocket, user, room_public_id)
    disconnect = manager.disconnect(websocket)

    assert disconnect is not None
    assert leave_calls == []

    manager.schedule_grace_leave(disconnect, leave_after_grace, grace_seconds=0)
    await asyncio.sleep(0.01)

    assert leave_calls == [(room_public_id, user.id)]
    assert manager.pending_grace_leave_count == 0


async def test_lobby_manager_cancels_grace_leave_when_user_reconnects_to_same_room() -> None:
    manager = LobbyConnectionManager()
    user = current_user()
    room_public_id = uuid4()
    first_socket = FakeWebSocket()
    second_socket = FakeWebSocket()
    leave_calls = []

    async def leave_after_grace(disconnect) -> None:
        leave_calls.append((disconnect.room_public_id, disconnect.user.id))

    await manager.connect(first_socket, user, room_public_id)
    disconnect = manager.disconnect(first_socket)

    assert disconnect is not None

    manager.schedule_grace_leave(disconnect, leave_after_grace, grace_seconds=0.01)
    await manager.connect(second_socket, user, room_public_id)
    await asyncio.sleep(0.02)

    assert leave_calls == []
    assert manager.pending_grace_leave_count == 0
    assert manager.room_subscription_count(room_public_id) == 1


async def test_lobby_manager_skips_failed_websocket_during_room_broadcast() -> None:
    manager = LobbyConnectionManager()
    room_public_id = uuid4()
    healthy_user = current_user()
    stale_user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_002",
        nickname="끊긴손님",
    )
    healthy_socket = FakeWebSocket()
    stale_socket = BrokenSendWebSocket()

    await manager.connect(healthy_socket, healthy_user, room_public_id)
    await manager.connect(stale_socket, stale_user, room_public_id)

    await manager.broadcast_room(room_public_id, {"type": "lobby.notice", "payload": {}})

    assert healthy_socket.sent_json == [{"type": "lobby.notice", "payload": {}}]
    assert manager.room_subscription_count(room_public_id) == 1


def test_join_room_api_broadcasts_to_lobby_room_subscribers() -> None:
    user = current_user()
    room_public_id = uuid4()
    joined_at = datetime(2026, 6, 12, tzinfo=KST)

    class FakeGameService:
        async def authorize_room_lobby_connection(
            self,
            *,
            room_public_id: UUID,
            user_id: UUID,
        ) -> RoomLobbyConnectionResult:
            return RoomLobbyConnectionResult(
                room_public_id=room_public_id,
                snapshot=build_lobby_snapshot(room_public_id=room_public_id, owner=user),
            )

        async def join_room(self, *, room_public_id: UUID, user: CurrentUser) -> RoomJoinResult:
            return RoomJoinResult(
                room_public_id=room_public_id,
                user_public_id=user.public_id,
                nickname=user.nickname,
                joined_at=joined_at,
                already_member=False,
            )

    app = create_app()
    use_fake_db_session(app)
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService(user)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)
    client.cookies.set("session_token", "valid-session")

    with client.websocket_connect(f"/ws/lobby/rooms/{room_public_id}") as websocket:
        assert websocket.receive_json()["type"] == "lobby.room.connected"
        maybe_snapshot = websocket.receive_json()
        assert maybe_snapshot["type"] == "lobby.room.snapshot"
        response = client.post(f"/api/v1/game/rooms/{room_public_id}/join")

        assert response.status_code == 200
        assert response.json()["data"] == {
            "room_public_id": str(room_public_id),
            "user_public_id": str(user.public_id),
            "nickname": "초보자",
            "joined_at": "2026-06-12T00:00:00+09:00",
            "already_member": False,
        }
        assert websocket.receive_json() == {
            "type": "lobby.room.joined",
            "payload": response.json()["data"],
        }


def test_join_room_api_does_not_broadcast_when_user_is_already_member(monkeypatch) -> None:
    user = current_user()
    room_public_id = uuid4()
    joined_at = datetime(2026, 6, 12, tzinfo=KST)
    broadcast_calls: list[tuple[object, dict]] = []

    class FakeGameService:
        async def join_room(self, *, room_public_id: UUID, user: CurrentUser) -> RoomJoinResult:
            return RoomJoinResult(
                room_public_id=room_public_id,
                user_public_id=user.public_id,
                nickname=user.nickname,
                joined_at=joined_at,
                already_member=True,
            )

    async def record_broadcast(room_public_id, message):
        broadcast_calls.append((room_public_id, message))

    monkeypatch.setattr(
        game_endpoint.lobby_connection_manager,
        "broadcast_room",
        record_broadcast,
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)

    response = client.post(f"/api/v1/game/rooms/{room_public_id}/join")

    assert response.status_code == 200
    assert response.json()["data"]["already_member"] is True
    assert broadcast_calls == []
