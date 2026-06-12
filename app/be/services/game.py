from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.be.security.session import generate_game_session_token, hash_game_session_token
from app.be.schemas.game_enum import GameSessionStatus, ParticipantType, RoomStatus
from app.be.services.auth import CurrentUser
from app.shared.core.identifiers import generate_uuid_v7
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


AI_DISPLAY_NAME = "수상한 손님"
GAME_SESSION_TOKEN_TTL = timedelta(hours=3)
STARTING_STATUS = GameSessionStatus.STARTING.value
WAITING_ROOM_STATUS = RoomStatus.WAITING.value


@dataclass(frozen=True)
class GameRoomRecord:
    id: UUID
    public_id: UUID
    owner_user_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    created_at: datetime | None = None


@dataclass(frozen=True)
class GameRoomListItem:
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    member_count: int


@dataclass(frozen=True)
class RoomCreateResult:
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    member_count: int
    created_at: datetime


@dataclass(frozen=True)
class RoomLobbyConnectionResult:
    room_public_id: UUID


@dataclass(frozen=True)
class RoomMemberRecord:
    room_id: UUID
    user_id: UUID
    nickname: str
    joined_at: datetime


@dataclass(frozen=True)
class RoomJoinResult:
    room_public_id: UUID
    user_public_id: UUID
    nickname: str
    joined_at: datetime
    already_member: bool


@dataclass(frozen=True)
class RoomLeaveResult:
    room_public_id: UUID
    user_public_id: UUID
    nickname: str
    left_at: datetime


@dataclass(frozen=True)
class GameSessionParticipantRecord:
    participant_id: UUID | None
    game_session_public_id: UUID
    user_id: UUID | None
    participant_type: str
    display_name: str
    seat_number: int
    is_uninvited_guest: bool
    resume_token_expires_at: datetime | None = None


@dataclass(frozen=True)
class GameSessionStartResult:
    game_session_public_id: UUID
    room_public_id: UUID
    game_type: str
    status: str
    participants: list[GameSessionParticipantRecord]
    game_session_token: str = ""
    game_session_token_expires_at: datetime | None = None


@dataclass(frozen=True)
class GameSessionEntryResult:
    game_session_public_id: UUID
    participant: GameSessionParticipantRecord
    game_session_token: str
    game_session_token_expires_at: datetime
    allowed: bool = True


@dataclass(frozen=True)
class GameSessionCredential:
    game_session_token: str
    expires_at: datetime


class GameRepositoryProtocol(Protocol):
    async def list_rooms(self) -> list[GameRoomListItem]:
        """로비 목록에 표시할 닫히지 않은 room 요약과 활성 멤버 수를 조회합니다."""

    async def create_room(
        self,
        *,
        owner_user_id: UUID,
        name: str,
        game_type: str,
        status: str,
        max_players: int,
    ) -> GameRoomRecord:
        """대기 상태 room을 생성하고 service record로 변환합니다."""

    async def get_room_by_public_id(self, room_public_id: UUID) -> GameRoomRecord | None:
        """WebSocket 로비 연결 권한 확인용으로 room을 lock 없이 조회합니다."""

    async def get_room_by_public_id_for_update(self, room_public_id: UUID) -> GameRoomRecord | None:
        """게임 시작 transaction 동안 room row를 잠그고 시작 정보를 조회합니다."""

    async def get_active_session_by_room_id(self, room_id: UUID) -> GameSessionStartResult | None:
        """이미 시작된 active 게임 세션과 참가자 snapshot을 조회합니다."""

    async def list_active_room_members(self, room_id: UUID) -> list[RoomMemberRecord]:
        """게임 시작 시 참가자로 고정할 활성 room member를 입장 순서대로 조회합니다."""

    async def get_active_room_member(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
    ) -> RoomMemberRecord | None:
        """유저가 현재 room에 활성 멤버로 참여 중인지 조회합니다."""

    async def create_room_member(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        nickname: str,
    ) -> RoomMemberRecord:
        """유저를 room의 활성 멤버로 추가합니다."""

    async def mark_room_member_left(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        left_at: datetime,
    ) -> RoomLeaveResult | None:
        """활성 room member의 퇴장 시각을 기록하고 없으면 None을 반환합니다."""

    async def create_game_session(
        self, *, session: GameSessionStartResult
    ) -> GameSessionStartResult:
        """게임 세션과 참가자 snapshot을 하나의 transaction 안에 추가합니다."""

    async def get_user_participant_for_session(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionParticipantRecord | None:
        """로그인 유저가 해당 게임 세션 참가자인지 조회합니다."""

    async def get_participant_for_game_session_token(
        self,
        *,
        token_hash: str,
        now: datetime,
    ) -> GameSessionParticipantRecord | None:
        """유효한 게임 세션 토큰 해시로 match 참가자를 조회합니다."""

    async def save_game_session_token(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        """게임 참가자의 match 복구 토큰 해시와 만료 시각을 저장합니다."""

    async def commit(self) -> None:
        """게임 시작 transaction을 확정합니다."""


class GameRoomNotFoundError(AppException):
    """요청한 room public_id가 존재하지 않을 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_NOT_FOUND)


class GameRoomStartForbiddenError(AppException):
    """방장 또는 허용된 멤버가 아닌 유저가 게임 시작을 요청할 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_START_FORBIDDEN)


class GameRoomNotStartableError(AppException):
    """room 상태나 멤버 조건이 게임 시작을 허용하지 않을 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_NOT_STARTABLE)


class GameRoomNotJoinableError(AppException):
    """room 상태나 정원 조건이 참여를 허용하지 않을 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_NOT_JOINABLE)


class GameRoomEntryForbiddenError(AppException):
    """room 활성 멤버가 아닌 유저가 room 로비에 진입하려 할 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_ENTRY_FORBIDDEN)


class GameSessionEntryForbiddenError(AppException):
    """게임 세션 참가자로 고정되지 않은 유저가 진입하려 할 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN)


class GameService:
    """게임 시작 시 세션을 발급하고 허용된 멤버만 진입하도록 검증합니다."""

    def __init__(self, repository: GameRepositoryProtocol) -> None:
        self.repository = repository

    async def list_rooms(self) -> list[GameRoomListItem]:
        """로비 화면에서 선택할 수 있는 닫히지 않은 객실 목록을 반환합니다."""
        return await self.repository.list_rooms()

    async def create_room(
        self,
        *,
        name: str,
        game_type: str,
        max_players: int,
        owner: CurrentUser,
    ) -> RoomCreateResult:
        """대기 상태 객실을 만들고 방장을 첫 활성 멤버로 등록합니다.

        room 생성과 방장 멤버십 생성은 같은 transaction에서 확정합니다. 이후 로비 WebSocket은 이
        `room_members` 행을 기준으로 연결 권한을 확인합니다.
        """
        room = await self.repository.create_room(
            owner_user_id=owner.id,
            name=name,
            game_type=game_type,
            status=WAITING_ROOM_STATUS,
            max_players=max_players,
        )
        await self.repository.create_room_member(
            room_id=room.id,
            user_id=owner.id,
            nickname=owner.nickname,
        )
        await self.repository.commit()
        if room.created_at is None:
            raise AppException(
                code=ErrorCode.HTTP_ERROR,
                details={"reason": "room_created_at_missing"},
            )
        return RoomCreateResult(
            room_public_id=room.public_id,
            name=room.name,
            game_type=room.game_type,
            status=room.status,
            max_players=room.max_players,
            member_count=1,
            created_at=room.created_at,
        )

    async def authorize_room_lobby_connection(
        self,
        *,
        room_public_id: UUID,
        user_id: UUID,
    ) -> RoomLobbyConnectionResult:
        """room 로비 WebSocket 연결 전에 해당 유저가 활성 room member인지 확인합니다."""
        room = await self.repository.get_room_by_public_id(room_public_id)
        if room is None:
            raise GameRoomNotFoundError
        member = await self.repository.get_active_room_member(
            room_id=room.id,
            user_id=user_id,
        )
        if member is None:
            raise GameRoomEntryForbiddenError
        return RoomLobbyConnectionResult(room_public_id=room.public_id)

    async def join_room(self, *, room_public_id: UUID, user: CurrentUser) -> RoomJoinResult:
        """로그인 유저를 대기 중인 room의 활성 멤버로 참여시킵니다.

        이미 참여 중인 유저의 반복 요청은 새 row를 만들지 않고 기존 참여 정보를 반환합니다.
        room 상태와 정원 판단은 room row lock 안에서 수행해 중복 참여와 초과 참여를 줄입니다.
        """
        room = await self.repository.get_room_by_public_id_for_update(room_public_id)
        if room is None:
            raise GameRoomNotFoundError
        if room.status != WAITING_ROOM_STATUS:
            raise GameRoomNotJoinableError

        existing_member = await self.repository.get_active_room_member(
            room_id=room.id,
            user_id=user.id,
        )
        if existing_member is not None:
            return RoomJoinResult(
                room_public_id=room.public_id,
                user_public_id=user.public_id,
                nickname=existing_member.nickname,
                joined_at=existing_member.joined_at,
                already_member=True,
            )

        members = await self.repository.list_active_room_members(room.id)
        if len(members) >= room.max_players:
            raise GameRoomNotJoinableError

        member = await self.repository.create_room_member(
            room_id=room.id,
            user_id=user.id,
            nickname=user.nickname,
        )
        await self.repository.commit()
        return RoomJoinResult(
            room_public_id=room.public_id,
            user_public_id=user.public_id,
            nickname=member.nickname,
            joined_at=member.joined_at,
            already_member=False,
        )

    async def leave_room_after_disconnect_grace(
        self,
        *,
        room_public_id: UUID,
        user: CurrentUser,
        left_at: datetime,
    ) -> RoomLeaveResult | None:
        """WebSocket grace timeout 이후에도 복귀하지 않은 유저를 room에서 퇴장 처리합니다.

        이미 다른 흐름에서 퇴장된 멤버라면 DB를 다시 변경하지 않고 None을 반환합니다.
        """
        room = await self.repository.get_room_by_public_id(room_public_id)
        if room is None:
            raise GameRoomNotFoundError
        result = await self.repository.mark_room_member_left(
            room_id=room.id,
            user_id=user.id,
            left_at=left_at,
        )
        if result is None:
            return None
        await self.repository.commit()
        return RoomLeaveResult(
            room_public_id=room.public_id,
            user_public_id=user.public_id,
            nickname=result.nickname,
            left_at=result.left_at,
        )

    async def start_session(self, *, room_public_id: UUID, user_id: UUID) -> GameSessionStartResult:
        """방장이 room의 활성 멤버를 참가자로 고정하고 게임 세션 식별자를 발급합니다.

        같은 방장이 start API를 반복 호출하면 기존 active session을 그대로 반환합니다.
        room row lock을 잡은 뒤 판단해서 동시 중복 요청도 같은 transaction 경계에서 직렬화합니다.
        """
        room = await self.repository.get_room_by_public_id_for_update(room_public_id)
        if room is None:
            raise GameRoomNotFoundError
        if room.owner_user_id != user_id:
            raise GameRoomStartForbiddenError
        active_session = await self.repository.get_active_session_by_room_id(room.id)
        if active_session is not None:
            credential = await self._issue_game_session_credential(
                game_session_public_id=active_session.game_session_public_id,
                user_id=user_id,
            )
            await self.repository.commit()
            return replace(
                active_session,
                game_session_token=credential.game_session_token,
                game_session_token_expires_at=credential.expires_at,
            )
        if room.status != WAITING_ROOM_STATUS:
            raise GameRoomNotStartableError

        members = await self.repository.list_active_room_members(room.id)
        if not any(member.user_id == user_id for member in members):
            raise GameRoomStartForbiddenError
        if not members:
            raise GameRoomNotStartableError

        game_session_public_id = generate_uuid_v7()
        participants = [
            GameSessionParticipantRecord(
                participant_id=None,
                game_session_public_id=game_session_public_id,
                user_id=member.user_id,
                participant_type=ParticipantType.USER.value,
                display_name=member.nickname,
                seat_number=index,
                is_uninvited_guest=False,
            )
            for index, member in enumerate(members, start=1)
        ]
        participants.append(
            GameSessionParticipantRecord(
                participant_id=None,
                game_session_public_id=game_session_public_id,
                user_id=None,
                participant_type=ParticipantType.AI.value,
                display_name=AI_DISPLAY_NAME,
                seat_number=len(participants) + 1,
                is_uninvited_guest=True,
            )
        )

        result = await self.repository.create_game_session(
            session=GameSessionStartResult(
                game_session_public_id=game_session_public_id,
                room_public_id=room.public_id,
                game_type=room.game_type,
                status=STARTING_STATUS,
                participants=participants,
            )
        )
        credential = await self._issue_game_session_credential(
            game_session_public_id=game_session_public_id,
            user_id=user_id,
        )
        await self.repository.commit()
        return replace(
            result,
            game_session_token=credential.game_session_token,
            game_session_token_expires_at=credential.expires_at,
        )

    async def authorize_entry(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionEntryResult:
        """로그인 유저가 게임 시작 시 고정된 참가자인지 확인하고 진입 정보를 반환합니다."""
        participant = await self.repository.get_user_participant_for_session(
            game_session_public_id=game_session_public_id,
            user_id=user_id,
        )
        if participant is None:
            raise GameSessionEntryForbiddenError
        credential = await self._issue_game_session_credential(
            game_session_public_id=game_session_public_id,
            user_id=user_id,
        )
        await self.repository.commit()
        return GameSessionEntryResult(
            game_session_public_id=game_session_public_id,
            participant=participant,
            game_session_token=credential.game_session_token,
            game_session_token_expires_at=credential.expires_at,
        )

    async def authorize_resume_token(self, game_session_token: str) -> GameSessionEntryResult:
        """로그인 세션 만료 후에도 유효한 게임 세션 토큰으로 match 참가자를 복원합니다."""
        participant = await self.repository.get_participant_for_game_session_token(
            token_hash=hash_game_session_token(game_session_token),
            now=datetime.now(UTC),
        )
        if participant is None:
            raise GameSessionEntryForbiddenError
        return GameSessionEntryResult(
            game_session_public_id=participant.game_session_public_id,
            participant=participant,
            game_session_token=game_session_token,
            game_session_token_expires_at=participant.resume_token_expires_at or datetime.now(UTC),
        )

    async def _issue_game_session_credential(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionCredential:
        """로그인 세션과 별개로 특정 match 참가자에게만 유효한 복구 토큰을 발급합니다."""
        game_session_token = generate_game_session_token()
        expires_at = datetime.now(UTC) + GAME_SESSION_TOKEN_TTL
        await self.repository.save_game_session_token(
            game_session_public_id=game_session_public_id,
            user_id=user_id,
            token_hash=hash_game_session_token(game_session_token),
            expires_at=expires_at,
        )
        return GameSessionCredential(
            game_session_token=game_session_token,
            expires_at=expires_at,
        )
