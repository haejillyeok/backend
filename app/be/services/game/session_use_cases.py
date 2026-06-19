from dataclasses import replace
from uuid import UUID

from app.be.models.game import GameSession, SessionParticipant
from app.be.schemas.game_enum import GameType
from app.be.services.game.errors import (
    GameRoomNotFoundError,
    GameRoomNotStartableError,
    GameRoomStartForbiddenError,
)
from app.be.services.game.records import (
    GameRoomRecord,
    GameSessionParticipantRecord,
    GameSessionStartResult,
    GameSessionTurnRecord,
    STARTING_STATUS,
    WAITING_ROOM_STATUS,
)
from app.shared.core.identifiers import generate_uuid_v7
from app.shared.core.timezone import kst_now


class GameSessionUseCaseMixin:
    async def start_session(self, *, room_public_id: UUID, user_id: UUID) -> GameSessionStartResult:
        """방장이 room의 활성 멤버를 참가자로 고정하고 게임 세션 식별자를 발급합니다.

        같은 방장이 start API를 반복 호출하면 기존 active session을 그대로 반환합니다.
        room row lock을 잡은 뒤 판단해서 동시 중복 요청도 같은 transaction 경계에서 직렬화합니다.
        """
        async with self.repository_scope():
            return await self._start_session(room_public_id=room_public_id, user_id=user_id)

    async def _start_session(
        self,
        *,
        room_public_id: UUID,
        user_id: UUID,
    ) -> GameSessionStartResult:
        """게임 시작 transaction 안에서 room lock과 session 생성을 처리합니다."""
        room = await self.repository.get_room_by_public_id_for_update(room_public_id)
        if room is None:
            raise GameRoomNotFoundError
        if room.owner_user_id != user_id:
            raise GameRoomStartForbiddenError
        active_session = await self._get_active_session_result(room.id)
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
        participants = self.participant_policy.build_participants(
            game_session_public_id=game_session_public_id,
            members=members,
        )

        result = await self._create_game_session_result(
            room=room,
            game_session_public_id=game_session_public_id,
            participants=participants,
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

    async def _get_active_session_result(self, room_id: UUID) -> GameSessionStartResult | None:
        """active session row와 부속 snapshot 조회를 조합해 시작 응답 record를 만듭니다."""
        row = await self.repository.get_active_game_session_for_room(room_id)
        if row is None:
            return None
        game_session, room = row
        participants = await self.repository.list_session_participants(
            game_session_id=game_session.id,
            game_session_public_id=game_session.public_id,
        )
        current_turn = await self.repository.get_current_word_turn(game_session=game_session)
        return GameSessionStartResult(
            game_session_public_id=game_session.public_id,
            room_public_id=room.public_id,
            game_type=game_session.game_type,
            status=game_session.status,
            participants=participants,
            rule_config=game_session.rule_config,
            current_turn=current_turn,
        )

    async def _create_game_session_result(
        self,
        *,
        room: GameRoomRecord,
        game_session_public_id: UUID,
        participants: list[GameSessionParticipantRecord],
    ) -> GameSessionStartResult:
        """게임 세션 생성에 필요한 DB step을 순서대로 실행하고 응답 record를 조립합니다."""
        now = kst_now()
        game_session = await self.repository.create_game_session_row(
            room_id=room.id,
            game_session_public_id=game_session_public_id,
            game_type=room.game_type,
            status=STARTING_STATUS,
            rule_config=room.rule_config,
            started_at=now,
        )
        participant_rows = [
            await self.repository.create_session_participant_row(
                game_session_id=game_session.id,
                participant=participant,
            )
            for participant in participants
        ]
        await self.repository.mark_room_status(
            room_id=room.id,
            status=STARTING_STATUS,
            updated_at=now,
        )
        current_turn = await self._create_initial_turn_if_needed(
            game_session=game_session,
            participant_rows=participant_rows,
            room=room,
        )
        return GameSessionStartResult(
            game_session_public_id=game_session_public_id,
            room_public_id=room.public_id,
            game_type=room.game_type,
            status=STARTING_STATUS,
            participants=participants,
            rule_config=room.rule_config,
            current_turn=current_turn,
        )

    async def _create_initial_turn_if_needed(
        self,
        *,
        game_session: GameSession,
        participant_rows: list[SessionParticipant],
        room: GameRoomRecord,
    ):
        """게임 타입에 따라 세션 시작 직후 필요한 첫 phase/turn을 생성합니다."""
        if room.game_type != GameType.WORD_CHAIN.value or not participant_rows:
            return None
        required_start_char = await self.repository.get_random_round_start_char(
            game_type=room.game_type,
        )
        first_participant = self.initial_turn_policy.choose_round_start_participant(
            participant_rows
        )
        draft = self.initial_turn_policy.build_word_chain_initial_turn(
            rule_config=room.rule_config,
            required_start_char=required_start_char,
        )
        phase = await self.repository.create_session_phase_row(
            session_id=game_session.id,
            phase_type=draft.phase_type,
            phase_number=draft.phase_number,
            actor_participant_id=first_participant.id,
            condition_payload=draft.condition_payload,
            time_limit_seconds=draft.time_limit_seconds,
            started_at=draft.started_at,
            deadline_at=draft.deadline_at,
        )
        await self.repository.create_word_turn_row(
            phase_id=phase.id,
            participant_id=first_participant.id,
            round_number=draft.round_number,
            turn_number=draft.turn_number,
            condition_payload=draft.condition_payload,
        )
        await self.repository.mark_game_session_current_phase(
            game_session=game_session,
            current_phase_id=phase.id,
        )
        return GameSessionTurnRecord(
            phase_id=phase.id,
            round_number=draft.round_number,
            turn_number=draft.turn_number,
            actor_seat_number=first_participant.seat_number,
            started_at=phase.started_at,
            deadline_at=phase.deadline_at,
            required_start_char=draft.condition_payload.get("required_start_char"),
        )
