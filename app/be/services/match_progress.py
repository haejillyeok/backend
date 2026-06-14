from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


AI_ANSWER_FAILED_EVENT_TYPE = "ai_answer_failed"
TURN_TIMEOUT_EVENT_TYPE = "turn_timeout"
WORD_ACCEPTED_EVENT_TYPE = "word.accepted"
WORD_REJECTED_EVENT_TYPE = "word.rejected"
WORD_SUBMIT_ACTION_TYPE = "word_submit"
WORD_REJECT_ACTION_TYPE = "word_reject"
TURN_RESOLVED_MESSAGE_TYPE = "match.turn.resolved"


@dataclass(frozen=True)
class AiAnswerFailureRecord:
    game_session_public_id: UUID
    phase_id: UUID
    participant_id: UUID
    display_name: str
    seat_number: int
    action_id: UUID
    event_id: UUID
    event_sequence: int
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    next_turn: MatchTurnEventPayload | None = None
    next_status: str | None = None
    voting_deadline_at: datetime | None = None


@dataclass(frozen=True)
class TurnTimeoutRecord:
    game_session_public_id: UUID
    phase_id: UUID
    participant_id: UUID
    display_name: str
    seat_number: int
    action_id: UUID
    event_id: UUID
    event_sequence: int
    deadline_at: datetime
    created_at: datetime
    round_number: int | None = None
    next_turn: MatchTurnEventPayload | None = None
    next_status: str | None = None
    voting_deadline_at: datetime | None = None


@dataclass(frozen=True)
class MatchTurnEventPayload:
    phase_id: UUID
    round_number: int
    turn_number: int
    actor_seat_number: int
    deadline_at: datetime
    required_start_char: str | None


@dataclass(frozen=True)
class WordSubmissionRecord:
    game_session_public_id: UUID
    phase_id: UUID
    participant_id: UUID
    display_name: str
    seat_number: int
    word: str
    normalized_word: str
    action_id: UUID
    submission_id: UUID
    event_id: UUID
    event_sequence: int
    score_delta: int
    next_turn: MatchTurnEventPayload
    created_at: datetime


@dataclass(frozen=True)
class WordRejectionRecord:
    game_session_public_id: UUID
    phase_id: UUID
    participant_id: UUID
    display_name: str
    seat_number: int
    word: str
    normalized_word: str
    action_id: UUID
    event_id: UUID
    event_sequence: int
    reason: str
    details: dict[str, Any]
    score_delta: int
    created_at: datetime


@dataclass(frozen=True)
class MatchBroadcastEvent:
    game_session_public_id: UUID
    message: dict[str, Any]


class MatchProgressRepositoryProtocol(Protocol):
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
        """AI 턴 응답 실패를 action/event로 저장하고 브로드캐스트에 필요한 record를 반환합니다."""

    async def record_turn_timeout(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        now: datetime,
    ) -> TurnTimeoutRecord | None:
        """deadline이 지난 턴을 timeout action/event로 저장하고 record를 반환합니다."""

    async def record_word_submission(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        word: str,
        now: datetime,
    ) -> WordSubmissionRecord:
        """현재 턴의 단어 제출을 저장하고 다음 턴 record를 반환합니다."""

    async def record_word_rejection(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        word: str,
        reason: str,
        details: dict[str, Any] | None,
        now: datetime,
    ) -> WordRejectionRecord:
        """현재 턴 단어 제출 거절을 저장하고 record를 반환합니다."""

    async def commit(self) -> None:
        """진행 상태 변경 transaction을 확정합니다."""


class MatchProgressService:
    """게임 진행 event를 확정하고 WebSocket 브로드캐스트용 envelope로 변환합니다."""

    def __init__(self, repository: MatchProgressRepositoryProtocol) -> None:
        self.repository = repository

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
        record = await self.repository.record_ai_answer_failure(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
            participant_id=participant_id,
            reason=reason,
            details=details,
            response_ms=response_ms,
        )
        if record is None:
            return None
        await self.repository.commit()
        payload: dict[str, Any] = {
            "event_sequence": record.event_sequence,
            "phase_id": record.phase_id,
            "participant": {
                "display_name": record.display_name,
                "seat_number": record.seat_number,
            },
            "result": "failed",
            "word": None,
            "normalized_word": None,
            "reason": record.reason,
            "details": record.details,
            "score_delta": 0,
            "created_at": record.created_at,
        }
        if record.next_turn is not None:
            payload["next_turn"] = _serialize_next_turn(record.next_turn)
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
        record = await self.repository.record_turn_timeout(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
            now=now,
        )
        if record is None:
            return None
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
        }
        if record.round_number is not None:
            payload["round_number"] = record.round_number
        if record.next_turn is not None:
            payload["next_turn"] = _serialize_next_turn(record.next_turn)
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
        record = await self.repository.record_word_submission(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
            participant_id=participant_id,
            word=word,
            now=now,
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
                    "next_turn": _serialize_next_turn(record.next_turn),
                    "created_at": record.created_at,
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
        record = await self.repository.record_word_rejection(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
            participant_id=participant_id,
            word=word,
            reason=reason,
            details=details,
            now=now,
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
                },
            },
        )


def _serialize_next_turn(next_turn: MatchTurnEventPayload) -> dict[str, Any]:
    """다음 턴 record를 `match.turn.resolved` payload의 공통 객체로 변환합니다."""
    return {
        "phase_id": next_turn.phase_id,
        "round_number": next_turn.round_number,
        "turn_number": next_turn.turn_number,
        "actor_seat_number": next_turn.actor_seat_number,
        "deadline_at": next_turn.deadline_at,
        "required_start_char": next_turn.required_start_char,
    }
