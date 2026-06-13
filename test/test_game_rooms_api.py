from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.be.dependencies.services import get_current_user, get_game_service
from app.be.main import create_app
from app.be.services.auth import CurrentUser
from app.be.services.game import (
    CurrentLobbyMembership,
    GameRoomListItem,
    GameRoomListResult,
    RoomCreateResult,
    RoomLeaveResult,
)


KST = ZoneInfo("Asia/Seoul")


def current_user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="초보자",
    )


def test_list_game_rooms_returns_lobby_room_summaries() -> None:
    room_public_id = uuid4()

    class FakeGameService:
        async def list_rooms(self, *, user_id) -> GameRoomListResult:
            return GameRoomListResult(
                rooms=[
                    GameRoomListItem(
                        room_public_id=room_public_id,
                        name="첫 객실",
                        game_type="shiritori",
                        status="waiting",
                        max_players=4,
                        member_count=2,
                        is_current_user_member=True,
                        is_current_user_owner=False,
                    )
                ],
                current_membership=CurrentLobbyMembership(
                    room_public_id=room_public_id,
                    name="첫 객실",
                    game_type="shiritori",
                    status="waiting",
                    max_players=4,
                    member_count=2,
                    is_owner=False,
                    lobby_websocket_path=f"/ws/lobby/rooms/{room_public_id}",
                ),
            )

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: current_user()
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)

    response = client.get("/api/v1/game/rooms")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "rooms": [
            {
                "room_public_id": str(room_public_id),
                "name": "첫 객실",
                "game_type": "shiritori",
                "status": "waiting",
                "max_players": 4,
                "member_count": 2,
                "is_current_user_member": True,
                "is_current_user_owner": False,
                "lobby_websocket_path": f"/ws/lobby/rooms/{room_public_id}",
            }
        ],
        "current_membership": {
            "room_public_id": str(room_public_id),
            "name": "첫 객실",
            "game_type": "shiritori",
            "status": "waiting",
            "max_players": 4,
            "member_count": 2,
            "is_owner": False,
            "lobby_websocket_path": f"/ws/lobby/rooms/{room_public_id}",
        },
    }


def test_create_game_room_creates_owner_membership() -> None:
    user = current_user()
    room_public_id = uuid4()
    created_at = datetime(2026, 6, 12, tzinfo=KST)

    class FakeGameService:
        async def create_room(
            self,
            *,
            name: str,
            game_type: str,
            max_players: int,
            owner: CurrentUser,
        ) -> RoomCreateResult:
            assert owner == user
            assert name == "첫 객실"
            assert game_type == "shiritori"
            assert max_players == 4
            return RoomCreateResult(
                room_public_id=room_public_id,
                name=name,
                game_type=game_type,
                status="waiting",
                max_players=max_players,
                member_count=1,
                created_at=created_at,
            )

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)

    response = client.post(
        "/api/v1/game/rooms",
        json={"name": "첫 객실", "game_type": "shiritori", "max_players": 4},
    )

    assert response.status_code == 201
    assert response.json()["data"] == {
        "room_public_id": str(room_public_id),
        "name": "첫 객실",
        "game_type": "shiritori",
        "status": "waiting",
        "max_players": 4,
        "member_count": 1,
        "created_at": "2026-06-12T00:00:00+09:00",
    }


def test_create_game_room_rejects_unknown_game_type() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: current_user()

    class FakeGameService:
        async def create_room(self, **kwargs):
            raise AssertionError("enum validation 실패 요청은 service까지 도달하지 않아야 합니다.")

    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)

    response = client.post(
        "/api/v1/game/rooms",
        json={"name": "첫 객실", "game_type": "unknown", "max_players": 4},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"][0]["field"] == "body.game_type"


def test_leave_game_room_returns_leave_state_for_authenticated_member() -> None:
    user = current_user()
    room_public_id = uuid4()
    left_at = datetime(2026, 6, 12, tzinfo=KST)
    next_owner_id = uuid4()

    class FakeGameService:
        async def leave_room(self, *, room_public_id, user, left_at):
            assert user == current_user_override
            assert room_public_id == room_public_id_override
            assert left_at.tzinfo is not None
            return RoomLeaveResult(
                room_public_id=room_public_id,
                user_public_id=user.public_id,
                nickname=user.nickname,
                left_at=left_at_override,
                remaining_member_count=1,
                new_owner_user_public_id=next_owner_id,
                new_owner_nickname="다음방장",
                room_closed=False,
            )

    current_user_override = user
    room_public_id_override = room_public_id
    left_at_override = left_at
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)

    response = client.post(f"/api/v1/game/rooms/{room_public_id}/leave")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "room_public_id": str(room_public_id),
        "user_public_id": str(user.public_id),
        "nickname": "초보자",
        "left_at": "2026-06-12T00:00:00+09:00",
        "remaining_member_count": 1,
        "new_owner_user_public_id": str(next_owner_id),
        "new_owner_nickname": "다음방장",
        "room_closed": False,
    }
