from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Generic, Protocol, TypeVar

from starlette.requests import HTTPConnection


RepositoryT = TypeVar("RepositoryT")


class RepositoryContextFactory(Protocol[RepositoryT]):
    def __call__(self) -> AsyncIterator[RepositoryT]:
        """service usecase가 사용할 repository context를 생성합니다."""


class RepositoryScopedService(Generic[RepositoryT]):
    """service/usecase가 repository lifetime과 transaction 경계를 소유하게 돕습니다."""

    def __init__(
        self,
        repository: RepositoryT | None = None,
        *,
        repository_context_factory: RepositoryContextFactory[RepositoryT] | None = None,
    ) -> None:
        if repository is None and repository_context_factory is None:
            raise ValueError("repository or repository_context_factory is required")
        self._fallback_repository = repository
        self._repository_context_factory = repository_context_factory
        self._current_repository: ContextVar[RepositoryT | None] = ContextVar(
            f"{self.__class__.__name__}.repository",
            default=None,
        )

    @property
    def repository(self) -> RepositoryT:
        """현재 usecase transaction 안에서 사용할 repository를 반환합니다."""
        repository = self._current_repository.get()
        if repository is not None:
            return repository
        if self._fallback_repository is not None:
            return self._fallback_repository
        raise RuntimeError("repository is only available inside repository_scope")

    @asynccontextmanager
    async def repository_scope(self) -> AsyncIterator[RepositoryT]:
        """하나의 service/usecase 실행 동안 repository context를 엽니다."""
        current_repository = self._current_repository.get()
        if current_repository is not None:
            yield current_repository
            return
        if self._repository_context_factory is None:
            if self._fallback_repository is None:
                raise RuntimeError("repository context factory is not configured")
            yield self._fallback_repository
            return

        async with self._repository_context_factory() as repository:
            token = self._current_repository.set(repository)
            try:
                yield repository
            finally:
                self._current_repository.reset(token)


def build_repository_context_factory(
    connection: HTTPConnection,
    repository_type: type[RepositoryT],
) -> RepositoryContextFactory[RepositoryT]:
    """ASGI app의 sessionmaker로 repository context factory를 만듭니다."""
    sessionmaker = connection.app.state.db_sessionmaker

    @asynccontextmanager
    async def repository_context() -> AsyncIterator[RepositoryT]:
        async with sessionmaker() as db_session:
            yield repository_type(db_session)

    return repository_context
