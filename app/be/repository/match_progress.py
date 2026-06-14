from datetime import datetime, timedelta
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
)
from app.be.models.game import SessionPhase, UsedWord, ValidWord, WordSubmission, WordTurn
from app.be.schemas.game_enum import GameSessionStatus
from app.be.services.match_progress import (
    AI_ANSWER_FAILED_EVENT_TYPE,
    TURN_TIMEOUT_EVENT_TYPE,
    WORD_ACCEPTED_EVENT_TYPE,
    WORD_REJECT_ACTION_TYPE,
    WORD_REJECTED_EVENT_TYPE,
    WORD_SUBMIT_ACTION_TYPE,
    AiAnswerFailureRecord,
    MatchTurnEventPayload,
    TurnTimeoutRecord,
    WordRejectionRecord,
    WordSubmissionRecord,
)
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException
from app.shared.core.identifiers import generate_uuid_v7
from app.shared.core.timezone import kst_now


class MatchProgressRepository:
    """게임 진행 상태 변경과 감사 event 저장을 담당합니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def record_ai_answer_failure(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        reason: str,
        details: dict[str, Any] | None = None,
        response_ms: int | None = None,
    ) -> AiAnswerFailureRecord | None:
        """Agent API 미응답/오류를 현재 턴 실패 action과 event로 저장합니다."""
        game_session = await self._get_game_session(game_session_public_id)
        phase = await self._get_phase(session_id=game_session.id, phase_id=phase_id)
        if phase.finished_at is not None:
            return None
        participant = await self._get_participant(
            session_id=game_session.id,
            participant_id=participant_id,
        )
        await self._get_turn_actor(session_id=game_session.id, phase_id=phase.id)

        now = kst_now()
        action_number = await self._next_action_number(game_session.id)
        payload = {
            "source": "agent",
            "reason": reason,
            "details": details or {},
        }
        action = ParticipantAction(
            session_id=game_session.id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_type=AI_ANSWER_FAILED_EVENT_TYPE,
            action_number=action_number,
            attempt_number=1,
            payload=payload,
            submitted_at=now,
            response_ms=response_ms,
            is_valid=False,
            reject_reason=reason,
        )
        self.db_session.add(action)
        await self.db_session.flush()

        event_sequence = await self._next_event_sequence(game_session.id)
        event_payload = {
            "phase_id": str(phase.id),
            "participant": {
                "display_name": participant.display_name,
                "seat_number": participant.seat_number,
            },
            "reason": reason,
            "details": details or {},
            "result_status": "failed",
        }
        event = GameEvent(
            session_id=game_session.id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_id=action.id,
            sequence=event_sequence,
            event_type=AI_ANSWER_FAILED_EVENT_TYPE,
            payload=event_payload,
            created_at=now,
        )
        self.db_session.add(event)
        await self.db_session.flush()

        return AiAnswerFailureRecord(
            game_session_public_id=game_session.public_id,
            phase_id=phase.id,
            participant_id=participant.id,
            display_name=participant.display_name,
            seat_number=participant.seat_number,
            action_id=action.id,
            event_id=event.id,
            event_sequence=event.sequence,
            reason=reason,
            details=details or {},
            created_at=now,
        )

    async def commit(self) -> None:
        """진행 상태 변경 transaction을 확정합니다."""
        await self.db_session.commit()

    async def record_turn_timeout(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        now,
    ) -> TurnTimeoutRecord | None:
        """deadline이 지난 현재 턴을 서버 기준 timeout으로 확정합니다."""
        game_session = await self._get_game_session(game_session_public_id)
        phase = await self._get_phase(session_id=game_session.id, phase_id=phase_id)
        if phase.finished_at is not None or phase.deadline_at is None or now < phase.deadline_at:
            return None
        if phase.actor_participant_id is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "phase_actor_missing"},
            )
        participant = await self._get_participant(
            session_id=game_session.id,
            participant_id=phase.actor_participant_id,
        )
        turn, _ = await self._get_turn_actor(session_id=game_session.id, phase_id=phase.id)
        participants = await self._list_participants(game_session.id)

        action_number = await self._next_action_number(game_session.id)
        action_payload = {
            "reason": "deadline_exceeded",
            "deadline_at": phase.deadline_at.isoformat(),
        }
        action = ParticipantAction(
            session_id=game_session.id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_type=TURN_TIMEOUT_EVENT_TYPE,
            action_number=action_number,
            attempt_number=None,
            payload=action_payload,
            submitted_at=now,
            response_ms=None,
            is_valid=False,
            reject_reason="deadline_exceeded",
        )
        self.db_session.add(action)
        await self.db_session.flush()

        # Timeout은 클라이언트 표시 시간이 아니라 서버 deadline으로만 확정합니다.
        phase.finished_at = now
        phase.result_status = "timeout"

        next_items, transition_payload, next_turn_record, next_status, voting_deadline_at = (
            self._build_round_end_transition(
                game_session=game_session,
                phase=phase,
                turn=turn,
                participant=participant,
                participants=participants,
                now=now,
            )
        )
        next_phases = [item for item in next_items if isinstance(item, SessionPhase)]
        next_non_phases = [item for item in next_items if not isinstance(item, SessionPhase)]
        for item in next_phases:
            self.db_session.add(item)
        if next_phases:
            # current_phase_id와 다음 turn은 새 phase row를 참조하므로 phase를 먼저 확정합니다.
            await self.db_session.flush()
            game_session.current_phase_id = next_phases[-1].id

        event_sequence = await self._next_event_sequence(game_session.id)
        event_payload = {
            "phase_id": str(phase.id),
            "participant": {
                "display_name": participant.display_name,
                "seat_number": participant.seat_number,
            },
            "round_number": turn.round_number,
            "reason": "deadline_exceeded",
            "deadline_at": phase.deadline_at.isoformat(),
            "result_status": "timeout",
        }
        event_payload.update(transition_payload)
        event = GameEvent(
            session_id=game_session.id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_id=action.id,
            sequence=event_sequence,
            event_type=TURN_TIMEOUT_EVENT_TYPE,
            payload=event_payload,
            created_at=now,
        )
        for item in next_non_phases:
            self.db_session.add(item)
        self.db_session.add(event)
        await self.db_session.flush()

        return TurnTimeoutRecord(
            game_session_public_id=game_session.public_id,
            phase_id=phase.id,
            participant_id=participant.id,
            display_name=participant.display_name,
            seat_number=participant.seat_number,
            action_id=action.id,
            event_id=event.id,
            event_sequence=event.sequence,
            deadline_at=phase.deadline_at,
            created_at=now,
            round_number=turn.round_number,
            next_turn=next_turn_record,
            next_status=next_status,
            voting_deadline_at=voting_deadline_at,
        )

    async def record_word_submission(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        word: str,
        now,
    ) -> WordSubmissionRecord:
        """현재 턴 단어 제출을 승인하고 사용 단어, 점수, 다음 턴을 저장합니다."""
        game_session = await self._get_game_session(game_session_public_id)
        phase = await self._get_phase(session_id=game_session.id, phase_id=phase_id)
        turn, participant = await self._get_turn_actor(
            session_id=game_session.id,
            phase_id=phase.id,
        )
        self._validate_active_turn(
            phase=phase,
            turn=turn,
            participant_id=participant_id,
            now=now,
        )
        normalized_word = self._normalize_word(word)
        required_start_char = turn.condition_payload.get("required_start_char")
        if required_start_char and not normalized_word.startswith(required_start_char):
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={
                    "reason": "word_start_char_mismatch",
                    "required_start_char": required_start_char,
                },
            )
        await self._ensure_word_is_valid(
            game_type=game_session.game_type,
            normalized_word=normalized_word,
        )
        await self._ensure_word_not_used(
            session_id=game_session.id,
            normalized_word=normalized_word,
        )
        participants = await self._list_participants(game_session.id)
        next_participant = self._next_participant(participants, participant)
        next_required_start_char = normalized_word[-1]
        turn_time_seconds = int(game_session.rule_config.get("turn_time_seconds", 10))
        next_phase = SessionPhase(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            phase_type="turn",
            phase_number=phase.phase_number + 1,
            actor_participant_id=next_participant.id,
            condition_payload={"required_start_char": next_required_start_char},
            time_limit_seconds=turn_time_seconds,
            started_at=now,
            deadline_at=now + timedelta(seconds=turn_time_seconds),
        )
        next_turn = WordTurn(
            id=generate_uuid_v7(),
            phase_id=next_phase.id,
            participant_id=next_participant.id,
            round_number=turn.round_number,
            turn_number=turn.turn_number + 1,
            condition_payload=next_phase.condition_payload,
        )

        action_number = await self._next_action_number(game_session.id)
        action = ParticipantAction(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_type=WORD_SUBMIT_ACTION_TYPE,
            action_number=action_number,
            attempt_number=1,
            payload={"word": normalized_word, "normalized_word": normalized_word},
            submitted_at=now,
            response_ms=None,
            is_valid=True,
        )
        self.db_session.add(action)
        # submission, event가 action_id를 참조하므로 action row를 먼저 확정합니다.
        await self.db_session.flush()

        submission = WordSubmission(
            id=generate_uuid_v7(),
            action_id=action.id,
            turn_id=turn.id,
            word=normalized_word,
            normalized_word=normalized_word,
            dictionary_payload=None,
        )
        self.db_session.add(submission)
        # used_words.submission_id가 submissions.id를 참조하므로 submission row를 먼저 확정합니다.
        await self.db_session.flush()

        used_word = UsedWord(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            submission_id=submission.id,
            normalized_word=normalized_word,
        )
        score_delta = 10
        score = ScoreLedger(
            session_id=game_session.id,
            participant_id=participant.id,
            source_type="word_submission",
            source_id=submission.id,
            reason="word_accepted",
            score_delta=score_delta,
            created_at=now,
        )

        phase.finished_at = now
        phase.result_status = "success"
        game_session.status = GameSessionStatus.PLAYING.value
        for item in [used_word, score, next_phase]:
            self.db_session.add(item)
        # current_phase_id와 next turn이 참조할 다음 phase row를 먼저 확정합니다.
        await self.db_session.flush()
        game_session.current_phase_id = next_phase.id

        event_sequence = await self._next_event_sequence(game_session.id)
        next_turn_payload = {
            "phase_id": str(next_phase.id),
            "round_number": next_turn.round_number,
            "turn_number": next_turn.turn_number,
            "actor_seat_number": next_participant.seat_number,
            "deadline_at": next_phase.deadline_at.isoformat(),
            "required_start_char": next_required_start_char,
        }
        event = GameEvent(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_id=action.id,
            sequence=event_sequence,
            event_type=WORD_ACCEPTED_EVENT_TYPE,
            payload={
                "phase_id": str(phase.id),
                "participant": {
                    "display_name": participant.display_name,
                    "seat_number": participant.seat_number,
                },
                "word": normalized_word,
                "normalized_word": normalized_word,
                "score_delta": score_delta,
                "next_turn": next_turn_payload,
            },
            created_at=now,
        )

        for item in [next_turn, event]:
            self.db_session.add(item)
        await self.db_session.flush()

        return WordSubmissionRecord(
            game_session_public_id=game_session.public_id,
            phase_id=phase.id,
            participant_id=participant.id,
            display_name=participant.display_name,
            seat_number=participant.seat_number,
            word=normalized_word,
            normalized_word=normalized_word,
            action_id=action.id,
            submission_id=submission.id,
            event_id=event.id,
            event_sequence=event.sequence,
            score_delta=score_delta,
            next_turn=MatchTurnEventPayload(
                phase_id=next_phase.id,
                round_number=next_turn.round_number,
                turn_number=next_turn.turn_number,
                actor_seat_number=next_participant.seat_number,
                deadline_at=next_phase.deadline_at,
                required_start_char=next_required_start_char,
            ),
            created_at=now,
        )

    async def record_word_rejection(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        word: str,
        reason: str,
        details: dict[str, Any] | None,
        now,
    ) -> WordRejectionRecord:
        """게임 규칙상 실패한 단어 제출을 action, score, event로 저장합니다."""
        game_session = await self._get_game_session(game_session_public_id)
        phase = await self._get_phase(session_id=game_session.id, phase_id=phase_id)
        turn, participant = await self._get_turn_actor(
            session_id=game_session.id,
            phase_id=phase.id,
        )
        self._validate_active_turn(
            phase=phase,
            turn=turn,
            participant_id=participant_id,
            now=now,
        )
        normalized_word = self._normalize_word(word)
        rejection_details = details or {}
        action_number = await self._next_action_number(game_session.id)
        action = ParticipantAction(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_type=WORD_REJECT_ACTION_TYPE,
            action_number=action_number,
            attempt_number=1,
            payload={
                "word": normalized_word,
                "normalized_word": normalized_word,
                "reason": reason,
                "details": rejection_details,
            },
            submitted_at=now,
            response_ms=None,
            is_valid=False,
            reject_reason=reason,
        )
        self.db_session.add(action)
        # GameEvent.action_id가 participant_actions.id를 참조하므로 action row를 먼저 확정합니다.
        await self.db_session.flush()

        score_delta = self._word_rejection_score_delta(reason)
        score = ScoreLedger(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            participant_id=participant.id,
            source_type="word_rejection",
            source_id=action.id,
            reason=reason,
            score_delta=score_delta,
            created_at=now,
        )
        event_sequence = await self._next_event_sequence(game_session.id)
        event = GameEvent(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_id=action.id,
            sequence=event_sequence,
            event_type=WORD_REJECTED_EVENT_TYPE,
            payload={
                "phase_id": str(phase.id),
                "participant": {
                    "display_name": participant.display_name,
                    "seat_number": participant.seat_number,
                },
                "word": normalized_word,
                "normalized_word": normalized_word,
                "reason": reason,
                "details": rejection_details,
                "score_delta": score_delta,
            },
            created_at=now,
        )
        for item in [score, event]:
            self.db_session.add(item)
        await self.db_session.flush()

        return WordRejectionRecord(
            game_session_public_id=game_session.public_id,
            phase_id=phase.id,
            participant_id=participant.id,
            display_name=participant.display_name,
            seat_number=participant.seat_number,
            word=normalized_word,
            normalized_word=normalized_word,
            action_id=action.id,
            event_id=event.id,
            event_sequence=event.sequence,
            reason=reason,
            details=rejection_details,
            score_delta=score_delta,
            created_at=now,
        )

    async def _get_game_session(self, game_session_public_id: UUID) -> GameSession:
        result = await self.db_session.execute(
            select(GameSession).where(GameSession.public_id == game_session_public_id)
        )
        game_session = result.scalar_one_or_none()
        if game_session is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "game_session_not_found"},
            )
        return game_session

    async def _get_phase(self, *, session_id: UUID, phase_id: UUID) -> SessionPhase:
        result = await self.db_session.execute(
            select(SessionPhase)
            .where(SessionPhase.id == phase_id, SessionPhase.session_id == session_id)
            .with_for_update()
        )
        phase = result.scalar_one_or_none()
        if phase is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "phase_not_found"},
            )
        return phase

    async def _get_participant(
        self,
        *,
        session_id: UUID,
        participant_id: UUID,
    ) -> SessionParticipant:
        result = await self.db_session.execute(
            select(SessionParticipant).where(
                SessionParticipant.id == participant_id,
                SessionParticipant.session_id == session_id,
            )
        )
        participant = result.scalar_one_or_none()
        if participant is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "participant_not_found"},
            )
        return participant

    async def _get_turn_actor(
        self,
        *,
        session_id: UUID,
        phase_id: UUID,
    ) -> tuple[WordTurn, SessionParticipant]:
        result = await self.db_session.execute(
            select(WordTurn, SessionParticipant)
            .join(SessionParticipant, SessionParticipant.id == WordTurn.participant_id)
            .where(
                WordTurn.phase_id == phase_id,
                SessionParticipant.session_id == session_id,
            )
        )
        row = result.one_or_none()
        if row is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "turn_not_found"},
            )
        return row

    async def _ensure_word_not_used(self, *, session_id: UUID, normalized_word: str) -> None:
        result = await self.db_session.execute(
            select(UsedWord).where(
                UsedWord.session_id == session_id,
                UsedWord.normalized_word == normalized_word,
            )
        )
        if result.scalar_one_or_none() is not None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "word_already_used"},
            )

    async def _ensure_word_is_valid(self, *, game_type: str, normalized_word: str) -> None:
        result = await self.db_session.execute(
            select(ValidWord).where(
                ValidWord.game_type == game_type,
                ValidWord.normalized_word == normalized_word,
                ValidWord.is_active.is_(True),
            )
        )
        if result.scalar_one_or_none() is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "word_not_in_dictionary"},
            )

    async def _list_participants(self, session_id: UUID) -> list[SessionParticipant]:
        result = await self.db_session.execute(
            select(SessionParticipant)
            .where(SessionParticipant.session_id == session_id)
            .order_by(SessionParticipant.seat_number.asc())
        )
        return list(result.scalars().all())

    def _validate_active_turn(
        self,
        *,
        phase: SessionPhase,
        turn: WordTurn,
        participant_id: UUID,
        now,
    ) -> None:
        if phase.finished_at is not None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "phase_already_finished"},
            )
        if phase.deadline_at is not None and now > phase.deadline_at:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "turn_deadline_exceeded"},
            )
        if turn.participant_id != participant_id:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "not_turn_actor"},
            )

    def _next_participant(
        self,
        participants: list[SessionParticipant],
        current_participant: SessionParticipant,
    ) -> SessionParticipant:
        if not participants:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "participants_missing"},
            )
        later_participant = next(
            (
                participant
                for participant in participants
                if participant.seat_number > current_participant.seat_number
            ),
            None,
        )
        return later_participant or participants[0]

    def _build_round_end_transition(
        self,
        *,
        game_session: GameSession,
        phase: SessionPhase,
        turn: WordTurn,
        participant: SessionParticipant,
        participants: list[SessionParticipant],
        now,
    ) -> tuple[
        list[object],
        dict[str, Any],
        MatchTurnEventPayload | None,
        str | None,
        datetime | None,
    ]:
        """한 판 종료 뒤 다음 판 시작 또는 투표 전환 상태를 구성합니다."""
        max_rounds = int(game_session.rule_config.get("max_rounds", 8))
        if turn.round_number >= max_rounds:
            vote_time_seconds = int(game_session.rule_config.get("vote_time_seconds", 20))
            voting_phase = SessionPhase(
                id=generate_uuid_v7(),
                session_id=game_session.id,
                phase_type="voting",
                phase_number=phase.phase_number + 1,
                actor_participant_id=None,
                condition_payload={},
                time_limit_seconds=vote_time_seconds,
                started_at=now,
                deadline_at=now + timedelta(seconds=vote_time_seconds),
            )
            game_session.status = GameSessionStatus.VOTING.value
            return (
                [voting_phase],
                {
                    "next_status": GameSessionStatus.VOTING.value,
                    "voting_deadline_at": voting_phase.deadline_at.isoformat(),
                },
                None,
                GameSessionStatus.VOTING.value,
                voting_phase.deadline_at,
            )

        next_participant = self._next_participant(participants, participant)
        turn_time_seconds = int(game_session.rule_config.get("turn_time_seconds", 10))
        next_phase = SessionPhase(
            id=generate_uuid_v7(),
            session_id=game_session.id,
            phase_type="turn",
            phase_number=phase.phase_number + 1,
            actor_participant_id=next_participant.id,
            condition_payload={"required_start_char": None},
            time_limit_seconds=turn_time_seconds,
            started_at=now,
            deadline_at=now + timedelta(seconds=turn_time_seconds),
        )
        next_turn = WordTurn(
            id=generate_uuid_v7(),
            phase_id=next_phase.id,
            participant_id=next_participant.id,
            round_number=turn.round_number + 1,
            turn_number=1,
            condition_payload=next_phase.condition_payload,
        )
        game_session.status = GameSessionStatus.PLAYING.value
        next_turn_payload = {
            "phase_id": str(next_phase.id),
            "round_number": next_turn.round_number,
            "turn_number": next_turn.turn_number,
            "actor_seat_number": next_participant.seat_number,
            "deadline_at": next_phase.deadline_at.isoformat(),
            "required_start_char": None,
        }
        return (
            [next_phase, next_turn],
            {"next_turn": next_turn_payload},
            MatchTurnEventPayload(
                phase_id=next_phase.id,
                round_number=next_turn.round_number,
                turn_number=next_turn.turn_number,
                actor_seat_number=next_participant.seat_number,
                deadline_at=next_phase.deadline_at,
                required_start_char=None,
            ),
            None,
            None,
        )

    def _normalize_word(self, word: str) -> str:
        normalized_word = word.strip()
        if not normalized_word:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "word_empty"},
            )
        return normalized_word

    def _word_rejection_score_delta(self, reason: str) -> int:
        """거절 사유별 단어 제출 페널티를 반환합니다."""
        if reason == "word_start_char_mismatch":
            return -5
        if reason == "word_not_in_dictionary":
            return -5
        if reason == "word_already_used":
            return -1
        return 0

    async def _next_action_number(self, session_id: UUID) -> int:
        result = await self.db_session.execute(
            select(func.coalesce(func.max(ParticipantAction.action_number), 0)).where(
                ParticipantAction.session_id == session_id
            )
        )
        return int(result.scalar_one()) + 1

    async def _next_event_sequence(self, session_id: UUID) -> int:
        result = await self.db_session.execute(
            select(func.coalesce(func.max(GameEvent.sequence), 0)).where(
                GameEvent.session_id == session_id
            )
        )
        return int(result.scalar_one()) + 1
