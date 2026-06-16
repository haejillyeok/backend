from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class RoomCreateResult:
    room_public_id: UUID
    name: str
    game_type: str
    status: str
    max_players: int
    member_count: int
    created_at: datetime
