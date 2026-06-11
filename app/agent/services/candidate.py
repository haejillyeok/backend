import random
from dataclasses import dataclass

from app.agent.repository.qdrant import WordRepository
from app.agent.schemas.request.answer import AgentAnswerRequest
from app.agent.schemas.word import WordCandidate
from app.agent.services.game_handlers.base import GameHandler
from app.agent.utils.korean import normalize_word


@dataclass(frozen=True)
class CandidateSelection:
    selected: WordCandidate
    ranked: list[WordCandidate]


class CandidateService:
    """Qdrant 후보를 한 번 조회하고 규칙 기반 점수로 답변 후보를 선택합니다."""

    def __init__(
        self,
        repository: WordRepository,
        *,
        candidate_limit: int = 100,
        random_source: random.Random | None = None,
    ) -> None:
        self._repository = repository
        self._candidate_limit = candidate_limit
        self._random = random_source or random.SystemRandom()

    async def select(
        self,
        request: AgentAnswerRequest,
        handler: GameHandler,
    ) -> CandidateSelection | None:
        """used_words를 제외하고 낮은 사용 횟수와 짧은 길이를 우선 선택합니다."""
        used_words = {normalize_word(word) for word in request.used_words}
        query_filter = handler.build_filter(request, used_words)
        candidates = await self._repository.find_candidates(
            query_filter,
            self._candidate_limit,
        )
        candidates = [
            candidate for candidate in candidates if candidate.word_norm not in used_words
        ]
        if not candidates:
            return None

        scored = [(self._score(candidate), candidate) for candidate in candidates]
        best_score = max(score for score, _ in scored)
        best = [candidate for score, candidate in scored if score == best_score]
        selected = self._random.choice(best)
        ranked = [
            candidate
            for _, candidate in sorted(
                scored,
                key=lambda item: (
                    -item[0],
                    item[1].ai_used_count,
                    item[1].length,
                    item[1].word_norm,
                ),
            )
        ]
        return CandidateSelection(selected=selected, ranked=ranked)

    @staticmethod
    def _score(candidate: WordCandidate) -> int:
        usage_penalty = candidate.ai_used_count * 2
        length_penalty = max(candidate.length - 2, 0)
        return 100 - usage_penalty - length_penalty
