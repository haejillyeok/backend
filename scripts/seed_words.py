#!/usr/bin/env python3
import argparse
import asyncio
from pathlib import Path

from qdrant_client import AsyncQdrantClient

from app.agent.repository.qdrant import QdrantWordRepository
from app.agent.services.word import WordService


async def main() -> None:
    """텍스트 파일의 단어를 정규화해 Qdrant에 적재합니다."""
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--url", default="http://qdrant:6333")
    parser.add_argument("--collection", default="game_words")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    words = [
        line.strip()
        for line in args.file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    payloads = WordService().prepare_payloads(words)

    client = AsyncQdrantClient(url=args.url, check_compatibility=False)
    try:
        repository = QdrantWordRepository(client, args.collection)
        await repository.ensure_collection()
        count = await repository.upsert_words(
            payloads,
            overwrite_existing=args.overwrite,
            preserve_used_count=True,
        )
        print(f"upserted {count} of {len(payloads)} words")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
