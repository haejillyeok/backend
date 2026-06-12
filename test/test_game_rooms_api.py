from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.be.dependencies.services import get_current_user, get_game_service
from app.be.main import create_app
from app.be.services.auth import CurrentUser
from app.be.services.game import GameRoomListItem, RoomCreateResult


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
        async def list_rooms(self) -> list[GameRoomListItem]:
            return [
                GameRoomListItem(
                    room_public_id=room_public_id,
                    name="첫 객실",
                    game_type="shiritori",
                    status="waiting",
                    max_players=4,
                    member_count=2,
                )
            ]

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
            }
        ]
    }


def test_create_game_room_creates_owner_membership() -> None:
    user = current_user()
    room_public_id = uuid4()
    created_at = datetime(2026, 6, 12, tzinfo=UTC)

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
        "created_at": "2026-06-12T00:00:00Z",
    }
