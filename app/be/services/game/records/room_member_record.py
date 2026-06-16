from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class RoomMemberRecord:
    room_id: UUID
    user_id: UUID
    nickname: str
    joined_at: datetime
    user_public_id: UUID | None = None
