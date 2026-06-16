from app.be.security.password import verify_password
from app.be.services.auth.records import AuthLoginResult
from app.shared.core.exceptions import InvalidCredentialsError
from app.shared.core.observability import traced_method


class AuthLoginUseCaseMixin:
    async def login(
        self,
        *,
        account_id: str,
        password: str,
        last_access_ip: str | None,
        user_agent: str | None,
    ) -> AuthLoginResult:
        """기존 계정 ID와 비밀번호를 검증한 뒤 로그인 세션을 발급합니다."""
        async with self.repository_scope():
            return await self._login(
                account_id=account_id,
                password=password,
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
