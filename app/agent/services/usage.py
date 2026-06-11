from typing import Protocol

from app.agent.repository.qdrant import WordRepository
from app.agent.utils.korean import normalize_word


class UsageService(Protocol):
    async def increment_answer_usage(self, word: str) -> None: ...


class QdrantUsageService:
    """AI 답변 사용 횟수 갱신을 저장소 구현과 분리합니다."""

    def __init__(self, repository: WordRepository) -> None:
        self._repository = repository

    async def increment_answer_usage(self, word: str) -> None:
        """실제로 반환된 단어 하나의 사용 횟수만 증가시킵니다."""
        await self._repository.increment_ai_used_count(normalize_word(word))
