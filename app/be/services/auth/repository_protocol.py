from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.be.models.user import User


class AuthRepositoryProtocol(Protocol):
    """인증 service가 의존하는 repository 계약입니다."""

    async def get_user_by_account_id(self, account_id: str) -> User | None:
        """계정 ID로 유저를 조회합니다."""

    async def get_user_by_nickname(self, nickname: str) -> User | None:
        """닉네임 중복 확인을 위해 유저를 조회합니다."""

    async def create_user(
        self,
        *,
        account_id: str,
        nickname: str,
        password_hash: str,
        last_access_ip: str | None,
    ) -> User:
        """새 유저를 생성합니다."""

    async def create_user_session(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
        last_access_ip: str | None,
        user_agent: str | None,
    ) -> object:
        """로그인 세션을 생성합니다."""

    async def get_active_session_user(
        self,
        *,
        token_hash: str,
        now: datetime,
    ) -> tuple[User, object] | None:
        """활성 세션 토큰 해시로 현재 유저와 세션을 조회합니다."""

    async def touch_user_session(self, session: object, *, now: datetime) -> None:
        """인증된 세션의 마지막 접근 시각을 갱신합니다."""

    async def commit(self) -> None:
        """인증 transaction을 확정합니다."""
