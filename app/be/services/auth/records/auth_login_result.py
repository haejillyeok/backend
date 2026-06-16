from dataclasses import dataclass
from datetime import datetime

from app.be.services.auth.records.authenticated_user import AuthenticatedUser


@dataclass(frozen=True)
class AuthLoginResult:
    """가입/로그인 성공 후 반환하는 유저와 세션 토큰 정보입니다."""

    user: AuthenticatedUser
    session_token: str
    expires_at: datetime
