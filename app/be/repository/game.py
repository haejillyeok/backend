from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.models.game import GameSession, Room, RoomMember, SessionParticipant
from app.be.models.user import User, utc_now
from app.be.schemas.game_enum import GameSessionStatus
from app.be.services.game import (
    GameRoomListItem,
    GameRoomRecord,
    GameSessionParticipantRecord,
    GameSessionStartResult,
    RoomLeaveResult,
    RoomMemberRecord,
)
from app.shared.core.identifiers import generate_uuid_v7
from app.shared.core.observability import traced_method


TERMINAL_SESSION_STATUSES = (
    GameSessionStatus.RESULT.value,
    GameSessionStatus.ABORTED.value,
)


class GameRepository:
    """게임 시작과 세션 진입 권한 확인에 필요한 DB 접근을 담당합니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def list_rooms(self) -> list[GameRoomListItem]:
        """닫히지 않은 room 목록과 활성 멤버 수를 로비 목록 record로 조회합니다."""
        return await self._list_rooms()

    @traced_method("GameRepository.list_rooms", layer="repository")
    async def _list_rooms(self) -> list[GameRoomListItem]:
        """room 목록 조회 query 실행 시간을 trace span으로 기록합니다."""
        statement = (
            select(Room, func.count(RoomMember.id))
            .outerjoin(
                RoomMember,
                and_(RoomMember.room_id == Room.id, RoomMember.left_at.is_(None)),
            )
            .where(Room.closed_at.is_(None))
            .group_by(Room.id)
            .order_by(Room.created_at.desc())
        )
        result = await self.db_session.execute(statement)
        return [
            GameRoomListItem(
                room_public_id=room.public_id,
                name=room.name,
                game_type=room.game_type,
                status=room.status,
                max_players=room.max_players,
                member_count=member_count,
            )
            for room, member_count in result.all()
        ]

    async def create_room(
        self,
        *,
        owner_user_id: UUID,
        name: str,
        game_type: str,
        status: str,
        max_players: int,
    ) -> GameRoomRecord:
        """room row를 생성하고 flush된 식별자와 생성 시간을 service record로 반환합니다."""
        return await self._create_room(
            owner_user_id=owner_user_id,
            name=name,
            game_type=game_type,
            status=status,
            max_players=max_players,
        )

    @traced_method("GameRepository.create_room", layer="repository")
    async def _create_room(
        self,
        *,
        owner_user_id: UUID,
        name: str,
        game_type: str,
        status: str,
        max_players: int,
    ) -> GameRoomRecord:
        """room insert 실행 시간을 trace span으로 기록합니다."""
        now = utc_now()
        room = Room(
            public_id=generate_uuid_v7(),
            owner_user_id=owner_user_id,
            name=name,
            game_type=game_type,
            status=status,
            max_players=max_players,
            created_at=now,
            updated_at=now,
        )
        self.db_session.add(room)
        await self.db_session.flush()
        return self._room_to_record(room)

    async def get_room_by_public_id(self, room_public_id: UUID) -> GameRoomRecord | None:
        """WebSocket 연결 권한 확인에 사용할 room을 lock 없이 조회합니다."""
        return await self._get_room_by_public_id(room_public_id)

    @traced_method("GameRepository.get_room_by_public_id", layer="repository")
    async def _get_room_by_public_id(self, room_public_id: UUID) -> GameRoomRecord | None:
        """room 단건 조회 query 실행 시간을 trace span으로 기록합니다."""
        result = await self.db_session.execute(select(Room).where(Room.public_id == room_public_id))
        room = result.scalar_one_or_none()
        if room is None:
            return None
        return self._room_to_record(room)

    async def get_room_by_public_id_for_update(self, room_public_id: UUID) -> GameRoomRecord | None:
        """게임 시작 transaction 동안 room row를 잠그고 service record로 변환합니다."""
        return await self._get_room_by_public_id_for_update(room_public_id)

    @traced_method("GameRepository.get_room_by_public_id_for_update", layer="repository")
    async def _get_room_by_public_id_for_update(
        self, room_public_id: UUID
    ) -> GameRoomRecord | None:
        """room lock 조회 query 실행 시간을 trace span으로 기록합니다."""
        result = await self.db_session.execute(
            select(Room).where(Room.public_id == room_public_id).with_for_update()
        )
        room = result.scalar_one_or_none()
        if room is None:
            return None
        return self._room_to_record(room)

    async def get_active_session_by_room_id(self, room_id: UUID) -> GameSessionStartResult | None:
        """room에 이미 시작된 active session이 있으면 참가자 snapshot과 함께 반환합니다."""
        return await self._get_active_session_by_room_id(room_id)

    @traced_method("GameRepository.get_active_session_by_room_id", layer="repository")
    async def _get_active_session_by_room_id(self, room_id: UUID) -> GameSessionStartResult | None:
        """active session 조회 query 실행 시간을 trace span으로 기록합니다."""
        session_result = await self.db_session.execute(
            select(GameSession, Room)
            .join(Room, GameSession.room_id == Room.id)
            .where(
                GameSession.room_id == room_id,
                GameSession.ended_at.is_(None),
                GameSession.status.not_in(TERMINAL_SESSION_STATUSES),
            )
            .order_by(GameSession.started_at.desc())
            .limit(1)
        )
        row = session_result.one_or_none()
        if row is None:
            return None

        game_session, room = row
        participant_result = await self.db_session.execute(
            select(SessionParticipant)
            .where(SessionParticipant.session_id == game_session.id)
            .order_by(SessionParticipant.seat_number.asc())
        )
        participants = [
            GameSessionParticipantRecord(
                participant_id=participant.id,
                game_session_public_id=game_session.public_id,
                user_id=participant.user_id,
                participant_type=participant.participant_type,
                display_name=participant.display_name,
                seat_number=participant.seat_number,
                is_uninvited_guest=participant.is_uninvited_guest,
            )
            for participant in participant_result.scalars().all()
        ]
        return GameSessionStartResult(
            game_session_public_id=game_session.public_id,
            room_public_id=room.public_id,
            game_type=game_session.game_type,
            status=game_session.status,
            participants=participants,
        )

    async def list_active_room_members(self, room_id: UUID) -> list[RoomMemberRecord]:
        """게임 시작 시 참가자로 고정할 활성 room member를 입장 순서대로 조회합니다."""
        return await self._list_active_room_members(room_id)

    @traced_method("GameRepository.list_active_room_members", layer="repository")
    async def _list_active_room_members(self, room_id: UUID) -> list[RoomMemberRecord]:
        """활성 room member 조회 query 실행 시간을 trace span으로 기록합니다."""
        statement = (
            select(RoomMember, User)
            .join(User, RoomMember.user_id == User.id)
            .where(RoomMember.room_id == room_id, RoomMember.left_at.is_(None))
            .order_by(RoomMember.joined_at.asc())
        )
        result = await self.db_session.execute(statement)
        return [
            RoomMemberRecord(
                room_id=member.room_id,
                user_id=member.user_id,
                nickname=user.nickname,
                joined_at=member.joined_at,
            )
            for member, user in result.all()
        ]

    async def get_active_room_member(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
    ) -> RoomMemberRecord | None:
        """유저가 room의 활성 멤버인지 조회하고 service record로 변환합니다."""
        return await self._get_active_room_member(room_id=room_id, user_id=user_id)

    @traced_method("GameRepository.get_active_room_member", layer="repository")
    async def _get_active_room_member(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
    ) -> RoomMemberRecord | None:
        """활성 room member 단건 조회 query 실행 시간을 trace span으로 기록합니다."""
        statement = (
            select(RoomMember, User, Room)
            .join(User, RoomMember.user_id == User.id)
            .join(Room, RoomMember.room_id == Room.id)
            .where(
                RoomMember.room_id == room_id,
                RoomMember.user_id == user_id,
                RoomMember.left_at.is_(None),
            )
        )
        result = await self.db_session.execute(statement)
        row = result.one_or_none()
        if row is None:
            return None
        member, user = row
        return RoomMemberRecord(
            room_id=member.room_id,
            user_id=member.user_id,
            nickname=user.nickname,
            joined_at=member.joined_at,
        )

    async def create_room_member(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        nickname: str,
    ) -> RoomMemberRecord:
        """room_members에 활성 멤버를 추가하고 service record로 변환합니다."""
        return await self._create_room_member(room_id=room_id, user_id=user_id, nickname=nickname)

    @traced_method("GameRepository.create_room_member", layer="repository")
    async def _create_room_member(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        nickname: str,
    ) -> RoomMemberRecord:
        """room member insert 실행 시간을 trace span으로 기록합니다."""
        member = RoomMember(
            room_id=room_id,
            user_id=user_id,
            joined_at=utc_now(),
        )
        self.db_session.add(member)
        await self.db_session.flush()
        return RoomMemberRecord(
            room_id=member.room_id,
            user_id=member.user_id,
            nickname=nickname,
            joined_at=member.joined_at,
        )

    async def mark_room_member_left(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        left_at,
    ) -> RoomLeaveResult | None:
        """활성 room member의 left_at을 기록하고 퇴장 event용 record를 반환합니다."""
        return await self._mark_room_member_left(
            room_id=room_id,
            user_id=user_id,
            left_at=left_at,
        )

    @traced_method("GameRepository.mark_room_member_left", layer="repository")
    async def _mark_room_member_left(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        left_at,
    ) -> RoomLeaveResult | None:
        """room member 퇴장 update 실행 시간을 trace span으로 기록합니다."""
        statement = (
            select(RoomMember, User)
            .join(User, RoomMember.user_id == User.id)
            .where(
                RoomMember.room_id == room_id,
                RoomMember.user_id == user_id,
                RoomMember.left_at.is_(None),
            )
        )
        result = await self.db_session.execute(statement)
        row = result.one_or_none()
        if row is None:
            return None
        member, user, room = row
        member.left_at = left_at
        await self.db_session.flush()
        return RoomLeaveResult(
            room_public_id=room.public_id,
            user_public_id=user.public_id,
            nickname=user.nickname,
            left_at=left_at,
        )

    async def create_game_session(
        self,
        *,
        session: GameSessionStartResult,
    ) -> GameSessionStartResult:
        """게임 세션과 참가자 snapshot을 추가하고 flush해서 FK 대상 UUID를 확정합니다."""
        return await self._create_game_session(session=session)

    @traced_method("GameRepository.create_game_session", layer="repository")
    async def _create_game_session(
        self,
        *,
        session: GameSessionStartResult,
    ) -> GameSessionStartResult:
        """게임 세션 insert 실행 시간을 trace span으로 기록합니다."""
        room_result = await self.db_session.execute(
            select(Room).where(Room.public_id == session.room_public_id)
        )
        room = room_result.scalar_one()
        game_session = GameSession(
            public_id=session.game_session_public_id,
            room_id=room.id,
            game_type=session.game_type,
            status=session.status,
            rule_config={},
        )
        self.db_session.add(game_session)
        await self.db_session.flush()

        self.db_session.add_all(
            [
                SessionParticipant(
                    session_id=game_session.id,
                    user_id=participant.user_id,
                    participant_type=participant.participant_type,
                    display_name=participant.display_name,
                    original_nickname=participant.display_name
                    if participant.participant_type == "user"
                    else None,
                    seat_number=participant.seat_number,
                    is_uninvited_guest=participant.is_uninvited_guest,
                )
                for participant in session.participants
            ]
        )
        room.status = session.status
        await self.db_session.flush()
        return session

    async def get_user_participant_for_session(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionParticipantRecord | None:
        """로그인 유저가 해당 게임 세션 참가자로 고정되어 있는지 조회합니다."""
        return await self._get_user_participant_for_session(
            game_session_public_id=game_session_public_id,
            user_id=user_id,
        )

    @traced_method("GameRepository.get_user_participant_for_session", layer="repository")
    async def _get_user_participant_for_session(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionParticipantRecord | None:
        """세션 참가자 권한 조회 query 실행 시간을 trace span으로 기록합니다."""
        statement = (
            select(GameSession, SessionParticipant)
            .join(SessionParticipant, SessionParticipant.session_id == GameSession.id)
            .where(
                GameSession.public_id == game_session_public_id,
                SessionParticipant.user_id == user_id,
                SessionParticipant.left_at.is_(None),
            )
        )
        result = await self.db_session.execute(statement)
        row = result.one_or_none()
        if row is None:
            return None
        game_session, participant = row
        return GameSessionParticipantRecord(
            participant_id=participant.id,
            game_session_public_id=game_session.public_id,
            user_id=participant.user_id,
            participant_type=participant.participant_type,
            display_name=participant.display_name,
            seat_number=participant.seat_number,
            is_uninvited_guest=participant.is_uninvited_guest,
            resume_token_expires_at=participant.resume_token_expires_at,
        )

    async def get_participant_for_game_session_token(
        self,
        *,
        token_hash: str,
        now,
    ) -> GameSessionParticipantRecord | None:
        """유효한 게임 세션 토큰 해시로 match 참가자를 조회합니다."""
        return await self._get_participant_for_game_session_token(token_hash=token_hash, now=now)

    @traced_method("GameRepository.get_participant_for_game_session_token", layer="repository")
    async def _get_participant_for_game_session_token(
        self,
        *,
        token_hash: str,
        now,
    ) -> GameSessionParticipantRecord | None:
        """게임 세션 토큰 기반 참가자 조회 query 실행 시간을 trace span으로 기록합니다."""
        statement = (
            select(GameSession, SessionParticipant)
            .join(SessionParticipant, SessionParticipant.session_id == GameSession.id)
            .where(
                SessionParticipant.resume_token_hash == token_hash,
                SessionParticipant.resume_token_expires_at > now,
                SessionParticipant.left_at.is_(None),
            )
        )
        result = await self.db_session.execute(statement)
        row = result.one_or_none()
        if row is None:
            return None
        game_session, participant = row
        return GameSessionParticipantRecord(
            participant_id=participant.id,
            game_session_public_id=game_session.public_id,
            user_id=participant.user_id,
            participant_type=participant.participant_type,
            display_name=participant.display_name,
            seat_number=participant.seat_number,
            is_uninvited_guest=participant.is_uninvited_guest,
        )

    async def save_game_session_token(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
        token_hash: str,
        expires_at,
    ) -> None:
        """게임 참가자의 match 복구 토큰 해시와 만료 시각을 저장합니다."""
        await self._save_game_session_token(
            game_session_public_id=game_session_public_id,
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )

    @traced_method("GameRepository.save_game_session_token", layer="repository")
    async def _save_game_session_token(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
        token_hash: str,
        expires_at,
    ) -> None:
        """게임 세션 토큰 저장 update 실행 시간을 trace span으로 기록합니다."""
        statement = (
            select(GameSession, SessionParticipant)
            .join(SessionParticipant, SessionParticipant.session_id == GameSession.id)
            .where(
                GameSession.public_id == game_session_public_id,
                SessionParticipant.user_id == user_id,
                SessionParticipant.left_at.is_(None),
            )
        )
        result = await self.db_session.execute(statement)
        row = result.one_or_none()
        if row is None:
            return
        _, participant = row
        participant.resume_token_hash = token_hash
        participant.resume_token_expires_at = expires_at
        await self.db_session.flush()

    async def commit(self) -> None:
        """게임 시작 transaction을 확정합니다."""
        await self._commit()

    @traced_method("GameRepository.commit", layer="repository")
    async def _commit(self) -> None:
        """게임 transaction commit 실행 시간을 trace span으로 기록합니다."""
        await self.db_session.commit()

    def _room_to_record(self, room: Room) -> GameRoomRecord:
        """ORM room을 service 계층에서 사용하는 불변 record로 변환합니다."""
        return GameRoomRecord(
            id=room.id,
            public_id=room.public_id,
            owner_user_id=room.owner_user_id,
            name=room.name,
            game_type=room.game_type,
            status=room.status,
            max_players=room.max_players,
            created_at=room.created_at,
        )
