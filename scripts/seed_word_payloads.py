#!/usr/bin/env python3
import argparse
import asyncio
import json
import re
from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError
from qdrant_client import AsyncQdrantClient

from app.agent.repository.qdrant import QdrantWordRepository
from app.agent.schemas.word import WordCandidate
from app.agent.utils.korean import build_word_payload


EXPECTED_PAYLOAD_KEYS = {
    "word",
    "start_word",
    "end_word",
    "chosung",
    "syllables",
    "length",
    "used_count",
}


def iter_payload_batches(file: Path, batch_size: int) -> Iterator[list[dict]]:
    """JSONL을 한 줄씩 검증하고 지정한 크기의 Qdrant payload batch로 반환합니다."""
    batch: list[dict] = []
    seen_words: set[str] = set()
    with file.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at line {line_number}: {exc}") from exc

            if not isinstance(payload, dict) or set(payload) != EXPECTED_PAYLOAD_KEYS:
                raise ValueError(
                    f"invalid payload keys at line {line_number}: "
                    f"{sorted(payload) if isinstance(payload, dict) else type(payload).__name__}"
                )
            try:
                candidate = WordCandidate.model_validate(payload)
            except ValidationError as exc:
                raise ValueError(f"invalid payload at line {line_number}: {exc}") from exc

            if not re.fullmatch(r"[가-힣]{2,}", candidate.word):
                raise ValueError(
                    f"word must contain at least two complete Hangul syllables "
                    f"at line {line_number}: {candidate.word}"
                )
            expected = build_word_payload(candidate.word)
            if payload != expected:
                raise ValueError(
                    f"derived fields do not match word at line {line_number}: {candidate.word}"
                )
            if candidate.word in seen_words:
                raise ValueError(f"duplicate word at line {line_number}: {candidate.word}")
            seen_words.add(candidate.word)
            batch.append(payload)

            if len(batch) == batch_size:
                yield batch
                batch = []

    if batch:
        yield batch


async def main() -> None:
    """검증 완료 JSONL payload를 batch 단위로 Qdrant에 적재합니다."""
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--url", default="http://qdrant:6333")
    parser.add_argument("--collection", default="game_words")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")

    client = AsyncQdrantClient(url=args.url, check_compatibility=False)
    total = 0
    upserted = 0
    try:
        repository = QdrantWordRepository(client, args.collection)
        await repository.ensure_collection()
        for batch in iter_payload_batches(args.file, args.batch_size):
            total += len(batch)
            upserted += await repository.upsert_words(
                batch,
                overwrite_existing=args.overwrite,
                preserve_used_count=True,
            )
            print(f"processed={total} upserted={upserted}", flush=True)
    finally:
        await client.close()

    print(f"completed: upserted {upserted} of {total} words")


if __name__ == "__main__":
    asyncio.run(main())
