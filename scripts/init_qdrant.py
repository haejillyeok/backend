#!/usr/bin/env python3
import argparse
import asyncio

from qdrant_client import AsyncQdrantClient

from app.agent.repository.qdrant import QdrantWordRepository


async def main() -> None:
    """Qdrant collection과 payload index를 초기화합니다."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://qdrant:6333")
    parser.add_argument("--collection", default="game_words")
    args = parser.parse_args()

    client = AsyncQdrantClient(url=args.url, check_compatibility=False)
    try:
        repository = QdrantWordRepository(client, args.collection)
        await repository.ensure_collection()
        print(f"initialized collection: {args.collection}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
