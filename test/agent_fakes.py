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
        preserve_used_count: bool,
    ) -> int:
        self.upsert_calls.append(
            {
                "payloads": list(payloads),
                "overwrite_existing": overwrite_existing,
                "preserve_used_count": preserve_used_count,
            }
        )
        return len(payloads)

    async def increment_used_count(self, word: str) -> None:
        self.incremented.append(word)


def candidate(
    word: str,
    *,
    used_count: int = 0,
) -> WordCandidate:
    return WordCandidate(
        word=word,
        start_word=word[0],
        end_word=word[-1],
        chosung="",
        syllables=list(word),
        length=len(word),
        used_count=used_count,
    )
