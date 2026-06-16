from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class RoomLobbyMemberSnapshot:
    user_public_id: UUID
    nickname: str
    is_owner: bool
    joined_at: datetime
