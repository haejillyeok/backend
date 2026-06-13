from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.be.models.user import User
from app.be.models.user_session import SESSION_TTL
from app.be.security.password import hash_password, verify_password
from app.be.security.session import generate_session_token, hash_session_token
from app.shared.core.error_codes import ErrorCode
from app.shared.core.exceptions import AppException, AuthUserConflictError, InvalidCredentialsError
from app.shared.core.observability import traced_method
from app.shared.core.timezone import kst_now


class AuthRepositoryProtocol(Protocol):
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


@dataclass(frozen=True)
class AuthenticatedUser:
    public_id: UUID
    account_id: str
    nickname: str


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    public_id: UUID
    account_id: str
    nickname: str


@dataclass(frozen=True)
class AuthLoginResult:
    user: AuthenticatedUser
    session_token: str
    expires_at: datetime


class SessionExpiredError(AppException):
    """세션 쿠키가 없거나 만료/폐기된 세션일 때 발생합니다."""

    def __init__(self) -> None:
        super().__init__(code=ErrorCode.SESSION_EXPIRED)


class AuthService:
    """계정 ID/비밀번호 기반 회원가입, 로그인, 세션 인증을 처리하는 service입니다."""

    def __init__(self, repository: AuthRepositoryProtocol) -> None:
        self.repository = repository

    async def signup(
        self,
        *,
        account_id: str,
        nickname: str,
        password: str,
        last_access_ip: str | None,
        user_agent: str | None,
    ) -> AuthLoginResult:
        """신규 계정을 생성하고 로그인 세션을 발급합니다."""
        return await self._signup(
            account_id=account_id,
            nickname=nickname,
            password=password,
            last_access_ip=last_access_ip,
            user_agent=user_agent,
        )

    async def login(
        self,
        *,
        account_id: str,
        password: str,
        last_access_ip: str | None,
        user_agent: str | None,
    ) -> AuthLoginResult:
        """기존 계정 ID와 비밀번호를 검증한 뒤 로그인 세션을 발급합니다."""
        return await self._login(
            account_id=account_id,
            password=password,
            last_access_ip=last_access_ip,
            user_agent=user_agent,
        )

    async def authenticate_session(self, session_token: str | None) -> CurrentUser:
        """쿠키의 opaque 세션 토큰으로 현재 로그인 유저를 확인합니다."""
        if not session_token:
            raise SessionExpiredError
        return await self._authenticate_session(session_token)

    @traced_method("AuthService.authenticate_session", layer="service")
    async def _authenticate_session(self, session_token: str) -> CurrentUser:
        """세션 조회와 last_seen 갱신 실행 시간을 trace span으로 기록합니다."""
        now = kst_now()
        result = await self.repository.get_active_session_user(
            token_hash=hash_session_token(session_token),
            now=now,
        )
        if result is None:
            raise SessionExpiredError

        user, user_session = result
        await self.repository.touch_user_session(user_session, now=now)
        await self.repository.commit()
        return CurrentUser(
            id=user.id,
            public_id=user.public_id,
            account_id=user.account_id,
            nickname=user.nickname,
        )

    @traced_method("AuthService.signup", layer="service")
    async def _signup(
        self,
        *,
        account_id: str,
        nickname: str,
        password: str,
        last_access_ip: str | None,
        user_agent: str | None,
    ) -> AuthLoginResult:
        """회원가입과 최초 세션 발급 실행 시간을 trace span으로 기록합니다."""
        if await self.repository.get_user_by_account_id(account_id) is not None:
            raise AuthUserConflictError
        if await self.repository.get_user_by_nickname(nickname) is not None:
            raise AuthUserConflictError

        user = await self.repository.create_user(
            account_id=account_id,
            nickname=nickname,
            password_hash=hash_password(password),
            last_access_ip=last_access_ip,
        )
        return await self._create_session_result(
            user=user,
            last_access_ip=last_access_ip,
            user_agent=user_agent,
        )

    @traced_method("AuthService.login", layer="service")
    async def _login(
        self,
        *,
        account_id: str,
        password: str,
        last_access_ip: str | None,
        user_agent: str | None,
    ) -> AuthLoginResult:
        """로그인 검증과 세션 발급 실행 시간을 trace span으로 기록합니다."""
        user = await self.repository.get_user_by_account_id(account_id)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError
        user.last_access_ip = last_access_ip
        return await self._create_session_result(
            user=user,
            last_access_ip=last_access_ip,
            user_agent=user_agent,
        )

    async def _create_session_result(
        self,
        *,
        user: User,
        last_access_ip: str | None,
        user_agent: str | None,
    ) -> AuthLoginResult:
        """검증된 유저에 대한 세션 토큰을 생성하고 DB transaction을 확정합니다."""
        session_token = generate_session_token()
        expires_at = kst_now() + SESSION_TTL
        await self.repository.create_user_session(
            user_id=user.id,
            token_hash=hash_session_token(session_token),
            expires_at=expires_at,
            last_access_ip=last_access_ip,
            user_agent=user_agent,
        )
        await self.repository.commit()

        return AuthLoginResult(
            user=AuthenticatedUser(
                public_id=user.public_id,
                account_id=user.account_id,
                nickname=user.nickname,
            ),
            session_token=session_token,
            expires_at=expires_at,
        )
