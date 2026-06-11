from collections.abc import Sequence
from typing import Protocol

from qdrant_client import AsyncQdrantClient, models

from app.agent.schemas.word import WordCandidate
from app.agent.utils.hashing import point_id_for_word
from app.shared.core.observability import traced_method


class WordRepository(Protocol):
    async def find_candidates(
        self,
        query_filter: models.Filter,
        limit: int,
    ) -> list[WordCandidate]: ...

    async def upsert_words(
        self,
        payloads: Sequence[dict],
        *,
        overwrite_existing: bool,
        preserve_ai_used_count: bool,
    ) -> int: ...

    async def increment_ai_used_count(self, word_norm: str) -> None: ...


class QdrantWordRepository:
    """게임 단어 collection의 검색, 적재, 사용 횟수 갱신을 담당합니다."""

    def __init__(
        self,
        client: AsyncQdrantClient,
        collection_name: str,
    ) -> None:
        self._client = client
        self._collection_name = collection_name

    @traced_method(layer="repository")
    async def ensure_collection(self) -> None:
        """collection과 필수 payload index를 멱등하게 생성합니다."""
        if not await self._client.collection_exists(self._collection_name):
            await self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=1,
                    distance=models.Distance.COSINE,
                ),
            )
        indexes = {
            "word_norm": models.PayloadSchemaType.KEYWORD,
            "game_types": models.PayloadSchemaType.KEYWORD,
            "start_word": models.PayloadSchemaType.KEYWORD,
            "end_word": models.PayloadSchemaType.KEYWORD,
            "chosung": models.PayloadSchemaType.KEYWORD,
            "syllables": models.PayloadSchemaType.KEYWORD,
            "length": models.PayloadSchemaType.INTEGER,
            "ai_used_count": models.PayloadSchemaType.INTEGER,
            "is_valid": models.PayloadSchemaType.BOOL,
            "is_banned": models.PayloadSchemaType.BOOL,
        }
        for field_name, field_schema in indexes.items():
            await self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name=field_name,
                field_schema=field_schema,
                wait=True,
            )

    @traced_method(layer="repository")
    async def find_candidates(
        self,
        query_filter: models.Filter,
        limit: int,
    ) -> list[WordCandidate]:
        """payload filter에 맞는 단어 후보를 한 번의 scroll 요청으로 조회합니다."""
        records, _ = await self._client.scroll(
            collection_name=self._collection_name,
            scroll_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [
            WordCandidate.from_payload(record.payload or {}) for record in records if record.payload
        ]

    @traced_method(layer="repository")
    async def upsert_words(
        self,
        payloads: Sequence[dict],
        *,
        overwrite_existing: bool,
        preserve_ai_used_count: bool,
    ) -> int:
        """결정적 point ID로 단어를 적재하고 필요하면 기존 사용 횟수를 보존합니다."""
        if not payloads:
            return 0

        point_ids = [point_id_for_word(payload["word_norm"]) for payload in payloads]
        existing_records = await self._client.retrieve(
            collection_name=self._collection_name,
            ids=point_ids,
            with_payload=True,
            with_vectors=False,
        )
        existing_by_id = {str(record.id): record for record in existing_records}

        points: list[models.PointStruct] = []
        for point_id, original_payload in zip(point_ids, payloads, strict=True):
            existing = existing_by_id.get(point_id)
            if existing and not overwrite_existing:
                continue

            payload = dict(original_payload)
            if existing and preserve_ai_used_count:
                payload["ai_used_count"] = int((existing.payload or {}).get("ai_used_count", 0))
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=[1.0],
                    payload=payload,
                )
            )

        if points:
            await self._client.upsert(
                collection_name=self._collection_name,
                points=points,
                wait=True,
            )
        return len(points)

    @traced_method(layer="repository")
    async def increment_ai_used_count(self, word_norm: str) -> None:
        """AI가 반환한 단어의 사용 횟수를 read-modify-write 방식으로 증가시킵니다."""
        point_id = point_id_for_word(word_norm)
        records = await self._client.retrieve(
            collection_name=self._collection_name,
            ids=[point_id],
            with_payload=True,
            with_vectors=False,
        )
        if not records:
            return

        current_count = int((records[0].payload or {}).get("ai_used_count", 0))
        # 여러 Agent Pod가 동시에 갱신하면 일부 증가분이 유실될 수 있습니다.
        # UsageService는 향후 Redis INCR 구현으로 교체하기 위한 경계입니다.
        await self._client.set_payload(
            collection_name=self._collection_name,
            payload={"ai_used_count": current_count + 1},
            points=[point_id],
            wait=True,
        )
