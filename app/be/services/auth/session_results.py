from app.be.models.user import User
from app.be.models.user_session import SESSION_TTL
from app.be.security.session import generate_session_token, hash_session_token
from app.be.services.auth.records import AuthenticatedUser, AuthLoginResult
from app.shared.core.timezone import kst_now


class AuthSessionResultMixin:
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
