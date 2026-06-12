from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection


async def get_db_session(connection: HTTPConnection) -> AsyncIterator[AsyncSession]:
    """HTTP 요청과 WebSocket 연결에서 공통으로 요청 단위 DB session을 제공합니다."""
    sessionmaker = connection.app.state.db_sessionmaker

    async with sessionmaker() as session:
        yield session
