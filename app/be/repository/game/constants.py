from uuid import UUID

from app.be.schemas.game_enum import GameSessionStatus


TERMINAL_SESSION_STATUSES = (
    GameSessionStatus.RESULT.value,
    GameSessionStatus.ABORTED.value,
)
ADVISORY_LOCK_KEY_MASK = (1 << 63) - 1


def waiting_membership_lock_key(user_id: UUID) -> int:
    """PostgreSQL advisory lock에 사용할 유저별 양수 bigint key를 만듭니다."""
    return user_id.int & ADVISORY_LOCK_KEY_MASK
