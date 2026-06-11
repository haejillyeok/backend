import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar


T = TypeVar("T")


class IdempotencyStore(Protocol):
    async def get_or_create(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
    ) -> tuple[T, bool]: ...


@dataclass
class CacheEntry(Generic[T]):
    value: T
    expires_at: float


class InMemoryIdempotencyStore:
    """단일 프로세스에서만 보장되는 best-effort 멱등성 저장소입니다."""

    def __init__(self, ttl_seconds: int = 600, max_entries: int = 10_000) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: dict[str, CacheEntry] = {}
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._meta_lock = asyncio.Lock()

    async def get_or_create(
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
    ) -> tuple[T, bool]:
        """캐시된 값을 반환하거나 key별 잠금 아래에서 값을 한 번 생성합니다."""
        now = time.monotonic()
        async with self._meta_lock:
            self._purge_expired(now)
            cached = self._entries.get(key)
            if cached:
                return cached.value, False
            key_lock = self._key_locks.setdefault(key, asyncio.Lock())

        async with key_lock:
            now = time.monotonic()
            async with self._meta_lock:
                cached = self._entries.get(key)
                if cached and cached.expires_at > now:
                    return cached.value, False

            value = await factory()
            async with self._meta_lock:
                self._entries[key] = CacheEntry(
                    value=value,
                    expires_at=time.monotonic() + self._ttl_seconds,
                )
                self._key_locks.pop(key, None)
                self._trim_to_limit()
            return value, True

    def _purge_expired(self, now: float) -> None:
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)

    def _trim_to_limit(self) -> None:
        overflow = len(self._entries) - self._max_entries
        if overflow <= 0:
            return
        oldest = sorted(
            self._entries,
            key=lambda key: self._entries[key].expires_at,
        )
        for key in oldest[:overflow]:
            self._entries.pop(key, None)
