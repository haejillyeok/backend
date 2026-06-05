from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.models.user import User
from app.be.models.user_session import UserSession


class AuthRepository:
    """인증 흐름에서 필요한 유저와 세션 영속화를 담당합니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def get_user_by_nickname(self, nickname: str) -> User | None:
        """닉네임으로 유저를 조회하고, 없으면 None을 반환합니다."""
        result = await self.db_session.execute(
            select(User).where(User.nickname == nickname)
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        *,
        nickname: str,
        password_hash: str,
        last_access_ip: str | None,
    ) -> User:
        """새 유저를 추가하고 flush해서 UUID 기본값을 사용할 수 있게 합니다."""
        user = User(
            nickname=nickname,
            password_hash=password_hash,
            last_access_ip=last_access_ip,
        )
        self.db_session.add(user)
        await self.db_session.flush()
        return user

    async def create_user_session(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        last_access_ip: str | None,
        user_agent: str | None,
    ) -> UserSession:
        """세션 토큰 해시와 접속 정보를 저장합니다."""
        user_session = UserSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            last_access_ip=last_access_ip,
            user_agent=user_agent,
        )
        self.db_session.add(user_session)
        await self.db_session.flush()
        return user_session

    async def commit(self) -> None:
        """가입/로그인에 따른 변경 사항을 하나의 transaction으로 확정합니다."""
        await self.db_session.commit()
