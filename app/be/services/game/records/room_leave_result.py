from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class RoomLeaveResult:
    room_public_id: UUID
    user_public_id: UUID
    nickname: str
    left_at: datetime
    remaining_member_count: int = 0
    new_owner_user_public_id: UUID | None = None
    new_owner_nickname: str | None = None
    room_closed: bool = False
