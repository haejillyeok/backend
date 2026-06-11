from collections.abc import Sequence

from qdrant_client import models

from app.agent.schemas.word import WordCandidate


class FakeWordRepository:
    def __init__(self, candidates: list[WordCandidate] | None = None) -> None:
        self.candidates = candidates or []
        self.find_calls = 0
        self.incremented: list[str] = []
        self.upsert_calls: list[dict] = []

    async def find_candidates(
        self,
        query_filter: models.Filter,
        limit: int,
    ) -> list[WordCandidate]:
        self.find_calls += 1
        return self.candidates[:limit]

    async def upsert_words(
        self,
        payloads: Sequence[dict],
        *,
        overwrite_existing: bool,
        preserve_ai_used_count: bool,
    ) -> int:
        self.upsert_calls.append(
            {
                "payloads": list(payloads),
                "overwrite_existing": overwrite_existing,
                "preserve_ai_used_count": preserve_ai_used_count,
            }
        )
        return len(payloads)

    async def increment_ai_used_count(self, word_norm: str) -> None:
        self.incremented.append(word_norm)


def candidate(
    word: str,
    *,
    used_count: int = 0,
) -> WordCandidate:
    return WordCandidate(
        word=word,
        word_norm=word,
        game_types=["shiritori", "chosung", "contains"],
        start_word=word[0],
        end_word=word[-1],
        chosung="",
        syllables=list(word),
        length=len(word),
        ai_used_count=used_count,
    )
