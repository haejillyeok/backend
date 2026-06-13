from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from app.be.services.match_progress import MatchBroadcastEvent, MatchProgressService
from app.shared.clients.agent import (
    AgentAnswerClient,
    AgentAnswerCondition,
    AgentAnswerRequest,
    AgentClientError,
)
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException


@dataclass(frozen=True)
class AiTurnContext:
    game_session_public_id: UUID
    phase_id: UUID
    participant_id: UUID
    game_type: Literal["shiritori", "chosung", "contains"]
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


class MatchAiTurnService:
    """AI 참가자의 현재 턴을 Agent answer API와 match progress로 연결합니다."""

    def __init__(
        self,
        repository: MatchAiTurnRepositoryProtocol,
        agent_answer_client: AgentAnswerClient,
        progress_service: MatchProgressService,
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

        if result.status == "no_candidate" or not result.answer:
            return await self.progress_service.fail_ai_answer(
                game_session_public_id=context.game_session_public_id,
                phase_id=context.phase_id,
                participant_id=context.participant_id,
                reason="no_candidate",
                details={"agent_reason": result.reason},
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
