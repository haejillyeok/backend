from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.be.models.game import GameSession, Room, RoomMember, SessionParticipant
from app.be.models.user import User
from app.be.models.user_session import UserSession
from app.be.repository.auth import AuthRepository
from app.be.repository.game import GameRepository
from app.be.services.game import GameSessionParticipantRecord, GameSessionStartResult


class FakeScalarCollection:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeResult:
    def __init__(self, *, scalar=None, row=None, rows=None, scalars=None) -> None:
        self.scalar = scalar
        self.row = row
        self.rows = rows or []
        self.scalar_rows = scalars or []

    def scalar_one_or_none(self):
        return self.scalar

    def scalar_one(self):
        return self.scalar

    def one_or_none(self):
        return self.row

    def all(self):
        return self.rows

    def scalars(self):
        return FakeScalarCollection(self.scalar_rows)


class FakeDbSession:
    def __init__(self, results=None) -> None:
        self.results = list(results or [])
        self.added = []
        self.added_batches = []
        self.flush_count = 0
        self.committed = False

    async def execute(self, statement):
        return self.results.pop(0)

    def add(self, item) -> None:
        self.added.append(item)

    def add_all(self, items) -> None:
        self.added_batches.append(list(items))

    async def flush(self) -> None:
        self.flush_count += 1
        for item in [*self.added, *(child for batch in self.added_batches for child in batch)]:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    async def commit(self) -> None:
        self.committed = True


def build_user(*, nickname: str = "초보자") -> User:
    return User(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname=nickname,
        password_hash="hash",
        last_access_ip=None,
    )


async def test_auth_repository_creates_user_and_session_records() -> None:
    db_session = FakeDbSession()
    repository = AuthRepository(db_session)
    user_id = uuid4()
    expires_at = datetime.now(UTC) + timedelta(days=1)

    user = await repository.create_user(
        account_id="player_001",
        nickname="초보자",
        password_hash="hash",
        last_access_ip="203.0.113.1",
    )
    user_session = await repository.create_user_session(
        user_id=user_id,
        token_hash="token-hash",
        expires_at=expires_at,
        last_access_ip="203.0.113.1",
        user_agent="pytest",
    )
    await repository.commit()

    assert user.account_id == "player_001"
    assert user.nickname == "초보자"
    assert user.last_access_ip == "203.0.113.1"
    assert user_session.user_id == user_id
    assert user_session.token_hash == "token-hash"
    assert db_session.flush_count == 2
    assert db_session.committed is True


async def test_auth_repository_resolves_and_touches_active_session_user() -> None:
    user = build_user()
    user_session = UserSession(
        id=uuid4(),
        user_id=user.id,
        token_hash="token-hash",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session = FakeDbSession(
        [
            FakeResult(row=(user, user_session)),
            FakeResult(row=None),
        ]
    )
    repository = AuthRepository(db_session)
    now = datetime.now(UTC)

    active = await repository.get_active_session_user(token_hash="token-hash", now=now)
    missing = await repository.get_active_session_user(token_hash="missing", now=now)
    await repository.touch_user_session(user_session, now=now)

    assert active == (user, user_session)
    assert missing is None
    assert user_session.last_seen_at == now
    assert db_session.flush_count == 1


async def test_auth_repository_finds_user_by_account_id_and_nickname() -> None:
    account_user = build_user(nickname="계정유저")
    nickname_user = build_user(nickname="닉네임유저")
    db_session = FakeDbSession(
        [
            FakeResult(scalar=account_user),
            FakeResult(scalar=nickname_user),
        ]
    )
    repository = AuthRepository(db_session)

    assert await repository.get_user_by_account_id("player_001") == account_user
    assert await repository.get_user_by_nickname("닉네임유저") == nickname_user


def build_room(*, owner_user_id) -> Room:
    return Room(
        id=uuid4(),
        public_id=uuid4(),
        owner_user_id=owner_user_id,
        name="첫 객실",
        game_type="shiritori",
        status="waiting",
        max_players=4,
    )


async def test_game_repository_maps_locked_room_to_service_record() -> None:
    room = build_room(owner_user_id=uuid4())
    repository = GameRepository(FakeDbSession([FakeResult(scalar=room), FakeResult(scalar=None)]))

    record = await repository.get_room_by_public_id_for_update(room.public_id)
    missing = await repository.get_room_by_public_id_for_update(uuid4())

    assert record is not None
    assert record.public_id == room.public_id
    assert record.owner_user_id == room.owner_user_id
    assert record.status == "waiting"
    assert missing is None


async def test_game_repository_lists_rooms_with_active_member_counts() -> None:
    room = build_room(owner_user_id=uuid4())
    repository = GameRepository(FakeDbSession([FakeResult(rows=[(room, 2)])]))

    rooms = await repository.list_rooms()

    assert len(rooms) == 1
    assert rooms[0].room_public_id == room.public_id
    assert rooms[0].name == "첫 객실"
    assert rooms[0].member_count == 2


async def test_game_repository_creates_waiting_room_record() -> None:
    owner_user_id = uuid4()
    db_session = FakeDbSession()
    repository = GameRepository(db_session)

    room = await repository.create_room(
        owner_user_id=owner_user_id,
        name="첫 객실",
        game_type="shiritori",
        status="waiting",
        max_players=4,
    )

    assert room.owner_user_id == owner_user_id
    assert room.name == "첫 객실"
    assert room.status == "waiting"
    assert isinstance(db_session.added[0], Room)
    assert db_session.flush_count == 1


async def test_game_repository_gets_room_without_lock_for_lobby_connection() -> None:
    room = build_room(owner_user_id=uuid4())
    repository = GameRepository(FakeDbSession([FakeResult(scalar=room), FakeResult(scalar=None)]))

    found = await repository.get_room_by_public_id(room.public_id)
    missing = await repository.get_room_by_public_id(uuid4())

    assert found is not None
    assert found.public_id == room.public_id
    assert missing is None


async def test_game_repository_returns_active_session_with_participant_snapshot() -> None:
    owner_id = uuid4()
    room = build_room(owner_user_id=owner_id)
    game_session = GameSession(
        id=uuid4(),
        public_id=uuid4(),
        room_id=room.id,
        game_type="shiritori",
        status="starting",
        rule_config={},
    )
    participant = SessionParticipant(
        id=uuid4(),
        session_id=game_session.id,
        user_id=owner_id,
        participant_type="user",
        display_name="방장",
        original_nickname="방장",
        seat_number=1,
        is_uninvited_guest=False,
    )
    db_session = FakeDbSession(
        [
            FakeResult(row=(game_session, room)),
            FakeResult(scalars=[participant]),
            FakeResult(row=None),
        ]
    )
    repository = GameRepository(db_session)

    active_session = await repository.get_active_session_by_room_id(room.id)
    missing_session = await repository.get_active_session_by_room_id(uuid4())

    assert active_session is not None
    assert active_session.session_public_id == game_session.public_id
    assert active_session.participants[0].participant_id == participant.id
    assert active_session.participants[0].display_name == "방장"
    assert missing_session is None


async def test_game_repository_lists_room_members_in_repository_records() -> None:
    room_id = uuid4()
    user = build_user(nickname="손님1")
    member = RoomMember(
        id=uuid4(),
        room_id=room_id,
        user_id=user.id,
        joined_at=datetime(2026, 6, 12, tzinfo=UTC),
    )
    repository = GameRepository(FakeDbSession([FakeResult(rows=[(member, user)])]))

    members = await repository.list_active_room_members(room_id)

    assert len(members) == 1
    assert members[0].user_id == user.id
    assert members[0].nickname == "손님1"


async def test_game_repository_gets_active_room_member_record() -> None:
    room_id = uuid4()
    user = build_user(nickname="손님1")
    member = RoomMember(
        id=uuid4(),
        room_id=room_id,
        user_id=user.id,
        joined_at=datetime(2026, 6, 12, tzinfo=UTC),
    )
    repository = GameRepository(
        FakeDbSession(
            [
                FakeResult(row=(member, user)),
                FakeResult(row=None),
            ]
        )
    )

    active_member = await repository.get_active_room_member(room_id=room_id, user_id=user.id)
    missing_member = await repository.get_active_room_member(room_id=room_id, user_id=uuid4())

    assert active_member is not None
    assert active_member.user_id == user.id
    assert active_member.nickname == "손님1"
    assert missing_member is None


async def test_game_repository_creates_room_member_record() -> None:
    room_id = uuid4()
    user_id = uuid4()
    db_session = FakeDbSession()
    repository = GameRepository(db_session)

    member = await repository.create_room_member(
        room_id=room_id,
        user_id=user_id,
        nickname="초보자",
    )

    assert member.room_id == room_id
    assert member.user_id == user_id
    assert member.nickname == "초보자"
    assert isinstance(member.joined_at, datetime)
    assert isinstance(db_session.added[0], RoomMember)
    assert db_session.flush_count == 1


async def test_game_repository_marks_active_room_member_left() -> None:
    room_id = uuid4()
    user = build_user(nickname="손님1")
    room = build_room(owner_user_id=uuid4())
    room.id = room_id
    left_at = datetime(2026, 6, 12, tzinfo=UTC)
    member = RoomMember(
        id=uuid4(),
        room_id=room_id,
        user_id=user.id,
        joined_at=datetime(2026, 6, 12, tzinfo=UTC),
    )
    db_session = FakeDbSession([FakeResult(row=(member, user, room))])
    repository = GameRepository(db_session)

    result = await repository.mark_room_member_left(
        room_id=room_id,
        user_id=user.id,
        left_at=left_at,
    )

    assert result is not None
    assert result.nickname == "손님1"
    assert result.left_at == left_at
    assert member.left_at == left_at
    assert db_session.flush_count == 1


async def test_game_repository_skips_leave_when_no_active_room_member() -> None:
    db_session = FakeDbSession([FakeResult(row=None)])
    repository = GameRepository(db_session)

    result = await repository.mark_room_member_left(
        room_id=uuid4(),
        user_id=uuid4(),
        left_at=datetime(2026, 6, 12, tzinfo=UTC),
    )

    assert result is None
    assert db_session.flush_count == 0


async def test_game_repository_creates_game_session_and_participant_snapshot() -> None:
    owner_id = uuid4()
    room = build_room(owner_user_id=owner_id)
    session_public_id = uuid4()
    db_session = FakeDbSession([FakeResult(scalar=room)])
    repository = GameRepository(db_session)

    result = await repository.create_game_session(
        session=GameSessionStartResult(
            session_public_id=session_public_id,
            room_public_id=room.public_id,
            game_type="shiritori",
            status="starting",
            participants=[
                GameSessionParticipantRecord(
                    participant_id=None,
                    session_public_id=session_public_id,
                    user_id=owner_id,
                    participant_type="user",
                    display_name="방장",
                    seat_number=1,
                    is_uninvited_guest=False,
                ),
                GameSessionParticipantRecord(
                    participant_id=None,
                    session_public_id=session_public_id,
                    user_id=None,
                    participant_type="ai",
                    display_name="수상한 손님",
                    seat_number=2,
                    is_uninvited_guest=True,
                ),
            ],
        )
    )
    await repository.commit()

    assert result.session_public_id == session_public_id
    assert room.status == "starting"
    assert isinstance(db_session.added[0], GameSession)
    assert [participant.original_nickname for participant in db_session.added_batches[0]] == [
        "방장",
        None,
    ]
    assert db_session.flush_count == 2
    assert db_session.committed is True


async def test_game_repository_resolves_user_participant_for_session_entry() -> None:
    user_id = uuid4()
    game_session = SimpleNamespace(public_id=uuid4())
    participant = SessionParticipant(
        id=uuid4(),
        session_id=uuid4(),
        user_id=user_id,
        participant_type="user",
        display_name="참가자",
        original_nickname="참가자",
        seat_number=1,
        is_uninvited_guest=False,
    )
    db_session = FakeDbSession(
        [
            FakeResult(row=(game_session, participant)),
            FakeResult(row=None),
        ]
    )
    repository = GameRepository(db_session)

    record = await repository.get_user_participant_for_session(
        session_public_id=game_session.public_id,
        user_id=user_id,
    )
    missing = await repository.get_user_participant_for_session(
        session_public_id=uuid4(),
        user_id=user_id,
    )

    assert record is not None
    assert record.participant_id == participant.id
    assert record.display_name == "참가자"
    assert missing is None
