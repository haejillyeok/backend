from types import SimpleNamespace

from app.agent.repository.qdrant import QdrantWordRepository
from app.agent.services.word import WordService


class FakeQdrantClient:
    def __init__(self) -> None:
        self.points: dict[str, SimpleNamespace] = {}

    async def retrieve(self, collection_name, ids, **kwargs):
        return [self.points[point_id] for point_id in ids if point_id in self.points]

    async def upsert(self, collection_name, points, **kwargs):
        for point in points:
            self.points[str(point.id)] = SimpleNamespace(
                id=point.id,
                payload=point.payload,
            )


async def test_restacking_same_word_does_not_create_duplicate_point() -> None:
    client = FakeQdrantClient()
    repository = QdrantWordRepository(client, "game_words")
    payload = WordService().prepare_payloads(["사과"])

    first_count = await repository.upsert_words(
        payload,
        overwrite_existing=False,
        preserve_used_count=True,
    )
    second_count = await repository.upsert_words(
        payload,
        overwrite_existing=False,
        preserve_used_count=True,
    )

    assert first_count == 1
    assert second_count == 0
    assert len(client.points) == 1


async def test_overwrite_preserves_existing_used_count() -> None:
    client = FakeQdrantClient()
    repository = QdrantWordRepository(client, "game_words")
    payload = WordService().prepare_payloads(["사과"])
    await repository.upsert_words(
        payload,
        overwrite_existing=False,
        preserve_used_count=True,
    )
    next(iter(client.points.values())).payload["used_count"] = 120

    await repository.upsert_words(
        payload,
        overwrite_existing=True,
        preserve_used_count=True,
    )

    assert next(iter(client.points.values())).payload["used_count"] == 120


async def test_overwrite_migrates_legacy_ai_used_count() -> None:
    client = FakeQdrantClient()
    repository = QdrantWordRepository(client, "game_words")
    payload = WordService().prepare_payloads(["사과"])
    await repository.upsert_words(
        payload,
        overwrite_existing=False,
        preserve_used_count=True,
    )
    existing_payload = next(iter(client.points.values())).payload
    existing_payload.pop("used_count")
    existing_payload["ai_used_count"] = 7

    await repository.upsert_words(
        payload,
        overwrite_existing=True,
        preserve_used_count=True,
    )

    migrated_payload = next(iter(client.points.values())).payload
    assert migrated_payload["used_count"] == 7
    assert "ai_used_count" not in migrated_payload
