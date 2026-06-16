from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.be.models.game import (
    GameSession,
    Room,
    RoomMember,
    SessionParticipant,
    SessionPhase,
    ValidWord,
    WordTurn,
)
from app.be.models.user import User
from app.be.repository.game.constants import TERMINAL_SESSION_STATUSES, waiting_membership_lock_key
from app.be.schemas.game_enum import GameSessionStatus, RoomStatus
from app.be.services.game import (
    GameRoomListItem,
    GameRoomRecord,
    GameSessionParticipantRecord,
    GameSessionTurnRecord,
    RoomLeaveResult,
    RoomMemberRecord,
    RoomUpdateResult,
    default_room_rule_config,
)
from app.shared.core.identifiers import generate_uuid_v7
from app.shared.core.observability import traced_method
from app.shared.core.timezone import kst_now


class GameRepository:
    """게임 도메인의 DB 실행 단위 메서드를 소유하는 repository입니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    @traced_method("GameRepository.list_rooms", layer="repository")
    async def list_rooms(self, *, user_id: UUID) -> list[GameRoomListItem]:
        """닫히지 않고 활성 멤버가 있는 room 목록을 조회합니다."""
        active_member = aliased(RoomMember)
        current_member = aliased(RoomMember)
        active_member_count = func.count(func.distinct(active_member.id))
        statement = (
            select(
                Room,
                active_member_count,
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
            .having(active_member_count > 0)
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

    @traced_method("GameRepository.lock_waiting_room_membership_for_user", layer="repository")
    async def lock_waiting_room_membership_for_user(self, *, user_id: UUID) -> None:
        """같은 유저의 대기 room membership 변경을 transaction 안에서 직렬화합니다."""
        await self.db_session.execute(
            select(func.pg_advisory_xact_lock(waiting_membership_lock_key(user_id)))
        )

    @traced_method(
        "GameRepository.list_active_waiting_room_public_ids_for_user", layer="repository"
    )
    async def list_active_waiting_room_public_ids_for_user(self, *, user_id: UUID) -> list[UUID]:
        """유저가 active member로 남아 있는 대기 room public_id 목록을 조회합니다."""
        statement = (
            select(Room.public_id)
            .join(RoomMember, RoomMember.room_id == Room.id)
            .where(
                RoomMember.user_id == user_id,
                RoomMember.left_at.is_(None),
                Room.status == RoomStatus.WAITING.value,
                Room.closed_at.is_(None),
            )
            .order_by(Room.created_at.asc())
        )
        result = await self.db_session.execute(statement)
        return list(result.scalars().all())

    @traced_method("GameRepository.list_active_room_public_ids_for_user", layer="repository")
    async def list_active_room_public_ids_for_user(self, *, user_id: UUID) -> list[UUID]:
        """유저가 active member로 남아 있는 닫히지 않은 room public_id 목록을 조회합니다."""
        statement = (
            select(Room.public_id)
            .join(RoomMember, RoomMember.room_id == Room.id)
            .where(
                RoomMember.user_id == user_id,
                RoomMember.left_at.is_(None),
                Room.closed_at.is_(None),
            )
            .order_by(Room.created_at.asc())
        )
        result = await self.db_session.execute(statement)
        return list(result.scalars().all())

    @traced_method("GameRepository.create_room", layer="repository")
    async def create_room(
        self,
        *,
        owner_user_id: UUID,
        name: str,
        game_type: str,
        status: str,
        max_players: int,
    ) -> GameRoomRecord:
        """room row 하나를 추가하고 flush된 식별자와 생성 시각을 반환합니다."""
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

    @traced_method("GameRepository.get_room_by_public_id", layer="repository")
    async def get_room_by_public_id(self, room_public_id: UUID) -> GameRoomRecord | None:
        """WebSocket 로비 연결 권한 확인용으로 room을 lock 없이 조회합니다."""
        result = await self.db_session.execute(select(Room).where(Room.public_id == room_public_id))
        room = result.scalar_one_or_none()
        if room is None:
            return None
        return self._room_to_record(room)

    @traced_method("GameRepository.get_room_by_public_id_for_update", layer="repository")
    async def get_room_by_public_id_for_update(self, room_public_id: UUID) -> GameRoomRecord | None:
        """게임 시작 transaction 동안 room row를 잠그고 시작 정보를 조회합니다."""
        result = await self.db_session.execute(
            select(Room).where(Room.public_id == room_public_id).with_for_update()
        )
        room = result.scalar_one_or_none()
        if room is None:
            return None
        return self._room_to_record(room)

    @traced_method("GameRepository.get_active_game_session_for_room", layer="repository")
    async def get_active_game_session_for_room(
        self, room_id: UUID
    ) -> tuple[GameSession, Room] | None:
        """room의 최신 active game_session row와 room row를 한 번 조회합니다."""
        result = await self.db_session.execute(
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
        return result.one_or_none()

    @traced_method("GameRepository.list_session_participants", layer="repository")
    async def list_session_participants(
        self,
        *,
        game_session_id: UUID,
        game_session_public_id: UUID,
    ) -> list[GameSessionParticipantRecord]:
        """game_session에 고정된 참가자 snapshot을 seat 순서로 조회합니다."""
        result = await self.db_session.execute(
            select(SessionParticipant)
            .where(SessionParticipant.session_id == game_session_id)
            .order_by(SessionParticipant.seat_number.asc())
        )
        return [
            self._participant_to_record(
                participant,
                game_session_public_id=game_session_public_id,
            )
            for participant in result.scalars().all()
        ]

    @traced_method("GameRepository.get_current_word_turn", layer="repository")
    async def get_current_word_turn(
        self, *, game_session: GameSession
    ) -> GameSessionTurnRecord | None:
        """game.started handoff에 포함할 현재 단어 턴 정보를 조회합니다."""
        if game_session.current_phase_id is None:
            return None
        result = await self.db_session.execute(
            select(SessionPhase, WordTurn, SessionParticipant)
            .join(WordTurn, WordTurn.phase_id == SessionPhase.id)
            .join(SessionParticipant, SessionParticipant.id == WordTurn.participant_id)
            .where(
                SessionPhase.id == game_session.current_phase_id,
                SessionPhase.session_id == game_session.id,
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        phase, turn, participant = row
        return GameSessionTurnRecord(
            phase_id=phase.id,
            round_number=turn.round_number,
            turn_number=turn.turn_number,
            actor_seat_number=participant.seat_number,
            started_at=phase.started_at,
            deadline_at=phase.deadline_at,
            required_start_char=turn.condition_payload.get("required_start_char"),
        )

    @traced_method("GameRepository.list_active_room_members", layer="repository")
    async def list_active_room_members(self, room_id: UUID) -> list[RoomMemberRecord]:
        """게임 시작 시 참가자로 고정할 활성 room member를 입장 순서대로 조회합니다."""
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

    @traced_method("GameRepository.get_active_room_member", layer="repository")
    async def get_active_room_member(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
    ) -> RoomMemberRecord | None:
        """유저가 현재 room에 활성 멤버로 참여 중인지 조회합니다."""
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

    @traced_method("GameRepository.create_room_member", layer="repository")
    async def create_room_member(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        nickname: str,
    ) -> RoomMemberRecord:
        """room_members row 하나를 추가하고 flush된 참여 시각을 반환합니다."""
        member = RoomMember(room_id=room_id, user_id=user_id, joined_at=kst_now())
        self.db_session.add(member)
        await self.db_session.flush()
        return RoomMemberRecord(
            room_id=member.room_id,
            user_id=member.user_id,
            nickname=nickname,
            joined_at=member.joined_at,
        )

    @traced_method("GameRepository.mark_room_member_left", layer="repository")
    async def mark_room_member_left(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        left_at: datetime,
    ) -> RoomLeaveResult | None:
        """활성 room member의 퇴장 시각을 기록하고 없으면 None을 반환합니다."""
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

    @traced_method("GameRepository.transfer_room_owner", layer="repository")
    async def transfer_room_owner(self, *, room_id: UUID, owner_user_id: UUID) -> None:
        """room owner_user_id를 새 유저로 변경합니다."""
        result = await self.db_session.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one()
        room.owner_user_id = owner_user_id
        room.updated_at = kst_now()
        await self.db_session.flush()

    @traced_method("GameRepository.close_room", layer="repository")
    async def close_room(self, *, room_id: UUID, closed_at: datetime) -> None:
        """room을 closed 상태로 바꾸고 closed_at을 기록합니다."""
        result = await self.db_session.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one()
        room.status = RoomStatus.CLOSED.value
        room.closed_at = closed_at
        room.updated_at = closed_at
        await self.db_session.flush()

    @traced_method("GameRepository.abort_active_session_for_room", layer="repository")
    async def abort_active_session_for_room(self, *, room_id: UUID, ended_at: datetime) -> None:
        """room의 최신 active game_session을 aborted로 마감합니다."""
        result = await self.db_session.execute(
            select(GameSession)
            .where(
                GameSession.room_id == room_id,
                GameSession.ended_at.is_(None),
                GameSession.status.not_in(TERMINAL_SESSION_STATUSES),
            )
            .order_by(GameSession.started_at.desc())
            .limit(1)
            .with_for_update()
        )
        game_session = result.scalar_one_or_none()
        if game_session is None:
            return
        game_session.status = GameSessionStatus.ABORTED.value
        game_session.ended_at = ended_at
        game_session.updated_at = ended_at
        await self.db_session.flush()

    @traced_method("GameRepository.update_room_settings", layer="repository")
    async def update_room_settings(
        self,
        *,
        room_id: UUID,
        name: str,
        max_players: int,
        rule_config: dict[str, int],
    ) -> RoomUpdateResult:
        """대기 room의 표시 정보와 게임 시작 전 룰 설정을 갱신합니다."""
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

    @traced_method("GameRepository.create_game_session_row", layer="repository")
    async def create_game_session_row(
        self,
        *,
        room_id: UUID,
        game_session_public_id: UUID,
        game_type: str,
        status: str,
        rule_config: dict[str, int],
        started_at: datetime,
    ) -> GameSession:
        """game_sessions row 하나를 추가하고 flush된 내부 식별자를 반환합니다."""
        game_session = GameSession(
            id=generate_uuid_v7(),
            public_id=game_session_public_id,
            room_id=room_id,
            game_type=game_type,
            status=status,
            rule_config=rule_config,
            started_at=started_at,
        )
        self.db_session.add(game_session)
        await self.db_session.flush()
        return game_session

    @traced_method("GameRepository.create_session_participant_row", layer="repository")
    async def create_session_participant_row(
        self,
        *,
        game_session_id: UUID,
        participant: GameSessionParticipantRecord,
    ) -> SessionParticipant:
        """session_participants row 하나를 추가하고 flush된 내부 식별자를 반환합니다."""
        row = SessionParticipant(
            id=generate_uuid_v7(),
            session_id=game_session_id,
            user_id=participant.user_id,
            participant_type=participant.participant_type,
            display_name=participant.display_name,
            original_nickname=participant.original_nickname,
            seat_number=participant.seat_number,
            is_uninvited_guest=participant.is_uninvited_guest,
        )
        self.db_session.add(row)
        await self.db_session.flush()
        return row

    @traced_method("GameRepository.mark_room_status", layer="repository")
    async def mark_room_status(self, *, room_id: UUID, status: str, updated_at: datetime) -> None:
        """room status를 하나 변경합니다."""
        result = await self.db_session.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one()
        room.status = status
        room.updated_at = updated_at
        await self.db_session.flush()

    @traced_method("GameRepository.get_random_round_start_char", layer="repository")
    async def get_random_round_start_char(self, *, game_type: str) -> str | None:
        """활성 유효 단어셋에 실제 후보가 있는 시작글자 중 하나를 무작위로 고릅니다."""
        result = await self.db_session.execute(
            select(ValidWord.starts_with)
            .where(
                ValidWord.game_type == game_type,
                ValidWord.is_active.is_(True),
            )
            .group_by(ValidWord.starts_with)
            .order_by(func.random())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @traced_method("GameRepository.create_session_phase_row", layer="repository")
    async def create_session_phase_row(
        self,
        *,
        session_id: UUID,
        phase_type: str,
        phase_number: int,
        actor_participant_id: UUID,
        condition_payload: dict,
        time_limit_seconds: int,
        started_at: datetime,
        deadline_at: datetime,
    ) -> SessionPhase:
        """session_phases row 하나를 추가하고 flush된 내부 식별자를 반환합니다."""
        phase = SessionPhase(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_type=phase_type,
            phase_number=phase_number,
            actor_participant_id=actor_participant_id,
            condition_payload=condition_payload,
            time_limit_seconds=time_limit_seconds,
            started_at=started_at,
            deadline_at=deadline_at,
        )
        self.db_session.add(phase)
        await self.db_session.flush()
        return phase

    @traced_method("GameRepository.create_word_turn_row", layer="repository")
    async def create_word_turn_row(
        self,
        *,
        phase_id: UUID,
        participant_id: UUID,
        round_number: int,
        turn_number: int,
        condition_payload: dict,
    ) -> WordTurn:
        """word_game.turns row 하나를 추가하고 flush된 내부 식별자를 반환합니다."""
        turn = WordTurn(
            phase_id=phase_id,
            participant_id=participant_id,
            round_number=round_number,
            turn_number=turn_number,
            condition_payload=condition_payload,
        )
        self.db_session.add(turn)
        await self.db_session.flush()
        return turn

    @traced_method("GameRepository.mark_game_session_current_phase", layer="repository")
    async def mark_game_session_current_phase(
        self,
        *,
        game_session: GameSession,
        current_phase_id: UUID,
    ) -> None:
        """game_session의 현재 phase FK를 확정합니다."""
        game_session.current_phase_id = current_phase_id
        await self.db_session.flush()

    @traced_method("GameRepository.get_user_participant_for_session", layer="repository")
    async def get_user_participant_for_session(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionParticipantRecord | None:
        """로그인 유저가 해당 게임 세션 참가자인지 조회합니다."""
        statement = (
            select(GameSession, SessionParticipant)
            .join(SessionParticipant, SessionParticipant.session_id == GameSession.id)
            .where(
                GameSession.public_id == game_session_public_id,
                GameSession.ended_at.is_(None),
                GameSession.status.not_in(TERMINAL_SESSION_STATUSES),
                SessionParticipant.user_id == user_id,
                SessionParticipant.left_at.is_(None),
            )
        )
        result = await self.db_session.execute(statement)
        row = result.one_or_none()
        if row is None:
            return None
        game_session, participant = row
        return self._participant_to_record(
            participant, game_session_public_id=game_session.public_id
        )

    @traced_method("GameRepository.get_participant_for_game_session_token", layer="repository")
    async def get_participant_for_game_session_token(
        self,
        *,
        token_hash: str,
        now: datetime,
    ) -> GameSessionParticipantRecord | None:
        """유효한 게임 세션 토큰 해시로 match 참가자를 조회합니다."""
        statement = (
            select(GameSession, SessionParticipant)
            .join(SessionParticipant, SessionParticipant.session_id == GameSession.id)
            .where(
                GameSession.ended_at.is_(None),
                GameSession.status.not_in(TERMINAL_SESSION_STATUSES),
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
        return self._participant_to_record(
            participant, game_session_public_id=game_session.public_id
        )

    @traced_method("GameRepository.save_game_session_token", layer="repository")
    async def save_game_session_token(
        self,
        *,
        game_session_public_id: UUID,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        """게임 참가자의 match 복구 토큰 해시와 만료 시각을 저장합니다."""
        statement = (
            select(GameSession, SessionParticipant)
            .join(SessionParticipant, SessionParticipant.session_id == GameSession.id)
            .where(
                GameSession.public_id == game_session_public_id,
                GameSession.ended_at.is_(None),
                GameSession.status.not_in(TERMINAL_SESSION_STATUSES),
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

    @traced_method("GameRepository.commit", layer="repository")
    async def commit(self) -> None:
        """현재 transaction을 확정합니다."""
        await self.db_session.commit()

    def _room_to_record(self, room: Room) -> GameRoomRecord:
        """ORM room을 service 계층에서 사용하는 record로 변환합니다."""
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

    def _participant_to_record(
        self,
        participant: SessionParticipant,
        *,
        game_session_public_id: UUID,
    ) -> GameSessionParticipantRecord:
        """ORM 참가자 snapshot을 service record로 변환합니다."""
        return GameSessionParticipantRecord(
            participant_id=participant.id,
            game_session_public_id=game_session_public_id,
            user_id=participant.user_id,
            participant_type=participant.participant_type,
            display_name=participant.display_name,
            seat_number=participant.seat_number,
            is_uninvited_guest=participant.is_uninvited_guest,
            resume_token_expires_at=participant.resume_token_expires_at,
        )
