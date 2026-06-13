from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.be.models.game import GameSession, Room, RoomMember, SessionParticipant, SessionPhase
from app.be.models.game import WordTurn
from app.be.models.user import User
from app.be.schemas.game_enum import GameSessionStatus, GameType, RoomStatus
from app.be.services.game import (
    GameRoomListItem,
    GameRoomRecord,
    GameSessionParticipantRecord,
    GameSessionStartResult,
    RoomLeaveResult,
    RoomMemberRecord,
    RoomUpdateResult,
    default_room_rule_config,
)
from app.shared.core.identifiers import generate_uuid_v7
from app.shared.core.observability import traced_method
from app.shared.core.timezone import kst_now


TERMINAL_SESSION_STATUSES = (
    GameSessionStatus.RESULT.value,
    GameSessionStatus.ABORTED.value,
)


class GameRepository:
    """게임 시작과 세션 진입 권한 확인에 필요한 DB 접근을 담당합니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def list_rooms(self, *, user_id: UUID) -> list[GameRoomListItem]:
        """닫히지 않은 room 목록, 활성 멤버 수, 현재 유저 참여 여부를 조회합니다."""
        return await self._list_rooms(user_id=user_id)

    @traced_method("GameRepository.list_rooms", layer="repository")
    async def _list_rooms(self, *, user_id: UUID) -> list[GameRoomListItem]:
        """room 목록 조회 query 실행 시간을 trace span으로 기록합니다."""
        active_member = aliased(RoomMember)
        current_member = aliased(RoomMember)
        statement = (
            select(
                Room,
                func.count(func.distinct(active_member.id)),
                func.count(func.distinct(current_member.id)) > 0,
            )
            .outerjoin(
                active_member,
                and_(active_member.room_id == Room.id, active_member.left_at.is_(None)),
            )
            .outerjoin(
                current_member,
                and_(
                    current_member.room_id == Room.id,
                    current_member.user_id == user_id,
                    current_member.left_at.is_(None),
                ),
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
                is_current_user_member=bool(is_current_user_member),
                is_current_user_owner=room.owner_user_id == user_id,
            )
            for room, member_count, is_current_user_member in result.all()
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
        now = kst_now()
        room = Room(
            public_id=generate_uuid_v7(),
            owner_user_id=owner_user_id,
            name=name,
            game_type=game_type,
            status=status,
            max_players=max_players,
            rule_config=default_room_rule_config(),
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
                user_public_id=user.public_id,
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
        member, user, _room = row
        return RoomMemberRecord(
            room_id=member.room_id,
            user_id=member.user_id,
            nickname=user.nickname,
            joined_at=member.joined_at,
            user_public_id=user.public_id,
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
            joined_at=kst_now(),
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
        member, user, room = row
        member.left_at = left_at
        await self.db_session.flush()
        return RoomLeaveResult(
            room_public_id=room.public_id,
            user_public_id=user.public_id,
            nickname=user.nickname,
            left_at=left_at,
        )

    async def transfer_room_owner(self, *, room_id: UUID, owner_user_id: UUID) -> None:
        """room owner_user_id를 남은 활성 멤버 중 새 방장으로 변경합니다."""
        await self._transfer_room_owner(room_id=room_id, owner_user_id=owner_user_id)

    @traced_method("GameRepository.transfer_room_owner", layer="repository")
    async def _transfer_room_owner(self, *, room_id: UUID, owner_user_id: UUID) -> None:
        """room owner update 실행 시간을 trace span으로 기록합니다."""
        result = await self.db_session.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one()
        room.owner_user_id = owner_user_id
        room.updated_at = kst_now()
        await self.db_session.flush()

    async def close_room(self, *, room_id: UUID, closed_at) -> None:
        """room을 closed 상태로 바꾸고 closed_at을 기록합니다."""
        await self._close_room(room_id=room_id, closed_at=closed_at)

    @traced_method("GameRepository.close_room", layer="repository")
    async def _close_room(self, *, room_id: UUID, closed_at) -> None:
        """room close update 실행 시간을 trace span으로 기록합니다."""
        result = await self.db_session.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one()
        room.status = RoomStatus.CLOSED.value
        room.closed_at = closed_at
        room.updated_at = closed_at
        await self.db_session.flush()

    async def update_room_settings(
        self,
        *,
        room_id: UUID,
        name: str,
        max_players: int,
        rule_config: dict[str, int],
    ) -> RoomUpdateResult:
        """대기 room의 설정을 수정하고 WebSocket event용 record를 반환합니다."""
        return await self._update_room_settings(
            room_id=room_id,
            name=name,
            max_players=max_players,
            rule_config=rule_config,
        )

    @traced_method("GameRepository.update_room_settings", layer="repository")
    async def _update_room_settings(
        self,
        *,
        room_id: UUID,
        name: str,
        max_players: int,
        rule_config: dict[str, int],
    ) -> RoomUpdateResult:
        """room 설정 update 실행 시간을 trace span으로 기록합니다."""
        result = await self.db_session.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one()
        room.name = name
        room.max_players = max_players
        room.rule_config = rule_config
        room.updated_at = kst_now()
        await self.db_session.flush()
        return RoomUpdateResult(
            room_public_id=room.public_id,
            name=room.name,
            game_type=room.game_type,
            status=room.status,
            max_players=room.max_players,
            rule_config=room.rule_config,
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
        game_session_id = generate_uuid_v7()
        game_session = GameSession(
            id=game_session_id,
            public_id=session.game_session_public_id,
            room_id=room.id,
            game_type=session.game_type,
            status=session.status,
            rule_config=session.rule_config,
            started_at=kst_now(),
        )
        self.db_session.add(game_session)
        participant_rows = [
            SessionParticipant(
                id=generate_uuid_v7(),
                session_id=game_session.id,
                user_id=participant.user_id,
                participant_type=participant.participant_type,
                display_name=participant.display_name,
                original_nickname=participant.original_nickname,
                seat_number=participant.seat_number,
                is_uninvited_guest=participant.is_uninvited_guest,
            )
            for participant in session.participants
        ]
        self.db_session.add_all(participant_rows)
        if session.game_type == GameType.SHIRITORI.value and participant_rows:
            initial_phase = self._build_initial_word_turn_phase(
                game_session=game_session,
                first_participant=min(
                    participant_rows, key=lambda participant: participant.seat_number
                ),
                rule_config=session.rule_config,
            )
            game_session.current_phase_id = initial_phase.id
            self.db_session.add(initial_phase)
            self.db_session.add(
                WordTurn(
                    phase_id=initial_phase.id,
                    participant_id=initial_phase.actor_participant_id,
                    round_number=1,
                    turn_number=1,
                    condition_payload=initial_phase.condition_payload,
                )
            )
        room.status = session.status
        await self.db_session.flush()
        return session

    def _build_initial_word_turn_phase(
        self,
        *,
        game_session: GameSession,
        first_participant: SessionParticipant,
        rule_config: dict[str, int],
    ) -> SessionPhase:
        """끝말잇기 세션 시작 직후 첫 번째 턴 phase를 만듭니다."""
        now = kst_now()
        turn_time_seconds = int(rule_config.get("turn_time_seconds", 10))
        condition_payload = {"required_start_char": None}
        return SessionPhase(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            phase_type="turn",
            phase_number=1,
            actor_participant_id=first_participant.id,
            condition_payload=condition_payload,
            time_limit_seconds=turn_time_seconds,
            started_at=now,
            deadline_at=now + timedelta(seconds=turn_time_seconds),
        )

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
            resume_token_expires_at=participant.resume_token_expires_at,
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
            rule_config=room.rule_config or default_room_rule_config(),
            created_at=room.created_at,
        )
