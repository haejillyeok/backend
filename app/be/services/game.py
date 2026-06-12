from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.shared.core.identifiers import generate_uuid_v7
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


AI_DISPLAY_NAME = "수상한 손님"
STARTING_STATUS = "starting"
WAITING_ROOM_STATUS = "waiting"


@dataclass(frozen=True)
class GameRoomRecord:
    id: UUID
    public_id: UUID
    owner_user_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int


@dataclass(frozen=True)
class RoomMemberRecord:
    room_id: UUID
    user_id: UUID
    nickname: str
    joined_at: datetime


@dataclass(frozen=True)
class GameSessionParticipantRecord:
    participant_id: UUID | None
    session_public_id: UUID
    user_id: UUID | None
    participant_type: str
    display_name: str
    seat_number: int
    is_uninvited_guest: bool


@dataclass(frozen=True)
class GameSessionStartResult:
    session_public_id: UUID
    room_public_id: UUID
    game_type: str
    status: str
    participants: list[GameSessionParticipantRecord]


@dataclass(frozen=True)
class GameSessionEntryResult:
    session_public_id: UUID
    participant: GameSessionParticipantRecord
    allowed: bool = True


class GameRepositoryProtocol(Protocol):
    async def get_room_by_public_id_for_update(self, room_public_id: UUID) -> GameRoomRecord | None:
        """게임 시작 transaction 동안 room row를 잠그고 시작 정보를 조회합니다."""

    async def get_active_session_by_room_id(self, room_id: UUID) -> GameSessionStartResult | None:
        """이미 시작된 active 게임 세션과 참가자 snapshot을 조회합니다."""

    async def list_active_room_members(self, room_id: UUID) -> list[RoomMemberRecord]:
        """게임 시작 시 참가자로 고정할 활성 room member를 입장 순서대로 조회합니다."""

    async def create_game_session(
        self, *, session: GameSessionStartResult
    ) -> GameSessionStartResult:
        """게임 세션과 참가자 snapshot을 하나의 transaction 안에 추가합니다."""

    async def get_user_participant_for_session(
        self,
        *,
        session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionParticipantRecord | None:
        """로그인 유저가 해당 게임 세션 참가자인지 조회합니다."""

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


class GameSessionEntryForbiddenError(AppException):
    """게임 세션 참가자로 고정되지 않은 유저가 진입하려 할 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN)


class GameService:
    """게임 시작 시 세션을 발급하고 허용된 멤버만 진입하도록 검증합니다."""

    def __init__(self, repository: GameRepositoryProtocol) -> None:
        self.repository = repository

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
            return active_session
        if room.status != WAITING_ROOM_STATUS:
            raise GameRoomNotStartableError

        members = await self.repository.list_active_room_members(room.id)
        if not any(member.user_id == user_id for member in members):
            raise GameRoomStartForbiddenError
        if not members:
            raise GameRoomNotStartableError

        session_public_id = generate_uuid_v7()
        participants = [
            GameSessionParticipantRecord(
                participant_id=None,
                session_public_id=session_public_id,
                user_id=member.user_id,
                participant_type="user",
                display_name=member.nickname,
                seat_number=index,
                is_uninvited_guest=False,
            )
            for index, member in enumerate(members, start=1)
        ]
        participants.append(
            GameSessionParticipantRecord(
                participant_id=None,
                session_public_id=session_public_id,
                user_id=None,
                participant_type="ai",
                display_name=AI_DISPLAY_NAME,
                seat_number=len(participants) + 1,
                is_uninvited_guest=True,
            )
        )

        result = await self.repository.create_game_session(
            session=GameSessionStartResult(
                session_public_id=session_public_id,
                room_public_id=room.public_id,
                game_type=room.game_type,
                status=STARTING_STATUS,
                participants=participants,
            )
        )
        await self.repository.commit()
        return result

    async def authorize_entry(
        self,
        *,
        session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionEntryResult:
        """로그인 유저가 게임 시작 시 고정된 참가자인지 확인하고 진입 정보를 반환합니다."""
        participant = await self.repository.get_user_participant_for_session(
            session_public_id=session_public_id,
            user_id=user_id,
        )
        if participant is None:
            raise GameSessionEntryForbiddenError
        return GameSessionEntryResult(
            session_public_id=session_public_id,
            participant=participant,
        )
