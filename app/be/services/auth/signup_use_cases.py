from app.be.security.password import hash_password
from app.be.services.auth.records import AuthLoginResult
from app.shared.core.exceptions import AuthUserConflictError
from app.shared.core.observability import traced_method


class AuthSignupUseCaseMixin:
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
        async with self.repository_scope():
            return await self._signup(
                account_id=account_id,
                nickname=nickname,
                password=password,
                last_access_ip=last_access_ip,
                user_agent=user_agent,
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
