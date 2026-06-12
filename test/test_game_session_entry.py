import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.be.dependencies.services import get_current_user, get_game_service
from app.be.main import create_app
from app.be.services.auth import AuthService, CurrentUser
from app.be.services.game import (
    GameRepositoryProtocol,
    GameRoomRecord,
    GameService,
    GameSessionEntryForbiddenError,
    GameSessionParticipantRecord,
    RoomMemberRecord,
)
from app.be.models.user import User
from app.be.models.user_session import UserSession


class FakeAuthSessionRepository:
    def __init__(self, *, user: User | None, session: UserSession | None) -> None:
        self.user = user
        self.session = session
        self.touched_token_hash: str | None = None
        self.committed = False

    async def get_user_by_account_id(self, account_id: str) -> User | None:
        return None

    async def get_user_by_nickname(self, nickname: str) -> User | None:
        return None

    async def create_user(self, **kwargs) -> User:
        raise AssertionError("세션 조회 테스트에서는 새 유저를 만들지 않습니다.")

    async def create_user_session(self, **kwargs) -> object:
        raise AssertionError("세션 조회 테스트에서는 새 세션을 만들지 않습니다.")

    async def get_active_session_user(
        self,
        *,
        token_hash: str,
        now: datetime,
    ) -> tuple[User, UserSession] | None:
        self.touched_token_hash = token_hash
        if self.user is None or self.session is None:
            return None
        if self.session.revoked_at is not None or self.session.expires_at <= now:
            return None
        return self.user, self.session

    async def touch_user_session(self, session: UserSession, *, now: datetime) -> None:
        session.last_seen_at = now

    async def commit(self) -> None:
        self.committed = True


class FakeGameRepository(GameRepositoryProtocol):
    def __init__(
        self,
        *,
        room: GameRoomRecord | None,
        members: list[RoomMemberRecord] | None = None,
        participant: GameSessionParticipantRecord | None = None,
        active_session: object | None = None,
    ) -> None:
        self.room = room
        self.members = members or []
        self.participant = participant
        self.active_session = active_session
        self.created_sessions: list[dict[str, object]] = []
        self.committed = False
        self.locked_room_public_ids: list[object] = []

    async def get_room_by_public_id_for_update(self, room_public_id):
        self.locked_room_public_ids.append(room_public_id)
        return self.room if self.room and self.room.public_id == room_public_id else None

    async def get_active_session_by_room_id(self, room_id):
        if self.room and self.room.id == room_id:
            return self.active_session
        return None

    async def list_active_room_members(self, room_id):
        return [member for member in self.members if member.room_id == room_id]

    async def create_game_session(self, **kwargs):
        self.created_sessions.append(kwargs)
        return kwargs["session"]

    async def get_user_participant_for_session(self, *, session_public_id, user_id):
        if self.participant is None:
            return None
        if (
            self.participant.session_public_id == session_public_id
            and self.participant.user_id == user_id
        ):
            return self.participant
        return None

    async def commit(self):
        self.committed = True


def test_auth_service_resolves_current_user_from_active_session_token():
    user = User(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="초보자",
        password_hash="hash",
        last_access_ip=None,
    )
    session = UserSession(
        id=uuid4(),
        user_id=user.id,
        token_hash="stored-hash",
        user_agent="pytest",
        last_access_ip="203.0.113.10",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    repository = FakeAuthSessionRepository(user=user, session=session)
    service = AuthService(repository)

    current_user = asyncio.run(service.authenticate_session("plain-session-token"))

    assert current_user == CurrentUser(
        id=user.id,
        public_id=user.public_id,
        account_id="player_001",
        nickname="초보자",
    )
    assert repository.touched_token_hash is not None
    assert repository.committed is True


def test_game_service_starts_session_for_room_owner_and_freezes_allowed_members():
    owner_id = uuid4()
    member_id = uuid4()
    room_id = uuid4()
    room_public_id = uuid4()
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=owner_id,
            name="첫 객실",
            game_type="shiritori",
            status="waiting",
            max_players=4,
        ),
        members=[
            RoomMemberRecord(
                room_id=room_id,
                user_id=owner_id,
                nickname="방장",
                joined_at=datetime(2026, 6, 11, tzinfo=UTC),
            ),
            RoomMemberRecord(
                room_id=room_id,
                user_id=member_id,
                nickname="손님",
                joined_at=datetime(2026, 6, 11, 0, 1, tzinfo=UTC),
            ),
        ],
    )
    service = GameService(repository)

    result = asyncio.run(service.start_session(room_public_id=room_public_id, user_id=owner_id))

    assert result.room_public_id == room_public_id
    assert result.game_type == "shiritori"
    assert result.status == "starting"
    assert [participant.participant_type for participant in result.participants] == [
        "user",
        "user",
        "ai",
    ]
    assert [participant.seat_number for participant in result.participants] == [1, 2, 3]
    assert repository.locked_room_public_ids == [room_public_id]
    assert repository.committed is True


def test_game_service_returns_existing_session_for_repeated_start_request():
    owner_id = uuid4()
    room_id = uuid4()
    room_public_id = uuid4()
    session_public_id = uuid4()
    existing_session = type(
        "ExistingSession",
        (),
        {
            "session_public_id": session_public_id,
            "room_public_id": room_public_id,
            "game_type": "shiritori",
            "status": "starting",
            "participants": [
                GameSessionParticipantRecord(
                    participant_id=uuid4(),
                    session_public_id=session_public_id,
                    user_id=owner_id,
                    participant_type="user",
                    display_name="방장",
                    seat_number=1,
                    is_uninvited_guest=False,
                )
            ],
        },
    )()
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=owner_id,
            name="첫 객실",
            game_type="shiritori",
            status="starting",
            max_players=4,
        ),
        active_session=existing_session,
    )
    service = GameService(repository)

    result = asyncio.run(service.start_session(room_public_id=room_public_id, user_id=owner_id))

    assert result.session_public_id == session_public_id
    assert result.room_public_id == room_public_id
    assert repository.created_sessions == []
    assert repository.locked_room_public_ids == [room_public_id]
    assert repository.committed is False


def test_game_service_rejects_entry_for_user_outside_session():
    repository = FakeGameRepository(room=None, participant=None)
    service = GameService(repository)

    with pytest.raises(GameSessionEntryForbiddenError):
        asyncio.run(service.authorize_entry(session_public_id=uuid4(), user_id=uuid4()))


def test_game_service_resolves_participant_identity_for_allowed_session_entry():
    user_id = uuid4()
    participant_id = uuid4()
    session_public_id = uuid4()
    repository = FakeGameRepository(
        room=None,
        participant=GameSessionParticipantRecord(
            participant_id=participant_id,
            session_public_id=session_public_id,
            user_id=user_id,
            participant_type="user",
            display_name="참가자",
            seat_number=1,
            is_uninvited_guest=False,
        ),
    )
    service = GameService(repository)

    result = asyncio.run(
        service.authorize_entry(session_public_id=session_public_id, user_id=user_id)
    )

    assert result.session_public_id == session_public_id
    assert result.participant.participant_id == participant_id
    assert result.participant.user_id == user_id


def test_start_game_session_endpoint_returns_session_for_authenticated_owner():
    app = create_app()
    room_public_id = uuid4()
    session_public_id = uuid4()
    current_user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="방장",
    )

    class FakeGameService:
        async def start_session(self, *, room_public_id, user_id):
            assert user_id == current_user.id
            return type(
                "StartResult",
                (),
                {
                    "session_public_id": session_public_id,
                    "room_public_id": room_public_id,
                    "game_type": "shiritori",
                    "status": "starting",
                    "participants": [
                        type(
                            "Participant",
                            (),
                            {
                                "participant_type": "user",
                                "display_name": "방장",
                                "seat_number": 1,
                                "is_uninvited_guest": False,
                            },
                        )(),
                        type(
                            "Participant",
                            (),
                            {
                                "participant_type": "ai",
                                "display_name": "수상한 손님",
                                "seat_number": 2,
                                "is_uninvited_guest": True,
                            },
                        )(),
                    ],
                },
            )()

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)

    response = client.post(f"/api/v1/game/rooms/{room_public_id}/start")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "session_public_id": str(session_public_id),
            "room_public_id": str(room_public_id),
            "game_type": "shiritori",
            "status": "starting",
            "participants": [
                {
                    "participant_type": "user",
                    "display_name": "방장",
                    "seat_number": 1,
                    "is_uninvited_guest": False,
                },
                {
                    "participant_type": "ai",
                    "display_name": "수상한 손님",
                    "seat_number": 2,
                    "is_uninvited_guest": True,
                },
            ],
        },
    }


def test_game_session_entry_endpoint_rejects_uninvited_user():
    app = create_app()
    current_user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_002",
        nickname="외부인",
    )

    class FakeGameService:
        async def authorize_entry(self, *, session_public_id, user_id):
            raise GameSessionEntryForbiddenError

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)

    response = client.get(f"/api/v1/game/sessions/{uuid4()}/entry")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "GAME_SESSION_ENTRY_FORBIDDEN"
