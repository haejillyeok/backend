from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CurrentUser:
    """인증된 요청 처리에서 내부적으로 사용하는 현재 유저 정보입니다."""

    id: UUID
    public_id: UUID
    account_id: str
    nickname: str
