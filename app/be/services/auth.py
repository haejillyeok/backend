from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.be.models.user import User
from app.be.models.user_session import SESSION_TTL
from app.be.security.password import hash_password, verify_password
from app.be.security.session import generate_session_token, hash_session_token
from app.shared.core.exceptions import InvalidCredentialsError
from app.shared.core.observability import traced_method


class AuthRepositoryProtocol(Protocol):
    async def get_user_by_nickname(self, nickname: str) -> User | None:
        """닉네임으로 유저를 조회합니다."""

    async def create_user(
        self,
        *,
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

    async def commit(self) -> None:
        """인증 transaction을 확정합니다."""


@dataclass(frozen=True)
class AuthenticatedUser:
    public_id: UUID
    nickname: str


@dataclass(frozen=True)
class AuthLoginResult:
    user: AuthenticatedUser
    session_token: str
    is_new_user: bool
    expires_at: datetime


class AuthService:
    """닉네임/비밀번호 기반 가입 겸 로그인을 처리하는 service입니다."""

    def __init__(self, repository: AuthRepositoryProtocol) -> None:
        self.repository = repository

    async def login_or_register(
        self,
        *,
        nickname: str,
        password: str,
        last_access_ip: str | None,
        user_agent: str | None,
    ) -> AuthLoginResult:
        """닉네임이 없으면 가입하고, 있으면 비밀번호를 검증한 뒤 세션을 발급합니다."""
        return await self._login_or_register(
            nickname=nickname,
            password=password,
            last_access_ip=last_access_ip,
            user_agent=user_agent,
        )

    @traced_method("AuthService.login_or_register", layer="service")
    async def _login_or_register(
        self,
        *,
        nickname: str,
        password: str,
        last_access_ip: str | None,
        user_agent: str | None,
    ) -> AuthLoginResult:
        """가입 겸 로그인 유스케이스 전체 실행 시간을 trace span으로 기록합니다."""
        user = await self.repository.get_user_by_nickname(nickname)
        is_new_user = user is None

        if user is None:
            user = await self.repository.create_user(
                nickname=nickname,
                password_hash=hash_password(password),
                last_access_ip=last_access_ip,
            )
        elif not verify_password(password, user.password_hash):
            raise InvalidCredentialsError
        else:
            user.last_access_ip = last_access_ip

        session_token = generate_session_token()
        expires_at = datetime.now(UTC) + SESSION_TTL
        await self.repository.create_user_session(
            user_id=user.id,
            token_hash=hash_session_token(session_token),
            expires_at=expires_at,
            last_access_ip=last_access_ip,
            user_agent=user_agent,
        )
        await self.repository.commit()

        return AuthLoginResult(
            user=AuthenticatedUser(public_id=user.public_id, nickname=user.nickname),
            session_token=session_token,
            is_new_user=is_new_user,
            expires_at=expires_at,
        )
