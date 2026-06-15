import asyncio
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.be.api.endpoints import game as game_endpoint
from app.be.dependencies.services import get_current_user, get_game_service
from app.be.main import create_app
from app.be.services.auth import AuthService, CurrentUser
from app.be.services.game import (
    GameRepositoryProtocol,
    GameRoomEntryForbiddenError,
    GameRoomListItem,
    GameRoomNotJoinableError,
    GameRoomNotUpdateableError,
    GameRoomRecord,
    GameRoomUpdateForbiddenError,
    GameService,
    GameSessionEntryForbiddenError,
    GameSessionParticipantRecord,
    GameSessionStartResult,
    RoomCreateResult,
    RoomLeaveResult,
    RoomMemberRecord,
    RoomUpdateResult,
)
from app.be.models.user import User
from app.be.models.user_session import UserSession

KST = ZoneInfo("Asia/Seoul")


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
        rooms: list[GameRoomRecord] | None = None,
        members: list[RoomMemberRecord] | None = None,
        participant: GameSessionParticipantRecord | None = None,
        active_session: object | None = None,
        active_room_public_ids: list[object] | None = None,
        active_waiting_room_public_ids: list[object] | None = None,
    ) -> None:
        room_records = rooms or ([room] if room is not None else [])
        self.rooms_by_public_id = {record.public_id: record for record in room_records}
        self.room = room or (room_records[0] if room_records else None)
        self.members = members or []
        self.participant = participant
        self.active_session = active_session
        self.active_room_public_ids = active_room_public_ids or []
        self.active_waiting_room_public_ids = active_waiting_room_public_ids or []
        self.created_sessions: list[dict[str, object]] = []
        self.created_rooms: list[dict[str, object]] = []
        self.created_members: list[RoomMemberRecord] = []
        self.left_members: list[RoomLeaveResult] = []
        self.aborted_sessions: list[dict[str, object]] = []
        self.room_summaries: list[GameRoomListItem] = []
        self.issued_credentials: list[dict[str, object]] = []
        self.new_owner_user_id = None
        self.closed_rooms: list[dict[str, object]] = []
        self.updated_rooms: list[dict[str, object]] = []
        self.committed = False
        self.commit_count = 0
        self.locked_room_public_ids: list[object] = []
        self.locked_waiting_membership_user_ids: list[object] = []

    async def list_rooms(self, *, user_id):
        _ = user_id
        return self.room_summaries

    async def list_active_waiting_room_public_ids_for_user(self, *, user_id):
        _ = user_id
        return self.active_waiting_room_public_ids

    async def list_active_room_public_ids_for_user(self, *, user_id):
        _ = user_id
        return self.active_room_public_ids

    async def lock_waiting_room_membership_for_user(self, *, user_id):
        self.locked_waiting_membership_user_ids.append(user_id)

    async def create_room(self, *, owner_user_id, name, game_type, status, max_players):
        room = RoomCreateResult(
            room_public_id=uuid4(),
            name=name,
            game_type=game_type,
            status=status,
            max_players=max_players,
            member_count=0,
            created_at=datetime(2026, 6, 12, tzinfo=KST),
        )
        self.created_rooms.append(
            {
                "owner_user_id": owner_user_id,
                "name": name,
                "game_type": game_type,
                "status": status,
                "max_players": max_players,
                "room": room,
            }
        )
        self.room = GameRoomRecord(
            id=uuid4(),
            public_id=room.room_public_id,
            owner_user_id=owner_user_id,
            name=name,
            game_type=game_type,
            status=status,
            max_players=max_players,
            created_at=room.created_at,
        )
        self.rooms_by_public_id[self.room.public_id] = self.room
        return self.room

    async def get_room_by_public_id(self, room_public_id):
        return self.rooms_by_public_id.get(room_public_id)

    async def get_room_by_public_id_for_update(self, room_public_id):
        self.locked_room_public_ids.append(room_public_id)
        return self.rooms_by_public_id.get(room_public_id)

    async def get_active_session_by_room_id(self, room_id):
        if any(room.id == room_id for room in self.rooms_by_public_id.values()):
            return self.active_session
        return None

    async def list_active_room_members(self, room_id):
        return [member for member in self.members if member.room_id == room_id]

    async def get_active_room_member(self, *, room_id, user_id):
        return next(
            (
                member
                for member in self.members
                if member.room_id == room_id and member.user_id == user_id
            ),
            None,
        )

    async def create_room_member(self, *, room_id, user_id, nickname):
        member = RoomMemberRecord(
            room_id=room_id,
            user_id=user_id,
            nickname=nickname,
            joined_at=datetime(2026, 6, 12, tzinfo=KST),
        )
        self.members.append(member)
        self.created_members.append(member)
        return member

    async def mark_room_member_left(self, *, room_id, user_id, left_at):
        member = await self.get_active_room_member(room_id=room_id, user_id=user_id)
        if member is None:
            return None
        self.members = [
            existing
            for existing in self.members
            if not (existing.room_id == room_id and existing.user_id == user_id)
        ]
        result = RoomLeaveResult(
            room_public_id=self._room_public_id_for_room_id(room_id),
            user_public_id=uuid4(),
            nickname=member.nickname,
            left_at=left_at,
        )
        self.left_members.append(result)
        return result

    async def transfer_room_owner(self, *, room_id, owner_user_id):
        room = self._room_for_room_id(room_id)
        if room is not None:
            updated = GameRoomRecord(
                id=room.id,
                public_id=room.public_id,
                owner_user_id=owner_user_id,
                name=room.name,
                game_type=room.game_type,
                status=room.status,
                max_players=room.max_players,
                rule_config=room.rule_config,
                created_at=room.created_at,
            )
            self.rooms_by_public_id[updated.public_id] = updated
            if self.room and self.room.id == room_id:
                self.room = updated
            self.new_owner_user_id = owner_user_id

    async def close_room(self, *, room_id, closed_at):
        self.closed_rooms.append({"room_id": room_id, "closed_at": closed_at})
        room = self._room_for_room_id(room_id)
        if room is not None:
            updated = GameRoomRecord(
                id=room.id,
                public_id=room.public_id,
                owner_user_id=room.owner_user_id,
                name=room.name,
                game_type=room.game_type,
                status="closed",
                max_players=room.max_players,
                rule_config=room.rule_config,
                created_at=room.created_at,
            )
            self.rooms_by_public_id[updated.public_id] = updated
            if self.room and self.room.id == room_id:
                self.room = updated

    async def abort_active_session_for_room(self, *, room_id, ended_at):
        self.aborted_sessions.append({"room_id": room_id, "ended_at": ended_at})

    async def update_room_settings(self, *, room_id, name, max_players, rule_config):
        self.updated_rooms.append(
            {
                "room_id": room_id,
                "name": name,
                "max_players": max_players,
                "rule_config": rule_config,
            }
        )
        room = self._room_for_room_id(room_id)
        if room is None:
            raise AssertionError("room must exist before update")
        updated = GameRoomRecord(
            id=room.id,
            public_id=room.public_id,
            owner_user_id=room.owner_user_id,
            name=name,
            game_type=room.game_type,
            status=room.status,
            max_players=max_players,
            rule_config=rule_config,
            created_at=room.created_at,
        )
        self.rooms_by_public_id[updated.public_id] = updated
        if self.room and self.room.id == room_id:
            self.room = updated
        return RoomUpdateResult(
            room_public_id=updated.public_id,
            name=name,
            game_type=updated.game_type,
            status=updated.status,
            max_players=max_players,
            rule_config=rule_config,
        )

    async def create_game_session(self, **kwargs):
        self.created_sessions.append(kwargs)
        return kwargs["session"]

    async def get_user_participant_for_session(self, *, game_session_public_id, user_id):
        if self.participant is None:
            return None
        if (
            self.participant.game_session_public_id == game_session_public_id
            and self.participant.user_id == user_id
        ):
            return self.participant
        return None

    async def get_participant_for_game_session_token(self, *, token_hash, now):
        _ = now
        if self.participant is None:
            return None
        expected_hash = (
            self.issued_credentials[0]["token_hash"] if self.issued_credentials else None
        )
        return self.participant if token_hash == expected_hash else None

    async def save_game_session_token(
        self,
        *,
        game_session_public_id,
        user_id,
        token_hash,
        expires_at,
    ):
        self.issued_credentials.append(
            {
                "game_session_public_id": game_session_public_id,
                "user_id": user_id,
                "token_hash": token_hash,
                "expires_at": expires_at,
            }
        )

    async def commit(self):
        self.committed = True
        self.commit_count += 1

    def _room_for_room_id(self, room_id):
        return next(
            (room for room in self.rooms_by_public_id.values() if room.id == room_id),
            None,
        )

    def _room_public_id_for_room_id(self, room_id):
        room = self._room_for_room_id(room_id)
        if room is None:
            raise AssertionError("room must exist before leaving")
        return room.public_id


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
        expires_at=datetime.now(KST) + timedelta(days=1),
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


def test_game_service_joins_waiting_room_and_persists_membership():
    user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="초보자",
    )
    room_id = uuid4()
    room_public_id = uuid4()
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=uuid4(),
            name="첫 객실",
            game_type="word_chain",
            status="waiting",
            max_players=2,
        )
    )
    service = GameService(repository)

    result = asyncio.run(service.join_room(room_public_id=room_public_id, user=user))

    assert result.room_public_id == room_public_id
    assert result.user_public_id == user.public_id
    assert result.nickname == "초보자"
    assert result.already_member is False
    assert repository.created_members[0].user_id == user.id
    assert repository.committed is True


def test_game_service_leaves_existing_waiting_room_before_joining_another_room():
    user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="초보자",
    )
    old_room_id = uuid4()
    old_room_public_id = uuid4()
    new_room_id = uuid4()
    new_room_public_id = uuid4()
    old_room = GameRoomRecord(
        id=old_room_id,
        public_id=old_room_public_id,
        owner_user_id=user.id,
        name="이전 객실",
        game_type="word_chain",
        status="waiting",
        max_players=4,
    )
    new_room = GameRoomRecord(
        id=new_room_id,
        public_id=new_room_public_id,
        owner_user_id=uuid4(),
        name="새 객실",
        game_type="word_chain",
        status="waiting",
        max_players=4,
    )
    repository = FakeGameRepository(
        room=new_room,
        rooms=[old_room, new_room],
        members=[
            RoomMemberRecord(
                room_id=old_room_id,
                user_id=user.id,
                nickname=user.nickname,
                joined_at=datetime(2026, 6, 12, tzinfo=KST),
            )
        ],
        active_room_public_ids=[old_room_public_id],
    )
    service = GameService(repository)

    result = asyncio.run(service.join_room(room_public_id=new_room_public_id, user=user))

    assert result.room_public_id == new_room_public_id
    assert result.already_member is False
    assert repository.closed_rooms == [
        {
            "room_id": old_room_id,
            "closed_at": repository.left_members[0].left_at,
        }
    ]
    assert repository.created_members[-1].room_id == new_room_id
    assert repository.created_members[-1].user_id == user.id
    assert repository.commit_count == 1


def test_game_service_keeps_existing_waiting_room_when_target_room_is_full():
    user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="초보자",
    )
    old_room_id = uuid4()
    old_room_public_id = uuid4()
    full_room_id = uuid4()
    full_room_public_id = uuid4()
    old_room = GameRoomRecord(
        id=old_room_id,
        public_id=old_room_public_id,
        owner_user_id=user.id,
        name="이전 객실",
        game_type="word_chain",
        status="waiting",
        max_players=4,
    )
    full_room = GameRoomRecord(
        id=full_room_id,
        public_id=full_room_public_id,
        owner_user_id=uuid4(),
        name="가득 찬 객실",
        game_type="word_chain",
        status="waiting",
        max_players=1,
    )
    repository = FakeGameRepository(
        room=full_room,
        rooms=[old_room, full_room],
        members=[
            RoomMemberRecord(
                room_id=old_room_id,
                user_id=user.id,
                nickname=user.nickname,
                joined_at=datetime(2026, 6, 12, tzinfo=KST),
            ),
            RoomMemberRecord(
                room_id=full_room_id,
                user_id=uuid4(),
                nickname="다른손님",
                joined_at=datetime(2026, 6, 12, tzinfo=KST),
            ),
        ],
        active_room_public_ids=[old_room_public_id],
    )
    service = GameService(repository)

    with pytest.raises(GameRoomNotJoinableError):
        asyncio.run(service.join_room(room_public_id=full_room_public_id, user=user))

    assert repository.left_members == []
    assert repository.closed_rooms == []
    assert repository.created_members == []


def test_game_service_lists_rooms_for_lobby_selection():
    user_id = uuid4()
    room_public_id = uuid4()
    repository = FakeGameRepository(room=None)
    repository.room_summaries = [
        GameRoomListItem(
            room_public_id=room_public_id,
            name="첫 객실",
            game_type="word_chain",
            status="waiting",
            max_players=4,
            member_count=2,
            is_current_user_member=True,
            is_current_user_owner=False,
        )
    ]
    service = GameService(repository)

    result = asyncio.run(service.list_rooms(user_id=user_id))

    assert result.rooms[0].room_public_id == room_public_id
    assert result.rooms[0].member_count == 2
    assert result.current_membership is not None
    assert result.current_membership.room_public_id == room_public_id
    assert result.current_membership.lobby_websocket_path == f"/ws/lobby/rooms/{room_public_id}"


def test_game_service_creates_waiting_room_and_owner_membership():
    owner = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="방장",
    )
    repository = FakeGameRepository(room=None)
    service = GameService(repository)

    result = asyncio.run(
        service.create_room(
            name="첫 객실",
            game_type="word_chain",
            max_players=4,
            owner=owner,
        )
    )

    assert result.name == "첫 객실"
    assert result.status == "waiting"
    assert result.member_count == 1
    assert repository.created_rooms[0]["owner_user_id"] == owner.id
    assert repository.created_members[0].user_id == owner.id
    assert repository.locked_waiting_membership_user_ids == [owner.id]
    assert repository.committed is True


def test_game_service_locks_user_waiting_membership_before_creating_room():
    owner = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="방장",
    )
    repository = FakeGameRepository(room=None)
    service = GameService(repository)

    asyncio.run(
        service.create_room(
            name="첫 객실",
            game_type="word_chain",
            max_players=4,
            owner=owner,
        )
    )

    assert repository.locked_waiting_membership_user_ids == [owner.id]


def test_game_service_closes_existing_waiting_room_before_creating_new_room():
    owner = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="방장",
    )
    old_room_id = uuid4()
    old_room_public_id = uuid4()
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=old_room_id,
            public_id=old_room_public_id,
            owner_user_id=owner.id,
            name="이전 객실",
            game_type="word_chain",
            status="waiting",
            max_players=4,
        ),
        members=[
            RoomMemberRecord(
                room_id=old_room_id,
                user_id=owner.id,
                nickname=owner.nickname,
                joined_at=datetime(2026, 6, 12, tzinfo=KST),
            )
        ],
        active_room_public_ids=[old_room_public_id],
    )
    service = GameService(repository)

    result = asyncio.run(
        service.create_room(
            name="새 객실",
            game_type="word_chain",
            max_players=4,
            owner=owner,
        )
    )

    assert result.name == "새 객실"
    assert repository.closed_rooms == [
        {
            "room_id": old_room_id,
            "closed_at": repository.left_members[0].left_at,
        }
    ]
    assert repository.left_members[0].nickname == owner.nickname
    assert repository.created_members[-1].user_id == owner.id
    assert repository.committed is True
    assert repository.commit_count == 1


def test_game_service_aborts_solo_started_room_before_creating_new_room():
    owner = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="방장",
    )
    old_room_id = uuid4()
    old_room_public_id = uuid4()
    game_session_public_id = uuid4()
    old_session = GameSessionStartResult(
        game_session_public_id=game_session_public_id,
        room_public_id=old_room_public_id,
        game_type="word_chain",
        status="starting",
        participants=[
            GameSessionParticipantRecord(
                participant_id=uuid4(),
                game_session_public_id=game_session_public_id,
                user_id=owner.id,
                participant_type="user",
                display_name="1번 손님",
                seat_number=1,
                is_uninvited_guest=False,
            ),
            GameSessionParticipantRecord(
                participant_id=uuid4(),
                game_session_public_id=game_session_public_id,
                user_id=None,
                participant_type="ai",
                display_name="2번 손님",
                seat_number=2,
                is_uninvited_guest=True,
            ),
        ],
    )
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=old_room_id,
            public_id=old_room_public_id,
            owner_user_id=owner.id,
            name="이전 객실",
            game_type="word_chain",
            status="starting",
            max_players=4,
        ),
        members=[
            RoomMemberRecord(
                room_id=old_room_id,
                user_id=owner.id,
                nickname=owner.nickname,
                joined_at=datetime(2026, 6, 12, tzinfo=KST),
            )
        ],
        active_room_public_ids=[old_room_public_id],
        active_session=old_session,
    )
    service = GameService(repository)

    result = asyncio.run(
        service.create_room(
            name="새 객실",
            game_type="word_chain",
            max_players=4,
            owner=owner,
        )
    )

    assert result.name == "새 객실"
    assert repository.aborted_sessions == [
        {
            "room_id": old_room_id,
            "ended_at": repository.left_members[0].left_at,
        }
    ]
    assert repository.closed_rooms == [
        {
            "room_id": old_room_id,
            "closed_at": repository.left_members[0].left_at,
        }
    ]
    assert repository.created_members[-1].user_id == owner.id
    assert repository.commit_count == 1


def test_game_service_authorizes_room_lobby_connection_for_active_member():
    user_id = uuid4()
    user_public_id = uuid4()
    owner_public_id = uuid4()
    room_id = uuid4()
    room_public_id = uuid4()
    joined_at = datetime(2026, 6, 12, tzinfo=KST)
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=user_id,
            name="첫 객실",
            game_type="word_chain",
            status="waiting",
            max_players=4,
        ),
        members=[
            RoomMemberRecord(
                room_id=room_id,
                user_id=user_id,
                nickname="초보자",
                joined_at=joined_at,
                user_public_id=user_public_id,
            ),
            RoomMemberRecord(
                room_id=room_id,
                user_id=uuid4(),
                nickname="손님",
                joined_at=joined_at + timedelta(minutes=1),
                user_public_id=owner_public_id,
            ),
        ],
    )
    service = GameService(repository)

    result = asyncio.run(
        service.authorize_room_lobby_connection(
            room_public_id=room_public_id,
            user_id=user_id,
        )
    )

    assert result.room_public_id == room_public_id
    assert result.snapshot is not None
    assert result.snapshot.room_public_id == room_public_id
    assert result.snapshot.owner_user_public_id == user_public_id
    assert [member.nickname for member in result.snapshot.members] == ["초보자", "손님"]
    assert [member.is_owner for member in result.snapshot.members] == [True, False]


def test_game_service_rejects_room_lobby_connection_for_user_outside_room():
    room_id = uuid4()
    room_public_id = uuid4()
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=uuid4(),
            name="첫 객실",
            game_type="word_chain",
            status="waiting",
            max_players=4,
        ),
        members=[],
    )
    service = GameService(repository)

    with pytest.raises(GameRoomEntryForbiddenError):
        asyncio.run(
            service.authorize_room_lobby_connection(
                room_public_id=room_public_id,
                user_id=uuid4(),
            )
        )


def test_game_service_marks_room_member_left_after_disconnect_grace():
    user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="초보자",
    )
    room_id = uuid4()
    room_public_id = uuid4()
    left_at = datetime(2026, 6, 12, tzinfo=KST)
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=uuid4(),
            name="첫 객실",
            game_type="word_chain",
            status="waiting",
            max_players=4,
        ),
        members=[
            RoomMemberRecord(
                room_id=room_id,
                user_id=user.id,
                nickname=user.nickname,
                joined_at=datetime(2026, 6, 12, tzinfo=KST),
            )
        ],
    )
    service = GameService(repository)

    result = asyncio.run(
        service.leave_room_after_disconnect_grace(
            room_public_id=room_public_id,
            user=user,
            left_at=left_at,
        )
    )

    assert result == RoomLeaveResult(
        room_public_id=room_public_id,
        user_public_id=user.public_id,
        nickname=user.nickname,
        left_at=left_at,
        room_closed=True,
    )
    assert repository.left_members[0].nickname == user.nickname
    assert repository.committed is True


def test_game_service_transfers_owner_when_room_owner_leaves_waiting_room():
    owner = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="방장",
    )
    next_owner_id = uuid4()
    next_owner_public_id = uuid4()
    room_id = uuid4()
    room_public_id = uuid4()
    left_at = datetime(2026, 6, 12, tzinfo=KST)
    next_owner = RoomMemberRecord(
        room_id=room_id,
        user_id=next_owner_id,
        nickname="다음방장",
        joined_at=datetime(2026, 6, 12, 0, 1, tzinfo=KST),
        user_public_id=next_owner_public_id,
    )
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=owner.id,
            name="첫 객실",
            game_type="word_chain",
            status="waiting",
            max_players=4,
        ),
        members=[
            RoomMemberRecord(
                room_id=room_id,
                user_id=owner.id,
                nickname=owner.nickname,
                joined_at=datetime(2026, 6, 12, tzinfo=KST),
            ),
            next_owner,
        ],
    )
    service = GameService(repository)

    result = asyncio.run(
        service.leave_room(
            room_public_id=room_public_id,
            user=owner,
            left_at=left_at,
        )
    )

    assert result is not None
    assert result.new_owner_user_public_id == next_owner_public_id
    assert result.new_owner_nickname == "다음방장"
    assert result.remaining_member_count == 1
    assert result.room_closed is False
    assert repository.new_owner_user_id == next_owner_id
    assert repository.closed_rooms == []
    assert repository.committed is True


def test_game_service_closes_waiting_room_when_last_member_leaves():
    user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="방장",
    )
    room_id = uuid4()
    room_public_id = uuid4()
    left_at = datetime(2026, 6, 12, tzinfo=KST)
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=user.id,
            name="첫 객실",
            game_type="word_chain",
            status="waiting",
            max_players=4,
        ),
        members=[
            RoomMemberRecord(
                room_id=room_id,
                user_id=user.id,
                nickname=user.nickname,
                joined_at=datetime(2026, 6, 12, tzinfo=KST),
            )
        ],
    )
    service = GameService(repository)

    result = asyncio.run(
        service.leave_room(
            room_public_id=room_public_id,
            user=user,
            left_at=left_at,
        )
    )

    assert result is not None
    assert result.room_closed is True
    assert result.remaining_member_count == 0
    assert result.new_owner_user_public_id is None
    assert repository.closed_rooms == [{"room_id": room_id, "closed_at": left_at}]
    assert repository.committed is True


def test_game_service_skips_leave_when_room_member_already_inactive():
    user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="초보자",
    )
    room_id = uuid4()
    room_public_id = uuid4()
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=uuid4(),
            name="첫 객실",
            game_type="word_chain",
            status="waiting",
            max_players=4,
        ),
        members=[],
    )
    service = GameService(repository)

    result = asyncio.run(
        service.leave_room_after_disconnect_grace(
            room_public_id=room_public_id,
            user=user,
            left_at=datetime(2026, 6, 12, tzinfo=KST),
        )
    )

    assert result is None
    assert repository.left_members == []
    assert repository.committed is False


def test_game_service_returns_existing_room_member_for_repeated_join():
    user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="초보자",
    )
    room_id = uuid4()
    room_public_id = uuid4()
    existing_member = RoomMemberRecord(
        room_id=room_id,
        user_id=user.id,
        nickname="초보자",
        joined_at=datetime(2026, 6, 12, tzinfo=KST),
    )
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=uuid4(),
            name="첫 객실",
            game_type="word_chain",
            status="waiting",
            max_players=2,
        ),
        members=[existing_member],
    )
    service = GameService(repository)

    result = asyncio.run(service.join_room(room_public_id=room_public_id, user=user))

    assert result.already_member is True
    assert result.joined_at == existing_member.joined_at
    assert repository.created_members == []
    assert repository.committed is False


def test_game_service_updates_waiting_room_settings_for_owner():
    owner = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="방장",
    )
    room_id = uuid4()
    room_public_id = uuid4()
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=owner.id,
            name="첫 객실",
            game_type="word_chain",
            status="waiting",
            max_players=4,
            rule_config={"max_rounds": 4, "turn_time_seconds": 10},
        )
    )
    service = GameService(repository)

    result = asyncio.run(
        service.update_room(
            room_public_id=room_public_id,
            user=owner,
            name="수정된 객실",
            max_players=5,
            rule_config={"max_rounds": 8, "turn_time_seconds": 9},
        )
    )

    assert result == RoomUpdateResult(
        room_public_id=room_public_id,
        name="수정된 객실",
        game_type="word_chain",
        status="waiting",
        max_players=5,
        rule_config={"max_rounds": 8, "turn_time_seconds": 9},
    )
    assert repository.updated_rooms == [
        {
            "room_id": room_id,
            "name": "수정된 객실",
            "max_players": 5,
            "rule_config": {"max_rounds": 8, "turn_time_seconds": 9},
        }
    ]
    assert repository.locked_room_public_ids == [room_public_id]
    assert repository.committed is True


def test_game_service_rejects_room_update_from_non_owner():
    user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_002",
        nickname="손님",
    )
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=uuid4(),
            public_id=uuid4(),
            owner_user_id=uuid4(),
            name="첫 객실",
            game_type="word_chain",
            status="waiting",
            max_players=4,
        )
    )
    service = GameService(repository)

    with pytest.raises(GameRoomUpdateForbiddenError):
        asyncio.run(
            service.update_room(
                room_public_id=repository.room.public_id,
                user=user,
                name="수정된 객실",
                max_players=4,
                rule_config={"max_rounds": 8, "turn_time_seconds": 10},
            )
        )


def test_game_service_rejects_room_update_after_game_started():
    owner = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_001",
        nickname="방장",
    )
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=uuid4(),
            public_id=uuid4(),
            owner_user_id=owner.id,
            name="첫 객실",
            game_type="word_chain",
            status="starting",
            max_players=4,
        )
    )
    service = GameService(repository)

    with pytest.raises(GameRoomNotUpdateableError):
        asyncio.run(
            service.update_room(
                room_public_id=repository.room.public_id,
                user=owner,
                name="수정된 객실",
                max_players=4,
                rule_config={"max_rounds": 8, "turn_time_seconds": 10},
            )
        )


def test_game_service_rejects_join_when_room_is_full():
    user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_002",
        nickname="손님1",
    )
    room_id = uuid4()
    room_public_id = uuid4()
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=uuid4(),
            name="첫 객실",
            game_type="word_chain",
            status="waiting",
            max_players=1,
        ),
        members=[
            RoomMemberRecord(
                room_id=room_id,
                user_id=uuid4(),
                nickname="초보자",
                joined_at=datetime(2026, 6, 12, tzinfo=KST),
            )
        ],
    )
    service = GameService(repository)

    with pytest.raises(GameRoomNotJoinableError):
        asyncio.run(service.join_room(room_public_id=room_public_id, user=user))


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
            game_type="word_chain",
            status="waiting",
            max_players=4,
            rule_config={"max_rounds": 8, "turn_time_seconds": 10},
        ),
        members=[
            RoomMemberRecord(
                room_id=room_id,
                user_id=owner_id,
                nickname="방장",
                joined_at=datetime(2026, 6, 11, tzinfo=KST),
            ),
            RoomMemberRecord(
                room_id=room_id,
                user_id=member_id,
                nickname="손님",
                joined_at=datetime(2026, 6, 11, 0, 1, tzinfo=KST),
            ),
        ],
    )
    service = GameService(repository)

    result = asyncio.run(service.start_session(room_public_id=room_public_id, user_id=owner_id))

    assert result.room_public_id == room_public_id
    assert result.game_type == "word_chain"
    assert result.status == "starting"
    assert result.rule_config == {"max_rounds": 8, "turn_time_seconds": 10}
    assert [participant.participant_type for participant in result.participants] == [
        "user",
        "user",
        "ai",
    ]
    assert [participant.display_name for participant in result.participants] == [
        "1번 손님",
        "2번 손님",
        "3번 손님",
    ]
    assert [participant.seat_number for participant in result.participants] == [1, 2, 3]
    assert result.game_session_token
    assert result.game_session_token_expires_at == repository.issued_credentials[0]["expires_at"]
    assert (
        repository.issued_credentials[0]["game_session_public_id"] == result.game_session_public_id
    )
    assert repository.issued_credentials[0]["user_id"] == owner_id
    assert repository.issued_credentials[0]["token_hash"] != result.game_session_token
    assert repository.created_sessions[0]["session"].rule_config == {
        "max_rounds": 8,
        "turn_time_seconds": 10,
    }
    assert repository.locked_room_public_ids == [room_public_id]
    assert repository.committed is True


def test_game_service_returns_existing_session_for_repeated_start_request():
    owner_id = uuid4()
    room_id = uuid4()
    room_public_id = uuid4()
    game_session_public_id = uuid4()
    existing_session = GameSessionStartResult(
        game_session_public_id=game_session_public_id,
        room_public_id=room_public_id,
        game_type="word_chain",
        status="starting",
        participants=[
            GameSessionParticipantRecord(
                participant_id=uuid4(),
                game_session_public_id=game_session_public_id,
                user_id=owner_id,
                participant_type="user",
                display_name="방장",
                seat_number=1,
                is_uninvited_guest=False,
            )
        ],
    )
    repository = FakeGameRepository(
        room=GameRoomRecord(
            id=room_id,
            public_id=room_public_id,
            owner_user_id=owner_id,
            name="첫 객실",
            game_type="word_chain",
            status="starting",
            max_players=4,
        ),
        active_session=existing_session,
    )
    service = GameService(repository)

    result = asyncio.run(service.start_session(room_public_id=room_public_id, user_id=owner_id))

    assert result.game_session_public_id == game_session_public_id
    assert result.room_public_id == room_public_id
    assert result.game_session_token
    assert result.game_session_token_expires_at == repository.issued_credentials[0]["expires_at"]
    assert repository.issued_credentials[0]["game_session_public_id"] == game_session_public_id
    assert repository.issued_credentials[0]["user_id"] == owner_id
    assert repository.issued_credentials[0]["token_hash"] != result.game_session_token
    assert repository.created_sessions == []
    assert repository.locked_room_public_ids == [room_public_id]
    assert repository.committed is True


def test_game_service_rejects_entry_for_user_outside_session():
    repository = FakeGameRepository(room=None, participant=None)
    service = GameService(repository)

    with pytest.raises(GameSessionEntryForbiddenError):
        asyncio.run(service.authorize_entry(game_session_public_id=uuid4(), user_id=uuid4()))


def test_game_service_resolves_participant_identity_for_allowed_session_entry():
    user_id = uuid4()
    participant_id = uuid4()
    game_session_public_id = uuid4()
    repository = FakeGameRepository(
        room=None,
        participant=GameSessionParticipantRecord(
            participant_id=participant_id,
            game_session_public_id=game_session_public_id,
            user_id=user_id,
            participant_type="user",
            display_name="참가자",
            seat_number=1,
            is_uninvited_guest=False,
        ),
    )
    service = GameService(repository)

    result = asyncio.run(
        service.authorize_entry(game_session_public_id=game_session_public_id, user_id=user_id)
    )

    assert result.game_session_public_id == game_session_public_id
    assert result.participant.participant_id == participant_id
    assert result.participant.user_id == user_id
    assert result.game_session_token
    assert result.game_session_token_expires_at == repository.issued_credentials[0]["expires_at"]
    assert repository.issued_credentials[0]["game_session_public_id"] == game_session_public_id
    assert repository.issued_credentials[0]["user_id"] == user_id
    assert repository.issued_credentials[0]["token_hash"] != result.game_session_token


def test_game_service_resolves_participant_identity_from_game_session_token():
    user_id = uuid4()
    participant_id = uuid4()
    game_session_public_id = uuid4()
    participant = GameSessionParticipantRecord(
        participant_id=participant_id,
        game_session_public_id=game_session_public_id,
        user_id=user_id,
        participant_type="user",
        display_name="참가자",
        seat_number=1,
        is_uninvited_guest=False,
    )
    repository = FakeGameRepository(room=None, participant=participant)
    service = GameService(repository)
    issued = asyncio.run(
        service.authorize_entry(game_session_public_id=game_session_public_id, user_id=user_id)
    )

    result = asyncio.run(service.authorize_resume_token(issued.game_session_token))

    assert result.game_session_public_id == game_session_public_id
    assert result.participant.participant_id == participant_id
    assert result.participant.user_id == user_id


def test_game_service_rejects_invalid_game_session_token():
    repository = FakeGameRepository(room=None, participant=None)
    service = GameService(repository)

    with pytest.raises(GameSessionEntryForbiddenError):
        asyncio.run(service.authorize_resume_token("invalid-token"))


def test_start_game_session_endpoint_returns_session_for_authenticated_owner(monkeypatch):
    app = create_app()
    room_public_id = uuid4()
    game_session_public_id = uuid4()
    phase_id = uuid4()
    broadcast_calls: list[tuple[object, dict]] = []
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
                    "game_session_public_id": game_session_public_id,
                    "room_public_id": room_public_id,
                    "game_type": "word_chain",
                    "status": "starting",
                    "rule_config": {"max_rounds": 8, "turn_time_seconds": 10},
                    "game_session_token": "owner-resume-token",
                    "game_session_token_expires_at": datetime(2026, 6, 12, 1, tzinfo=KST),
                    "current_turn": type(
                        "CurrentTurn",
                        (),
                        {
                            "phase_id": phase_id,
                            "round_number": 1,
                            "turn_number": 1,
                            "actor_seat_number": 1,
                            "started_at": datetime(2026, 6, 12, 0, 0, 5, tzinfo=KST),
                            "deadline_at": datetime(2026, 6, 12, 0, 0, 10, tzinfo=KST),
                            "required_start_char": "가",
                        },
                    )(),
                    "participants": [
                        type(
                            "Participant",
                            (),
                            {
                                "participant_type": "user",
                                "display_name": "1번 손님",
                                "seat_number": 1,
                                "is_uninvited_guest": False,
                            },
                        )(),
                        type(
                            "Participant",
                            (),
                            {
                                "participant_type": "ai",
                                "display_name": "2번 손님",
                                "seat_number": 2,
                                "is_uninvited_guest": True,
                            },
                        )(),
                    ],
                },
            )()

    async def record_broadcast(room_public_id, message):
        broadcast_calls.append((room_public_id, message))

    monkeypatch.setattr(
        game_endpoint.lobby_connection_manager,
        "broadcast_room",
        record_broadcast,
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)

    response = client.post(f"/api/v1/game/rooms/{room_public_id}/start")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "game_session_public_id": str(game_session_public_id),
            "room_public_id": str(room_public_id),
            "game_type": "word_chain",
            "status": "starting",
            "game_session_token": "owner-resume-token",
            "game_session_token_expires_at": "2026-06-12T01:00:00+09:00",
            "rule_config": {"max_rounds": 8, "turn_time_seconds": 10},
            "current_turn": {
                "phase_id": str(phase_id),
                "round_number": 1,
                "turn_number": 1,
                "actor_seat_number": 1,
                "started_at": "2026-06-12T00:00:05+09:00",
                "deadline_at": "2026-06-12T00:00:10+09:00",
                "required_start_char": "가",
            },
            "participants": [
                {
                    "display_name": "1번 손님",
                    "seat_number": 1,
                },
                {
                    "display_name": "2번 손님",
                    "seat_number": 2,
                },
            ],
        },
    }
    assert broadcast_calls == [
        (
            room_public_id,
            {
                "type": "game.started",
                "payload": {
                    "game_session_public_id": str(game_session_public_id),
                    "room_public_id": str(room_public_id),
                    "game_type": "word_chain",
                    "status": "starting",
                    "rule_config": {"max_rounds": 8, "turn_time_seconds": 10},
                    "current_turn": {
                        "phase_id": str(phase_id),
                        "round_number": 1,
                        "turn_number": 1,
                        "actor_seat_number": 1,
                        "started_at": "2026-06-12T00:00:05+09:00",
                        "deadline_at": "2026-06-12T00:00:10+09:00",
                        "required_start_char": "가",
                    },
                    "participants": [
                        {
                            "display_name": "1번 손님",
                            "seat_number": 1,
                        },
                        {
                            "display_name": "2번 손님",
                            "seat_number": 2,
                        },
                    ],
                },
            },
        )
    ]


def test_game_session_entry_endpoint_rejects_uninvited_user():
    app = create_app()
    current_user = CurrentUser(
        id=uuid4(),
        public_id=uuid4(),
        account_id="player_002",
        nickname="외부인",
    )

    class FakeGameService:
        async def authorize_entry(self, *, game_session_public_id, user_id):
            raise GameSessionEntryForbiddenError

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_game_service] = lambda: FakeGameService()
    client = TestClient(app)

    response = client.get(f"/api/v1/game/sessions/{uuid4()}/entry")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "GAME_SESSION_ENTRY_FORBIDDEN"
