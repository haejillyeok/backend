from datetime import datetime
from uuid import UUID

from app.be.services.match_ai.protocols import (
    MatchAiTurnProgressServiceProtocol,
    MatchAiTurnRepositoryProtocol,
)
from app.be.services.match_ai.rejection_helpers import (
    ai_answer_rejection_details,
    ai_answer_rejection_reason,
    ai_no_candidate_details,
    is_ai_turn_deadline_exception,
    is_stale_ai_turn_exception,
)
from app.be.services.match_progress import MatchBroadcastEvent
from app.be.services.repository_scope import RepositoryContextFactory, RepositoryScopedService
from app.shared.clients.agent import (
    AgentAnswerClient,
    AgentAnswerCondition,
    AgentAnswerRequest,
    AgentClientError,
)
from app.shared.core.exceptions import AppException


class MatchAiTurnService(RepositoryScopedService[MatchAiTurnRepositoryProtocol]):
    """AI 참가자의 현재 턴을 Agent answer API와 match progress로 연결합니다."""

    def __init__(
        self,
        repository: MatchAiTurnRepositoryProtocol | None = None,
        agent_answer_client: AgentAnswerClient | None = None,
        progress_service: MatchAiTurnProgressServiceProtocol | None = None,
        *,
        repository_context_factory: RepositoryContextFactory[MatchAiTurnRepositoryProtocol]
        | None = None,
    ) -> None:
        if agent_answer_client is None or progress_service is None:
            raise ValueError("agent_answer_client and progress_service are required")
        super().__init__(
            repository=repository,
            repository_context_factory=repository_context_factory,
        )
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
        async with self.repository_scope():
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
                details=ai_answer_rejection_details(
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
                details=ai_no_candidate_details(result.answer, result.reason),
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
            if is_stale_ai_turn_exception(exc):
                return None
            if is_ai_turn_deadline_exception(exc):
                return await self.progress_service.timeout_turn_if_due(
                    game_session_public_id=context.game_session_public_id,
                    phase_id=context.phase_id,
                    now=now,
                )
            rejection_reason = ai_answer_rejection_reason(exc)
            if rejection_reason is not None:
                return await self.progress_service.reject_word(
                    game_session_public_id=context.game_session_public_id,
                    phase_id=context.phase_id,
                    participant_id=context.participant_id,
                    word=result.answer,
                    reason=rejection_reason,
                    details=ai_answer_rejection_details(
                        reason=rejection_reason,
                        details=exc.details,
                    ),
                    now=now,
                )
            raise
