from app.be.security.session import hash_session_token
from app.be.services.auth.errors import SessionExpiredError
from app.be.services.auth.records import CurrentUser
from app.shared.core.observability import traced_method
from app.shared.core.timezone import kst_now


class AuthSessionUseCaseMixin:
    async def authenticate_session(self, session_token: str | None) -> CurrentUser:
        """쿠키의 opaque 세션 토큰으로 현재 로그인 유저를 확인합니다."""
        if not session_token:
            raise SessionExpiredError(message="로그인이 필요합니다.")
        async with self.repository_scope():
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
