from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from app.be.services.match_progress import MatchBroadcastEvent
from app.shared.clients.agent import (
    AgentAnswerClient,
    AgentAnswerCondition,
    AgentAnswerRequest,
    AgentClientError,
)
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException

AI_ANSWER_REJECTION_REASONS = {
    "word_already_used",
    "word_empty",
    "word_not_in_dictionary",
    "word_start_char_mismatch",
}


@dataclass(frozen=True)
class AiTurnContext:
    game_session_public_id: UUID
    phase_id: UUID
    participant_id: UUID
    game_type: Literal["word_chain", "chosung", "contains"]
    used_words: list[str]
    required_start_char: str | None


class MatchAiTurnRepositoryProtocol(Protocol):
    async def get_ai_turn_context(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
    ) -> AiTurnContext | None:
        """현재 phase가 AI 턴이면 Agent 요청에 필요한 context를 반환합니다."""


class MatchAiTurnProgressServiceProtocol(Protocol):
    async def submit_word(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        word: str,
        now: datetime,
    ) -> MatchBroadcastEvent:
        """AI가 낸 단어를 일반 참가자 제출과 같은 경로로 확정합니다."""

    async def reject_word(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        word: str,
        reason: str,
        details: dict[str, object] | None,
        now: datetime,
    ) -> MatchBroadcastEvent:
        """AI가 낸 단어의 규칙 위반을 일반 참가자 거절과 같은 경로로 확정합니다."""

    async def fail_ai_answer(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        participant_id: UUID,
        reason: str,
        details: dict[str, object] | None = None,
    ) -> MatchBroadcastEvent | None:
        """Agent가 제출 단어를 만들지 못한 실패만 AI 실패로 확정합니다."""

    async def timeout_turn_if_due(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        now: datetime,
    ) -> MatchBroadcastEvent | None:
        """AI 답변이 deadline 이후 도착한 경우 timeout 확정 경로로 보냅니다."""


class MatchAiTurnService:
    """AI 참가자의 현재 턴을 Agent answer API와 match progress로 연결합니다."""

    def __init__(
        self,
        repository: MatchAiTurnRepositoryProtocol,
        agent_answer_client: AgentAnswerClient,
        progress_service: MatchAiTurnProgressServiceProtocol,
    ) -> None:
        self.repository = repository
        self.agent_answer_client = agent_answer_client
        self.progress_service = progress_service

    async def play_ai_turn(
        self,
        *,
        game_session_public_id: UUID,
        phase_id: UUID,
        now: datetime,
    ) -> MatchBroadcastEvent | None:
        """현재 phase가 AI 턴이면 Agent 답변을 받아 제출 또는 실패 event로 확정합니다."""
        context = await self.repository.get_ai_turn_context(
            game_session_public_id=game_session_public_id,
            phase_id=phase_id,
        )
        if context is None:
            return None

        try:
            result = await self.agent_answer_client.get_answer(
                AgentAnswerRequest(
                    request_id=str(context.phase_id),
                    room_id=str(context.game_session_public_id),
                    game_type=context.game_type,
                    used_words=context.used_words,
                    last_char=context.required_start_char,
                    condition=AgentAnswerCondition(last_char=context.required_start_char),
                )
            )
        except AgentClientError as exc:
            reason = "agent_timeout" if "timed out" in str(exc) else "agent_error"
            return await self.progress_service.fail_ai_answer(
                game_session_public_id=context.game_session_public_id,
                phase_id=context.phase_id,
                participant_id=context.participant_id,
                reason=reason,
                details={"error": str(exc), "status_code": exc.status_code},
            )

        if result.status == "no_candidate" and result.answer:
            return await self.progress_service.reject_word(
                game_session_public_id=context.game_session_public_id,
                phase_id=context.phase_id,
                participant_id=context.participant_id,
                word=result.answer,
                reason=result.reason or "no_candidate",
                details=_ai_answer_rejection_details(
                    reason=result.reason or "no_candidate",
                    details=None,
                ),
                now=now,
            )

        if result.status == "no_candidate" or not result.answer:
            return await self.progress_service.fail_ai_answer(
                game_session_public_id=context.game_session_public_id,
                phase_id=context.phase_id,
                participant_id=context.participant_id,
                reason="no_candidate",
                details=_ai_no_candidate_details(result.answer, result.reason),
            )

        try:
            return await self.progress_service.submit_word(
                game_session_public_id=context.game_session_public_id,
                phase_id=context.phase_id,
                participant_id=context.participant_id,
                word=result.answer,
                now=now,
            )
        except AppException as exc:
            if _is_stale_ai_turn_exception(exc):
                return None
            if _is_ai_turn_deadline_exception(exc):
                return await self.progress_service.timeout_turn_if_due(
                    game_session_public_id=context.game_session_public_id,
                    phase_id=context.phase_id,
                    now=now,
                )
            rejection_reason = _ai_answer_rejection_reason(exc)
            if rejection_reason is not None:
                return await self.progress_service.reject_word(
                    game_session_public_id=context.game_session_public_id,
                    phase_id=context.phase_id,
                    participant_id=context.participant_id,
                    word=result.answer,
                    reason=rejection_reason,
                    details=_ai_answer_rejection_details(
                        reason=rejection_reason,
                        details=exc.details,
                    ),
                    now=now,
                )
            raise


def _is_stale_ai_turn_exception(exc: AppException) -> bool:
    """AI Agent 응답 대기 중 이미 종료된 phase에서 발생한 progress 예외인지 확인합니다."""
    return (
        exc.code == ErrorCode.VALIDATION_ERROR
        and isinstance(exc.details, dict)
        and exc.details.get("reason") == "phase_already_finished"
    )


def _is_ai_turn_deadline_exception(exc: AppException) -> bool:
    """AI 답변이 도착했지만 서버 deadline이 지난 경우 timeout 확정 경로로 보낼지 판단합니다."""
    return (
        exc.code == ErrorCode.VALIDATION_ERROR
        and isinstance(exc.details, dict)
        and exc.details.get("reason") == "turn_deadline_exceeded"
    )


def _ai_answer_rejection_reason(exc: AppException) -> str | None:
    """AI가 낸 단어가 Backend 단어 규칙을 통과하지 못한 사유를 반환합니다."""
    if exc.code != ErrorCode.VALIDATION_ERROR or not isinstance(exc.details, dict):
        return None
    reason = exc.details.get("reason")
    if isinstance(reason, str) and reason in AI_ANSWER_REJECTION_REASONS:
        return reason
    return None


def _ai_answer_rejection_details(
    *,
    reason: str,
    details: object,
) -> dict[str, object]:
    """AI 제출 단어의 검증 실패를 일반 단어 거절 details로 변환합니다."""
    failure_details: dict[str, object] = {
        "validation_reason": reason,
    }
    if isinstance(details, dict):
        failure_details.update({key: value for key, value in details.items() if key != "reason"})
    return failure_details


def _ai_no_candidate_details(answer: str | None, reason: str | None) -> dict[str, object]:
    """Agent가 실패 상태와 함께 후보 단어를 돌려준 경우 UI에 공개할 수 있게 보존합니다."""
    failure_details: dict[str, object] = {"agent_reason": reason}
    if answer:
        failure_details["agent_answer"] = answer
    return failure_details
