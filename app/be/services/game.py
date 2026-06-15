from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.be.security.session import generate_game_session_token, hash_game_session_token
from app.be.schemas.game_enum import GameSessionStatus, ParticipantType, RoomStatus
from app.be.services.auth import CurrentUser
from app.shared.core.identifiers import generate_uuid_v7
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException
from app.shared.core.timezone import kst_now


AI_DISPLAY_NAME = "수상한 손님"
GAME_SESSION_TOKEN_TTL = timedelta(hours=3)
STARTING_STATUS = GameSessionStatus.STARTING.value
WAITING_ROOM_STATUS = RoomStatus.WAITING.value
SOLO_ABORTABLE_ROOM_STATUSES = (RoomStatus.STARTING.value, RoomStatus.PLAYING.value)
DEFAULT_ROOM_RULE_CONFIG = {"max_rounds": 8, "turn_time_seconds": 10}


def default_room_rule_config() -> dict[str, int]:
    """새 room과 기존 설정 누락 room에 적용할 단어 게임 기본 룰을 반환합니다."""
    return dict(DEFAULT_ROOM_RULE_CONFIG)


@dataclass(frozen=True)
class GameRoomRecord:
    id: UUID
    public_id: UUID
    owner_user_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    rule_config: dict[str, int] = field(default_factory=default_room_rule_config)
    created_at: datetime | None = None


@dataclass(frozen=True)
class GameRoomListItem:
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    member_count: int
    is_current_user_member: bool = False
    is_current_user_owner: bool = False


@dataclass(frozen=True)
class CurrentLobbyMembership:
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    member_count: int
    is_owner: bool
    lobby_websocket_path: str


@dataclass(frozen=True)
class GameRoomListResult:
    rooms: list[GameRoomListItem]
    current_membership: CurrentLobbyMembership | None = None


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
class RoomUpdateResult:
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    rule_config: dict[str, int]


@dataclass(frozen=True)
class RoomLobbyConnectionResult:
    room_public_id: UUID
    snapshot: "RoomLobbySnapshotResult | None" = None


@dataclass(frozen=True)
class RoomLobbyMemberSnapshot:
    user_public_id: UUID
    nickname: str
    is_owner: bool
    joined_at: datetime


@dataclass(frozen=True)
class RoomLobbySnapshotResult:
    room_public_id: UUID
    owner_user_public_id: UUID | None
    members: list[RoomLobbyMemberSnapshot]


@dataclass(frozen=True)
class RoomMemberRecord:
    room_id: UUID
    user_id: UUID
    nickname: str
    joined_at: datetime
    user_public_id: UUID | None = None


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
    remaining_member_count: int = 0
    new_owner_user_public_id: UUID | None = None
    new_owner_nickname: str | None = None
    room_closed: bool = False


@dataclass(frozen=True)
class GameSessionParticipantRecord:
    participant_id: UUID | None
    game_session_public_id: UUID
    user_id: UUID | None
    participant_type: str
    display_name: str
    seat_number: int
    is_uninvited_guest: bool
    original_nickname: str | None = None
    resume_token_expires_at: datetime | None = None


@dataclass(frozen=True)
class GameSessionTurnRecord:
    phase_id: UUID
    round_number: int
    turn_number: int
    actor_seat_number: int
    deadline_at: datetime | None
    required_start_char: str | None


@dataclass(frozen=True)
class GameSessionStartResult:
    game_session_public_id: UUID
    room_public_id: UUID
    game_type: str
    status: str
    participants: list[GameSessionParticipantRecord]
    rule_config: dict[str, int] = field(default_factory=default_room_rule_config)
    game_session_token: str = ""
    game_session_token_expires_at: datetime | None = None
    current_turn: GameSessionTurnRecord | None = None


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
    async def list_rooms(self, *, user_id: UUID) -> list[GameRoomListItem]:
        """로비 목록과 현재 유저의 활성 room membership 여부를 조회합니다."""

    async def lock_waiting_room_membership_for_user(self, *, user_id: UUID) -> None:
        """한 유저의 대기 room membership 변경을 transaction 안에서 직렬화합니다."""

    async def list_active_waiting_room_public_ids_for_user(self, *, user_id: UUID) -> list[UUID]:
        """유저가 현재 active member로 남아 있는 대기 room public_id 목록을 조회합니다."""

    async def list_active_room_public_ids_for_user(self, *, user_id: UUID) -> list[UUID]:
        """유저가 현재 active member로 남아 있는 닫히지 않은 room public_id 목록을 조회합니다."""

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

    async def transfer_room_owner(self, *, room_id: UUID, owner_user_id: UUID) -> None:
        """활성 멤버가 남아 있는 room의 방장을 새 유저로 승계합니다."""

    async def close_room(self, *, room_id: UUID, closed_at: datetime) -> None:
        """활성 멤버가 없는 room을 더 이상 사용할 수 없도록 닫습니다."""

    async def abort_active_session_for_room(self, *, room_id: UUID, ended_at: datetime) -> None:
        """room의 active 게임 세션을 중단 상태로 닫습니다."""

    async def update_room_settings(
        self,
        *,
        room_id: UUID,
        name: str,
        max_players: int,
        rule_config: dict[str, int],
    ) -> RoomUpdateResult:
        """대기 room의 표시 정보와 게임 시작 전 룰 설정을 갱신합니다."""

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


class GameRoomUpdateForbiddenError(AppException):
    """방장이 아닌 유저가 room 설정 변경을 요청할 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_UPDATE_FORBIDDEN)


class GameRoomNotUpdateableError(AppException):
    """room 상태가 설정 변경을 허용하지 않을 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_NOT_UPDATEABLE)


class GameRoomEntryForbiddenError(AppException):
    """room 활성 멤버가 아닌 유저가 room 로비에 진입하려 할 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_ROOM_ENTRY_FORBIDDEN)


class GameSessionEntryForbiddenError(AppException):
    """게임 세션 참가자로 고정되지 않은 유저가 진입하려 할 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN)


def build_lobby_websocket_path(room_public_id: UUID) -> str:
    """REST 응답에서 클라이언트가 같은 origin으로 연결할 로비 WebSocket path를 만듭니다."""
    return f"/ws/lobby/rooms/{room_public_id}"


def build_anonymous_display_name(seat_number: int) -> str:
    """게임 진행 중 참가자 정체를 숨기기 위해 좌석 번호 기반 표시명을 만듭니다."""
    return f"{seat_number}번 손님"


class GameService:
    """게임 시작 시 세션을 발급하고 허용된 멤버만 진입하도록 검증합니다."""

    def __init__(self, repository: GameRepositoryProtocol) -> None:
        self.repository = repository

    async def list_rooms(self, *, user_id: UUID) -> GameRoomListResult:
        """로비 화면에서 선택할 수 있는 객실과 현재 참여 중인 유효 로비를 반환합니다."""
        rooms = await self.repository.list_rooms(user_id=user_id)
        current_room = next(
            (
                room
                for room in rooms
                if room.is_current_user_member and room.status == WAITING_ROOM_STATUS
            ),
            None,
        )
        return GameRoomListResult(
            rooms=rooms,
            current_membership=(
                CurrentLobbyMembership(
                    room_public_id=current_room.room_public_id,
                    name=current_room.name,
                    game_type=current_room.game_type,
                    status=current_room.status,
                    max_players=current_room.max_players,
                    member_count=current_room.member_count,
                    is_owner=current_room.is_current_user_owner,
                    lobby_websocket_path=build_lobby_websocket_path(current_room.room_public_id),
                )
                if current_room is not None
                else None
            ),
        )

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
        await self.repository.lock_waiting_room_membership_for_user(user_id=owner.id)
        await self._leave_existing_rooms_for_lobby_move(user=owner)
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

    async def update_room(
        self,
        *,
        room_public_id: UUID,
        user: CurrentUser,
        name: str,
        max_players: int,
        rule_config: dict[str, int],
    ) -> RoomUpdateResult:
        """방장이 대기 중인 객실의 게임 시작 전 설정을 수정합니다.

        room row lock 안에서 방장, 상태, 현재 활성 멤버 수를 검증하고 DB 설정만 확정합니다.
        WebSocket 동기화는 API endpoint가 commit 이후 별도로 수행합니다.
        """
        room = await self.repository.get_room_by_public_id_for_update(room_public_id)
        if room is None:
            raise GameRoomNotFoundError
        if room.owner_user_id != user.id:
            raise GameRoomUpdateForbiddenError
        if room.status != WAITING_ROOM_STATUS:
            raise GameRoomNotUpdateableError
        members = await self.repository.list_active_room_members(room.id)
        if len(members) > max_players:
            raise GameRoomNotUpdateableError
        result = await self.repository.update_room_settings(
            room_id=room.id,
            name=name,
            max_players=max_players,
            rule_config=rule_config,
        )
        await self.repository.commit()
        return result

    async def authorize_room_lobby_connection(
        self,
        *,
        room_public_id: UUID,
        user_id: UUID,
    ) -> RoomLobbyConnectionResult:
        """room 로비 WebSocket 연결 전에 권한을 확인하고 초기 room snapshot을 반환합니다."""
        room = await self.repository.get_room_by_public_id(room_public_id)
        if room is None:
            raise GameRoomNotFoundError
        member = await self.repository.get_active_room_member(
            room_id=room.id,
            user_id=user_id,
        )
        if member is None:
            raise GameRoomEntryForbiddenError
        members = await self.repository.list_active_room_members(room.id)
        owner = next((member for member in members if member.user_id == room.owner_user_id), None)
        return RoomLobbyConnectionResult(
            room_public_id=room.public_id,
            snapshot=RoomLobbySnapshotResult(
                room_public_id=room.public_id,
                owner_user_public_id=owner.user_public_id if owner else None,
                members=[
                    RoomLobbyMemberSnapshot(
                        user_public_id=member.user_public_id,
                        nickname=member.nickname,
                        is_owner=member.user_id == room.owner_user_id,
                        joined_at=member.joined_at,
                    )
                    for member in members
                    if member.user_public_id is not None
                ],
            ),
        )

    async def join_room(self, *, room_public_id: UUID, user: CurrentUser) -> RoomJoinResult:
        """로그인 유저를 대기 중인 room의 활성 멤버로 참여시킵니다.

        이미 참여 중인 유저의 반복 요청은 새 row를 만들지 않고 기존 참여 정보를 반환합니다.
        room 상태와 정원 판단은 room row lock 안에서 수행해 중복 참여와 초과 참여를 줄입니다.
        """
        await self.repository.lock_waiting_room_membership_for_user(user_id=user.id)
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

        await self._leave_existing_rooms_for_lobby_move(
            user=user,
            excluded_room_public_id=room.public_id,
        )
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

    async def leave_room(
        self,
        *,
        room_public_id: UUID,
        user: CurrentUser,
        left_at: datetime,
    ) -> RoomLeaveResult:
        """현재 유저를 대기 room에서 퇴장시키고 방장 승계 또는 room 폐쇄를 처리합니다."""
        result = await self._leave_waiting_room(
            room_public_id=room_public_id,
            user=user,
            left_at=left_at,
            ignore_inactive_member=False,
            commit=True,
        )
        if result is None:
            raise GameRoomEntryForbiddenError
        return result

    async def leave_room_after_disconnect_grace(
        self,
        *,
        room_public_id: UUID,
        user: CurrentUser,
        left_at: datetime,
    ) -> RoomLeaveResult | None:
        """WebSocket grace timeout 이후에도 복귀하지 않은 유저를 room에서 퇴장 처리합니다.

        이미 다른 흐름에서 퇴장됐거나 room이 더 이상 대기 로비가 아니면 DB를 다시 변경하지 않고
        None을 반환합니다.
        """
        return await self._leave_waiting_room(
            room_public_id=room_public_id,
            user=user,
            left_at=left_at,
            ignore_inactive_member=True,
            commit=True,
        )

    async def _leave_waiting_room(
        self,
        *,
        room_public_id: UUID,
        user: CurrentUser,
        left_at: datetime,
        ignore_inactive_member: bool,
        commit: bool,
    ) -> RoomLeaveResult | None:
        """대기 room 퇴장 후 남은 멤버 기준으로 방장 승계 또는 room 폐쇄를 결정합니다."""
        room = await self.repository.get_room_by_public_id_for_update(room_public_id)
        if room is None:
            raise GameRoomNotFoundError
        if room.status != WAITING_ROOM_STATUS:
            if ignore_inactive_member:
                return None
            raise GameRoomNotJoinableError
        return await self._leave_locked_waiting_room(
            room=room,
            user=user,
            left_at=left_at,
            ignore_inactive_member=ignore_inactive_member,
            commit=commit,
        )

    async def _leave_locked_waiting_room(
        self,
        *,
        room: GameRoomRecord,
        user: CurrentUser,
        left_at: datetime,
        ignore_inactive_member: bool,
        commit: bool,
    ) -> RoomLeaveResult | None:
        """이미 lock을 잡은 대기 room의 퇴장, 방장 승계, 폐쇄를 처리합니다."""
        result = await self.repository.mark_room_member_left(
            room_id=room.id,
            user_id=user.id,
            left_at=left_at,
        )
        if result is None:
            if ignore_inactive_member:
                return None
            raise GameRoomEntryForbiddenError
        remaining_members = await self.repository.list_active_room_members(room.id)
        new_owner = None
        room_closed = False
        if not remaining_members:
            await self.repository.close_room(room_id=room.id, closed_at=left_at)
            room_closed = True
        elif room.owner_user_id == user.id:
            new_owner = remaining_members[0]
            await self.repository.transfer_room_owner(
                room_id=room.id,
                owner_user_id=new_owner.user_id,
            )
        if commit:
            await self.repository.commit()
        return RoomLeaveResult(
            room_public_id=room.public_id,
            user_public_id=user.public_id,
            nickname=result.nickname,
            left_at=result.left_at,
            remaining_member_count=len(remaining_members),
            new_owner_user_public_id=new_owner.user_public_id if new_owner else None,
            new_owner_nickname=new_owner.nickname if new_owner else None,
            room_closed=room_closed,
        )

    async def _leave_existing_rooms_for_lobby_move(
        self,
        *,
        user: CurrentUser,
        excluded_room_public_id: UUID | None = None,
    ) -> None:
        """새 대기방 생성/입장 전 유저가 남아 있던 다른 room membership을 정리합니다.

        한 유저가 여러 room에 동시에 active member로 남으면 로비 목록에 유령 객실이 누적됩니다.
        대기 room은 REST 퇴장과 같은 규칙으로 정리하고, 이미 시작됐지만 실제 유저가 현재 유저
        한 명뿐인 세션은 다른 유저에게 영향이 없으므로 abort 후 room을 닫습니다. 같은 room 반복
        입장은 기존 membership을 그대로 반환해야 하므로 제외합니다.
        """
        room_public_ids = await self.repository.list_active_room_public_ids_for_user(
            user_id=user.id,
        )
        for room_public_id in room_public_ids:
            if room_public_id == excluded_room_public_id:
                continue
            room = await self.repository.get_room_by_public_id_for_update(room_public_id)
            if room is None:
                continue
            left_at = kst_now()
            if room.status == WAITING_ROOM_STATUS:
                await self._leave_locked_waiting_room(
                    room=room,
                    user=user,
                    left_at=left_at,
                    ignore_inactive_member=True,
                    commit=False,
                )
                continue
            if room.status in SOLO_ABORTABLE_ROOM_STATUSES:
                await self._abort_solo_started_room(room=room, user=user, left_at=left_at)

    async def _abort_solo_started_room(
        self,
        *,
        room: GameRoomRecord,
        user: CurrentUser,
        left_at: datetime,
    ) -> None:
        """실제 유저가 1명뿐인 started room을 새 로비 이동 전 안전하게 닫습니다."""
        active_session = await self.repository.get_active_session_by_room_id(room.id)
        if active_session is None or not self._is_solo_user_session(active_session, user.id):
            return
        leave_result = await self.repository.mark_room_member_left(
            room_id=room.id,
            user_id=user.id,
            left_at=left_at,
        )
        if leave_result is None:
            return
        await self.repository.abort_active_session_for_room(room_id=room.id, ended_at=left_at)
        await self.repository.close_room(room_id=room.id, closed_at=left_at)

    @staticmethod
    def _is_solo_user_session(session: GameSessionStartResult, user_id: UUID) -> bool:
        """AI 참가자를 제외했을 때 현재 유저만 남은 세션인지 확인합니다."""
        user_participants = [
            participant
            for participant in session.participants
            if participant.participant_type == ParticipantType.USER.value
        ]
        return len(user_participants) == 1 and user_participants[0].user_id == user_id

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
                display_name=build_anonymous_display_name(index),
                seat_number=index,
                is_uninvited_guest=False,
                original_nickname=member.nickname,
            )
            for index, member in enumerate(members, start=1)
        ]
        ai_seat_number = len(participants) + 1
        participants.append(
            GameSessionParticipantRecord(
                participant_id=None,
                game_session_public_id=game_session_public_id,
                user_id=None,
                participant_type=ParticipantType.AI.value,
                display_name=build_anonymous_display_name(ai_seat_number),
                seat_number=ai_seat_number,
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
                rule_config=room.rule_config,
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
            now=kst_now(),
        )
        if participant is None:
            raise GameSessionEntryForbiddenError
        return GameSessionEntryResult(
            game_session_public_id=participant.game_session_public_id,
            participant=participant,
            game_session_token=game_session_token,
            game_session_token_expires_at=participant.resume_token_expires_at or kst_now(),
        )

    async def _issue_game_session_credential(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionCredential:
        """로그인 세션과 별개로 특정 match 참가자에게만 유효한 복구 토큰을 발급합니다."""
        game_session_token = generate_game_session_token()
        expires_at = kst_now() + GAME_SESSION_TOKEN_TTL
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
