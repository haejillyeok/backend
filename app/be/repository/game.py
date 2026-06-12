from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.models.game import GameSession, Room, RoomMember, SessionParticipant
from app.be.models.user import User
from app.be.services.game import (
    GameRoomRecord,
    GameSessionParticipantRecord,
    GameSessionStartResult,
    RoomMemberRecord,
)
from app.shared.core.observability import traced_method


TERMINAL_SESSION_STATUSES = ("result", "aborted")


class GameRepository:
    """게임 시작과 세션 진입 권한 확인에 필요한 DB 접근을 담당합니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

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
        return GameRoomRecord(
            id=room.id,
            public_id=room.public_id,
            owner_user_id=room.owner_user_id,
            name=room.name,
            game_type=room.game_type,
            status=room.status,
            max_players=room.max_players,
        )

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
                session_public_id=game_session.public_id,
                user_id=participant.user_id,
                participant_type=participant.participant_type,
                display_name=participant.display_name,
                seat_number=participant.seat_number,
                is_uninvited_guest=participant.is_uninvited_guest,
            )
            for participant in participant_result.scalars().all()
        ]
        return GameSessionStartResult(
            session_public_id=game_session.public_id,
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
            public_id=session.session_public_id,
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
        session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionParticipantRecord | None:
        """로그인 유저가 해당 게임 세션 참가자로 고정되어 있는지 조회합니다."""
        return await self._get_user_participant_for_session(
            session_public_id=session_public_id,
            user_id=user_id,
        )

    @traced_method("GameRepository.get_user_participant_for_session", layer="repository")
    async def _get_user_participant_for_session(
        self,
        *,
        session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionParticipantRecord | None:
        """세션 참가자 권한 조회 query 실행 시간을 trace span으로 기록합니다."""
        statement = (
            select(GameSession, SessionParticipant)
            .join(SessionParticipant, SessionParticipant.session_id == GameSession.id)
            .where(
                GameSession.public_id == session_public_id,
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
            session_public_id=game_session.public_id,
            user_id=participant.user_id,
            participant_type=participant.participant_type,
            display_name=participant.display_name,
            seat_number=participant.seat_number,
            is_uninvited_guest=participant.is_uninvited_guest,
        )

    async def commit(self) -> None:
        """게임 시작 transaction을 확정합니다."""
        await self._commit()

    @traced_method("GameRepository.commit", layer="repository")
    async def _commit(self) -> None:
        """게임 transaction commit 실행 시간을 trace span으로 기록합니다."""
        await self.db_session.commit()
