from dataclasses import dataclass

from app.agent.schemas.request.answer import AgentAnswerRequest, GameType
from app.agent.schemas.response.answer import AgentAnswerResponse
from app.agent.services.candidate import CandidateService
from app.agent.services.game_handlers.base import GameHandler
from app.agent.services.idempotency import IdempotencyStore
from app.agent.services.usage import UsageService
from app.agent.services.vllm import VllmService
from app.agent.utils.hashing import stable_hash
from app.agent.utils.korean import normalize_word


@dataclass(frozen=True)
class AgentExecution:
    response: AgentAnswerResponse
    usage_word: str | None


class AgentService:
    """게임 handler, 후보 선택, 멱등성, 사용 횟수 처리를 조정합니다."""

    def __init__(
        self,
        candidate_service: CandidateService,
        handlers: dict[GameType, GameHandler],
        idempotency_store: IdempotencyStore,
        usage_service: UsageService,
        vllm_service: VllmService,
    ) -> None:
        self._candidate_service = candidate_service
        self._handlers = handlers
        self._idempotency_store = idempotency_store
        self._usage_service = usage_service
        self._vllm_service = vllm_service

    async def answer(self, request: AgentAnswerRequest) -> AgentExecution:
        """동일 요청은 한 번만 조회하며 검증된 후보가 없으면 즉시 실패 응답을 반환합니다."""
        key = self._idempotency_key(request)

        async def create_response() -> AgentAnswerResponse:
            handler = self._handlers[request.game_type]
            selection = await self._candidate_service.select(request, handler)
            if selection is None:
                return AgentAnswerResponse(
                    request_id=request.request_id,
                    room_id=request.room_id,
                    game_type=request.game_type,
                    answer=None,
                    status="no_candidate",
                    reason="no_available_word",
                )

            chosen = await self._vllm_service.refine_choice(
                request.game_type,
                selection.ranked,
                selection.selected,
            )
            used_words = {normalize_word(word) for word in request.used_words}
            if chosen.word_norm in used_words:
                return AgentAnswerResponse(
                    request_id=request.request_id,
                    room_id=request.room_id,
                    game_type=request.game_type,
                    answer=None,
                    status="no_candidate",
                    reason="no_available_word",
                )
            return AgentAnswerResponse(
                request_id=request.request_id,
                room_id=request.room_id,
                game_type=request.game_type,
                answer=chosen.word,
                status="ok",
            )

        response, created = await self._idempotency_store.get_or_create(
            key,
            create_response,
        )
        usage_word = response.answer if created and response.answer else None
        return AgentExecution(response=response, usage_word=usage_word)

    async def record_usage(self, word: str) -> None:
        """실제로 반환된 답변 단어의 AI 사용 횟수를 증가시킵니다."""
        await self._usage_service.increment_answer_usage(word)

    @staticmethod
    def _idempotency_key(request: AgentAnswerRequest) -> str:
        if request.request_id:
            return f"answer:{request.request_id}"
        condition = request.condition.model_dump() if request.condition else {}
        return "answer:" + stable_hash(
            {
                "room_id": request.room_id,
                "game_type": request.game_type.value,
                "last_char": normalize_word(request.last_char or ""),
                "condition": condition,
                "used_words": sorted(normalize_word(word) for word in request.used_words),
            }
        )
