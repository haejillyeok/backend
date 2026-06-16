from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class AuthenticatedUser:
    """로그인 응답에 노출하는 인증 유저 정보입니다."""

    public_id: UUID
    account_id: str
    nickname: str
