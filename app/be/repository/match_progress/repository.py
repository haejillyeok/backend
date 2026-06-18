from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.models.game import (
    GameEvent,
    GameSession,
    ParticipantAction,
    ScoreLedger,
    SessionParticipant,
    SessionPhase,
    UsedWord,
    ValidWord,
    WordSubmission,
    WordTurn,
)
from app.be.services.match_progress import (
    AI_ANSWER_FAILED_EVENT_TYPE,
    TURN_TIMEOUT_EVENT_TYPE,
    WORD_ACCEPTED_EVENT_TYPE,
    WORD_REJECT_ACTION_TYPE,
    WORD_REJECTED_EVENT_TYPE,
    WORD_SUBMIT_ACTION_TYPE,
)
from app.be.schemas.game_enum import GameSessionStatus
from app.shared.core.identifiers import generate_uuid_v7


class MatchProgressRepository:
    """게임 진행 상태 변경과 감사 event 저장을 담당합니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def get_game_session(self, game_session_public_id: UUID) -> GameSession | None:
        """게임 진행 기준 game session row를 조회합니다."""
        result = await self.db_session.execute(
            select(GameSession).where(GameSession.public_id == game_session_public_id)
        )
        return result.scalar_one_or_none()

    async def get_phase(self, *, session_id: UUID, phase_id: UUID) -> SessionPhase | None:
        """게임 진행 phase row를 잠그고 조회합니다."""
        result = await self.db_session.execute(
            select(SessionPhase)
            .where(SessionPhase.id == phase_id, SessionPhase.session_id == session_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_turn_actor(
        self,
        *,
        session_id: UUID,
        phase_id: UUID,
    ) -> tuple[WordTurn, SessionParticipant] | None:
        """현재 단어 턴과 담당 참가자를 조회합니다."""
        result = await self.db_session.execute(
            select(WordTurn, SessionParticipant)
            .join(SessionParticipant, SessionParticipant.id == WordTurn.participant_id)
            .where(
                WordTurn.phase_id == phase_id,
                SessionParticipant.session_id == session_id,
            )
        )
        return result.one_or_none()

    async def get_participant(
        self,
        *,
        session_id: UUID,
        participant_id: UUID,
    ) -> SessionParticipant | None:
        """세션 내 참가자 row 하나를 조회합니다."""
        result = await self.db_session.execute(
            select(SessionParticipant).where(
                SessionParticipant.id == participant_id,
                SessionParticipant.session_id == session_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_valid_word(self, *, game_type: str, normalized_word: str) -> ValidWord | None:
        """활성 사전 단어 row를 조회합니다."""
        result = await self.db_session.execute(
            select(ValidWord).where(
                ValidWord.game_type == game_type,
                ValidWord.normalized_word == normalized_word,
                ValidWord.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_used_word(
        self,
        *,
        session_id: UUID,
        round_number: int,
        normalized_word: str,
    ) -> UsedWord | None:
        """현재 라운드에서 이미 사용한 단어 row를 조회합니다."""
        result = await self.db_session.execute(
            select(UsedWord).where(
                UsedWord.session_id == session_id,
                UsedWord.round_number == round_number,
                UsedWord.normalized_word == normalized_word,
            )
        )
        return result.scalar_one_or_none()

    async def get_random_round_start_char(self, game_type: str) -> str | None:
        """활성 유효 단어셋에서 다음 라운드 시작 글자 후보 하나를 무작위로 조회합니다."""
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

    async def list_participants(self, session_id: UUID) -> list[SessionParticipant]:
        """세션 참가자 목록을 좌석 번호 순으로 조회합니다."""
        result = await self.db_session.execute(
            select(SessionParticipant)
            .where(SessionParticipant.session_id == session_id)
            .order_by(SessionParticipant.seat_number.asc())
        )
        return list(result.scalars().all())

    async def get_next_action_number(self, session_id: UUID) -> int:
        """다음 participant action 번호를 조회합니다."""
        result = await self.db_session.execute(
            select(func.coalesce(func.max(ParticipantAction.action_number), 0)).where(
                ParticipantAction.session_id == session_id
            )
        )
        return int(result.scalar_one()) + 1

    async def get_next_event_sequence(self, session_id: UUID) -> int:
        """다음 game event sequence를 조회합니다."""
        result = await self.db_session.execute(
            select(func.coalesce(func.max(GameEvent.sequence), 0)).where(
                GameEvent.session_id == session_id
            )
        )
        return int(result.scalar_one()) + 1

    async def create_word_submit_action(
        self,
        *,
        session_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        action_number: int,
        normalized_word: str,
        now: datetime,
    ) -> ParticipantAction:
        """단어 제출 action row 하나를 session에 추가합니다."""
        action = ParticipantAction(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_id=phase_id,
            participant_id=participant_id,
            action_type=WORD_SUBMIT_ACTION_TYPE,
            action_number=action_number,
            attempt_number=1,
            payload={"word": normalized_word, "normalized_word": normalized_word},
            submitted_at=now,
            response_ms=None,
            is_valid=True,
        )
        self.db_session.add(action)
        return action

    async def create_ai_answer_failed_action(
        self,
        *,
        session_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        action_number: int,
        reason: str,
        details: dict[str, Any],
        response_ms: int | None,
        now: datetime,
    ) -> ParticipantAction:
        """AI 응답 실패 action row 하나를 session에 추가합니다."""
        action = ParticipantAction(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_id=phase_id,
            participant_id=participant_id,
            action_type=AI_ANSWER_FAILED_EVENT_TYPE,
            action_number=action_number,
            attempt_number=1,
            payload={
                "source": "agent",
                "reason": reason,
                "details": details,
            },
            submitted_at=now,
            response_ms=response_ms,
            is_valid=False,
            reject_reason=reason,
        )
        self.db_session.add(action)
        return action

    async def create_turn_timeout_action(
        self,
        *,
        session_id: UUID,
        phase: SessionPhase,
        participant: SessionParticipant,
        action_number: int,
        now: datetime,
    ) -> ParticipantAction:
        """턴 deadline 초과 action row 하나를 session에 추가합니다."""
        action = ParticipantAction(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_type=TURN_TIMEOUT_EVENT_TYPE,
            action_number=action_number,
            attempt_number=None,
            payload={
                "reason": "deadline_exceeded",
                "deadline_at": phase.deadline_at.isoformat(),
            },
            submitted_at=now,
            response_ms=None,
            is_valid=False,
            reject_reason="deadline_exceeded",
        )
        self.db_session.add(action)
        return action

    async def create_word_reject_action(
        self,
        *,
        session_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        action_number: int,
        normalized_word: str,
        reason: str,
        details: dict[str, Any],
        now: datetime,
    ) -> ParticipantAction:
        """거절된 단어 제출 action row 하나를 session에 추가합니다."""
        action = ParticipantAction(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_id=phase_id,
            participant_id=participant_id,
            action_type=WORD_REJECT_ACTION_TYPE,
            action_number=action_number,
            attempt_number=1,
            payload={
                "word": normalized_word,
                "normalized_word": normalized_word,
                "reason": reason,
                "details": details,
            },
            submitted_at=now,
            response_ms=None,
            is_valid=False,
            reject_reason=reason,
        )
        self.db_session.add(action)
        return action

    async def create_word_submission(
        self,
        *,
        action_id: UUID,
        turn_id: UUID,
        normalized_word: str,
    ) -> WordSubmission:
        """단어 제출 상세 row 하나를 session에 추가합니다."""
        submission = WordSubmission(
            id=generate_uuid_v7(),
            action_id=action_id,
            turn_id=turn_id,
            word=normalized_word,
            normalized_word=normalized_word,
            dictionary_payload=None,
        )
        self.db_session.add(submission)
        return submission

    async def create_used_word(
        self,
        *,
        session_id: UUID,
        submission_id: UUID,
        round_number: int,
        normalized_word: str,
    ) -> UsedWord:
        """라운드 내 중복 방지용 used word row 하나를 session에 추가합니다."""
        used_word = UsedWord(
            id=generate_uuid_v7(),
            session_id=session_id,
            submission_id=submission_id,
            round_number=round_number,
            normalized_word=normalized_word,
        )
        self.db_session.add(used_word)
        return used_word

    async def create_word_submission_score(
        self,
        *,
        session_id: UUID,
        participant_id: UUID,
        submission_id: UUID,
        score_delta: int,
        now: datetime,
    ) -> ScoreLedger:
        """승인된 단어 제출 점수 ledger row 하나를 session에 추가합니다."""
        score = ScoreLedger(
            session_id=session_id,
            participant_id=participant_id,
            source_type="word_submission",
            source_id=submission_id,
            reason="word_accepted",
            score_delta=score_delta,
            created_at=now,
        )
        self.db_session.add(score)
        return score

    async def create_word_rejection_score(
        self,
        *,
        session_id: UUID,
        participant_id: UUID,
        action_id: UUID,
        reason: str,
        score_delta: int,
        now: datetime,
    ) -> ScoreLedger:
        """거절된 단어 제출 점수 ledger row 하나를 session에 추가합니다."""
        score = ScoreLedger(
            id=generate_uuid_v7(),
            session_id=session_id,
            participant_id=participant_id,
            source_type="word_rejection",
            source_id=action_id,
            reason=reason,
            score_delta=score_delta,
            created_at=now,
        )
        self.db_session.add(score)
        return score

    async def create_session_phase(self, phase: SessionPhase) -> SessionPhase:
        """다음 phase row 하나를 session에 추가합니다."""
        self.db_session.add(phase)
        return phase

    async def mark_phase_success(self, *, phase: SessionPhase, now: datetime) -> None:
        """현재 phase row 하나를 성공 종료 상태로 변경합니다."""
        phase.finished_at = now
        phase.result_status = "success"

    async def mark_phase_timeout(self, *, phase: SessionPhase, now: datetime) -> None:
        """현재 phase row 하나를 timeout 종료 상태로 변경합니다."""
        phase.finished_at = now
        phase.result_status = "timeout"

    async def mark_game_session_playing(
        self,
        *,
        game_session: GameSession,
        current_phase_id: UUID,
    ) -> None:
        """game session row 하나의 진행 상태와 현재 phase를 변경합니다."""
        game_session.status = GameSessionStatus.PLAYING.value
        game_session.current_phase_id = current_phase_id

    async def mark_game_session_voting(
        self,
        *,
        game_session: GameSession,
        current_phase_id: UUID,
    ) -> None:
        """game session row 하나를 투표 상태와 현재 phase로 변경합니다."""
        game_session.status = GameSessionStatus.VOTING.value
        game_session.current_phase_id = current_phase_id

    async def create_word_turn(self, turn: WordTurn) -> WordTurn:
        """다음 word turn row 하나를 session에 추가합니다."""
        self.db_session.add(turn)
        return turn

    async def create_word_accepted_event(
        self,
        *,
        session_id: UUID,
        phase: SessionPhase,
        participant: SessionParticipant,
        action: ParticipantAction,
        event_sequence: int,
        payload: dict[str, object],
        now: datetime,
    ) -> GameEvent:
        """단어 승인 event row 하나를 session에 추가합니다."""
        event = GameEvent(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_id=action.id,
            sequence=event_sequence,
            event_type=WORD_ACCEPTED_EVENT_TYPE,
            payload=payload,
            created_at=now,
        )
        self.db_session.add(event)
        return event

    async def create_ai_answer_failed_event(
        self,
        *,
        session_id: UUID,
        phase: SessionPhase,
        participant: SessionParticipant,
        action_id: UUID,
        event_sequence: int,
        payload: dict[str, object],
        now: datetime,
    ) -> GameEvent:
        """AI 응답 실패 event row 하나를 session에 추가합니다."""
        event = GameEvent(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_id=action_id,
            sequence=event_sequence,
            event_type=AI_ANSWER_FAILED_EVENT_TYPE,
            payload=payload,
            created_at=now,
        )
        self.db_session.add(event)
        return event

    async def create_turn_timeout_event(
        self,
        *,
        session_id: UUID,
        phase: SessionPhase,
        participant: SessionParticipant,
        action: ParticipantAction,
        event_sequence: int,
        round_number: int,
        payload: dict[str, object],
        now: datetime,
    ) -> GameEvent:
        """턴 timeout event row 하나를 session에 추가합니다."""
        event_payload = {
            "phase_id": str(phase.id),
            "participant": {
                "display_name": participant.display_name,
                "seat_number": participant.seat_number,
            },
            "round_number": round_number,
            "reason": "deadline_exceeded",
            "deadline_at": phase.deadline_at.isoformat(),
            "result_status": "timeout",
        }
        event_payload.update(payload)
        event = GameEvent(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_id=action.id,
            sequence=event_sequence,
            event_type=TURN_TIMEOUT_EVENT_TYPE,
            payload=event_payload,
            created_at=now,
        )
        self.db_session.add(event)
        return event

    async def create_word_rejected_event(
        self,
        *,
        session_id: UUID,
        phase: SessionPhase,
        participant: SessionParticipant,
        action_id: UUID,
        event_sequence: int,
        payload: dict[str, object],
        now: datetime,
    ) -> GameEvent:
        """단어 거절 event row 하나를 session에 추가합니다."""
        event = GameEvent(
            id=generate_uuid_v7(),
            session_id=session_id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_id=action_id,
            sequence=event_sequence,
            event_type=WORD_REJECTED_EVENT_TYPE,
            payload=payload,
            created_at=now,
        )
        self.db_session.add(event)
        return event

    async def flush(self) -> None:
        """현재 session의 pending 변경을 DB에 반영해 row id와 제약을 확정합니다."""
        await self.db_session.flush()

    async def commit(self) -> None:
        """진행 상태 변경 transaction을 확정합니다."""
        await self.db_session.commit()
