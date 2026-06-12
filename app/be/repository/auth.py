from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.be.models.user import User
from app.be.models.user_session import UserSession
from app.shared.core.observability import traced_method


class AuthRepository:
    """인증 흐름에서 필요한 유저와 세션 영속화를 담당합니다."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def get_user_by_account_id(self, account_id: str) -> User | None:
        """계정 ID로 유저를 조회하고, 없으면 None을 반환합니다."""
        return await self._get_user_by_account_id(account_id)

    @traced_method("AuthRepository.get_user_by_account_id", layer="repository")
    async def _get_user_by_account_id(self, account_id: str) -> User | None:
        """계정 ID 조회 query 실행 시간을 trace span으로 기록합니다."""
        result = await self.db_session.execute(select(User).where(User.account_id == account_id))
        return result.scalar_one_or_none()

    async def get_user_by_nickname(self, nickname: str) -> User | None:
        """닉네임으로 유저를 조회하고, 없으면 None을 반환합니다."""
        return await self._get_user_by_nickname(nickname)

    @traced_method("AuthRepository.get_user_by_nickname", layer="repository")
    async def _get_user_by_nickname(self, nickname: str) -> User | None:
        """닉네임 중복 확인 query 실행 시간을 trace span으로 기록합니다."""
        result = await self.db_session.execute(select(User).where(User.nickname == nickname))
        return result.scalar_one_or_none()

    async def create_user(
        self,
        *,
        account_id: str,
        nickname: str,
        password_hash: str,
        last_access_ip: str | None,
    ) -> User:
        """새 유저를 추가하고 flush해서 UUID 기본값을 사용할 수 있게 합니다."""
        return await self._create_user(
            account_id=account_id,
            nickname=nickname,
            password_hash=password_hash,
            last_access_ip=last_access_ip,
        )

    @traced_method("AuthRepository.create_user", layer="repository")
    async def _create_user(
        self,
        *,
        account_id: str,
        nickname: str,
        password_hash: str,
        last_access_ip: str | None,
    ) -> User:
        """유저 insert와 flush 실행 시간을 trace span으로 기록합니다."""
        user = User(
            account_id=account_id,
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
        return await self._create_user_session(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            last_access_ip=last_access_ip,
            user_agent=user_agent,
        )

    @traced_method("AuthRepository.create_user_session", layer="repository")
    async def _create_user_session(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        last_access_ip: str | None,
        user_agent: str | None,
    ) -> UserSession:
        """세션 insert와 flush 실행 시간을 trace span으로 기록합니다."""
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

    async def get_active_session_user(
        self,
        *,
        token_hash: str,
        now: datetime,
    ) -> tuple[User, UserSession] | None:
        """활성 세션 토큰 해시로 유저와 세션을 조회합니다."""
        return await self._get_active_session_user(token_hash=token_hash, now=now)

    @traced_method("AuthRepository.get_active_session_user", layer="repository")
    async def _get_active_session_user(
        self,
        *,
        token_hash: str,
        now: datetime,
    ) -> tuple[User, UserSession] | None:
        """세션 인증 query 실행 시간을 trace span으로 기록합니다."""
        statement = (
            select(User, UserSession)
            .join(UserSession, UserSession.user_id == User.id)
            .where(
                UserSession.token_hash == token_hash,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
        )
        result = await self.db_session.execute(statement)
        row = result.one_or_none()
        if row is None:
            return None
        user, user_session = row
        return user, user_session

    async def touch_user_session(self, session: UserSession, *, now: datetime) -> None:
        """인증에 성공한 세션의 마지막 접근 시각을 갱신합니다."""
        await self._touch_user_session(session, now=now)

    @traced_method("AuthRepository.touch_user_session", layer="repository")
    async def _touch_user_session(self, session: UserSession, *, now: datetime) -> None:
        """세션 last_seen_at 갱신 실행 시간을 trace span으로 기록합니다."""
        session.last_seen_at = now
        await self.db_session.flush()

    async def commit(self) -> None:
        """가입/로그인에 따른 변경 사항을 하나의 transaction으로 확정합니다."""
        await self._commit()

    @traced_method("AuthRepository.commit", layer="repository")
    async def _commit(self) -> None:
        """인증 transaction commit 실행 시간을 trace span으로 기록합니다."""
        await self.db_session.commit()
