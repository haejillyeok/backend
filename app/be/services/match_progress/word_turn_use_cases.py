from datetime import datetime
from typing import Any
from uuid import UUID

from app.be.services.match_progress.constants import TURN_RESOLVED_MESSAGE_TYPE
from app.be.services.match_progress.records import (
    MatchBroadcastEvent,
    MatchTurnEventPayload,
    WordRejectionRecord,
    WordSubmissionRecord,
)
from app.be.services.match_progress.turn_resolution_payloads import serialize_next_turn
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


class MatchProgressWordTurnUseCaseMixin:
    async def submit_word(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        word: str,
        now: datetime,
    ) -> MatchBroadcastEvent:
        """현재 턴 단어 제출을 확정하고 다음 턴 broadcast event를 반환합니다."""
        async with self.repository_scope():
            return await self._submit_word(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
                word=word,
                now=now,
            )

    async def _submit_word(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        word: str,
        now: datetime,
    ) -> MatchBroadcastEvent:
        """단어 제출 transaction 안에서 검증, 저장, 다음 턴 생성을 처리합니다."""
        game_session = await self.repository.get_game_session(game_session_public_id)
        if game_session is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "game_session_not_found"},
            )
        phase = await self.repository.get_phase(session_id=game_session.id, phase_id=phase_id)
        if phase is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "phase_not_found"},
            )
        turn_actor = await self.repository.get_turn_actor(
            session_id=game_session.id,
            phase_id=phase.id,
        )
        if turn_actor is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "turn_not_found"},
            )
        turn, participant = turn_actor
        self.turn_policy.validate_active_turn(
            phase=phase,
            turn=turn,
            participant_id=participant_id,
            now=now,
        )
        normalized_word = self.turn_policy.normalize_word(word)
        self.word_submission_policy.ensure_word_starts_with_required_char(
            normalized_word=normalized_word,
            required_start_char=turn.condition_payload.get("required_start_char"),
        )
        valid_word = await self.repository.get_valid_word(
            game_type=game_session.game_type,
            normalized_word=normalized_word,
        )
        self.word_submission_policy.ensure_word_is_valid(valid_word)
        used_word = await self.repository.get_used_word(
            session_id=game_session.id,
            round_number=turn.round_number,
            normalized_word=normalized_word,
        )
        self.word_submission_policy.ensure_word_not_used(used_word)

        participants = await self.repository.list_participants(game_session.id)
        next_participant = self.turn_policy.next_participant(participants, participant)
        next_turn_draft = self.word_submission_policy.build_next_turn(
            game_session=game_session,
            phase=phase,
            turn=turn,
            next_participant=next_participant,
            normalized_word=normalized_word,
            now=now,
        )
        action_number = await self.repository.get_next_action_number(game_session.id)
        action = await self.repository.create_word_submit_action(
            session_id=game_session.id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_number=action_number,
            normalized_word=normalized_word,
            now=now,
        )
        await self.repository.flush()
        submission = await self.repository.create_word_submission(
            action_id=action.id,
            turn_id=turn.id,
            normalized_word=normalized_word,
        )
        await self.repository.flush()
        await self.repository.create_used_word(
            session_id=game_session.id,
            submission_id=submission.id,
            round_number=turn.round_number,
            normalized_word=normalized_word,
        )
        score_delta = self.word_submission_policy.accepted_score_delta()
        await self.repository.create_word_submission_score(
            session_id=game_session.id,
            participant_id=participant.id,
            submission_id=submission.id,
            score_delta=score_delta,
            now=now,
        )
        await self.repository.create_session_phase(next_turn_draft.phase)
        await self.repository.flush()
        await self.repository.mark_phase_success(phase=phase, now=now)
        await self.repository.mark_game_session_playing(
            game_session=game_session,
            current_phase_id=next_turn_draft.phase.id,
        )
        await self.repository.create_word_turn(next_turn_draft.turn)
        event_sequence = await self.repository.get_next_event_sequence(game_session.id)
        event = await self.repository.create_word_accepted_event(
            session_id=game_session.id,
            phase=phase,
            participant=participant,
            action=action,
            event_sequence=event_sequence,
            payload=self.word_submission_policy.build_accepted_event_payload(
                phase=phase,
                participant=participant,
                normalized_word=normalized_word,
                score_delta=score_delta,
                next_turn_payload=next_turn_draft.payload,
            ),
            now=now,
        )
        await self.repository.flush()
        record = WordSubmissionRecord(
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
                phase_id=next_turn_draft.phase.id,
                round_number=next_turn_draft.turn.round_number,
                turn_number=next_turn_draft.turn.turn_number,
                actor_seat_number=int(next_turn_draft.payload["actor_seat_number"]),
                started_at=next_turn_draft.phase.started_at,
                deadline_at=next_turn_draft.phase.deadline_at,
                required_start_char=next_turn_draft.required_start_char,
            ),
            created_at=now,
        )
        await self.repository.commit()
        return MatchBroadcastEvent(
            game_session_public_id=record.game_session_public_id,
            message={
                "type": TURN_RESOLVED_MESSAGE_TYPE,
                "payload": {
                    "event_sequence": record.event_sequence,
                    "phase_id": record.phase_id,
                    "participant": {
                        "display_name": record.display_name,
                        "seat_number": record.seat_number,
                    },
                    "result": "accepted",
                    "word": record.word,
                    "normalized_word": record.normalized_word,
                    "reason": None,
                    "details": {},
                    "score_delta": record.score_delta,
                    "next_turn": serialize_next_turn(record.next_turn),
                    "created_at": record.created_at,
                    "server_time": record.created_at,
                },
            },
        )

    async def reject_word(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        word: str,
        reason: str,
        details: dict[str, Any] | None,
        now: datetime,
    ) -> MatchBroadcastEvent:
        """게임 규칙상 실패한 단어 제출을 확정하고 broadcast event를 반환합니다."""
        async with self.repository_scope():
            return await self._reject_word(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
                word=word,
                reason=reason,
                details=details,
                now=now,
            )

    async def _reject_word(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        word: str,
        reason: str,
        details: dict[str, Any] | None,
        now: datetime,
    ) -> MatchBroadcastEvent:
        """단어 거절 transaction 안에서 action, score, event를 확정합니다."""
        game_session = await self.repository.get_game_session(game_session_public_id)
        if game_session is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "game_session_not_found"},
            )
        phase = await self.repository.get_phase(session_id=game_session.id, phase_id=phase_id)
        if phase is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "phase_not_found"},
            )
        turn_actor = await self.repository.get_turn_actor(
            session_id=game_session.id,
            phase_id=phase.id,
        )
        if turn_actor is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "turn_not_found"},
            )
        turn, participant = turn_actor
        self.turn_policy.validate_active_turn(
            phase=phase,
            turn=turn,
            participant_id=participant_id,
            now=now,
        )
        normalized_word = self.turn_policy.normalize_word(word)
        rejection_details = details or {}
        action_number = await self.repository.get_next_action_number(game_session.id)
        action = await self.repository.create_word_reject_action(
            session_id=game_session.id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_number=action_number,
            normalized_word=normalized_word,
            reason=reason,
            details=rejection_details,
            now=now,
        )
        await self.repository.flush()
        score_delta = self.turn_policy.word_rejection_score_delta(reason)
        await self.repository.create_word_rejection_score(
            session_id=game_session.id,
            participant_id=participant.id,
            action_id=action.id,
            reason=reason,
            score_delta=score_delta,
            now=now,
        )
        event_sequence = await self.repository.get_next_event_sequence(game_session.id)
        event = await self.repository.create_word_rejected_event(
            session_id=game_session.id,
            phase=phase,
            participant=participant,
            action_id=action.id,
            event_sequence=event_sequence,
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
            now=now,
        )
        await self.repository.flush()
        record = WordRejectionRecord(
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
        await self.repository.commit()
        return MatchBroadcastEvent(
            game_session_public_id=record.game_session_public_id,
            message={
                "type": TURN_RESOLVED_MESSAGE_TYPE,
                "payload": {
                    "event_sequence": record.event_sequence,
                    "phase_id": record.phase_id,
                    "participant": {
                        "display_name": record.display_name,
                        "seat_number": record.seat_number,
                    },
                    "result": "rejected",
                    "word": record.word,
                    "normalized_word": record.normalized_word,
                    "reason": record.reason,
                    "details": record.details,
                    "score_delta": record.score_delta,
                    "created_at": record.created_at,
                    "server_time": record.created_at,
                },
            },
        )
