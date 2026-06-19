from datetime import datetime
from typing import Any
from uuid import UUID

from app.be.services.match_progress.constants import TURN_RESOLVED_MESSAGE_TYPE
from app.be.services.match_progress.records import (
    AiAnswerFailureRecord,
    MatchBroadcastEvent,
    TurnTimeoutRecord,
)
from app.be.services.match_progress.turn_resolution_payloads import (
    public_ai_failure_details,
    public_ai_failure_reason,
    serialize_next_turn,
    submitted_word_from_ai_failure_details,
)
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException
from app.shared.core.timezone import kst_now


class MatchProgressAiFailureUseCaseMixin:
    async def fail_ai_answer(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        reason: str,
        details: dict[str, Any] | None = None,
        response_ms: int | None = None,
    ) -> MatchBroadcastEvent | None:
        """Agent 미응답/오류를 턴 실패로 확정하고 commit 이후 보낼 socket event를 반환합니다.

        이 service는 WebSocket manager를 호출하지 않습니다. 호출자는 반환된 event를 transaction 밖에서
        `match_connection_manager.broadcast_session`으로 전송해야 합니다.
        """
        async with self.repository_scope():
            return await self._fail_ai_answer(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                participant_id=participant_id,
                reason=reason,
                details=details,
                response_ms=response_ms,
            )

    async def _fail_ai_answer(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        reason: str,
        details: dict[str, Any] | None = None,
        response_ms: int | None = None,
    ) -> MatchBroadcastEvent | None:
        """AI 응답 실패 transaction 안에서 실패 action과 event를 확정합니다."""
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
        if phase.finished_at is not None:
            return None
        participant = await self.repository.get_participant(
            session_id=game_session.id,
            participant_id=participant_id,
        )
        if participant is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "participant_not_found"},
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

        now = kst_now()
        failure_details = details or {}
        action_number = await self.repository.get_next_action_number(game_session.id)
        action = await self.repository.create_ai_answer_failed_action(
            session_id=game_session.id,
            phase_id=phase.id,
            participant_id=participant.id,
            action_number=action_number,
            reason=reason,
            details=failure_details,
            response_ms=response_ms,
            now=now,
        )
        await self.repository.flush()
        event_sequence = await self.repository.get_next_event_sequence(game_session.id)
        event = await self.repository.create_ai_answer_failed_event(
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
                "reason": reason,
                "details": failure_details,
                "result_status": "failed",
            },
            now=now,
        )
        await self.repository.flush()
        record = AiAnswerFailureRecord(
            game_session_public_id=game_session.public_id,
            phase_id=phase.id,
            participant_id=participant.id,
            display_name=participant.display_name,
            seat_number=participant.seat_number,
            action_id=action.id,
            event_id=event.id,
            event_sequence=event.sequence,
            reason=reason,
            details=failure_details,
            created_at=event.created_at,
        )
        await self.repository.commit()
        submitted_word = submitted_word_from_ai_failure_details(record.details)
        public_reason = public_ai_failure_reason(record.reason)
        public_details = public_ai_failure_details(record.details)
        payload: dict[str, Any] = {
            "event_sequence": record.event_sequence,
            "phase_id": record.phase_id,
            "participant": {
                "display_name": record.display_name,
                "seat_number": record.seat_number,
            },
            "result": "failed",
            "word": submitted_word,
            "normalized_word": submitted_word,
            "reason": public_reason,
            "details": public_details,
            "score_delta": 0,
            "created_at": record.created_at,
            "server_time": record.created_at or kst_now(),
        }
        if record.next_turn is not None:
            payload["next_turn"] = serialize_next_turn(record.next_turn)
        if record.next_status is not None:
            payload["next_status"] = record.next_status
        if record.voting_deadline_at is not None:
            payload["voting_deadline_at"] = record.voting_deadline_at
        return MatchBroadcastEvent(
            game_session_public_id=record.game_session_public_id,
            message={
                "type": TURN_RESOLVED_MESSAGE_TYPE,
                "payload": payload,
            },
        )

    async def timeout_turn_if_due(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        now: datetime,
    ) -> MatchBroadcastEvent | None:
        """서버 deadline 기준으로 현재 턴 timeout을 확정하고 broadcast event를 반환합니다."""
        async with self.repository_scope():
            return await self._timeout_turn_if_due(
                game_session_public_id=game_session_public_id,
                phase_id=phase_id,
                now=now,
            )

    async def _timeout_turn_if_due(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        now: datetime,
    ) -> MatchBroadcastEvent | None:
        """턴 timeout transaction 안에서 phase 종료와 다음 상태 전환을 확정합니다."""
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
        if phase.finished_at is not None or phase.deadline_at is None or now < phase.deadline_at:
            return None
        if phase.actor_participant_id is None:
            raise AppException(
                code=ErrorCode.VALIDATION_ERROR,
                details={"reason": "phase_actor_missing"},
            )
        participant = await self.repository.get_participant(
            session_id=game_session.id,
            participant_id=phase.actor_participant_id,
        )
        if participant is None:
            raise AppException(
                code=ErrorCode.GAME_SESSION_ENTRY_FORBIDDEN,
                details={"reason": "participant_not_found"},
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
        turn, _ = turn_actor
        participants = await self.repository.list_participants(game_session.id)
        action_number = await self.repository.get_next_action_number(game_session.id)
        action = await self.repository.create_turn_timeout_action(
            session_id=game_session.id,
            phase=phase,
            participant=participant,
            action_number=action_number,
            now=now,
        )
        await self.repository.flush()
        await self.repository.mark_phase_timeout(phase=phase, now=now)

        max_rounds = int(game_session.rule_config.get("max_rounds", 8))
        next_participant = self.turn_policy.choose_round_start_participant(participants)
        round_start_char = None
        if turn.round_number < max_rounds:
            round_start_char = await self.repository.get_random_round_start_char(
                game_session.game_type
            )
        transition = self.round_transition_policy.build_round_end_transition(
            game_session=game_session,
            phase=phase,
            turn=turn,
            next_participant=next_participant,
            round_start_char=round_start_char,
            now=now,
        )
        await self.repository.create_session_phase(transition.phase)
        await self.repository.flush()
        if transition.turn is None:
            await self.repository.mark_game_session_voting(
                game_session=game_session,
                current_phase_id=transition.phase.id,
            )
        else:
            await self.repository.mark_game_session_playing(
                game_session=game_session,
                current_phase_id=transition.phase.id,
            )
            await self.repository.create_word_turn(transition.turn)

        event_sequence = await self.repository.get_next_event_sequence(game_session.id)
        event = await self.repository.create_turn_timeout_event(
            session_id=game_session.id,
            phase=phase,
            participant=participant,
            action=action,
            event_sequence=event_sequence,
            round_number=turn.round_number,
            payload=transition.payload,
            now=now,
        )
        await self.repository.flush()
        record = TurnTimeoutRecord(
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
            next_turn=transition.next_turn,
            next_status=transition.next_status,
            voting_deadline_at=transition.voting_deadline_at,
        )
        payload: dict[str, Any] = {
            "event_sequence": record.event_sequence,
            "phase_id": record.phase_id,
            "participant": {
                "display_name": record.display_name,
                "seat_number": record.seat_number,
            },
            "result": "timeout",
            "word": None,
            "normalized_word": None,
            "reason": "deadline_exceeded",
            "details": {},
            "score_delta": 0,
            "deadline_at": record.deadline_at,
            "created_at": record.created_at,
            "server_time": record.created_at,
        }
        if record.round_number is not None:
            payload["round_number"] = record.round_number
        if record.next_turn is not None:
            payload["next_turn"] = serialize_next_turn(record.next_turn)
        if record.next_status is not None:
            payload["next_status"] = record.next_status
        if record.voting_deadline_at is not None:
            payload["voting_deadline_at"] = record.voting_deadline_at
        await self.repository.commit()
        return MatchBroadcastEvent(
            game_session_public_id=record.game_session_public_id,
            message={
                "type": TURN_RESOLVED_MESSAGE_TYPE,
                "payload": payload,
            },
        )
