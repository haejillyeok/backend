import random
from dataclasses import dataclass

from app.agent.repository.qdrant import WordRepository
from app.agent.schemas.request.answer import AgentAnswerRequest
from app.agent.schemas.word import WordCandidate
from app.agent.services.game_handlers.base import GameHandler
from app.agent.utils.korean import normalize_word


@dataclass(frozen=True)
class CandidateSelection:
    condition: str
    selected: WordCandidate | None
    shortlist: list[WordCandidate]


class CandidateService:
    """Qdrant 후보를 한 번 조회하고 무작위 후보군에서 답변을 선택합니다."""

    def __init__(
        self,
        repository: WordRepository,
        *,
        candidate_limit: int = 100,
        shortlist_size: int = 10,
        random_source: random.Random | None = None,
    ) -> None:
        self._repository = repository
        self._candidate_limit = candidate_limit
        self._shortlist_size = shortlist_size
        self._random = random_source or random.SystemRandom()

    async def select(
        self,
        request: AgentAnswerRequest,
        handler: GameHandler,
    ) -> CandidateSelection:
        """used_words를 제외한 후보 중 최대 10개를 무작위 추출해 하나를 선택합니다."""
        used_words = {normalize_word(word) for word in request.used_words}
        condition = handler.get_condition(request)
        query_filter = handler.build_filter(
            request,
            used_words,
            condition=condition,
        )
        candidates = await self._repository.find_candidates(
            query_filter,
            self._candidate_limit,
        )
        candidates = [
            candidate for candidate in candidates if candidate.word_norm not in used_words
        ]
        if not candidates:
            return CandidateSelection(
                condition=condition,
                selected=None,
                shortlist=[],
            )

        shortlist = self._random.sample(
            candidates,
            k=min(self._shortlist_size, len(candidates)),
        )
        return CandidateSelection(
            condition=condition,
            selected=self._random.choice(shortlist),
            shortlist=shortlist,
        )
